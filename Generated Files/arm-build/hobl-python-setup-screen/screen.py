"""One bounded setup-only comparison; no project dependencies or qualification."""

import ctypes
import hashlib
import json
import os
import struct
import sys
import time
from dataclasses import asdict
from pathlib import Path

GUARD_SHA = "45d6db4f6452c4f7116ca23c6e2aa74cda90a15548bd5c9bb3b3574973ef458e"


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def require(value, message):
    if not value:
        raise RuntimeError(message)


def native_pe(path):
    data = Path(path).read_bytes()
    offset = struct.unpack_from("<I", data, 0x3C)[0]
    require(data[:2] == b"MZ" and data[offset:offset + 4] == b"PE\0\0"
            and struct.unpack_from("<H", data, offset + 4)[0] == 0xAA64, "ARM64 PE required")


def owned_candidate(raw, install):
    path = Path(raw.strip()).resolve(strict=True)
    require(path.is_file() and path.is_relative_to(install.resolve()), "candidate escaped owned root")
    return path


def identity():
    import asyncio
    import platform
    import sqlite3
    import ssl
    import sysconfig
    import urllib.request

    native_pe(sys.executable)
    process, native = ctypes.c_ushort(), ctypes.c_ushort()
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.GetCurrentProcess.restype = ctypes.c_void_p
    api.IsWow64Process2.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    require(api.IsWow64Process2(api.GetCurrentProcess(), ctypes.byref(process), ctypes.byref(native)),
            "process architecture query failed")
    require(process.value == 0 and native.value == 0xAA64 and struct.calcsize("P") == 8,
            "actual process must be native ARM64")
    require(sys.implementation.name == "cpython" and sys.version_info[:3] == (3, 13, 15),
            "exact CPython 3.13.15 required")
    require(not sysconfig.get_config_var("Py_GIL_DISABLED") and sys._is_gil_enabled()
            and not sysconfig.get_config_var("Py_DEBUG") and not hasattr(sys, "gettotalrefcount"),
            "normal nondebug GIL required")
    async def basic():
        await asyncio.sleep(0)
        return "ok"
    require(asyncio.run(basic()) == "ok", "asyncio loop failed")
    with sqlite3.connect(":memory:") as db:
        require(db.execute("select 1").fetchone() == (1,), "sqlite failed")
    with urllib.request.urlopen("https://pypi.org/pypi/pip/json", timeout=20,
                                context=ssl.create_default_context()) as response:
        require(response.status == 200 and json.load(response)["info"]["name"] == "pip",
                "default TLS public PyPI JSON failed")
    print(json.dumps(dict(python=sys.executable, version=sys.version, machine=platform.machine(),
                         process_machine=process.value, native_machine=native.value,
                         normal_gil=True, nondebug=True, asyncio="ok", tls_pypi="ok",
                         openssl=ssl.OPENSSL_VERSION, sqlite=sqlite3.sqlite_version)))


def run(root, uv):
    guardian = Path(__file__).parent.parent / "hobl-complete-ci" / "owned_process.py"
    require(hashlib.sha256(guardian.read_bytes()).hexdigest() == GUARD_SHA, "original guardian required")
    sys.path.insert(0, str(guardian.parent))
    from owned_process import run_owned

    env = dict(os.environ, UV_PYTHON_INSTALL_DIR=str(root / "python"),
               UV_CACHE_DIR=str(root / "cache"), UV_HTTP_RETRIES="0", UV_HTTP_TIMEOUT="20")

    def invoke(label, argv, timeout=30):
        start = time.perf_counter_ns()
        receipt = run_owned(argv, cwd=root, env=env, stdout_path=root / f"{label}.stdout",
                            stderr_path=root / f"{label}.stderr", timeout=timeout, native_clock=True)
        save(root / f"{label}.json", dict(receipt=asdict(receipt), argv=list(map(str, argv)),
                                        invocation_wall_ns=time.perf_counter_ns() - start))
        require(receipt.succeeded, f"{label} failed; raw receipt preserved")
        return (root / f"{label}.stdout").read_text(encoding="utf-8").strip()

    initial = json.loads((root / "initial-cache.json").read_text(encoding="utf-8-sig"))
    if initial["initially_cached"]:
        save(root / "result.json", dict(status="gap not reproduced,no change",
                                       scope="SCREEN/setup-only", candidate_skipped=True))
    stock = json.loads(invoke("stock-identity", [sys.executable, "-I", "-B", __file__, "identity"]))
    if initial["initially_cached"]:
        save(root / "result.json", dict(status="gap not reproduced,no change", stock=stock,
                                       scope="SCREEN/setup-only", candidate_skipped=True))
        return
    native_pe(uv)
    version = invoke("uv-version", [uv, "--version"])
    require(version.split()[:2] == ["uv", "0.13.6"], "pinned native uv required")
    (root / "python").mkdir()
    (root / "cache").mkdir()
    invoke("install", [uv, "python", "install", "3.13.15", "--no-bin", "--no-registry",
                       "--no-config", "--no-progress"], timeout=60)
    found = invoke("find", [uv, "python", "find", "3.13.15", "--managed-python",
                           "--no-python-downloads", "--no-project", "--no-config", "--no-progress"])
    candidate = owned_candidate(found, root / "python")
    managed = json.loads(invoke("candidate-identity", [str(candidate), "-I", "-B", __file__, "identity"]))
    save(root / "result.json", dict(scope="SCREEN/setup-only", status="identities passed",
                                   stock=stock, candidate=managed, uv=version,
                                   qualification="basic stdlib only; distribution and bundled libraries differ"))


if __name__ == "__main__":
    if sys.argv[1] == "identity":
        identity()
    else:
        run(Path(sys.argv[2]).resolve(), sys.argv[3])
