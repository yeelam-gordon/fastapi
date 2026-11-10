"""Observed private SDK/uv-venv preparation; no build or admission authority."""

import dataclasses
import hashlib
import json
import math
import os
import platform
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.with_name("matched-build-reference-screen")
sys.path.insert(0, str(CORE))

import owned_process  # noqa: E402
import reference  # noqa: E402

PIN = "29c9e239434dfcf1479c2767de26d6df1088e9bcd85a3989241af993540b86e6"
PUBLISHER = {
    "win32": "c609338dbee5de09cbd15d7167081295bc7ae53481af55fb5b2cd2aa8c52d44f",
    "darwin": "d66c67f16148c7454b1509c32747175f7669c8b8e105b97b92a0000d66af6e6e",
}
LOCATION_HANDOFF = frozenset(
    {
        "UV_PYTHON_INSTALL_DIR",
        "UV_TOOL_BIN_DIR",
        "UV_TOOL_DIR",
        "pythonLocation",
        "Python_ROOT_DIR",
        "Python2_ROOT_DIR",
        "Python3_ROOT_DIR",
    }
)
PROBE = r"""
import hashlib, json, os, platform, sys, sysconfig
from pathlib import Path
venv = Path(sys.prefix)
cfg = (venv / "pyvenv.cfg").read_bytes()
links = {}
if sys.platform == "darwin":
    for name in ("python", "python3", "python3.13"):
        path = venv / "bin" / name
        links[name] = os.readlink(path) if path.is_symlink() else None
print(json.dumps({
    "executable": sys.executable, "prefix": sys.prefix,
    "base_prefix": sys.base_prefix, "base_executable": sys._base_executable,
    "version": sys.version, "version_info": list(sys.version_info[:3]),
    "platform": sys.platform, "platform_tag": sysconfig.get_platform(),
    "machine": platform.machine(), "optimization": sys.flags.optimize,
    "isolated": sys.flags.isolated, "dont_write_bytecode": sys.dont_write_bytecode,
    "pycache_prefix": sys.pycache_prefix,
    "gil": getattr(sys, "_is_gil_enabled", lambda: False)(),
    "gil_disabled": sysconfig.get_config_var("Py_GIL_DISABLED"),
    "jit_build": sysconfig.get_config_var("PYTHON_JIT"),
    "jit_enabled": getattr(getattr(sys, "_jit", None), "is_enabled", lambda: False)(),
    "debug": sysconfig.get_config_var("Py_DEBUG"),
    "cfg_utf8": cfg.decode("utf-8"), "cfg_sha256": hashlib.sha256(cfg).hexdigest(),
    "venv_links": links, "cpu_count": os.cpu_count(),
    "bootstrap_environment": {key: value for key, value in os.environ.items()
        if key.upper().startswith(("UV_", "PYTHON", "PIP_", "COVERAGE", "COV_CORE"))
        or key.upper() == "SOURCE_DATE_EPOCH"}
}))
"""


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def is_location_handoff(name, target):
    if target == "win32":
        return name.upper() in {allowed.upper() for allowed in LOCATION_HANDOFF}
    return name in LOCATION_HANDOFF


def handoff(inherited):
    """Only explicit setup locations cross this boundary, never arbitrary overrides."""
    removed = sorted(
        name for name in inherited if is_location_handoff(name, sys.platform)
    )
    clean = {name: value for name, value in inherited.items() if name not in removed}
    forbidden = sorted(
        name
        for name in clean
        if (
            name.upper().startswith(
                ("UV_", "PYTHON", "PIP_", "PYTEST", "COVERAGE", "COV_CORE")
            )
            or name.upper() in {"SOURCE_DATE_EPOCH", "PIP_CONFIG_FILE"}
        )
    )
    require(not forbidden, f"Unknown ambient overrides: {forbidden}")
    return clean, {"removed_location_variable_names": removed, "values_retained": False}


def fixed_paths(workspace, target):
    workspace = Path(workspace)
    require(target in PUBLISHER, "unsupported native platform")
    require(
        workspace.is_absolute() and ".." not in workspace.parts, "absolute workspace"
    )
    require(workspace.resolve(strict=True) == workspace, "canonical workspace")
    for ancestor in (workspace, *workspace.parents):
        require(
            not ancestor.is_symlink() and not ancestor.is_junction(), "workspace alias"
        )
    if target == "win32":
        require(
            workspace.drive.upper() == "C:", "Windows runtime/source/output must be C:"
        )
    return {
        "install": workspace / "matched-sdk",
        "venv": workspace / "matched-venv",
        "wheels": workspace / "matched-wheels",
        "source": workspace / "package-source",
        "output": workspace / "matched-output",
        "cache": Path(r"D:\matched-reference-cache")
        if target == "win32"
        else workspace / "matched-cache",
        "evidence": workspace / "matched-evidence",
    }


def observe_runtime(observed, found, paths, target):
    """Return receipt associations from the created interpreter, not intended paths."""
    require(observed["platform"] == target, "observed platform")
    require(observed["version_info"] == [3, 13, 15], "observed exact patch")
    require(observed["machine"].lower() in {"arm64", "aarch64"}, "observed native ISA")
    require(
        observed["platform_tag"] == "win-arm64"
        if target == "win32"
        else observed["platform_tag"].startswith("macosx-")
        and observed["platform_tag"].endswith("-arm64"),
        "observed native ABI",
    )
    require(
        observed["gil"] is True
        and not any(
            observed[key]
            for key in ("gil_disabled", "jit_build", "jit_enabled", "debug")
        ),
        "normal GIL/no JIT/debug",
    )
    require(
        observed["optimization"] == 0
        and observed["isolated"] == 1
        and observed["dont_write_bytecode"] is True
        and observed["pycache_prefix"] is None
        and observed["bootstrap_environment"] == {},
        "safe default-optimization probe",
    )
    sdk, venv = Path(observed["base_prefix"]), Path(observed["prefix"])
    require(
        sdk.is_absolute()
        and sdk.resolve(strict=True) == sdk
        and sdk.parent == paths["install"]
        and sdk != venv
        and venv == paths["venv"]
        and venv.resolve(strict=True) == venv,
        "actual private disjoint SDK and venv prefixes",
    )
    expected_name = (
        "cpython-3.13.15-windows-aarch64-none"
        if target == "win32"
        else "cpython-3.13.15-macos-aarch64-none"
    )
    require(sdk.name == expected_name, "normal managed SDK selection")
    cfg = dict(
        line.split(" = ", 1)
        for line in observed["cfg_utf8"].splitlines()
        if " = " in line
    )
    require(cfg.get("include-system-site-packages") == "false", "private unseeded venv")
    if target == "win32":
        require(
            observed["executable"] == str(venv / "Scripts" / "python.exe")
            and observed["base_executable"] == str(sdk / "python.exe")
            and Path(found) == sdk / "python.exe"
            and Path(cfg["home"]) == sdk,
            "actual Windows base/home association",
        )
        base_python = observed["base_executable"]
    else:
        links = observed["venv_links"]
        base_python = links["python"]
        aliases = {
            str(sdk / "bin" / name) for name in ("python", "python3", "python3.13")
        }
        require(
            observed["executable"] == str(venv / "bin" / "python")
            and observed["base_executable"] == str(sdk / "bin" / "python3.13")
            and base_python in aliases
            and found in aliases
            and Path(found).resolve(strict=True)
            == Path(base_python).resolve(strict=True)
            and links["python3"] == links["python3.13"] == "python"
            and Path(cfg["home"]) == sdk / "bin",
            "actual Darwin finite link graph",
        )
        policy = reference.DarwinRuntimeLinks(sdk, venv, base_python, PUBLISHER[target])
        # Full SDK publisher-nine/venv-three graph, regular inputs and compiler
        # preservation are checked by the unchanged core, not waived by this probe.
        reference.runtime_input_hashes([str(sdk), str(venv)], policy)
    return {"sdk_root": str(sdk), "venv_root": str(venv), "base_python": base_python}


class Preparation:
    def __init__(self, evidence, env, seconds=120):
        require(
            type(seconds) in (int, float)
            and math.isfinite(seconds)
            and 0 < seconds <= 120,
            "finite preparation ceiling",
        )
        self.evidence, self.env = Path(evidence), env
        self.deadline = time.monotonic() + seconds
        self.commands = []

    def command(self, label, argv, *, env=None, cap=40):
        remaining = self.deadline - time.monotonic() - 25
        require(remaining > 0, "preparation reserve prevents launch")
        timeout = min(cap, remaining)
        stdout, stderr = (
            self.evidence / f"{label}.{suffix}" for suffix in ("stdout", "stderr")
        )
        launch_env = self.env if env is None else env
        record = {
            "argv": [str(item) for item in argv],
            "cwd": str(self.evidence),
            "timeout_seconds": timeout,
            "cleanup_reserve_seconds": 25,
            "environment_values": {
                name: value
                for name, value in launch_env.items()
                if name.startswith("UV_") or name in {"TEMP", "TMP", "TMPDIR"}
            },
            "environment_scope": "Whitelist only; complete override rejection in memory.",
            "clock_scope": "PREPARATION_METADATA_ONLY_NOT_BUILD_SAMPLES",
            "stdout_path": str(stdout),
            "stderr_path": str(stderr),
        }
        save(self.evidence / f"{label}.command.json", record)
        receipt = owned_process.run_owned(
            record["argv"],
            cwd=self.evidence,
            env=launch_env,
            stdout_path=stdout,
            stderr_path=stderr,
            timeout=timeout,
            native_clock=True,
        )
        record.update(
            owned_receipt=dataclasses.asdict(receipt), succeeded=receipt.succeeded
        )
        for name, path in (("stdout", stdout), ("stderr", stderr)):
            if path.is_file():
                record[name + "_sha256"] = sha(path)
        self.commands.append(record)
        save(self.evidence / f"{label}.result.json", record)
        require(
            receipt.succeeded
            and receipt.actual_process is not None
            and not receipt.liveness,
            f"first failed preparation stops: {label}",
        )
        require(time.monotonic() < self.deadline, "preparation deadline exceeded")
        return stdout.read_text(encoding="utf-8")


def prepare(workspace, uv, inherited=None):
    """Prospective producer only. Caller must independently authorize host allocation."""
    started = time.monotonic()
    require(
        sys.flags.isolated == 1 and sys.dont_write_bytecode, "bootstrap requires -I -B"
    )
    target = sys.platform
    require(reference.source_preflight() == PIN, "unchanged qualified core")
    paths = fixed_paths(workspace, target)
    clean, removed = handoff(os.environ if inherited is None else inherited)
    require(
        all(
            not paths[name].exists()
            for name in ("install", "venv", "wheels", "output", "cache", "evidence")
        ),
        "fresh private preparation roots; no fallback or reuse",
    )
    paths["evidence"].mkdir(mode=0o700)
    save(paths["evidence"] / "setup-location-handoff.json", removed)
    uv = Path(uv)
    identity = reference.qualified_uv_identity(uv, platform=target)
    save(paths["evidence"] / "uv-static-identity.json", identity)
    (paths["evidence"] / "qualified-uv.bin").write_bytes(uv.read_bytes())
    stage_env = dict(
        clean,
        UV_PYTHON_INSTALL_DIR=str(paths["install"]),
        UV_PYTHON_PREFERENCE="only-managed",
        UV_HTTP_RETRIES="0",
        UV_HTTP_TIMEOUT="20",
    )
    preparation = Preparation(
        paths["evidence"], clean, 120 - (time.monotonic() - started)
    )
    try:
        install = [
            str(uv),
            "python",
            "install",
            "3.13.15",
            "--no-bin",
            "--no-config",
            "--no-progress",
        ]
        if target == "win32":
            install.append("--no-registry")
        preparation.command("install", install, env=stage_env, cap=50)
        found = preparation.command(
            "find",
            [
                str(uv),
                "python",
                "find",
                "3.13.15",
                "--no-python-downloads",
                "--no-project",
                "--no-config",
                "--no-progress",
            ],
            env=stage_env,
            cap=10,
        ).strip()
        require(
            "\n" not in found
            and Path(found).is_absolute()
            and Path(found).is_relative_to(paths["install"])
            and Path(found).is_file(),
            "observed private find stdout",
        )
        preparation.command(
            "venv",
            [
                str(uv),
                "venv",
                str(paths["venv"]),
                "--python",
                "3.13.15",
                "--no-python-downloads",
                "--no-config",
                "--no-progress",
            ],
            env=stage_env,
            cap=20,
        )
        python = paths["venv"] / ("Scripts" if target == "win32" else "bin")
        python /= "python.exe" if target == "win32" else "python"
        observed = json.loads(
            preparation.command(
                "probe",
                [str(python), "-I", "-B", "-c", PROBE],
                cap=10,
            )
        )
        associations = observe_runtime(observed, found, paths, target)
        save(paths["evidence"] / "runtime-observed.json", observed)
        (paths["evidence"] / "new-pyvenv.cfg").write_bytes(
            observed["cfg_utf8"].encode()
        )
        backend = json.loads(
            preparation.command(
                "backend",
                [
                    str(python),
                    "-I",
                    "-B",
                    str(HERE / "prepare_backend.py"),
                    "--output",
                    str(paths["wheels"]),
                ],
                cap=40,
            )
        )
        require(
            backend["bytes"] == 199650
            and backend["sha256"] == reference.shared.WHEEL_SHA,
            "exact backend bytes",
        )
        wheel = paths["wheels"] / reference.shared.WHEEL
        require(
            list(paths["wheels"].iterdir()) == [wheel]
            and wheel.stat().st_size == 199650
            and sha(wheel) == reference.shared.WHEEL_SHA,
            "actual pinned unseeded backend bytes",
        )
        require(time.monotonic() < preparation.deadline, "preparation total ceiling")
        save(paths["evidence"] / "commands.json", preparation.commands)
        receipt = {
            "kind": "observed-uv-venv-creation",
            "uv_version": identity["qualified_version"],
            "python_request": preparation.commands[2]["argv"][4],
            "venv_requested_python_argument": preparation.commands[2]["argv"][4],
            "variant": "normal",
            **associations,
            "publisher_sha256": PUBLISHER[target],
            "publisher_sdk_build_expectation": "20260929",
            "publisher_digest_basis": "CATALOG_EXPECTATION_ONLY",
            "publisher_archive_freshly_verified": False,
            "find_actual_stdout": (paths["evidence"] / "find.stdout").read_text(),
            "probe_bytecode_policy": "-I -B; optimization=0 observed; default writes not claimed",
            "native_coordinator_or_WA_WB_prior_success": False,
            "elapsed_seconds": time.monotonic() - started,
            "cpu_identity": {"machine": platform.machine(), "logical": os.cpu_count()},
            "evidence_sha256": {
                path.name: sha(path)
                for path in sorted(paths["evidence"].iterdir())
                if path.is_file()
            },
        }
        save(paths["evidence"] / "creation-receipt.json", receipt)
        return receipt
    except BaseException as error:
        save(
            paths["evidence"] / "preparation-failure.json",
            {
                "type": type(error).__name__,
                "error": str(error),
                "elapsed_seconds": time.monotonic() - started,
                "commands": preparation.commands,
                "measurements_started": False,
            },
        )
        raise
