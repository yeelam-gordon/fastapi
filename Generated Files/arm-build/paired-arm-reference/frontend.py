"""Bounded supported-frontend cohort; no dispatch, retry, or full-suite workload."""

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

import installer
import tomllib
from compare import compare_outputs
from driver import HERE, Run, canonical_name, constraints, verify_versions
from frozen import full_inventory, summary, verify_record
from guards import (
    REV,
    WHEEL,
    WHEEL_HASHES,
    binary_guard,
    native_guard,
    require,
    sequence,
    sha,
    tree,
)
from source import extract, fetch, mode_receipt, prove, save, unchanged

STOCK = WHEEL_HASHES["A"]
EXPECTED_BUILD_SYSTEM = {"requires": ["pdm-backend"], "build-backend": "pdm.backend"}


def argv_for(arm, python, uv, constraint):
    if arm == "A":
        return [str(python), "-m", "build", "-v", "--installer", "uv"]
    require(arm == "B", "Unknown frontend arm")
    return [
        str(uv),
        "build",
        "-v",
        "--python",
        str(python),
        "--build-constraints",
        str(constraint),
        "--require-hashes",
        "--offline",
        "--no-index",
        "--no-config",
        "--no-managed-python",
        "--no-python-downloads",
        "--no-create-gitignore",
    ]


def constraint_text(wheel, digest=STOCK):
    return f"pdm-backend @ {wheel.as_uri()}#sha256={digest} --hash=sha256:{digest}\n"


def outer_snapshot(root):
    return {
        p.relative_to(root).as_posix(): {
            "sha256": sha(p),
            "size": p.stat().st_size,
            "mtime_ns": p.stat().st_mtime_ns,
            "mode": p.stat().st_mode,
        }
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def verify_python_abi(abi):
    require(
        abi["cache_tag"] == "cpython-312"
        and abi["version"] == "3.12.10"
        and abi["bits"] == 64
        and abi["machine"].lower() in ("arm64", "aarch64"),
        "Actual child ABI must be native CPython 3.12",
    )
    system = platform.system()
    require(abi["system"] == system, "Child ABI host mismatch")
    if system == "Windows":
        require(
            abi["soabi"] is None
            and abi["sysconfig_platform"] == "win-arm64"
            and abi["ext_suffix"] == ".cp312-win_arm64.pyd",
            "Require Windows CPython 3.12 ARM64 extension ABI",
        )
    elif system == "Darwin":
        require(
            abi["soabi"] == "cpython-312-darwin"
            and abi["ext_suffix"] == ".cpython-312-darwin.so"
            and isinstance(abi["sysconfig_platform"], str)
            and re.fullmatch(
                r"macosx-\d+\.\d+-(arm64|universal2)", abi["sysconfig_platform"]
            ),
            "Require macOS CPython 3.12 native-capable extension ABI",
        )
    else:
        raise RuntimeError("Unsupported child ABI host")
    require(
        Path(abi["base"]).resolve() == Path(sys._base_executable).resolve(),
        "Child interpreter uses a different native base",
    )
    binary_guard(Path(abi["base"]))


def helper_imports(inputs):
    result = {}
    runtime_roots = (Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve())
    for name, module in tuple(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if not filename:
            continue
        path = Path(filename).resolve()
        if path.is_relative_to(HERE):
            relative = path.relative_to(HERE).as_posix()
            require(
                relative in inputs and sha(path) == inputs[relative],
                "Unmanifested/changed executed helper import: " + name,
            )
            result[name] = {"path": relative, "sha256": inputs[relative]}
        else:
            require(
                any(path.is_relative_to(root) for root in runtime_roots),
                "Unexpected external helper import: " + name,
            )
    return result


def transient_paths(base, system):
    if system == "Windows":
        return base / "Scripts" / "python.exe", [base / "Lib" / "site-packages"]
    require(system == "Darwin", "Unsupported transient host")
    return base / "bin" / "python", list(
        (base / "lib").glob("python3.12/site-packages")
    )


def verify_log(text, wheel, uv, *, sdist_only=False):
    count = 1 if sdist_only else 2
    expected = wheel.as_uri().lower() + "#sha256=" + STOCK
    selected = re.findall(
        r"^DEBUG Installing build requirement: (.+)$", text, re.MULTILINE
    )
    require(
        [s.lower() for s in selected]
        == [f"pdm-backend==2.5.0 (from {expected})"] * count,
        "Unknown/missing native frontend installed input",
    )
    require(text.count("Building source distribution...") == 1, "Missing/extra sdist")
    require(
        text.count("Building wheel from source distribution...")
        == (0 if sdist_only else 1),
        "Native frontend must use default SdistToWheel",
    )
    require(
        text.count("Creating PEP 517 build environment") == count,
        "Wrong native isolation count",
    )
    hooks = ("sdist",) if sdist_only else ("sdist", "wheel")
    for kind in hooks:
        require(
            text.count(f"Calling `pdm.backend.get_requires_for_build_{kind}()`") == 1,
            "Missing/extra native backend hook",
        )
    require(
        "Installing extra requirements for build backend" not in text,
        "Unknown get_requires inputs",
    )
    require("http/1.1" not in text.lower(), "Network lookup in offline build")
    return {"selected": selected, "hooks": hooks, "uv_sha256": sha(uv)}


class Observation:
    """Read ordinary uv transients only during untimed correctness and hash gates."""

    def __init__(self, cache, wheel):
        self.cache, self.wheel = cache, wheel
        self.stop = threading.Event()
        self.rows, self.errors = {}, []

    def run(self):
        while not self.stop.is_set():
            for cfg in (self.cache / "builds-v0").glob("*/pyvenv.cfg"):
                base = cfg.parent
                row = self.rows.setdefault(str(base), {})
                try:
                    config = cfg.read_text(encoding="utf-8")
                    if "include-system-site-packages" not in config.lower():
                        continue
                    require(
                        "include-system-site-packages = false" in config.lower(),
                        "Native frontend exposed system packages",
                    )
                    row["pyvenv_cfg"] = config
                    exe, sites = transient_paths(base, platform.system())
                    if exe.is_file() and "slices" not in row:
                        row["slices"] = binary_guard(exe)
                        row["executable_sha256"] = sha(exe)
                    for site in sites:
                        distributions = sorted(p.name for p in site.glob("*.dist-info"))
                        if distributions:
                            require(
                                distributions == ["pdm_backend-2.5.0.dist-info"],
                                "Unknown installed native frontend input",
                            )
                            row["distributions"] = distributions
                        record = site / "pdm_backend-2.5.0.dist-info" / "RECORD"
                        if record.is_file() and "stock_payloads" not in row:
                            with zipfile.ZipFile(self.wheel) as archive:
                                names = [
                                    n
                                    for n in archive.namelist()
                                    if not n.endswith(("/", ".dist-info/RECORD"))
                                ]
                                if all(
                                    (site / n).is_file()
                                    and (site / n).read_bytes() == archive.read(n)
                                    for n in names
                                ):
                                    row["stock_payloads"] = len(names)
                                    row["installed_RECORD"] = (
                                        installer.installed_record(site, base)
                                    )
                    for kind in ("sdist", "wheel"):
                        hook = base / f"get_requires_for_build_{kind}.txt"
                        if hook.is_file():
                            value = json.loads(hook.read_bytes())
                            require(value == [], "Unknown native get_requires input")
                            row[kind] = value
                except (OSError, ValueError):
                    # The unmodified frontend owns creation/deletion of these files.
                    pass
                except BaseException as exc:
                    self.errors.append(repr(exc))
            self.stop.wait(0.01)

    def verify(self, hooks):
        require(not self.errors, "Untimed observer detected unknown input")
        for kind in hooks:
            require(
                any(row.get(kind) == [] for row in self.rows.values()),
                f"Actual frontend {kind} get_requires JSON not captured; stop",
            )
        return {
            "rows": self.rows,
            "hooks": {kind: [] for kind in hooks},
            "scope": "Actual uv-written JSON plus closed-input raw logs. Transient "
            "binary/payload/RECORD snapshots are opportunistic, not guaranteed; "
            "unsampled isolation uses pinned wheel metadata and native selector.",
        }


class FrontendRun(Run):
    def spawn_frontend(self, label, argv, source, env, *, timed, expected):
        directory = self.upload / (label + "-process")
        directory.mkdir()
        row = {"argv": argv, "expected_exit": expected, "valid": False}
        save(directory / "command.json", row)
        with (
            (directory / "stdout").open("wb") as out,
            (directory / "stderr").open("wb") as err,
        ):
            utc_before_ns = time.time_ns()
            start_ns = time.perf_counter_ns()
            try:
                result = subprocess.run(
                    argv, cwd=source, env=env, stdout=out, stderr=err, timeout=180
                )
            except BaseException as exc:
                stop_ns = time.perf_counter_ns()
                utc_after_ns = time.time_ns()
                row["error"] = repr(exc)
                raise
            else:
                stop_ns = time.perf_counter_ns()
                utc_after_ns = time.time_ns()
            finally:
                row["perf_counter_ns_start"] = start_ns
                row["perf_counter_ns_stop"] = stop_ns
                row["wall_utc_ns_before"] = utc_before_ns
                row["wall_utc_ns_after"] = utc_after_ns
                row["elapsed_ns"] = stop_ns - start_ns
                row["wall_seconds"] = row["elapsed_ns"] / 1_000_000_000
                row["performance_eligible"] = timed
                row["stdout_sha256"] = sha(directory / "stdout")
                row["stderr_sha256"] = sha(directory / "stderr")
                save(directory / "command.json", row)
        row.update(
            exit=result.returncode,
            valid=result.returncode == expected and row["elapsed_ns"] > 0,
        )
        save(directory / "command.json", row)
        require(row["elapsed_ns"] > 0, "Invalid monotonic clock interval; stop")
        require(row["valid"], f"{label} failed; preserve, stop, no replacement")
        return (
            row,
            (directory / "stdout").read_bytes(),
            (directory / "stderr").read_bytes(),
        )

    def setup_frontend(
        self, uv, *, preflight=False, stock_wheel=None, source_repo=None
    ):
        preflight_outer = outer_snapshot(Path(sys.prefix)) if preflight else None
        if preflight:
            save(self.upload / "outer-before.json", preflight_outer)
        save(self.upload / "native.json", native_guard())
        installer.reject_bypass(os.environ)
        installer.native_uv(uv)
        self.uv = uv.resolve()
        _, out, _ = self.command("uv-version", [self.uv, "--version"])
        require(re.match(rb"uv 0\.13\.6(?:\s|$)", out), "Wrong uv version")
        require(
            preflight or not (stock_wheel or source_repo), "Local inputs preflight-only"
        )
        if source_repo:
            self.archive = self.root / "fastapi.tar"
            self.command(
                "fastapi-archive",
                [
                    "git",
                    "-c",
                    "core.autocrlf=false",
                    "-c",
                    "core.eol=lf",
                    "-C",
                    str(source_repo),
                    "archive",
                    "--format=tar",
                    "--output=" + str(self.archive),
                    REV,
                ],
            )
            self.proof = prove(source_repo, REV, self.archive)
        else:
            self.archive, self.proof = fetch(
                self.root,
                "fastapi",
                "https://github.com/fastapi/fastapi.git",
                REV,
                self.command,
            )
        require(len(self.proof["files"]) == 2557, "Wrong complete source payload")
        save(self.upload / "git-payload-proof.json", self.proof)
        self.source = self.root / "reference-source"
        self.source_before = extract(self.archive, self.source, self.proof)
        save(
            self.upload / "mode-gate.json", mode_receipt(self.source_before, self.proof)
        )
        require(
            tomllib.loads((self.source / "pyproject.toml").read_text())["build-system"]
            == EXPECTED_BUILD_SYSTEM,
            "Original backend declaration changed",
        )
        self.wheels, self.backend_constraints = {}, {}
        for arm in "AB":
            folder = self.root / arm
            wheel = folder / "wheelhouse" / WHEEL
            wheel.parent.mkdir(parents=True)
            if stock_wheel:
                require(stock_wheel.name == WHEEL, "Wrong stock wheel filename")
                shutil.copyfile(stock_wheel, wheel)
            elif arm == "B":
                shutil.copyfile(self.wheels["A"], wheel)
            else:
                import urllib.request

                with urllib.request.urlopen(
                    "https://pypi.org/pypi/pdm-backend/2.5.0/json"
                ) as reply:
                    metadata = json.load(reply)
                entry = next(f for f in metadata["urls"] if f["filename"] == WHEEL)
                require(
                    entry["digests"]["sha256"] == STOCK
                    and entry["url"].startswith("https://files.pythonhosted.org/"),
                    "Nonofficial stock wheel",
                )
                urllib.request.urlretrieve(entry["url"], wheel)
            require(sha(wheel) == STOCK, "Stock wheel hash mismatch")
            with zipfile.ZipFile(wheel) as archive:
                verify_record(archive)
            constraint = folder / "constraints.txt"
            constraint.write_text(
                constraint_text(wheel), encoding="utf-8", newline="\n"
            )
            self.wheels[arm], self.backend_constraints[arm] = wheel, constraint
        self.setup_constraint = self.root / "setup-backend.txt"
        self.setup_constraint.write_text(
            f"pdm-backend @ {self.wheels['A'].as_uri()}#sha256={STOCK}\n",
            encoding="utf-8",
            newline="\n",
        )
        if preflight:
            self.build_python = Path(sys.executable).absolute()
        else:
            self.build_python = self.make_venv("minimal", "build-constraints.txt")
        identity = self.identity(self.build_python, "frontend-outer")
        installed = {canonical_name(k): v for k, v in identity["distributions"].items()}
        verify_versions(
            installed,
            constraints(HERE / "build-constraints.txt"),
            system=platform.system(),
        )
        if not preflight:
            require(
                set(installed) == set(constraints(HERE / "build-constraints.txt")),
                "Hosted frontend requires only the five minimal build distributions",
            )
        self.outer = Path(identity["prefix"])
        require(
            not self.root.is_relative_to(self.outer),
            "Owned root must not alter outer venv",
        )
        self.outer_before = preflight_outer if preflight else outer_snapshot(self.outer)
        save(self.upload / "outer-before.json", self.outer_before)
        require(
            outer_snapshot(self.outer) == self.outer_before,
            "Read-only preflight outer changed during setup",
        )
        _, abi_out, _ = self.py(
            self.build_python,
            "actual-python-abi",
            [
                "-B",
                "-c",
                "import json,sys,sysconfig,struct,platform;"
                "print(json.dumps(dict(cache_tag=sys.implementation.cache_tag,"
                "version=platform.python_version(),system=platform.system(),"
                "bits=struct.calcsize('P')*8,machine=platform.machine(),"
                "soabi=sysconfig.get_config_var('SOABI'),"
                "sysconfig_platform=sysconfig.get_platform(),"
                "ext_suffix=sysconfig.get_config_var('EXT_SUFFIX'),"
                "base=sys._base_executable)))",
            ],
        )
        abi = json.loads(abi_out)
        verify_python_abi(abi)
        save(self.upload / "actual-python-abi.json", abi)
        self.base_before = {
            str(p): sha(p)
            for p in {
                Path(sys._base_executable).resolve(),
                Path(abi["base"]).resolve(),
                Path(self.uv).resolve(),
            }
        }
        save(self.upload / "native-tools.json", self.base_before)
        self.native_before = native_guard()
        self.imports_before = helper_imports(self.frozen_inputs)
        save(self.upload / "helper-imports.json", self.imports_before)
        save(
            self.upload / "scope.json",
            {
                "experiment": "P40 supported frontend; no PDM candidate",
                "source": REV,
                "stock_backend_sha256": STOCK,
                "preflight_only": preflight,
                "full_suite_executed": False,
                "prior_separate_correctness": {
                    "windows": "41002642194",
                    "macos": "41007566488",
                    "passed": 2513,
                    "skipped": 130,
                    "helper_commit": "1ddfc4135",
                    "not_P40_performance": True,
                },
                "audit": "Prior P40 PASS WITH LIMITS: high retained timing/artifact/source, "
                "medium transfer; legacy closure and historical clock-receipt limits "
                "remain qualified. No legacy import chain is reused here.",
            },
        )

    def env_for(self, arm, work, cache, constraint=None):
        env = self.env.copy()
        wheel = self.wheels[arm]
        constraint = constraint or self.backend_constraints[arm]
        env.update(
            UV=str(self.uv),
            UV_CACHE_DIR=str(cache),
            UV_FIND_LINKS=wheel.parent.as_uri(),
            UV_OFFLINE="1",
            UV_NO_INDEX="1",
            UV_NO_CONFIG="1",
            UV_NO_MANAGED_PYTHON="1",
            UV_PYTHON_DOWNLOADS="never",
            PIP_NO_INDEX="1",
            PIP_FIND_LINKS=wheel.parent.as_uri(),
            PIP_CONSTRAINT=constraint.as_uri(),
            PIP_CACHE_DIR=str(self.root / arm / "pip-cache"),
            SOURCE_DATE_EPOCH="1700000000",
            COLUMNS="4096",
            TERM="dumb",
            PATH=str(self.uv.parent) + os.pathsep + env["PATH"],
        )
        for key in ("TEMP", "TMP", "TMPDIR"):
            env[key] = str(work / "scratch")
        if arm == "A":
            env["UV_CONSTRAINT"] = constraint.as_uri()
        else:
            env["UV_BUILD_CONSTRAINT"] = constraint.as_uri()
        installer.reject_bypass(env)
        return env

    def fresh_source(self, label):
        work = self.root / label
        (work / "scratch").mkdir(parents=True)
        source = work / "source"
        before = extract(self.archive, source, self.proof)
        require(before == self.source_before, "Fresh source metadata mismatch")
        save(self.upload / label / "source-before.json", before)
        return work, source, before

    def execute_frontend(self, label, arm, *, pair=0, timed=False, probe=None):
        work, source, before = self.fresh_source(label)
        cache = (
            self.root
            / arm
            / (
                "cold-probe-cache"
                if probe == "negative-cold"
                else "positive-probe-cache"
                if probe
                else "correctness-cache"
                if label.startswith("correctness-")
                else "trials-cache"
            )
        )
        cache_before = outer_snapshot(cache) if probe and cache.exists() else {}
        if probe:
            require(
                bool(cache_before) == (probe == "negative-warm"),
                "Incorrect cold/positive-seeded-warm probe cache",
            )
            save(self.upload / label / "cache-before.json", cache_before)
        constraint = self.backend_constraints[arm]
        if probe and probe != "positive":
            constraint = work / "wrong-constraints.txt"
            constraint.write_text(
                constraint_text(self.wheels[arm], installer.WRONG_SHA),
                encoding="utf-8",
                newline="\n",
            )
        env = self.env_for(arm, work, cache, constraint)
        argv = argv_for(arm, self.build_python, self.uv, constraint)
        if probe == "positive":
            argv.append("--sdist")
        observe = arm == "B" and (probe or label.startswith("correctness-"))
        observer = Observation(cache, self.wheels[arm]) if observe else None
        thread = (
            threading.Thread(target=observer.run, daemon=True) if observer else None
        )
        save(
            self.upload / label / "plan.json",
            {
                "argv": argv,
                "cwd": str(source),
                "timed": timed,
                "environment": {
                    k: v
                    for k, v in env.items()
                    if k.startswith(("UV_", "PIP_", "PYTHON"))
                    or k in ("SOURCE_DATE_EPOCH", "COLUMNS", "TERM")
                },
            },
        )
        if thread:
            thread.start()
        try:
            row, out, err = self.spawn_frontend(
                label,
                argv,
                source,
                env,
                timed=timed,
                expected=2 if probe and probe != "positive" else 0,
            )
        finally:
            output = source / "dist"
            if output.exists():
                shutil.copytree(output, self.upload / label / "artifacts")
            if thread:
                observer.stop.set()
                thread.join(timeout=30)
                require(not thread.is_alive(), "Untimed observer did not stop")
                save(
                    self.upload / label / "observation.json",
                    {
                        "rows": observer.rows,
                        "errors": observer.errors,
                    },
                )
            unchanged(source, before)
            save(self.upload / label / "source-after.json", tree(source))
            if probe:
                save(self.upload / label / "cache-after.json", outer_snapshot(cache))
        text = out.decode("utf-8") + "\n" + err.decode("utf-8")
        if probe and probe != "positive":
            require(
                "hash mismatch" in text.lower()
                and installer.WRONG_SHA in text
                and STOCK in text,
                "Expected/computed hash rejection missing",
            )
            require(
                "Creating PEP 517 build environment" not in text
                and "Calling `pdm.backend." not in text,
                "Negative reached backend hooks",
            )
            require(not list((source / "dist").glob("*")), "Negative emitted artifacts")
            require(not observer.errors, "Negative observer failure")
            require(
                not any(r.get("distributions") for r in observer.rows.values()),
                "Negative installed backend",
            )
        elif arm == "A":
            row["phase_proof"] = installer.phases(
                out.decode("utf-8"),
                err.decode("utf-8"),
                "B",
                self.uv,
                self.wheels[arm],
                self.wheels["B"],
            )
        else:
            row["phase_proof"] = verify_log(
                text, self.wheels[arm], self.uv, sdist_only=bool(probe)
            )
            if observer:
                row["provenance"] = observer.verify(
                    ("sdist",) if probe else ("sdist", "wheel")
                )
        if not probe:
            output = source / "dist"
            save(self.upload / label / "inventory.json", full_inventory(output))
            baseline = getattr(self, "baseline", output)
            row["comparison"] = compare_outputs(baseline, output)
            artifacts = self.upload / label / "artifacts"
            row["artifacts"] = {p.name: sha(p) for p in artifacts.iterdir()}
            if not hasattr(self, "baseline"):
                self.baseline = output
        row.update(label=label, arm=arm, pair=pair, timed=timed, valid=True)
        save(self.upload / label / "result.json", row)
        self.integrity_frontend(outer=False)
        return row

    def integrity_frontend(self, *, outer=True):
        self.inputs_unchanged()
        imports = helper_imports(self.frozen_inputs)
        save(self.upload / "helper-imports-after.json", imports)
        require(
            imports == self.imports_before, "Executed helper import closure changed"
        )
        if outer:
            require(
                outer_snapshot(self.outer) == self.outer_before,
                "Read-only outer venv changed (including bytecode)",
            )
        require(native_guard() == self.native_before, "Actual native ABI changed")
        require(
            all(sha(Path(p)) == digest for p, digest in self.base_before.items()),
            "Native base/uv changed",
        )
        unchanged(self.source, self.source_before)
        for arm in "AB":
            wheel = self.wheels[arm]
            require(
                list(wheel.parent.iterdir()) == [wheel] and sha(wheel) == STOCK,
                "Stock singleton changed",
            )
            require(
                self.backend_constraints[arm].read_bytes()
                == constraint_text(wheel).encode(),
                "Closed constraint changed",
            )

    def run_frontend(self, *, preflight):
        self.integrity_frontend()
        for case in ("positive", "negative-cold", "negative-warm"):
            self.execute_frontend("frontend-hash-" + case, "B", probe=case)
        rows = [self.execute_frontend("correctness-" + arm, arm) for arm in "AB"]
        if not preflight:
            for label, arm, pair in sequence():
                rows.append(
                    self.execute_frontend(label, arm, pair=pair, timed=pair > 0)
                )
        result = {
            "status": "preflight-ready" if preflight else "complete",
            "complete_outputs": len(rows),
            "archives": 2 * len(rows),
            "new_commands_after_correctness": 0 if preflight else 14,
            "rows": rows,
        }
        if not preflight:
            result["summary"] = summary(rows)
        self.integrity_frontend()
        save(self.upload / "frontend-result.json", result)


def hosted_guard(env):
    require(
        env.get("GITHUB_REPOSITORY") == "yeelam-gordon/fastapi"
        and env.get("GITHUB_REF") == "refs/heads/perf/hobl-arm-frontend"
        and env.get("GITHUB_RUN_ATTEMPT") == "1"
        and env.get("GITHUB_EVENT_NAME") == "workflow_dispatch",
        "Hosted frontend requires exact fork/ref, manual attempt 1",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--uv", required=True, type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--stock-wheel", type=Path)
    parser.add_argument("--source-repo", type=Path)
    args = parser.parse_args(argv)
    if args.preflight_only:
        require(not args.root.exists(), "Preflight needs a fresh owned root")
        require(
            sys.prefix != sys.base_prefix, "Preflight reuses a read-only outer venv"
        )
        require(args.stock_wheel is not None, "Preflight requires local stock wheel")
    else:
        hosted_guard(os.environ)
    run = FrontendRun(args.root)
    try:
        run.setup_frontend(
            args.uv,
            preflight=args.preflight_only,
            stock_wheel=args.stock_wheel,
            source_repo=args.source_repo,
        )
        run.run_frontend(preflight=args.preflight_only)
    except BaseException as exc:
        save(
            run.upload / "frontend-failure.json",
            {
                "error": type(exc).__name__,
                "message": str(exc),
                "policy": "Preserve first failure, no retries/replacements/retuning",
            },
        )
        raise


if __name__ == "__main__":
    main()
