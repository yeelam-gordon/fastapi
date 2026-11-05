"""Use the tested native PE / Mach-O checks without changing CPU affinity."""

import platform
import struct
import subprocess
import sys


def native_machine(path):
    assert platform.machine().lower() in {"arm64", "aarch64"}
    if sys.platform == "win32":
        data = path.read_bytes()
        offset = struct.unpack_from("<I", data, 0x3C)[0]
        assert data[:2] == b"MZ"
        assert struct.unpack_from("<H", data, offset + 4)[0] == 0xAA64
        return "PE-ARM64"
    assert sys.platform == "darwin"
    slices = subprocess.run(
        ["/usr/bin/lipo", "-archs", str(path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.split()
    assert "arm64" in slices
    return "MachO-arm64"
