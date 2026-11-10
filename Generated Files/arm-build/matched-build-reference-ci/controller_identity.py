"""In-process metadata-controller identity, never startup ownership proof."""

import platform
import re
import sys
import sysconfig
from pathlib import Path


def validate(observed, directory, version):
    if not re.fullmatch(r"3\.13\.(0|[1-9][0-9]*)", version):
        raise ValueError("stable cached Python 3.13 patch required")
    expected = [int(value) for value in version.split(".")]
    if (
        observed["version_info"] != expected
        or observed["releaselevel"] != "final"
        or observed["platform"] != "win32"
        or observed["abi"] != "win-arm64"
        or observed["machine"].lower() not in {"arm64", "aarch64"}
        or not observed["gil"]
        or any(
            observed[key]
            for key in ("gil_disabled", "jit", "jit_enabled", "debug", "optimization")
        )
        or observed["isolated"] != 1
        or observed["dont_write_bytecode"] is not True
        or observed["pycache_prefix"] is not None
        or observed["no_site"] != 1
    ):
        raise ValueError("normal native cached metadata launcher required")
    root = Path(directory)
    if (
        Path(observed["prefix"]) != root
        or Path(observed["base_prefix"]) != root
        or Path(observed["executable"]) != root / "python.exe"
    ):
        raise ValueError("cached launcher prefix/executable association")
    return observed


def observe_self(directory, version):
    observed = {
        "role": "METADATA_CONTROLLER_ONLY_NOT_MEASURED_SDK",
        "version": sys.version,
        "version_info": list(sys.version_info[:3]),
        "releaselevel": sys.version_info.releaselevel,
        "platform": sys.platform,
        "abi": sysconfig.get_platform(),
        "machine": platform.machine(),
        "executable": sys.executable,
        "prefix": sys.prefix,
        "base_prefix": sys.base_prefix,
        "gil": getattr(sys, "_is_gil_enabled", lambda: False)(),
        "gil_disabled": sysconfig.get_config_var("Py_GIL_DISABLED"),
        "jit": sysconfig.get_config_var("PYTHON_JIT"),
        "jit_enabled": getattr(
            getattr(sys, "_jit", None), "is_enabled", lambda: False
        )(),
        "debug": sysconfig.get_config_var("Py_DEBUG"),
        "optimization": sys.flags.optimize,
        "isolated": sys.flags.isolated,
        "dont_write_bytecode": sys.dont_write_bytecode,
        "pycache_prefix": sys.pycache_prefix,
        "no_site": sys.flags.no_site,
        "startup_ownership": "TRUSTED_BASELINE_UNOWNED_UNOBSERVED",
    }
    return validate(observed, directory, version)
