"""P50 single-stock native UV control; source-only preparation is not allocation."""

import argparse
import dataclasses
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from compare import compare_outputs
from frontend import argv_for, constraint_text, verify_log, verify_python_abi
from frozen import full_inventory, verify_record
from guards import (
    REV,
    WHEEL,
    WHEEL_HASHES,
    environment,
    native_guard,
    require,
    sha,
    tree,
)
from hardware_control import comparable, cpu_receipt, filesystem_context
from installer import native_uv
from source import extract, generated_cache, mode_receipt, prove, save, unchanged

HERE = Path(__file__).resolve().parent
OWNERSHIP = HERE.parent / "protocol" / "owned_process.py"
WORKFLOW = HERE.parents[2] / ".github" / "workflows" / "arm-build-experiment.yml"
ARCHIVE_HASH = "4cba86b9b9d61883fe786425a505149ca777782cfe266e274796097c30eb8e83"
SECURITY = (
    "NoDefaultCurrentDirectoryInExePath",
    "PYTHONSAFEPATH",
    "PYTHONNOUSERSITE",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "NODE_EXTRA_CA_CERTS",
    "UV_SYSTEM_CERTS",
    "UV_NATIVE_TLS",
    "PIP_CERT",
)


def ownership():
    spec = importlib.util.spec_from_file_location("p50_owned_process", OWNERSHIP)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def schedule(local):
    return [("warmup", False)] + (
        [] if local else [(f"sample-{n}", True) for n in range(1, 7)]
    )


def hosted_guard(env):
    require(
        env.get("GITHUB_REPOSITORY") == "yeelam-gordon/fastapi"
        and env.get("GITHUB_REF") == "refs/heads/perf/arm-cobalt-control"
        and env.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
        and env.get("GITHUB_RUN_ATTEMPT") == "1",
        "Require exact fork/ref/manual attempt 1",
    )


def stock_environment(root):
    env = environment(root)
    env.update({key: os.environ[key] for key in SECURITY if key in os.environ})
    env.update(SOURCE_DATE_EPOCH="1700000000", COLUMNS="4096", TERM="dumb")
    if os.name == "nt":
        env["NoDefaultCurrentDirectoryInExePath"] = "1"
    require("PYTHONDONTWRITEBYTECODE" not in env, "Default backend bytecode required")
    return env


def security_fingerprint(env):
    return hashlib.sha256(
        json.dumps({key: env.get(key) for key in SECURITY}, sort_keys=True).encode()
    ).hexdigest()


def closure():
    paths = [*HERE.glob("*.py"), HERE / "bootstrap.ps1", OWNERSHIP, WORKFLOW]
    return {str(p): sha(p) for p in paths}


def imports(inputs):
    roots = (Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve())
    rows = {}
    for name, module in tuple(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if not filename:
            continue
        path = Path(filename).resolve()
        if str(path) in inputs:
            rows[name] = {"path": str(path), "sha256": sha(path)}
        else:
            require(
                any(path.is_relative_to(root) for root in roots),
                "Unmanifested helper import: " + name,
            )
    return rows


def artifact_payloads(inventory, proof, source):
    checked = {}
    for kind, members in inventory.items():
        count = 0
        for name, row in members.items():
            path = name.removeprefix("fastapi-0.119.1/") if kind == "sdist" else name
            if path in proof["files"]:
                expected = (
                    sha(source / ".pdm-build" / "pyproject.toml")
                    if path == "pyproject.toml"
                    else proof["files"][path]["sha256"]
                )
                require(
                    row["sha256"] == expected,
                    "Artifact/canonical source payload mismatch",
                )
                count += 1
        checked[kind] = count
    require(
        checked["sdist"] > 1100 and checked["wheel"] >= 50,
        "Incomplete artifact/source proof",
    )
    require(
        inventory["sdist"]["fastapi-0.119.1/PKG-INFO"]["sha256"]
        == inventory["wheel"]["fastapi-0.119.1.dist-info/METADATA"]["sha256"],
        "sdist/wheel metadata differs",
    )
    return checked


def execute(args):
    if not args.local_correctness:
        hosted_guard(os.environ)
    else:
        require(platform.system() == "Windows", "Only Windows local proof authorized")
    require(not args.root.exists(), "Fresh owned root required; no retry/replacement")
    args.root.mkdir(parents=True)
    result = {
        "status": "preparing",
        "rows": [],
        "performance_cohort": not args.local_correctness,
    }
    output = args.root / "evidence"
    output.mkdir()
    env = stock_environment(args.root / "environment")
    os.environ.clear()
    os.environ.update(env)
    inputs = closure()
    save(output / "inputs.json", inputs)
    own = ownership()
    save(output / "executed-imports.json", imports(inputs))
    try:
        cpu = cpu_receipt(local=args.local_correctness)
        save(output / "cpu.json", cpu)
        save(output / "comparability.json", comparable(cpu))
        native = native_guard()
        save(output / "native.json", native)
        abi = {
            "cache_tag": sys.implementation.cache_tag,
            "version": platform.python_version(),
            "system": platform.system(),
            "bits": 64 if sys.maxsize > 2**32 else 32,
            "machine": platform.machine(),
            "base": sys._base_executable,
            "source_prefix": sys.base_prefix,
        }
        import sysconfig

        abi.update(
            soabi=sysconfig.get_config_var("SOABI"),
            sysconfig_platform=sysconfig.get_platform(),
            ext_suffix=sysconfig.get_config_var("EXT_SUFFIX"),
        )
        verify_python_abi(abi)
        save(output / "actual-abi.json", abi)
        native_uv(args.uv)
        tools = {
            str(p): sha(p)
            for p in (Path(sys._base_executable).resolve(), args.uv.resolve())
        }
        if os.name == "nt":
            dll = Path(sys.base_prefix) / "python312.dll"
            require(
                sha(Path(sys._base_executable))
                == "7f1ebbbb04164caf8f8073aafa7f82321fb44695e10fe6a9ebaf2138b63892c4"
                and sha(dll)
                == "84df280a69e539107d2537b36ef1ff6e67713634a5c374c96a600da86939e98f",
                "Require stock official Windows Python, not P47 patched runtime",
            )
            tools[str(dll)] = sha(dll)
        save(output / "native-tools.json", tools)
        lifecycle = own.run_owned(
            [
                sys.executable,
                "-B",
                "-c",
                f"import sys; sys.path.insert(0,{str(HERE)!r}); "
                "import os,json; from hardware_control import windows_affinity; "
                "from control import security_fingerprint; "
                "print(json.dumps(dict(usable=windows_affinity()['usable'] "
                "if os.name=='nt' else len(os.sched_getaffinity(0)),"
                "security_fingerprint=security_fingerprint(os.environ),"
                "security=os.environ.get('NoDefaultCurrentDirectoryInExePath'),"
                "bytecode=os.environ.get('PYTHONDONTWRITEBYTECODE'))))",
            ],
            cwd=args.root,
            env=env,
            stdout_path=output / "lifecycle.stdout",
            stderr_path=output / "lifecycle.stderr",
            native_clock=True,
            timeout=30,
        )
        save(output / "lifecycle.json", dataclasses.asdict(lifecycle))
        require(
            lifecycle.succeeded and lifecycle.native_end_ns > lifecycle.native_start_ns,
            "Native platform owned lifecycle/clock preflight failed",
        )
        child = json.loads((output / "lifecycle.stdout").read_bytes())
        require(
            child["usable"] == 4
            and child["security_fingerprint"] == security_fingerprint(env)
            and child["bytecode"] is None
            and (os.name != "nt" or child["security"] == "1"),
            "Actual child security/default-bytecode mismatch",
        )
        archive = args.root / "source.tar.gz"
        subprocess.run(
            [
                "git",
                "-c",
                "core.autocrlf=false",
                "-C",
                str(args.source_repo),
                "archive",
                "--format=tar.gz",
                "--output=" + str(archive),
                REV,
            ],
            check=True,
            stdin=subprocess.DEVNULL,
            timeout=120,
        )
        proof = prove(args.source_repo, REV, archive)
        require(
            len(proof["files"]) == 2557 and sha(archive) == ARCHIVE_HASH,
            "Full canonical raw-LF source identity mismatch",
        )
        save(output / "source-proof.json", proof)
        wheel = args.root / "wheelhouse" / WHEEL
        wheel.parent.mkdir()
        if args.stock_wheel:
            require(args.local_correctness, "Local wheel only in local proof")
            shutil.copyfile(args.stock_wheel, wheel)
        else:
            with urllib.request.urlopen(
                "https://pypi.org/pypi/pdm-backend/2.5.0/json"
            ) as reply:
                entry = next(
                    f for f in json.load(reply)["urls"] if f["filename"] == WHEEL
                )
            require(
                entry["digests"]["sha256"] == WHEEL_HASHES["A"]
                and entry["url"].startswith("https://files.pythonhosted.org/"),
                "Official stock wheel",
            )
            urllib.request.urlretrieve(entry["url"], wheel)
        require(sha(wheel) == WHEEL_HASHES["A"], "Stock PDM wheel hash")
        with zipfile.ZipFile(wheel) as zipped:
            verify_record(zipped)
        constraint = args.root / "constraints.txt"
        constraint.write_text(constraint_text(wheel), encoding="utf-8", newline="\n")
        cache = args.root / "cache"
        cache.mkdir()
        baseline = None
        for label, timed in schedule(args.local_correctness):
            folder = args.root / label
            folder.mkdir()
            source = folder / "source"
            before = extract(archive, source, proof)
            save(output / label / "source-before.json", before)
            save(output / label / "mode.json", mode_receipt(before, proof))
            scratch = folder / "scratch"
            scratch.mkdir()
            active = dict(
                env,
                UV_CACHE_DIR=str(cache),
                UV_FIND_LINKS=wheel.parent.as_uri(),
                UV_OFFLINE="1",
                UV_NO_INDEX="1",
                UV_NO_CONFIG="1",
                UV_PYTHON_DOWNLOADS="never",
                UV_NO_MANAGED_PYTHON="1",
                UV_BUILD_CONSTRAINT=constraint.as_uri(),
                PIP_NO_INDEX="1",
                PIP_FIND_LINKS=wheel.parent.as_uri(),
                PIP_CONSTRAINT=constraint.as_uri(),
                TEMP=str(scratch),
                TMP=str(scratch),
                TMPDIR=str(scratch),
            )
            save(
                output / label / "filesystem.json",
                filesystem_context(
                    {
                        "workspace": args.source_repo,
                        "source": source,
                        "cache": cache,
                        "temp": scratch,
                        "home": Path(active["HOME"]),
                        "runtime": Path(sys.base_prefix),
                    }
                ),
            )
            argv = argv_for("B", Path(sys.executable), args.uv, constraint)
            row = {
                "label": label,
                "timed": timed,
                "valid": False,
                "argv": argv,
                "cwd": str(source),
                "environment": {
                    k: v
                    for k, v in active.items()
                    if (k.startswith(("UV_", "PIP_", "PYTHON")) and k not in SECURITY)
                    or k
                    in (
                        "HOME",
                        "USERPROFILE",
                        "TEMP",
                        "TMP",
                        "TMPDIR",
                        "SOURCE_DATE_EPOCH",
                        "COLUMNS",
                        "TERM",
                        "NoDefaultCurrentDirectoryInExePath",
                    )
                },
            }
            result["rows"].append(row)
            save(output / "result.json", result)
            require(
                closure() == inputs
                and all(sha(Path(p)) == h for p, h in tools.items()),
                "Helper/native input drift",
            )
            receipt = own.run_owned(
                argv,
                cwd=source,
                env=active,
                stdout_path=output / label / "stdout",
                stderr_path=output / label / "stderr",
                timeout=180,
                native_clock=not args.local_correctness,
            )
            row["ownership"] = dataclasses.asdict(receipt)
            save(output / "result.json", result)
            require(receipt.succeeded, "Native UV/family failed; preserve, stop")
            if timed:
                require(
                    receipt.native_end_ns > receipt.native_start_ns,
                    "Invalid native clock",
                )
                row["elapsed_ns"] = receipt.native_end_ns - receipt.native_start_ns
            unchanged(source, before)
            row["generated_source"] = generated_cache(source, proof)
            save(output / label / "source-after.json", tree(source))
            text = (
                (output / label / "stdout").read_text(encoding="utf-8")
                + "\n"
                + (output / label / "stderr").read_text(encoding="utf-8")
            )
            row["phase_proof"] = verify_log(text, wheel, args.uv)
            inventory = full_inventory(source / "dist")
            require(
                {k: len(v) for k, v in inventory.items()}
                == {"sdist": 1196, "wheel": 58},
                "Full artifact member counts changed",
            )
            row["source_artifact_payloads"] = artifact_payloads(
                inventory, proof, source
            )
            save(output / label / "artifact-inventory.json", inventory)
            if args.reference:
                require(
                    args.local_correctness,
                    "Historical reference only local correctness",
                )
                row["reference"] = compare_outputs(args.reference, source / "dist")
            if baseline:
                row["within_host"] = compare_outputs(baseline, source / "dist")
            else:
                baseline = source / "dist"
            shutil.copytree(source / "dist", output / label / "artifacts")
            require(
                closure() == inputs
                and sha(wheel) == WHEEL_HASHES["A"]
                and constraint.read_bytes() == constraint_text(wheel).encode()
                and all(sha(Path(p)) == h for p, h in tools.items()),
                "Post-command frozen input drift",
            )
            row["valid"] = True
            save(output / "executed-imports.json", imports(inputs))
            save(output / "result.json", result)
        values = [r["elapsed_ns"] for r in result["rows"] if r["timed"]]
        result.update(
            status="local-correctness-complete"
            if args.local_correctness
            else "complete",
            measured_samples=len(values),
            median_ns=statistics.median(values) if values else None,
            interpretation="New-cohort platform stack only; no OS causality/Mac/Windows gain claim",
            cross_host_raw_identity="UNWAIVED mode/creator provenance gap",
        )
    except BaseException as error:
        result.update(status="stopped-no-replacement", first_failure=repr(error))
        raise
    finally:
        save(output / "result.json", result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--local-correctness", action="store_true")
    parser.add_argument("--stock-wheel", type=Path)
    parser.add_argument("--reference", type=Path)
    args = parser.parse_args()
    for key in ("root", "uv", "source_repo", "stock_wheel", "reference"):
        value = getattr(args, key)
        if value is not None:
            setattr(args, key, value.resolve())
    execute(args)


if __name__ == "__main__":
    main()
