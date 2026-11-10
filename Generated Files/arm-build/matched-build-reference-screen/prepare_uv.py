"""Attest the pinned official wheel's bundled native executable before timing."""

import base64
import hashlib
import importlib
import importlib.metadata
import json
import platform
import struct
import subprocess
import sys
from pathlib import Path


def attest(executable):
    if not executable.is_absolute() or not executable.is_file():
        raise RuntimeError("absolute existing native uv executable required")
    data = executable.read_bytes()
    if sys.platform == "win32":
        offset = struct.unpack_from("<I", data, 0x3C)[0]
        if data[:2] != b"MZ" or struct.unpack_from("<H", data, offset + 4)[0] != 0xAA64:
            raise RuntimeError("uv must be native ARM64 PE")
    elif sys.platform == "darwin":
        slices = subprocess.run(
            ["/usr/bin/lipo", "-archs", str(executable)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()
        if "arm64" not in slices or platform.machine().lower() != "arm64":
            raise RuntimeError("uv must execute on native macOS ARM64")
    else:
        raise RuntimeError("paired uv experiment supports Windows/macOS ARM64 only")
    version = subprocess.run(
        [str(executable), "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not version.startswith("uv 0.13.6 "):
        raise RuntimeError("uv 0.13.6 required")
    return {
        "executable": str(executable),
        "version": version,
        "sha256": hashlib.sha256(data).hexdigest(),
        "native_arm64": True,
    }


def installed_identity():
    distribution = importlib.metadata.distribution("uv")
    if distribution.version != "0.13.6":
        raise RuntimeError("pinned official uv wheel required")
    uv = importlib.import_module("uv")
    executable = Path(uv.find_uv_bin()).absolute()
    result = attest(executable)
    bundled = [
        entry
        for entry in distribution.files or ()
        if entry.name in {"uv", "uv.exe"}
        and Path(distribution.locate_file(entry)).resolve() == executable.resolve()
    ]
    expected = (
        base64.urlsafe_b64encode(bytes.fromhex(result["sha256"])).rstrip(b"=").decode()
    )
    if (
        len(bundled) != 1
        or bundled[0].hash is None
        or bundled[0].hash.mode != "sha256"
        or bundled[0].hash.value != expected
    ):
        raise RuntimeError("uv executable must match installed distribution RECORD")
    result["distribution_version"] = distribution.version
    result["distribution_record_sha256"] = expected
    return result


if __name__ == "__main__":
    Path(sys.argv[1]).write_text(
        json.dumps(installed_identity(), indent=2) + "\n", encoding="utf-8"
    )
