"""Fail-closed portable guards; no workload or platform mutation on import."""

import gzip
import hashlib
import os
import platform
import struct
import subprocess
import sys
from pathlib import Path

REV = "864b569cf8453654fc3bc2c64108c0f644e2918c"
OWNER = "c89fd8ca549ed54c79a0db7ece3ba8bb256be148"
SCHEDULE = ("AB", "BA", "AB", "BA", "AB", "BA")
WHEEL = "pdm_backend-2.5.0-py3-none-any.whl"
STORAGE_HASH = "6a508d629d16e07e17b8d4b464b39884da5e5ed31fac068d5cee6870383fa649"
WHEEL_HASHES = {
    "A": "5b8746b567a16a1fd506ce66ee28e89d46374526f52238aa1b96cc2c08245c63",
    "B": "98048fc49ebd86884266e0b572d7ec5f7b1c571a206aa9cbecbac8c575433d28",
}
MODULE_HASHES = {
    "A": "f62cdc17df1b922d03e1ef8103ce1c0109c94966931d8909f8543b9243f41396",
    "B": "50f0bad699bda95cfe58901f81f1dc30782a46d693efacbeb4ca64c58b434bb4",
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def candidate_bytes(path):
    require(
        path.stat().st_size < 200_000 and sha(path) == STORAGE_HASH,
        "Frozen candidate storage identity/cap changed",
    )
    data = gzip.decompress(path.read_bytes())
    require(
        hashlib.sha256(data).hexdigest() == WHEEL_HASHES["B"],
        "Unwrapped candidate wheel identity changed",
    )
    return data


def slices(data):
    """Return actual PE/Mach-O architectures, accepting native universal2."""
    if data[:2] == b"MZ":
        offset = struct.unpack_from("<I", data, 60)[0]
        require(data[offset : offset + 4] == b"PE\0\0", "Invalid PE")
        return {struct.unpack_from("<H", data, offset + 4)[0]}
    if data[:4] in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe"):
        return {struct.unpack_from("<I", data, 4)[0]}
    if data[:4] in (b"\xfe\xed\xfa\xcf", b"\xfe\xed\xfa\xce"):
        return {struct.unpack_from(">I", data, 4)[0]}
    if data[:4] in (b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"):
        count = struct.unpack_from(">I", data, 4)[0]
        stride = 32 if data[:4] == b"\xca\xfe\xba\xbf" else 20
        return {struct.unpack_from(">I", data, 8 + i * stride)[0] for i in range(count)}
    raise RuntimeError("Not a supported native binary")


def architecture_ok(system, machine, bits, architectures, translated=0):
    require(
        bits == 64 and machine.lower() in ("arm64", "aarch64"), "Not ARM64 execution"
    )
    if system == "Windows":
        require(architectures == {0xAA64}, "Not native Windows ARM64 PE")
    elif system == "Darwin":
        require(not translated and 0x100000C in architectures, "Rosetta/non-ARM Mach-O")
    else:
        raise RuntimeError("Only native Windows/macOS ARM are supported")


def binary_guard(path, system=None):
    system = system or platform.system()
    architectures = slices(Path(path).resolve().read_bytes())
    required = 0xAA64 if system == "Windows" else 0x100000C
    require(required in architectures, "Interpreter/extension lacks native ARM64 slice")
    if system == "Windows":
        require(architectures == {required}, "Mixed/non-native PE")
    return sorted(architectures)


def native_guard():
    system = platform.system()
    translated = 0
    if system == "Darwin":
        probe = subprocess.run(
            ["sysctl", "-in", "sysctl.proc_translated"], capture_output=True, text=True
        )
        require(
            probe.returncode == 0 and probe.stdout.strip() in ("", "0", "1"),
            "Cannot establish Rosetta state",
        )
        translated = int(probe.stdout.strip() or "0")
    architectures = binary_guard(sys.executable, system)
    architecture_ok(
        system,
        platform.machine(),
        struct.calcsize("P") * 8,
        set(architectures),
        translated,
    )
    require(platform.python_version() == "3.12.10", "Require exact CPython 3.12.10")
    # sysconfig is deliberately imported only on a real, initialized platform.
    import sysconfig

    return {
        "version": sys.version,
        "compiler": platform.python_compiler(),
        "machine": platform.machine(),
        "platform": platform.platform(),
        "sysconfig_platform": sysconfig.get_platform(),
        "translated": translated,
        "slices": architectures,
        "executable_sha256": sha(sys.executable),
        "cpu_count": os.cpu_count(),
    }


def environment(root, inherited=None):
    inherited = os.environ if inherited is None else inherited
    prefixes = (
        "PIP_",
        "UV_",
        "PYTHON",
        "COVERAGE_",
        "PYTEST_",
        "FASTAPI_",
        "SENTRY_",
        "HOBL_CPU_",
    )
    # Never carry deployment credentials, index overrides, user Python hooks or
    # profiling settings into workloads. No environment dump is persisted.
    env = {
        k: v
        for k, v in inherited.items()
        if not k.upper().startswith(prefixes)
        and not any(
            word in k.upper() for word in ("TOKEN", "SECRET", "PASSWORD", "AUTH")
        )
        and k not in ("CONTEXT", "SOURCE_DATE_EPOCH")
    }
    for key, subdir in (
        ("HOME", "home"),
        ("USERPROFILE", "home"),
        ("APPDATA", "config"),
        ("LOCALAPPDATA", "cache"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_CACHE_HOME", "cache"),
        ("TEMP", "scratch"),
        ("TMP", "scratch"),
        ("TMPDIR", "scratch"),
    ):
        dest = root / subdir
        dest.mkdir(parents=True, exist_ok=True)
        env[key] = str(dest)
    env.update(
        PIP_CONFIG_FILE=os.devnull,
        PIP_INDEX_URL="https://pypi.org/simple",
        PIP_CACHE_DIR=str(root / "cache" / "pip"),
        PIP_RETRIES="0",
        PIP_TIMEOUT="30",
        PIP_DISABLE_PIP_VERSION_CHECK="1",
        PIP_NO_INPUT="1",
        PYTHONIOENCODING="utf8",
    )
    return env


def forbid_cpu_hook(env):
    require(
        not any(key.upper().startswith("HOBL_CPU_") for key in env),
        "SELF receipt variables forbidden outside instrumented correctness/smoke",
    )
    hook = Path(__file__).resolve().parent / "cpu-hook"
    require(
        not any(
            Path(entry).resolve() == hook.resolve()
            for entry in env.get("PYTHONPATH", "").split(os.pathsep)
            if entry
        ),
        "SELF startup hook forbidden outside instrumented correctness/smoke",
    )


def tree(root):
    return {
        p.relative_to(root).as_posix(): {
            "sha256": sha(p),
            "mtime_ns": p.stat().st_mtime_ns,
            "mode": p.stat().st_mode,
        }
        for p in sorted(root.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }


def payload_tree(root):
    return {k: v["sha256"] for k, v in tree(root).items()}


def cli_command(python):
    return [
        str(python),
        "-m",
        "coverage",
        "run",
        "-m",
        "fastapi",
        "dev",
        "non_existent_file.py",
    ]


def cli_valid(code, stdout, stderr):
    require(code == 1, "Missing-file CLI must exit exactly 1")
    require(b"Path does not exist non_existent_file.py" in stdout, "Missing CLI oracle")
    require(not stderr, "Unexpected CLI stderr")


def raw_equal(a, b):
    require(a == b, "Raw stdout/stderr differ (no text/EOL normalization)")


def sequence():
    return [("warmup-A", "A", 0), ("warmup-B", "B", 0)] + [
        (f"pair-{i}-{arm}", arm, i)
        for i, order in enumerate(SCHEDULE, 1)
        for arm in order
    ]
