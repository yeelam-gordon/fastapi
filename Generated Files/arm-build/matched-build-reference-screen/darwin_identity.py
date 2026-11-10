"""Source-only libproc child identity prototype; not an ownership handle."""

import ctypes
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PROC_PIDTBSDINFO = 3
PROC_PIDPATHINFO_MAXSIZE = 4096
PROC_FLAG_INEXIT = 4


class ProcBsdInfo(ctypes.Structure):
    """xnu f6217f891ac0bb64f3d375211650a4c1ff8ca1ea proc_bsdinfo."""

    _fields_ = [
        ("pbi_flags", ctypes.c_uint32),
        ("pbi_status", ctypes.c_uint32),
        ("pbi_xstatus", ctypes.c_uint32),
        ("pbi_pid", ctypes.c_uint32),
        ("pbi_ppid", ctypes.c_uint32),
        ("pbi_uid", ctypes.c_uint32),
        ("pbi_gid", ctypes.c_uint32),
        ("pbi_ruid", ctypes.c_uint32),
        ("pbi_rgid", ctypes.c_uint32),
        ("pbi_svuid", ctypes.c_uint32),
        ("pbi_svgid", ctypes.c_uint32),
        ("rfu_1", ctypes.c_uint32),
        ("pbi_comm", ctypes.c_char * 16),
        ("pbi_name", ctypes.c_char * 32),
        ("pbi_nfiles", ctypes.c_uint32),
        ("pbi_pgid", ctypes.c_uint32),
        ("pbi_pjobc", ctypes.c_uint32),
        ("e_tdev", ctypes.c_uint32),
        ("e_tpgid", ctypes.c_uint32),
        ("pbi_nice", ctypes.c_int32),
        ("pbi_start_tvsec", ctypes.c_uint64),
        ("pbi_start_tvusec", ctypes.c_uint64),
    ]


class IdentityError(RuntimeError):
    """A bounded observation could not establish the requested identity."""


@dataclass(frozen=True)
class ChildIdentity:
    pid: int
    parent_pid: int
    executable: str
    observed_executable: str
    # Half-open UTC Unix interval in integer microseconds, not monotonic time.
    start_unix_interval_us: tuple[int, int]


def _load_libproc():
    if sys.platform != "darwin":
        raise IdentityError("libproc native loading requires Darwin")
    library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    library.proc_pidinfo.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint64,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    library.proc_pidinfo.restype = ctypes.c_int
    library.proc_pidpath.argtypes = [
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    library.proc_pidpath.restype = ctypes.c_int
    return library


def _require_running(child: subprocess.Popen, pid: int) -> None:
    if child.pid != pid or child.returncode is not None or child.poll() is not None:
        raise IdentityError("retained child exited or changed during capture")


def _bsd_identity(library, pid: int, parent_pid: int) -> tuple[int, int]:
    information = ProcBsdInfo()
    size = ctypes.sizeof(information)
    returned = library.proc_pidinfo(
        pid, PROC_PIDTBSDINFO, 0, ctypes.byref(information), size
    )
    if returned != size:
        raise IdentityError(
            f"proc_pidinfo returned {returned}, expected {size}; "
            f"errno={ctypes.get_errno()}"
        )
    if information.pbi_pid != pid or information.pbi_ppid != parent_pid:
        raise IdentityError("BSD PID/current parent mismatch")
    if information.pbi_flags & PROC_FLAG_INEXIT:
        raise IdentityError("BSD process is exiting")
    seconds = information.pbi_start_tvsec
    microseconds = information.pbi_start_tvusec
    if seconds == 0 or microseconds >= 1_000_000:
        raise IdentityError("invalid BSD process start")
    return seconds, microseconds


def _executable_path(library, pid: int) -> tuple[str, Path]:
    # A sentinel avoids mistaking untouched zero-initialized bytes for a NUL.
    buffer = ctypes.create_string_buffer(
        b"\xff" * PROC_PIDPATHINFO_MAXSIZE, PROC_PIDPATHINFO_MAXSIZE
    )
    length = library.proc_pidpath(pid, buffer, len(buffer))
    if not 0 < length < len(buffer):
        raise IdentityError(
            f"invalid proc_pidpath length {length}; errno={ctypes.get_errno()}"
        )
    raw = buffer.raw
    if raw[length] != 0 or b"\0" in raw[:length]:
        raise IdentityError("proc_pidpath length/NUL mismatch")
    observed = raw[:length].decode("utf-8", errors="strict")
    path = Path(observed)
    if not path.is_absolute():
        raise IdentityError("proc_pidpath is not absolute")
    return observed, path.resolve(strict=True)


def capture_child_identity(
    child: subprocess.Popen, expected_executable: str | Path
) -> ChildIdentity:
    """Observe one retained child: BSD -> image -> BSD, with no retries.

    The caller must exclusively retain the actual Popen child (no concurrent
    wait/reap), then perform its own subsequent wait/drain. This is not atomic:
    intervening execs or changes outside the sampled instants are not excluded.
    Only exact canonical image equality is allowed; runtime links are not sealed.
    The decoded proc_pidpath spelling is retained separately from its resolution.
    Native Darwin ABI and SDK/image aliases remain unqualified.
    """
    if not isinstance(child, subprocess.Popen):
        raise IdentityError("an actual retained Popen child is required")
    pid = child.pid
    parent_pid = os.getpid()
    if type(pid) is not int or not 0 < pid <= 2**31 - 1:
        raise IdentityError("invalid positive child PID")
    if not 0 < parent_pid <= 2**31 - 1 or pid == parent_pid:
        raise IdentityError("invalid current parent PID")
    _require_running(child, pid)
    expected = Path(expected_executable).resolve(strict=True)
    if not expected.is_file() or not os.access(expected, os.X_OK):
        raise IdentityError("expected image must be an existing executable file")
    library = _load_libproc()
    first = _bsd_identity(library, pid, parent_pid)
    _require_running(child, pid)
    observed_image, image = _executable_path(library, pid)
    _require_running(child, pid)
    second = _bsd_identity(library, pid, parent_pid)
    _require_running(child, pid)
    if first != second:
        raise IdentityError("BSD process start changed during capture")
    if str(image) != str(expected):
        raise IdentityError("canonical executable image mismatch")
    start_us = first[0] * 1_000_000 + first[1]
    if start_us > time.time_ns() // 1000:
        raise IdentityError("BSD process start is later than capture UTC")
    _require_running(child, pid)
    return ChildIdentity(
        pid=pid,
        parent_pid=parent_pid,
        executable=str(image),
        observed_executable=observed_image,
        start_unix_interval_us=(start_us, start_us + 1),
    )
