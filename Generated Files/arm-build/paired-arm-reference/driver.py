"""One bounded native-host reference. No retries, dispatch, publication or profiling."""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

import cpu_audit
from compare import compare_outputs
from frozen import full_inventory, summary, verify_record
from guards import (
    MODULE_HASHES,
    OWNER,
    REV,
    WHEEL,
    WHEEL_HASHES,
    binary_guard,
    candidate_bytes,
    cli_command,
    cli_valid,
    environment,
    forbid_cpu_hook,
    native_guard,
    payload_tree,
    raw_equal,
    require,
    sequence,
    sha,
)
from source import extract, fetch, mode_receipt, save, unchanged

HERE = Path(__file__).resolve().parent
IDENTITY = """
import importlib.metadata as m, json, pathlib, platform, sys
from packaging.tags import sys_tags
print(json.dumps({
    "distributions": {d.metadata["Name"]: d.version for d in m.distributions()},
    "tags": [str(t) for t in sys_tags()],
    "prefix": sys.prefix,
    "site": str(pathlib.Path(m.distribution("pip").locate_file(""))),
    "executable": sys.executable,
    "python_version": platform.python_version(), "machine": platform.machine(),
}))
"""
ORIGIN = """
import importlib, importlib.metadata, json, pathlib, pkgutil, sys
import fastapi_cloud_cli as package
import fastapi_cloud_cli.cli as cli
import fastapi_cloud_cli.utils.sentry as helper
from typer.main import get_command
def walk(command):
    return {n: walk(c) for n, c in sorted(getattr(command, "commands", {}).items())}
names = sorted(m.name for m in pkgutil.walk_packages(
    package.__path__, package.__name__ + ".") if not m.name.endswith(".__main__"))
for name in names:
    importlib.import_module(name)
print(json.dumps({
    "package": package.__file__, "helper": helper.__file__,
    "sentry_loaded": "sentry_sdk" in sys.modules,
    "commands": walk(get_command(cli.app)), "siblings": names,
    "distributions": sorted((d.metadata["Name"], d.version)
                            for d in importlib.metadata.distributions()),
}))
"""


def canonical_name(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def constraints(path):
    return {
        canonical_name(line.split("==")[0]): line.split("==")[1]
        for line in path.read_text().splitlines()
        if "==" in line and not line.startswith("#")
    }


def input_hashes():
    files = [p for p in HERE.iterdir() if p.is_file()]
    files.extend((HERE / "SOURCE").glob("*"))
    files.extend((HERE / "cpu-hook").glob("*.py"))
    return {p.relative_to(HERE).as_posix(): sha(p) for p in files if p.is_file()}


def verify_backend(a, b):
    with zipfile.ZipFile(a) as stock, zipfile.ZipFile(b) as candidate:
        for arm, archive, path in (("A", stock, a), ("B", candidate, b)):
            require(sha(path) == WHEEL_HASHES[arm], "Frozen backend wheel changed")
            verify_record(archive)
            data = archive.read("pdm/backend/sdist.py")
            require(
                hashlib.sha256(data).hexdigest() == MODULE_HASHES[arm],
                "Backend source hash changed",
            )
        require(
            stock.namelist() == candidate.namelist(), "Backend member shape changed"
        )
        changed = [n for n in stock.namelist() if stock.read(n) != candidate.read(n)]
        require(
            set(changed)
            == {"pdm/backend/sdist.py", "pdm_backend-2.5.0.dist-info/RECORD"},
            "Unrelated backend bytes changed",
        )


def verify_phases(stdout, stderr):
    streams = {}
    for name, text in (("stdout", stdout), ("stderr", stderr)):
        streams[name] = {
            "venv_phases": text.count("Creating isolated environment: venv+pip"),
            "all_environment_phases": text.count("Creating isolated environment:"),
            "backend_versions": re.findall(
                r"^\s*-\s+pdm-backend==(\S+)\s*$", text, re.MULTILINE
            ),
            "wheel_from_sdist_phases": text.count("Building wheel from sdist"),
        }
    versions = [
        version for stream in streams.values() for version in stream["backend_versions"]
    ]
    require(
        sum(stream["venv_phases"] for stream in streams.values()) == 2
        and sum(stream["all_environment_phases"] for stream in streams.values()) == 2
        and versions == ["2.5.0", "2.5.0"]
        and sum(stream["wheel_from_sdist_phases"] for stream in streams.values()) == 1,
        "Unexpected frontend/bootstrap/backend/payload",
    )
    return streams


def verify_selection(log, selected, other):
    text = log.read_bytes().decode("utf-8").lower().replace("\\", "/")
    wheel = str(selected).lower().replace("\\", "/")
    require(
        text.count("processing " + wheel) == 2, "Two exact backend selections missing"
    )
    require(str(other).lower().replace("\\", "/") not in text, "Wrong backend selected")
    require("successfully installed pdm-backend-2.5.0" in text, "Missing install")
    require(
        "http/1.1" not in text and '"get ' not in text, "Network in controlled build"
    )


def junit_oracle(path):
    cases = ET.parse(path).findall(".//testcase")
    keys = [(c.get("classname"), c.get("name")) for c in cases]
    require(len(cases) == len(set(keys)) == 2643, "Full node count/uniqueness changed")
    counts = {"passed": 0, "skipped": 0}
    for case in cases:
        require(
            case.find("failure") is None and case.find("error") is None, "Test failure"
        )
        skipped = case.find("skipped")
        if skipped is None:
            counts["passed"] += 1
        else:
            require(skipped.get("message") == "requires Pydantic v1", "New skip reason")
            counts["skipped"] += 1
    require(counts == {"passed": 2513, "skipped": 130}, "Reference statuses changed")
    statuses = sorted(
        (
            case.get("classname"),
            case.get("name"),
            "skipped" if case.find("skipped") is not None else "passed",
        )
        for case in cases
    )
    digest = hashlib.sha256(
        json.dumps(statuses, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    require(
        digest == "ef8e9cd5bf0d4a5b6ffb3389d61d75fbed44b2d84e2e2c4a268ff22a60b7f37d",
        "Canonical JUnit node identities/statuses changed",
    )
    return counts


class Run:
    def __init__(self, root):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.upload = self.root / "upload"
        require(not self.upload.exists(), "Already attempted: no retries/replacements")
        self.upload.mkdir()
        self.env = environment(self.root / "environment")
        self.frozen_inputs = input_hashes()
        save(self.upload / "inputs.json", self.frozen_inputs)
        self.rows = {"build": [], "cli": []}
        self.stock_wheel = None
        self.respx_wheel = None
        self.owner_dev_index = self.env["PIP_INDEX_URL"]

    def preflight_inputs(self, preflight, stock_wheel=None, respx_wheel=None):
        self.owner_dev_index = self.env["PIP_INDEX_URL"]
        require(
            preflight or not (stock_wheel or respx_wheel),
            "Local wheel inputs are preflight-only",
        )
        for path, expected in (
            (stock_wheel, WHEEL_HASHES["A"]),
            (
                respx_wheel,
                (HERE / "owner-dev.txt").read_text().split("--hash=sha256:")[1].strip(),
            ),
        ):
            if path is not None:
                require(
                    path.is_file() and sha(path) == expected,
                    "Local preflight wheel does not match frozen official SHA256",
                )
        self.stock_wheel = stock_wheel.resolve() if stock_wheel else None
        self.respx_wheel = respx_wheel.resolve() if respx_wheel else None
        if self.respx_wheel:
            require(
                self.respx_wheel.name.startswith("respx-0.23.1-")
                and self.respx_wheel.suffix == ".whl",
                "Invalid respx wheel filename",
            )
        if preflight and not self.respx_wheel:
            index = os.environ.get("PIP_INDEX_URL", self.env["PIP_INDEX_URL"])
            parsed = urlsplit(index)
            require(
                parsed.scheme == "https"
                and parsed.hostname
                and parsed.username is None
                and parsed.password is None
                and not parsed.query
                and not parsed.fragment,
                "Preflight owner index requires plain verified HTTPS, without URL credentials",
            )
            self.owner_dev_index = index

    def inputs_unchanged(self):
        require(input_hashes() == self.frozen_inputs, "Committed helper input drift")

    def command(
        self,
        label,
        argv,
        cwd=None,
        env=None,
        expected=0,
        timed=False,
        cpu_receipt=False,
    ):
        active_env = self.env if env is None else env
        if cpu_receipt:
            require(
                not timed and label in ("full-correctness", "cpu-hook-smoke"),
                "SELF hook is only allowed in non-performance correctness/smoke",
            )
            directory = Path(active_env.get("HOBL_CPU_RECEIPT_DIR", "")).resolve()
            require(
                directory.parent == self.upload.resolve(),
                "SELF receipt directory must be owned evidence",
            )
            require(
                str(cpu_audit.HOOK)
                in active_env.get("PYTHONPATH", "").split(os.pathsep),
                "Expected validated startup hook missing",
            )
        else:
            forbid_cpu_hook(active_env)
        directory = self.upload / label
        directory.mkdir()
        row = {
            "argv": [str(a) for a in argv],
            "expected_exit": expected,
            "valid": False,
        }
        save(directory / "command.json", row)
        with (
            (directory / "stdout").open("wb") as out,
            (directory / "stderr").open("wb") as err,
        ):
            start = time.perf_counter()
            try:
                if cpu_receipt:
                    with subprocess.Popen(
                        row["argv"],
                        cwd=cwd or self.root,
                        env=active_env,
                        stdout=out,
                        stderr=err,
                    ) as process:
                        row["entry_pid"] = process.pid
                        try:
                            row["exit"] = process.wait(timeout=1800)
                        except BaseException:
                            process.kill()
                            process.wait()
                            raise
                else:
                    result = subprocess.run(
                        row["argv"],
                        cwd=cwd or self.root,
                        env=active_env,
                        stdout=out,
                        stderr=err,
                        timeout=1800,
                    )
                    row["exit"] = result.returncode
            except BaseException as exc:
                row["error"] = type(exc).__name__
                raise
            finally:
                row["wall_seconds"] = time.perf_counter() - start
                row["performance_eligible"] = timed
                row["stdout_sha256"] = sha(directory / "stdout")
                row["stderr_sha256"] = sha(directory / "stderr")
                save(directory / "command.json", row)
        row["stdout_sha256"] = sha(directory / "stdout")
        row["stderr_sha256"] = sha(directory / "stderr")
        row["valid"] = row["exit"] == expected
        save(directory / "command.json", row)
        require(row["valid"], f"{label}: exit {row['exit']} != {expected}; no retry")
        return (
            row,
            (directory / "stdout").read_bytes(),
            (directory / "stderr").read_bytes(),
        )

    def py(self, python, label, args, **kwargs):
        binary_guard(python)
        return self.command(label, [python, *args], **kwargs)

    def setup(self, build_python=None, test_python=None):
        save(self.upload / "native.json", native_guard())
        context = {
            key: os.environ.get(key)
            for key in (
                "RUNNER_OS",
                "RUNNER_ARCH",
                "ImageOS",
                "ImageVersion",
                "GITHUB_RUN_ID",
                "GITHUB_RUN_ATTEMPT",
                "GITHUB_JOB",
                "GITHUB_SHA",
            )
        }
        context["scope"] = (
            "Hosted hardware/compiler/distribution differences, not pyenv binary parity"
        )
        save(self.upload / "runner.json", context)
        system = platform.system()
        hardware = (
            [
                "sysctl",
                "-n",
                "hw.model",
                "hw.ncpu",
                "hw.memsize",
                "machdep.cpu.brand_string",
            ]
            if system == "Darwin"
            else [
                "pwsh",
                "-NoProfile",
                "-Command",
                "$ErrorActionPreference='Stop'; "
                "$drive=[IO.Path]::GetPathRoot((Get-Location).Path).Substring(0,1); "
                "@{cpu=@(Get-CimInstance Win32_Processor | "
                "Select-Object Name,NumberOfCores,NumberOfLogicalProcessors); "
                "system=(Get-CimInstance Win32_ComputerSystem | "
                "Select-Object Manufacturer,Model,TotalPhysicalMemory); "
                "volume=(Get-Volume -DriveLetter $drive | "
                "Select-Object FileSystem,DriveType,AllocationUnitSize,Size)} "
                "| ConvertTo-Json -Depth 4",
            ]
        )
        self.command("hardware", hardware)
        self.archive, self.proof = fetch(
            self.root,
            "fastapi",
            "https://github.com/fastapi/fastapi.git",
            REV,
            self.command,
        )
        require(len(self.proof["files"]) == 2557, "Wrong pinned payload count")
        save(self.upload / "git-payload-proof.json", self.proof)
        self.source = self.root / "reference-source"
        self.source_before = extract(self.archive, self.source, self.proof)
        save(self.upload / "source-before.json", self.source_before)
        save(
            self.upload / "mode-gate.json", mode_receipt(self.source_before, self.proof)
        )
        self.wheels = {}
        self.backend_constraints = {}
        for arm in "AB":
            folder = self.root / arm
            folder.mkdir()
            wheelhouse = folder / "wheelhouse"
            wheelhouse.mkdir()
            wheel = wheelhouse / WHEEL
            if arm == "B":
                wheel.write_bytes(candidate_bytes(HERE / (WHEEL + ".gz")))
            elif self.stock_wheel:
                shutil.copyfile(self.stock_wheel, wheel)
            else:
                # PyPI JSON and distribution downloads use normal verified TLS.
                import urllib.request

                with urllib.request.urlopen(
                    "https://pypi.org/pypi/pdm-backend/2.5.0/json"
                ) as reply:
                    metadata = json.load(reply)
                entry = next(f for f in metadata["urls"] if f["filename"] == WHEEL)
                require(
                    entry["digests"]["sha256"] == WHEEL_HASHES["A"],
                    "Official wheel identity",
                )
                require(
                    entry["url"].startswith("https://files.pythonhosted.org/"),
                    "Nonofficial wheel",
                )
                urllib.request.urlretrieve(entry["url"], wheel)
            require(sha(wheel) == WHEEL_HASHES[arm], "Backend download/copy hash")
            path = folder / "constraints.txt"
            path.write_text(
                f"pdm-backend @ {wheel.as_uri()}#sha256={WHEEL_HASHES[arm]} "
                f"--hash=sha256:{WHEEL_HASHES[arm]}\n",
                encoding="utf-8",
            )
            self.wheels[arm] = wheel
            self.backend_constraints[arm] = path
        self.setup_constraint = self.root / "setup-backend.txt"
        self.setup_constraint.write_text(
            f"pdm-backend @ {self.wheels['A'].as_uri()}#sha256={WHEEL_HASHES['A']}\n",
            encoding="utf-8",
        )
        verify_backend(self.wheels["A"], self.wheels["B"])
        if build_python is None:
            self.build_python = self.make_venv("minimal", "build-constraints.txt")
            self.test_python = self.make_venv("reference", "reference-constraints.txt")
        else:
            require(
                build_python.resolve() != test_python.resolve(),
                "Use two isolated venvs",
            )
            self.build_python, self.test_python = (
                build_python.resolve(),
                test_python.resolve(),
            )
            for name, python, filename in (
                ("existing-minimal", self.build_python, "build-constraints.txt"),
                ("existing-reference", self.test_python, "reference-constraints.txt"),
            ):
                identity = self.identity(python, name)
                installed = {
                    canonical_name(k): v for k, v in identity["distributions"].items()
                }
                for key, value in constraints(HERE / filename).items():
                    require(
                        installed.get(key) == value,
                        f"Existing venv version drift: {key}",
                    )
        build_identity = self.identity(self.build_python, "minimal-frozen")
        self.build_site = Path(build_identity["site"])
        self.build_before = payload_tree(self.build_site)
        save(self.upload / "minimal-packages-before.json", self.build_before)
        self.isolation_probe()
        self.backend_provenance()
        self.full_env = self.env.copy()
        self.full_env.update(
            PYTHONPATH=str(self.source / "docs_src"),
            CONTEXT="",
            COVERAGE_FILE=str(self.root / "full-coverage" / ".coverage"),
        )
        (self.root / "full-coverage").mkdir()
        self.test_identity = self.identity(self.test_python, "reference")
        self.reference_site = Path(self.test_identity["site"])
        self.reference_before = payload_tree(self.reference_site)
        save(self.upload / "reference-packages-before.json", self.reference_before)

    def make_venv(self, name, constraint):
        folder = self.root / (name + "-venv")
        self.py(sys.executable, name + "-venv", ["-m", "venv", str(folder)])
        python = (
            folder
            / ("Scripts" if os.name == "nt" else "bin")
            / ("python.exe" if os.name == "nt" else "python")
        )
        # A venv redirector is inspected before it is ever executed.
        self.py(
            python,
            name + "-pip",
            [
                "-m",
                "pip",
                "install",
                "--index-url",
                "https://pypi.org/simple",
                "--only-binary=:all:",
                "--report",
                str(self.upload / (name + "-pip.json")),
                "pip==25.0.1",
            ],
        )
        report = self.upload / (name + "-install.json")
        if name == "minimal":
            args = ["-r", str(HERE / constraint)]
        else:
            args = ["-r", "requirements-tests.txt", "-c", str(HERE / constraint)]
        install_env = self.env.copy()
        # URL-fragment verification without --hash: full editable requirements
        # must not accidentally enable pip's all-requirements hash mode.
        install_env["PIP_CONSTRAINT"] = self.setup_constraint.as_uri()
        self.py(
            python,
            name + "-install",
            [
                "-m",
                "pip",
                "install",
                "--only-binary=:all:",
                "--report",
                str(report),
                *args,
            ],
            cwd=self.source,
            env=install_env,
        )
        self.py(python, name + "-check", ["-m", "pip", "check"])
        identity = self.identity(python, name + "-setup")
        installed = {canonical_name(k): v for k, v in identity["distributions"].items()}
        for key, value in constraints(HERE / constraint).items():
            require(installed.get(key) == value, f"Frozen {name} version drift: {key}")
        if name == "reference":
            expected = constraints(HERE / constraint)
            extras = {k: v for k, v in installed.items() if k not in expected}
            allowed = {"uvloop"} if platform.system() == "Darwin" else set()
            require(
                set(extras) <= allowed,
                "Unexpected reference distributions/platform extras",
            )
            save(
                self.upload / "platform-extras.json",
                {
                    "resolved": extras,
                    "policy": "Only original uvicorn[standard] macOS uvloop marker",
                },
            )
        return python

    def identity(self, python, label):
        _, stdout, _ = self.py(python, label + "-identity", ["-c", IDENTITY])
        identity = json.loads(stdout)
        require(identity["python_version"] == "3.12.10", "Child is not CPython 3.12.10")
        require(
            identity["machine"].lower() in ("arm64", "aarch64"), "Child is not ARM64"
        )
        site = Path(identity["site"])
        identity["native_extensions"] = {
            p.relative_to(site).as_posix(): {
                "sha256": sha(p),
                "slices": binary_guard(p),
            }
            for p in site.rglob("*")
            if p.is_file() and p.suffix in (".pyd", ".so")
        }
        save(self.upload / (label + "-identity.json"), identity)
        return identity

    def backend_provenance(self):
        for arm in "AB":
            target = self.root / ("backend-proof-" + arm)
            self.py(
                self.build_python,
                "backend-install-" + arm,
                [
                    "-m",
                    "pip",
                    "install",
                    "--no-index",
                    "--no-deps",
                    "--target",
                    str(target),
                    str(self.wheels[arm]),
                    "--report",
                    str(self.upload / ("backend-install-" + arm + ".json")),
                ],
            )
            env = self.env.copy()
            env["PYTHONPATH"] = str(target)
            code = """
import hashlib, importlib.metadata, json, pathlib
import pdm.backend.sdist as s
print(json.dumps({"origin": s.__file__,
 "sha256": hashlib.sha256(pathlib.Path(s.__file__).read_bytes()).hexdigest(),
 "version": importlib.metadata.version("pdm-backend")}))
"""
            _, out, _ = self.py(
                self.build_python, "backend-origin-" + arm, ["-c", code], env=env
            )
            origin = json.loads(out)
            require(
                Path(origin["origin"]).is_relative_to(target),
                "Wrong installed backend origin",
            )
            require(
                origin["sha256"] == MODULE_HASHES[arm] and origin["version"] == "2.5.0",
                "Installed backend source/version drift",
            )

    def isolation_probe(self):
        code = """
import json
from build.env import _PipBackend
b = _PipBackend()
print(json.dumps({
    "valid_outer_pip": b._has_valid_outer_pip,
    "virtualenv_available": b._has_virtualenv,
    "create_with_virtualenv": b._create_with_virtualenv,
    "display_name": b.display_name,
}))
"""
        _, out, _ = self.py(self.build_python, "isolation-selection", ["-c", code])
        self.isolation = json.loads(out)
        require(
            self.isolation["valid_outer_pip"] is True
            and not self.isolation["create_with_virtualenv"]
            and self.isolation["display_name"] == "venv+pip",
            "Require default stdlib venv without ensurepip, using valid outer pip",
        )
        save(self.upload / "isolation-selection.json", self.isolation)

    def build_env(self, arm, work, stage):
        env = self.env.copy()
        env.update(
            SOURCE_DATE_EPOCH="1700000000",
            PIP_NO_INDEX="1",
            PIP_REQUIRE_HASHES="1",
            PIP_FIND_LINKS=self.wheels[arm].parent.as_uri(),
            PIP_CONSTRAINT=self.backend_constraints[arm].as_uri(),
            PIP_CACHE_DIR=str(self.root / arm / (stage + "-cache")),
            PIP_LOG=str(self.upload / work.name / "pip.log"),
        )
        for key in ("TEMP", "TMP", "TMPDIR"):
            env[key] = str(work / "scratch")
        return env

    def build(self, label, arm, pair=0, timed=False):
        prepare_start = time.perf_counter()
        self.inputs_unchanged()
        require(
            payload_tree(self.build_site) == self.build_before,
            "Minimal outer environment drift",
        )
        verify_backend(self.wheels["A"], self.wheels["B"])
        work = self.root / ("work-" + label)
        work.mkdir()
        (work / "scratch").mkdir()
        source = work / "source"
        before = extract(self.archive, source, self.proof)
        require(before == self.source_before, "Fresh source conditions differ")
        # command creates the evidence directory immediately before invocation.
        env = self.build_env(
            arm, self.upload / label, "trials" if timed else "correctness"
        )
        for key in ("TEMP", "TMP", "TMPDIR"):
            env[key] = str(work / "scratch")
        prepare_seconds = time.perf_counter() - prepare_start
        row, out, err = self.py(
            self.build_python,
            label,
            ["-m", "build"],
            cwd=source,
            env=env,
            timed=timed,
        )
        validation_start = time.perf_counter()
        unchanged(source, before)
        phases = verify_phases(out.decode("utf-8"), err.decode("utf-8"))
        verify_selection(
            self.upload / label / "pip.log",
            self.wheels[arm],
            self.wheels["B" if arm == "A" else "A"],
        )
        save(
            self.upload / label / "selection.json",
            {
                "arm": arm,
                "wheel_sha256": WHEEL_HASHES[arm],
                "module_sha256": MODULE_HASHES[arm],
                "exact_pip_processing_count": 2,
                "phases": phases,
                "isolation": self.isolation,
            },
        )
        dist = self.upload / label / "dist"
        shutil.copytree(source / "dist", dist)
        save(self.upload / label / "inventory.json", full_inventory(dist))
        save(self.upload / label / "artifacts.json", payload_tree(dist))
        row.update(
            arm=arm,
            pair=pair,
            timed=pair > 0,
            label=label,
            valid=True,
            preparation_seconds=prepare_seconds,
            validation_seconds=time.perf_counter() - validation_start,
        )
        return row, dist

    def overlays(self):
        owner_archive, owner_proof = fetch(
            self.root,
            "cloud-owner",
            "https://github.com/fastapilabs/fastapi-cloud-cli.git",
            OWNER,
            self.command,
        )
        self.owner = self.root / "cloud-owner-source"
        extract(owner_archive, self.owner, owner_proof)
        installed = self.reference_site / "fastapi_cloud_cli"
        require(
            payload_tree(installed)
            == payload_tree(self.owner / "src" / "fastapi_cloud_cli"),
            "Installed cloud code differs from official owner Git",
        )
        self.overlay = {}
        for arm in "AB":
            base = self.root / ("overlay-" + arm)
            shutil.copytree(
                installed,
                base / "fastapi_cloud_cli",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            self.overlay[arm] = base
        self.command(
            "owner-patch",
            [
                "git",
                "apply",
                "--unidiff-zero",
                str(HERE / "cloud.patch"),
            ],
            cwd=self.owner,
        )
        shutil.copyfile(
            self.owner / "src" / "fastapi_cloud_cli" / "utils" / "sentry.py",
            self.overlay["B"] / "fastapi_cloud_cli" / "utils" / "sentry.py",
        )
        a, b = [payload_tree(self.overlay[arm]) for arm in "AB"]
        require(a.keys() == b.keys(), "Overlay shape drift")
        require(
            [p for p in a if a[p] != b[p]] == ["fastapi_cloud_cli/utils/sentry.py"],
            "Unexpected overlay differences",
        )
        save(
            self.upload / "overlay-provenance.json",
            {
                "owner_commit": OWNER,
                "A": a,
                "B": b,
                "patch_sha256": sha(HERE / "cloud.patch"),
                "B_label": "LOCAL source variant, NOT an official release",
            },
        )
        self.owner_dev_install()

    def owner_dev_install(self):
        self.dev = self.root / "owner-dev-only"
        env = self.env.copy()
        env["PIP_INDEX_URL"] = self.owner_dev_index
        if self.respx_wheel:
            env.update(
                PIP_NO_INDEX="1", PIP_FIND_LINKS=self.respx_wheel.parent.as_uri()
            )
        self.py(
            self.test_python,
            "owner-dev-install",
            [
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--require-hashes",
                "--only-binary=:all:",
                "--target",
                str(self.dev),
                "-r",
                str(HERE / "owner-dev.txt"),
            ],
            env=env,
        )

    def cli_env(self, arm, label, *, owner_dev=False, covered=False):
        env = self.full_env.copy()
        entries = [str(self.overlay[arm]), str(self.source / "docs_src")]
        if owner_dev:
            entries.append(str(self.dev))
        env["PYTHONPATH"] = os.pathsep.join(entries)
        coverage = self.root / "cli-coverage" / label
        coverage.mkdir(parents=True)
        env["COVERAGE_FILE"] = str(coverage / ".coverage")
        if covered:
            env["PYTEST_CURRENT_TEST"] = (
                "tests/test_fastapi_cli.py::test_fastapi_cli (call)"
            )
        return env

    def semantic_gates(self):
        self.overlays()
        origins = {}
        for arm in "AB":
            _, out, _ = self.py(
                self.test_python,
                "origin-" + arm,
                ["-c", ORIGIN],
                cwd=self.source,
                env=self.cli_env(arm, "origin-" + arm),
            )
            origin = origins[arm] = json.loads(out)
            require(
                Path(origin["helper"]).is_relative_to(self.overlay[arm]),
                "Wrong overlay origin",
            )
            require(
                Path(origin["package"]).is_relative_to(self.overlay[arm]),
                "Wrong package origin",
            )
            require(origin["sentry_loaded"] is (arm == "A"), "Cold import boundary")
        for key in ("commands", "siblings", "distributions"):
            require(origins["A"][key] == origins["B"][key], "Changed CLI " + key)
        for arm in "AB":
            args = ["-m", "pytest", "tests/test_sentry_lazy.py", "-q"]
            if arm == "B":
                args.insert(-1, "tests/test_sentry.py")
            _, out, _ = self.py(
                self.test_python,
                "owner-tests-" + arm,
                args,
                cwd=self.owner,
                env=self.cli_env(arm, "owner-tests-" + arm, owner_dev=True),
                expected=0 if arm == "B" else 1,
            )
            require(
                (b"10 passed" if arm == "B" else b"4 failed, 3 passed") in out,
                "Owner targeted/negative proof changed",
            )
            _, out, _ = self.py(
                self.test_python,
                "fastapi-cli-tests-" + arm,
                ["-m", "pytest", "tests/test_fastapi_cli.py", "-q"],
                cwd=self.source,
                env=self.cli_env(arm, "fastapi-cli-tests-" + arm),
            )
            require(b"2 passed" in out, "Original covered FastAPI CLI proofs")
        for label, args in (
            ("help", ["-m", "fastapi", "--help"]),
            ("version", ["-m", "fastapi", "--version"]),
            ("cloud-help", ["-m", "fastapi", "cloud", "--help"]),
        ):
            outputs = [
                self.py(
                    self.test_python,
                    label + "-" + arm,
                    args,
                    cwd=self.source,
                    env=self.cli_env(arm, label + "-" + arm),
                )[1:]
                for arm in "AB"
            ]
            raw_equal(outputs[0], outputs[1])
        self.integrity()
        save(
            self.upload / "semantic-gates.json",
            {"passed": True, "raw_byte_comparison": True},
        )

    def full_correctness(self):
        # Exactly one original full coverage/pytest command, stock packages only.
        shards = self.root / "full-coverage"
        raw = self.upload / "raw-full-coverage"
        require(
            not list(shards.iterdir()), "Refuse stale/mixed coverage before full run"
        )
        env, receipts = self.cpu_environment("full")
        try:
            row, stdout, stderr = self.py(
                self.test_python,
                "full-correctness",
                [
                    "-m",
                    "coverage",
                    "run",
                    "-m",
                    "pytest",
                    "tests",
                    "-vv",
                    "-rA",
                    "--durations=25",
                    "--durations-min=0",
                    "-o",
                    "junit_duration_report=total",
                    "--junitxml=" + str(self.upload / "junit.xml"),
                ],
                cwd=self.source,
                env=env,
                cpu_receipt=True,
            )
        finally:
            # Raw SQLite shards survive failed tests and any later auto-combine.
            shutil.copytree(shards, raw)
            save(self.upload / "raw-coverage-hashes.json", payload_tree(raw))
            command = self.upload / "full-correctness"
            metadata = (
                json.loads((command / "command.json").read_bytes())
                if (command / "command.json").exists()
                else {}
            )
            cpu = cpu_audit.audit(
                receipts,
                raw,
                metadata.get("entry_pid"),
                (command / "stderr").read_bytes()
                if (command / "stderr").exists()
                else b"",
            )
            save(self.upload / "CPU-AUDIT.json", cpu)
        require(
            cpu["covered_worker_receipts_complete"],
            "Covered worker SELF CPU receipts incomplete",
        )
        require(
            len(list(raw.glob(".coverage.*"))) == 2,
            "Expected worker and CLI child shards",
        )
        save(
            self.upload / "full-statuses.json", junit_oracle(self.upload / "junit.xml")
        )
        require(
            b"2513 passed" in stdout and b"130 skipped" in stdout,
            "Console status drift",
        )
        require(not stderr, "Unexpected full-suite stderr")
        self.py(
            self.test_python,
            "coverage-combine",
            ["-m", "coverage", "combine", "--keep", str(shards)],
            cwd=self.source,
            env=self.full_env,
        )
        self.py(
            self.test_python,
            "coverage-json",
            [
                "-m",
                "coverage",
                "json",
                "--show-contexts",
                "-o",
                str(self.upload / "coverage.json"),
            ],
            cwd=self.source,
            env=self.full_env,
        )
        with closing(
            sqlite3.connect((shards / ".coverage").as_uri() + "?mode=ro", uri=True)
        ) as db:
            files = [r[0] for r in db.execute("SELECT path FROM file")]
            contexts = {r[0] for r in db.execute("SELECT context FROM context")}
        report = json.loads((self.upload / "coverage.json").read_text())
        json_contexts = {
            context
            for item in report["files"].values()
            for entries in item.get("contexts", {}).values()
            for context in entries
        }
        shape = {"files": len(files), "contexts": len(contexts)}
        save(
            self.upload / "coverage-shape.json",
            {
                **shape,
                "expected": {"files": 863, "contexts": 1409},
                "json_contexts_equal_sqlite": json_contexts == contexts,
            },
        )
        require(
            shape == {"files": 863, "contexts": 1409},
            "Coverage reference shape changed",
        )
        require(
            len(report["files"]) == len(files) and json_contexts == contexts,
            "JSON/SQLite coverage oracles disagree",
        )
        for marker in ("docs_src/", "tests/", "fastapi/"):
            require(
                any(marker in path.replace("\\", "/") for path in files),
                "Original coverage source missing: " + marker,
            )
        save(
            self.upload / "correctness-boundary.json",
            {
                "performance_eligible": False,
                "wall_seconds": row["wall_seconds"],
                "cpu": "CPU-AUDIT.json: observed Python SELF only, not whole OS tree or launcher CPU",
                "baseline": "Stock source/packages; AnyIO 4.14.2 compatible reference",
            },
        )
        self.integrity()

    def cpu_environment(self, stage):
        require(
            sha(cpu_audit.HOOK / "sitecustomize.py")
            == "35dc681fc09f34774c359826a61aa1376e352c973336085ab2bf176c5f6d9517",
            "Validated SELF hook bytes changed",
        )
        _, out, _ = self.py(
            self.test_python,
            "cpu-startup-guard-" + stage,
            ["-c", cpu_audit.STARTUP_CHECK],
            cwd=self.source,
            env=self.full_env,
        )
        guard = json.loads(out)
        require(
            not guard["existing_hooks"] and not guard["trace"] and not guard["profile"],
            "Refuse to shadow an existing startup hook/trace/profile callback",
        )
        receipts = self.upload / (stage + "-worker-cpu")
        receipts.mkdir()
        env = self.full_env.copy()
        env["PYTHONPATH"] = os.pathsep.join([str(cpu_audit.HOOK), env["PYTHONPATH"]])
        env["HOBL_CPU_RECEIPT_DIR"] = str(receipts)
        return env, receipts

    def cpu_hook_smoke(self):
        env, receipts = self.cpu_environment("smoke")
        row, _, stderr = self.py(
            self.test_python,
            "cpu-hook-smoke",
            ["-c", "pass"],
            cwd=self.source,
            env=env,
            cpu_receipt=True,
        )
        result = cpu_audit.smoke(receipts, row.get("entry_pid"), stderr)
        save(self.upload / "CPU-SMOKE.json", result)
        require(result["complete"], "Native no-test SELF hook smoke failed")

    def integrity(self):
        self.inputs_unchanged()
        require(
            payload_tree(self.build_site) == self.build_before,
            "Minimal outer environment drift",
        )
        unchanged(self.source, self.source_before)
        require(
            payload_tree(self.reference_site) == self.reference_before,
            "Reference package bytes changed",
        )

    def cli(self, label, arm, pair=0, timed=False):
        prepare_start = time.perf_counter()
        self.integrity()
        env = self.cli_env(arm, label, covered=True)
        prepare_seconds = time.perf_counter() - prepare_start
        row, stdout, stderr = self.py(
            self.test_python,
            label,
            cli_command(self.test_python)[1:],
            cwd=self.source,
            env=env,
            expected=1,
            timed=timed,
        )
        cli_valid(row["exit"], stdout, stderr)
        row.update(
            arm=arm,
            pair=pair,
            timed=pair > 0,
            label=label,
            valid=True,
            preparation_seconds=prepare_seconds,
        )
        return row, (stdout, stderr)

    def execute(
        self,
        *,
        preflight=False,
        build_python=None,
        test_python=None,
        stock_wheel=None,
        respx_wheel=None,
    ):
        self.preflight_inputs(preflight, stock_wheel, respx_wheel)
        setup_start = time.perf_counter()
        self.setup(build_python, test_python)
        if preflight:
            self.cpu_hook_smoke()
        setup_end = time.perf_counter()
        a = self.build("correctness-build-A", "A")[1]
        b = self.build("correctness-build-B", "B")[1]
        save(self.upload / "build-correctness.json", compare_outputs(a, b))
        self.semantic_gates()
        cli_reference = self.cli("correctness-cli-A", "A")[1]
        raw_equal(cli_reference, self.cli("correctness-cli-B", "B")[1])
        if preflight:
            self.integrity()
            save(
                self.upload / "result.json",
                {
                    "status": "PREFLIGHT_ONLY_NO_TIMINGS_OR_FULL_SUITE",
                    "parity": "NOT_ACCEPTED: cross-platform mode gate unresolved",
                },
            )
            return
        self.full_correctness()
        save(
            self.upload / "schedule.json",
            {
                "commands_per_experiment": sequence(),
                "no_retries": True,
                "bytecode": "default enabled",
                "profile": "none",
                "cache": "Two A/B warmups; no OS-cache purge; per-arm build caches",
            },
        )
        gates_end = time.perf_counter()
        for label, arm, pair in sequence():
            row, dist = self.build("build-" + label, arm, pair, timed=True)
            compare_start = time.perf_counter()
            compare_outputs(a, dist)
            row["comparison_seconds"] = time.perf_counter() - compare_start
            self.rows["build"].append(row)
            save(self.upload / "partial-rows.json", self.rows)
        for label, arm, pair in sequence():
            row, output = self.cli("cli-" + label, arm, pair, timed=True)
            raw_equal(cli_reference, output)
            self.rows["cli"].append(row)
            save(self.upload / "partial-rows.json", self.rows)
        self.integrity()
        save(
            self.upload / "result.json",
            {
                "status": "WITHIN_HOST_VALIDATED_REFERENCE",
                "parity": "NOT_ACCEPTED: cross-platform source/artifact mode gate unresolved",
                "build": summary(self.rows["build"]),
                "cli": summary(self.rows["cli"]),
                "setup_seconds": setup_end - setup_start,
                "gates_seconds": gates_end - setup_end,
                "experiments_seconds": time.perf_counter() - gates_end,
                "scope": "Controlled local backend and SDK mechanism; not unmodified HOBL.",
            },
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--guard-only", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--build-python", type=Path)
    parser.add_argument("--test-python", type=Path)
    parser.add_argument("--stock-wheel", type=Path)
    parser.add_argument("--respx-wheel", type=Path)
    args = parser.parse_args()
    require(
        bool(args.build_python) == bool(args.test_python),
        "Supply both existing venvs or neither",
    )
    require(
        not args.build_python or args.preflight,
        "Existing venv override is preflight-only",
    )
    require(
        not (args.stock_wheel or args.respx_wheel) or args.preflight,
        "Local wheel inputs are preflight-only",
    )
    if args.guard_only:
        save(args.root / "bootstrap-native.json", native_guard())
        return
    native_guard()
    run = Run(args.root)
    started = time.perf_counter()
    try:
        run.execute(
            preflight=args.preflight,
            build_python=args.build_python,
            test_python=args.test_python,
            stock_wheel=args.stock_wheel,
            respx_wheel=args.respx_wheel,
        )
    finally:
        save(
            run.upload / "total-boundary.json",
            {
                "total_seconds": time.perf_counter() - started,
                "queue_checkout_bootstrap": "Outside driver; use Actions timestamps",
                "status": "completed"
                if (run.upload / "result.json").exists()
                else "FAILED_NO_RETRY",
            },
        )


if __name__ == "__main__":
    main()
