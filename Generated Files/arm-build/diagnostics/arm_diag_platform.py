"""Analysis-only platform receipts. Hook imports require the standard library only."""

import os
import sys
import time


def _metric(value=None, *, unit, source, aggregation, reason=None, **extra):
    return {
        "status": "unavailable" if value is None else "measured",
        "value": value,
        "unit": unit,
        "scope": "self_all_threads",
        "source": source,
        "aggregation": aggregation,
        **({"reason": reason} if reason else {}),
        **extra,
    }


def _windows_process():
    import ctypes as c
    from ctypes import wintypes as w

    class Memory(c.Structure):
        _fields_ = [
            ("cb", w.DWORD),
            ("PageFaultCount", w.DWORD),
            *[
                (name, c.c_size_t)
                for name in (
                    "PeakWorkingSetSize",
                    "WorkingSetSize",
                    "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage",
                    "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage",
                    "PagefileUsage",
                    "PeakPagefileUsage",
                )
            ],
        ]

    class IO(c.Structure):
        _fields_ = [
            (name, c.c_ulonglong)
            for name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = w.HANDLE
    handle = kernel.GetCurrentProcess()
    memory = Memory()
    memory.cb = c.sizeof(memory)
    get_memory = c.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
    get_memory.argtypes = [w.HANDLE, c.POINTER(Memory), w.DWORD]
    get_memory.restype = w.BOOL
    mem = {}
    if get_memory(handle, c.byref(memory), memory.cb):
        for key, field, aggregation in (
            ("rss", "WorkingSetSize", "gauge"),
            ("peak_rss", "PeakWorkingSetSize", "lifetime_peak"),
        ):
            mem[key] = _metric(
                getattr(memory, field),
                unit="bytes",
                source="GetProcessMemoryInfo",
                aggregation=aggregation,
                semantics="resident working set, not private bytes",
            )
    else:
        for key in ("rss", "peak_rss"):
            mem[key] = _metric(
                unit="bytes",
                source="GetProcessMemoryInfo",
                aggregation="gauge" if key == "rss" else "lifetime_peak",
                reason=f"WinError {c.get_last_error()}",
            )
    get_io = kernel.GetProcessIoCounters
    get_io.argtypes = [w.HANDLE, c.POINTER(IO)]
    get_io.restype = w.BOOL
    counters = IO()
    ok = get_io(handle, c.byref(counters))
    error = None if ok else f"WinError {c.get_last_error()}"
    io = {}
    for field, _ in IO._fields_:
        io[field] = _metric(
            getattr(counters, field) if ok else None,
            unit="bytes" if "Transfer" in field else "operations",
            source="GetProcessIoCounters",
            aggregation="lifetime_cumulative",
            reason=error,
            semantics=(
                "Windows process I/O accounting, including file/device/other I/O; "
                "not physical disk activity, latency, or Darwin block I/O"
            ),
        )
    return mem, io


def _posix_process():
    import resource

    usage = resource.getrusage(resource.RUSAGE_SELF)
    memory = {
        "rss": _metric(
            unit="bytes",
            source="resource",
            aggregation="gauge",
            reason="getrusage does not expose current resident bytes",
        ),
        "peak_rss": _metric(
            unit="bytes",
            source="resource.ru_maxrss",
            aggregation="lifetime_peak",
            reason="native ru_maxrss byte conversion not verified on this runner",
        ),
        "peak_rss_raw": _metric(
            usage.ru_maxrss,
            unit="unverified_native_unit",
            source="resource.ru_maxrss",
            aggregation="lifetime_peak",
            semantics="raw native high-water mark; never subtract snapshots",
        ),
    }
    io = {
        field: _metric(
            getattr(usage, field),
            unit="block_io_operations",
            source="resource.getrusage(RUSAGE_SELF)",
            aggregation="lifetime_cumulative",
            semantics=(
                "filesystem block input/output accounting; cache semantics are "
                "OS-specific; not Windows logical read/write counts or bytes"
            ),
        )
        for field in ("ru_inblock", "ru_oublock")
    }
    return memory, io


def process_snapshot() -> dict:
    """Self-only lifetime counters; snapshot overhead is inside its own window."""
    started = time.monotonic_ns()
    cpu = {
        "status": "unavailable",
        "user_seconds": None,
        "kernel_seconds": None,
        "unit": "seconds",
        "scope": "self_all_threads",
        "aggregation": "lifetime_cumulative",
        "source": "os.times",
    }
    try:
        times = os.times()
        cpu.update(
            status="measured", user_seconds=times.user, kernel_seconds=times.system
        )
    except (OSError, AttributeError) as exc:
        cpu["reason"] = type(exc).__name__
    try:
        memory, io = _windows_process() if sys.platform == "win32" else _posix_process()
    except (OSError, ImportError, AttributeError) as exc:
        memory = {
            key: _metric(
                unit="bytes",
                source="native",
                aggregation=aggregation,
                reason=type(exc).__name__,
            )
            for key, aggregation in (("rss", "gauge"), ("peak_rss", "lifetime_peak"))
        }
        io = {"status": "unavailable", "value": None, "reason": type(exc).__name__}
    ended = time.monotonic_ns()
    return {
        "schema_version": 1,
        "performance_eligible": False,
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "scope": "self_all_threads",
        "started_monotonic_ns": started,
        "ended_monotonic_ns": ended,
        "cost_ns": ended - started,
        "window": "sequential, non-atomic counters; collector cost included",
        "family_coverage": "none; no child or polling-based family CPU claim",
        "cpu": cpu,
        "memory": memory,
        "io": io,
    }


# Named fields only. PATH and authentication/checkout values are never retained.
_ENV_FIELDS = (
    "CI",
    "GITHUB_ACTIONS",
    "GITHUB_RUN_ID",
    "GITHUB_RUN_ATTEMPT",
    "GITHUB_JOB",
    "GITHUB_WORKFLOW",
    "RUNNER_OS",
    "RUNNER_ARCH",
    "RUNNER_ENVIRONMENT",
    "ImageOS",
    "ImageVersion",
    "PYTHONHASHSEED",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONPYCACHEPREFIX",
    "SOURCE_DATE_EPOCH",
    "UV_CACHE_DIR",
    "UV_OFFLINE",
    "UV_NO_CACHE",
    "PIP_CACHE_DIR",
    "PDM_CACHE_DIR",
    "UV_LOG_CONTEXT",
)


def _safe(value):
    import re

    text = str(value)
    if re.search(
        r"(?i)(bearer\s|(?:token|password|secret|authorization)\s*[=:]|"
        r"gh[pousr]_|github_pat_|https?://[^/\s]*@)",
        text,
    ) or any(ord(char) < 32 for char in text):
        return "<REDACTED>"
    home = os.path.expanduser("~")
    return text.replace(home, "<HOME>")[:4096] if home else text[:4096]


def _unknown(reason):
    return {"status": "unavailable", "value": None, "reason": reason}


def _observed(value, source):
    return {"status": "measured", "value": value, "source": source}


def _probe(argv):
    import subprocess

    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            timeout=5,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        return {
            "status": "measured" if result.returncode == 0 else "unavailable",
            "returncode": result.returncode,
            "stdout": result.stdout.decode("utf-8", errors="replace")[:32768],
            "reason": None if result.returncode == 0 else "command returned nonzero",
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _unknown(type(exc).__name__)


def _architectures(path):
    import struct

    with open(path, "rb") as stream:
        header = stream.read(4096)
        if header[:2] == b"MZ" and len(header) >= 64:
            offset = struct.unpack_from("<I", header, 60)[0]
            stream.seek(offset)
            pe = stream.read(6)
            if pe[:4] == b"PE\0\0":
                machine = struct.unpack_from("<H", pe, 4)[0]
                return [
                    {
                        "machine": hex(machine),
                        "name": {
                            0xAA64: "arm64",
                            0x8664: "x86_64",
                            0x14C: "x86",
                            0xA641: "arm64ec",
                            0xA64E: "arm64x",
                        }.get(machine, "unknown"),
                    }
                ]
        magic = header[:4]
        endian = {
            b"\xcf\xfa\xed\xfe": "<",
            b"\xce\xfa\xed\xfe": "<",
            b"\xfe\xed\xfa\xcf": ">",
            b"\xfe\xed\xfa\xce": ">",
        }.get(magic)
        if endian and len(header) >= 8:
            cpus = [struct.unpack_from(endian + "I", header, 4)[0]]
        elif magic in (b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf") and len(header) >= 8:
            count = struct.unpack_from(">I", header, 4)[0]
            width = 32 if magic[-1] == 0xBF else 20
            if count > 64 or 8 + count * width > len(header):
                raise ValueError("invalid fat Mach-O header")
            cpus = [
                struct.unpack_from(">I", header, 8 + i * width)[0] for i in range(count)
            ]
        else:
            return None
        return [
            {
                "machine": hex(cpu),
                "name": {
                    0x100000C: "arm64",
                    0x1000007: "x86_64",
                    7: "x86",
                }.get(cpu, "unknown"),
            }
            for cpu in cpus
        ]


def _binary(path):
    import hashlib
    from pathlib import Path

    try:
        resolved = Path(path).resolve(strict=True)
        digest = hashlib.sha256()
        with resolved.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        architecture = _architectures(resolved)
        return {
            "status": "measured",
            "path": _safe(path),
            "resolved_path": _safe(resolved),
            "path_redaction": "home prefix only",
            "sha256": digest.hexdigest(),
            "size_bytes": resolved.stat().st_size,
            "architecture": _observed(architecture, "binary header")
            if architecture
            else _unknown("not a supported PE/Mach-O binary"),
            "selected_runtime_slice": _unknown(
                "file architecture is not execution proof"
            ),
        }
    except (OSError, ValueError) as exc:
        return _unknown(type(exc).__name__)


def _filesystem(path):
    from pathlib import Path

    requested = Path(path).absolute()
    existing = requested
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    result = {
        "requested_path": _safe(requested),
        "resolved_path": _safe(requested.resolve()),
        "exists": requested.exists(),
        "probed_existing_ancestor": _safe(existing),
        "path_redaction": "home prefix only",
        "storage_device_class": _unknown("not exposed by filesystem identity"),
    }
    try:
        if sys.platform == "win32":
            import ctypes as c
            from ctypes import wintypes as w

            kernel = c.WinDLL("kernel32", use_last_error=True)
            volume = c.create_unicode_buffer(32768)
            get_path = kernel.GetVolumePathNameW
            get_path.argtypes = [w.LPCWSTR, w.LPWSTR, w.DWORD]
            get_path.restype = w.BOOL
            if not get_path(str(existing), volume, len(volume)):
                raise OSError("GetVolumePathNameW")
            fs = c.create_unicode_buffer(256)
            get_info = kernel.GetVolumeInformationW
            get_info.argtypes = [
                w.LPCWSTR,
                w.LPWSTR,
                w.DWORD,
                c.POINTER(w.DWORD),
                c.POINTER(w.DWORD),
                c.POINTER(w.DWORD),
                w.LPWSTR,
                w.DWORD,
            ]
            get_info.restype = w.BOOL
            if not get_info(volume.value, None, 0, None, None, None, fs, len(fs)):
                raise OSError("GetVolumeInformationW")
            result.update(
                status="measured", filesystem=fs.value, mount=_safe(volume.value)
            )
        elif sys.platform == "darwin":
            import plistlib

            probe = _probe(["/usr/sbin/diskutil", "info", "-plist", str(existing)])
            if probe["status"] != "measured":
                raise OSError("diskutil unavailable for actual path")
            data = plistlib.loads(probe["stdout"].encode())
            result.update(
                status="measured",
                filesystem=data.get("FilesystemType"),
                mount=_safe(data.get("MountPoint", "")) or None,
            )
            if not result["filesystem"]:
                raise ValueError("filesystem type absent")
        else:
            result.update(_unknown("filesystem type query not implemented for this OS"))
    except (OSError, ValueError) as exc:
        result.update(_unknown(type(exc).__name__))
    return result


def _hardware():
    import platform

    result = {
        "logical_cores": _observed(os.cpu_count(), "os.cpu_count")
        if os.cpu_count()
        else _unknown("OS did not report CPU count"),
        "physical_cores": _unknown("no native physical-core receipt"),
        "cpu_model": _unknown("native CPU identity unavailable"),
        "ram_bytes": _unknown("native RAM identity unavailable"),
        "process_machine": _observed(platform.machine(), "platform.machine"),
        "virtualization": _unknown("not established by model string"),
        "power_frequency_contention": _unknown("not collected"),
    }
    if sys.platform == "win32":
        try:
            import ctypes as c
            import winreg
            from ctypes import wintypes as w

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            ) as key:
                model = winreg.QueryValueEx(key, "ProcessorNameString")[0]
            result["cpu_model"] = _observed(_safe(model.strip()), "Windows registry")

            class MemoryStatus(c.Structure):
                _fields_ = [("length", w.DWORD), ("load", w.DWORD)] + [
                    (name, c.c_ulonglong)
                    for name in (
                        "physical",
                        "available",
                        "pagefile",
                        "available_pagefile",
                        "virtual",
                        "available_virtual",
                        "extended",
                    )
                ]

            status = MemoryStatus()
            status.length = c.sizeof(status)
            get_status = c.WinDLL("kernel32", use_last_error=True).GlobalMemoryStatusEx
            get_status.argtypes = [c.POINTER(MemoryStatus)]
            get_status.restype = w.BOOL
            if get_status(c.byref(status)):
                result["ram_bytes"] = _observed(status.physical, "GlobalMemoryStatusEx")
        except (OSError, ImportError):
            pass
    elif sys.platform == "darwin":
        for name, field, numeric in (
            ("machdep.cpu.brand_string", "cpu_model", False),
            ("hw.memsize", "ram_bytes", True),
            ("hw.physicalcpu", "physical_cores", True),
        ):
            probe = _probe(["/usr/sbin/sysctl", "-n", name])
            if probe["status"] == "measured":
                value = probe["stdout"].strip()
                if not numeric or value.isdecimal():
                    result[field] = _observed(
                        int(value) if numeric else _safe(value), name
                    )
    try:
        import psutil

        result["controller_psutil"] = _observed(
            psutil.__version__, "lazy inventory import"
        )
        physical = psutil.cpu_count(logical=False)
        if physical is not None:
            result["physical_cores"] = _observed(physical, "psutil.cpu_count")
    except (ImportError, OSError, AttributeError):
        result["controller_psutil"] = _unknown("optional controller psutil unavailable")
    return result


def _action_inventory():
    import json
    import ntpath
    import re
    from pathlib import Path

    path = os.environ.get("ARM_DIAGNOSTIC_ACTION_JSON")
    if not path:
        return _unknown("separate Actions Node receipt not supplied")
    try:
        file = Path(path)
        if file.stat().st_size > 65536:
            raise ValueError("receipt exceeds limit")
        data = json.loads(file.read_text(encoding="utf-8"))
        schema = "arm-analysis-action-runtime-v1"
        if not isinstance(data, dict) or data.get("schema") != schema:
            return _unknown("missing or unsupported action runtime schema")
        node, host = data.get("node"), data.get("host")
        if not isinstance(node, dict) or not isinstance(host, dict):
            return _unknown(
                "action runtime node/host identity objects missing or invalid"
            )
        checks = {
            "node.version": (
                node.get("version"),
                lambda value: re.fullmatch(
                    r"v\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", value
                ),
            ),
            "node.architecture": (
                node.get("architecture"),
                lambda value: (
                    value
                    in {
                        "arm",
                        "arm64",
                        "ia32",
                        "loong64",
                        "mips",
                        "mipsel",
                        "ppc",
                        "ppc64",
                        "riscv64",
                        "s390",
                        "s390x",
                        "x64",
                    }
                ),
            ),
            "node.executable": (
                node.get("executable"),
                lambda value: os.path.isabs(value) or ntpath.isabs(value),
            ),
            "node.sha256": (
                node.get("sha256"),
                lambda value: re.fullmatch(r"[0-9a-fA-F]{64}", value),
            ),
            "host.platform": (
                host.get("platform"),
                lambda value: (
                    value
                    in {
                        "aix",
                        "android",
                        "darwin",
                        "freebsd",
                        "linux",
                        "openbsd",
                        "sunos",
                        "win32",
                    }
                ),
            ),
        }
        for field, (value, valid) in checks.items():
            if not isinstance(value, str) or not value or not valid(value):
                return _unknown(
                    f"action runtime required identity missing or invalid: {field}"
                )
        environment = data.get("environment", {})
        if not isinstance(environment, dict):
            return _unknown("action runtime environment object invalid")
        allowed_environment = (
            "GITHUB_RUN_ID",
            "GITHUB_RUN_ATTEMPT",
            "GITHUB_JOB",
            "RUNNER_OS",
            "RUNNER_ARCH",
            "RUNNER_ENVIRONMENT",
            "ImageOS",
            "ImageVersion",
        )
        # Preserve producer field paths; never copy arbitrary receipt/environment fields.
        receipt = {
            "schema": schema,
            "node": {
                key: _safe(node[key])
                for key in ("version", "architecture", "executable", "sha256")
            },
            "host": {"platform": host["platform"]},
            "environment": {
                key: _safe(environment[key])
                if isinstance(environment.get(key), str)
                else None
                for key in allowed_environment
            },
        }
        if data.get("execution_context") in ("github-action", "local-validation"):
            receipt["execution_context"] = data["execution_context"]
        return {
            "status": "partial",
            "source": "ARM_DIAGNOSTIC_ACTION_JSON",
            "producer_schema": schema,
            "receipt": receipt,
            "reason": "external receipt retained separately; execution/binary not independently verified",
        }
    except (OSError, ValueError, AttributeError) as exc:
        return _unknown(type(exc).__name__)


def _execution_architecture():
    if sys.platform == "win32":
        try:
            import ctypes as c
            from ctypes import wintypes as w

            kernel = c.WinDLL("kernel32", use_last_error=True)
            kernel.GetCurrentProcess.restype = w.HANDLE
            query = kernel.IsWow64Process2
            query.argtypes = [w.HANDLE, c.POINTER(w.WORD), c.POINTER(w.WORD)]
            query.restype = w.BOOL
            process, native = w.WORD(), w.WORD()
            if not query(kernel.GetCurrentProcess(), c.byref(process), c.byref(native)):
                raise OSError("IsWow64Process2")
            return _observed(
                {
                    "process_machine": hex(process.value),
                    "native_machine": hex(native.value),
                    "emulated": process.value != 0,
                    "semantics": "process machine 0 means native on native_machine",
                },
                "IsWow64Process2(current process)",
            )
        except (OSError, AttributeError) as exc:
            return _unknown(type(exc).__name__)
    return _unknown(
        "current execution slice/translation requires native runner verification"
    )


def _write_json(output_dir, name, data):
    import json
    from pathlib import Path

    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / name).write_text(
        json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def inventory(paths: list[str], output_dir: str) -> dict:
    """Read-only identities of this controller and explicit public input paths."""
    import importlib.metadata
    import platform
    import shutil
    import sysconfig
    import zlib
    from pathlib import Path

    tools = {}
    for name in ("node", "git", "uv"):
        binary = shutil.which(name)
        if not binary:
            tools[name] = _unknown("not selected on PATH")
            continue
        version = _probe([binary, "--version"])
        tools[name] = {
            "binary": _binary(binary),
            "version": _observed(_safe(version["stdout"].strip()), "--version")
            if version["status"] == "measured"
            else _unknown(version.get("reason", "version query failed")),
            "selection": "PATH-selected executable; PATH itself not retained",
        }
    packages = {}
    for package in ("pdm-backend", "psutil"):
        try:
            packages[package] = _observed(
                importlib.metadata.version(package), "controller metadata"
            )
        except importlib.metadata.PackageNotFoundError:
            packages[package] = _unknown(
                "not installed in controller; isolated backend may differ"
            )
    inputs = []
    for path in paths:
        item = {"filesystem": _filesystem(path)}
        if Path(path).is_file():
            item["file_identity"] = _binary(path)
        elif Path(path).is_dir():
            revision = _probe(
                [
                    "git",
                    "-C",
                    str(Path(path).resolve()),
                    "rev-parse",
                    "--verify",
                    "HEAD",
                ]
            )
            text = revision.get("stdout", "").strip()
            item["git_revision"] = (
                _observed(text, "git rev-parse HEAD")
                if revision["status"] == "measured"
                and len(text) in (40, 64)
                and all(ch in "0123456789abcdef" for ch in text)
                else _unknown("no verified Git revision for supplied directory")
            )
        else:
            item["file_identity"] = _unknown("supplied path does not exist")
        inputs.append(item)
    config = {
        key: _observed(_safe(value), "sysconfig (controller, not backend)")
        if (value := sysconfig.get_config_var(key)) is not None
        else _unknown("not exposed by this runtime")
        for key in (
            "CC",
            "CFLAGS",
            "CONFIG_ARGS",
            "PY_CFLAGS",
            "PY_LDFLAGS",
            "PGO_PROF_USE_FLAG",
            "LTOFLAGS",
        )
    }
    result = {
        "schema_version": 1,
        "status": "partial",
        "performance_eligible": False,
        "scope": "controller and supplied paths; not isolated backend runtime identity",
        "hardware": _hardware(),
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
        },
        "environment": {
            name: _observed(_safe(os.environ[name]), f"environment:{name}")
            if name in os.environ
            else _unknown("not set")
            for name in _ENV_FIELDS
        },
        "runner_image_origins": {
            "current_environment": {
                name: _safe(os.environ[name]) if name in os.environ else None
                for name in ("ImageOS", "ImageVersion")
            },
            "historical_windows_console": {
                "image": "windows-11-vs2026-arm64",
                "version": "20261025.196.1",
                "source": "ci-foundation-audit/AUDIT.md console",
            },
            "historical_windows_bootstrap": {
                "version": "20261026.197.1",
                "source": "ci-foundation-audit/AUDIT.md bootstrap runner_image",
            },
            "reconciliation": "unresolved historical conflict; new inventory does not supersede either origin",
        },
        "runtime": {
            "binary": _binary(sys.executable),
            "execution_architecture": _execution_architecture(),
            "version": sys.version,
            "implementation": platform.python_implementation(),
            "compiler": platform.python_compiler(),
            "build": list(platform.python_build()),
            "build_config": config,
            "pgo_lto_applied": _unknown(
                "configuration strings do not prove applied build recipe"
            ),
            "codecs": {
                "zlib_compile": zlib.ZLIB_VERSION,
                "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
                "bz2_version": _unknown("stdlib bz2 exposes no codec library version"),
                "lzma_version": _unknown(
                    "stdlib lzma exposes no codec library version"
                ),
            },
        },
        "tools": tools,
        "controller_packages": packages,
        "actions_node": _action_inventory(),
        "paths": inputs,
        "source_manifest": _unknown(
            "caller must supply canonical byte/mode manifest separately"
        ),
        "uv_duration_export": _unknown(
            "uv 0.13.6 release tracing-durations-export is development-only; checked cache-dir probe emitted no export"
        ),
        "uv_log_context": "UV_LOG_CONTEXT=1 verbose timestamps are log event boundaries, not exact internal spans",
        "privacy": "explicit field whitelist; no PATH/full environment/source contents; home prefix redacted",
    }
    _write_json(output_dir, "platform-inventory.json", result)
    return result


def native_capture(run_build, output_dir: str) -> dict:
    """Request native CPU/file-I/O, fail closed before an unvalidated trace."""
    if (
        os.environ.get("DIAG_NATIVE_TRACES_REQUESTED", "true").strip().lower()
        == "false"
    ):
        reason = (
            "DIAG_NATIVE_TRACES_REQUESTED=false; native collectors explicitly disabled"
        )
        result = {
            "schema_version": 1,
            "status": "not-requested",
            "performance_eligible": False,
            "requested": False,
            "build_invoked": False,
            "build_result": None,
            "collectors": {
                name: {
                    "requested": False,
                    "status": "not-requested",
                    "value": None,
                    "reason": reason,
                }
                for name in ("native_cpu", "native_file_io", "native_scheduling")
            },
            "capabilities": {},
            "reason": reason,
            "capture_window": None,
            "lost_events": {"status": "not-requested", "value": None, "reason": reason},
            "symbols": {"status": "not-requested", "value": None, "reason": reason},
            "raw_policy": "private_raw only, excluded from upload; no raw traces produced",
            "upload_summaries": [],
            "mac_runtime_validation": "runner-only, not executed locally",
        }
        _write_json(output_dir, "native-capabilities.json", result)
        return result

    import shutil

    candidates = (
        ("wpr", "xperf")
        if sys.platform == "win32"
        else (("sample", "xctrace", "fs_usage") if sys.platform == "darwin" else ())
    )
    probes = {}
    for name in candidates:
        binary = shutil.which(name)
        if not binary:
            probes[name] = _unknown("native CLI not installed/on PATH")
            continue
        # Only documented non-recording help; sample has no assumed safe help invocation.
        if name in ("sample", "fs_usage"):
            probes[name] = {
                "binary": _binary(binary),
                "status": "unavailable",
                "reason": "installed candidate only; runner CLI/permissions and owned-tree export unvalidated",
            }
            continue
        args = (
            ["-help", "start"]
            if name == "wpr"
            else (["-help"] if name == "xperf" else ["help", "record"])
        )
        probe = _probe([binary, *args])
        text = probe.get("stdout", "")
        probes[name] = {
            "binary": _binary(binary),
            "help_status": probe["status"],
            "returncode": probe.get("returncode"),
            "help_observed": bool(text),
            "status": "unavailable",
            "reason": "help is not proof of safe bounded owned-process capture and reviewed export",
        }
    reason = (
        "No validated owned-process-tree CPU/file-I/O capture and privacy-reviewed summary exporter. "
        "Local system-wide capture prohibited; CI identity alone is not consent or permission. "
        "Callback has no pre-launch process identity; sampling this controller would miss backend children. "
        "No recording started, existing session queried/cancelled, privilege changed, or extra build invoked."
    )
    result = {
        "schema_version": 1,
        "status": "partial",
        "performance_eligible": False,
        "requested": True,
        "build_invoked": False,
        "build_result": None,
        "collectors": {
            name: {
                "requested": True,
                "status": "unavailable",
                "value": None,
                "reason": reason,
            }
            for name in ("native_cpu", "native_file_io", "native_scheduling")
        },
        "capabilities": probes,
        "reason": reason,
        "capture_window": None,
        "lost_events": _unknown("no capture"),
        "symbols": _unknown("no capture"),
        "raw_policy": "private_raw only, excluded from upload; no raw traces produced",
        "upload_summaries": [],
        "mac_runtime_validation": "runner-only, not executed locally",
    }
    _write_json(output_dir, "native-capabilities.json", result)
    return result
