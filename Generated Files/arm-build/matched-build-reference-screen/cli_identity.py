"""Prospective native process association; PID numbers alone are insufficient."""

import ctypes
import os
import sys
from pathlib import Path


def windows_api():
    from ctypes import wintypes as w

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "GetCurrentProcess": ([], w.HANDLE),
        "GetProcessId": ([w.HANDLE], w.DWORD),
        "GetProcessTimes": ([w.HANDLE, *([ctypes.POINTER(w.FILETIME)] * 4)], w.BOOL),
        "OpenProcess": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
        "CloseHandle": ([w.HANDLE], w.BOOL),
        "WaitForSingleObject": ([w.HANDLE, w.DWORD], w.DWORD),
        "QueryFullProcessImageNameW": (
            [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)],
            w.BOOL,
        ),
    }
    for name, (arguments, result) in signatures.items():
        getattr(api, name).argtypes = arguments
        getattr(api, name).restype = result
    return api


def handle_key(api, handle):
    from ctypes import wintypes as w

    times = [w.FILETIME() for _ in range(4)]
    if not api.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
        raise ctypes.WinError(ctypes.get_last_error())
    pid = api.GetProcessId(handle)
    if not pid:
        raise ctypes.WinError(ctypes.get_last_error())
    birth = times[0].dwHighDateTime << 32 | times[0].dwLowDateTime
    if birth <= 0:
        raise RuntimeError("Missing real Windows creation FILETIME")
    return {"pid": pid, "birth_filetime": birth}


def handle_identity(api, handle):
    from ctypes import wintypes as w

    value = handle_key(api, handle)
    if api.WaitForSingleObject(handle, 0) != 258:
        raise RuntimeError("Image provenance requires a live process")
    buffer, size = ctypes.create_unicode_buffer(32768), w.DWORD(32768)
    if not api.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
        raise ctypes.WinError(ctypes.get_last_error())
    return {**value, "image": buffer.value}


def popen_key(process):
    if sys.platform == "win32":
        value = handle_key(windows_api(), int(process._handle))
        if value["pid"] != process.pid:
            raise RuntimeError("Actual Popen handle/PID mismatch")
        return value
    if sys.platform != "darwin":
        raise RuntimeError("Only Windows/Mac association is defined")
    return {"pid": process.pid}


def popen_identity(process):
    if sys.platform == "win32":
        value = handle_identity(windows_api(), int(process._handle))
        if value["pid"] != process.pid:
            raise RuntimeError("Actual Popen handle/PID mismatch")
        return value
    if sys.platform != "darwin":
        raise RuntimeError("Only Windows/Mac association is defined")
    return {"pid": process.pid}


def native_identity():
    if sys.platform == "darwin":
        return {"platform": "darwin", "process": {"pid": os.getpid()}}
    if sys.platform != "win32":
        raise RuntimeError("Unsupported native association platform")
    api = windows_api()
    current = handle_identity(api, api.GetCurrentProcess())
    parent_pid = os.getppid()
    handle = api.OpenProcess(0x101000, False, parent_pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if api.WaitForSingleObject(handle, 0) != 258:
            raise RuntimeError("Parent is not live during native identity capture")
        parent = handle_identity(api, handle)
        if parent["pid"] != parent_pid or api.WaitForSingleObject(handle, 0) != 258:
            raise RuntimeError("Parent identity/liveness changed during capture")
    finally:
        if not api.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())
    return {
        "platform": "win32",
        "process": current,
        "parent": parent,
        "parent_live_during_capture": True,
    }


def same_identity(left, right):
    return (left.get("pid"), left.get("birth_filetime")) == (
        right.get("pid"),
        right.get("birth_filetime"),
    )


def associate(actual, waited, native):
    if len(actual) != len(waited):
        raise ValueError("Unpaired actual Popen/wait records")
    bound, used = {}, set()
    for row in actual:
        identity = row["process_identity"]
        waits = [
            value
            for value in waited
            if value["native_popen_object_id"] == row["native_popen_object_id"]
        ]
        if (
            len(waits) != 1
            or waits[0]["returncode"] != 1
            or not same_identity(waits[0]["process_identity"], identity)
        ):
            raise ValueError("Actual Popen object/wait identity mismatch")
        matches = []
        for record in native:
            process = record["process"]
            if record["platform"] == "darwin":
                valid = process["pid"] == identity["pid"]
            else:
                if not all(
                    value.get("birth_filetime", 0) > 0 for value in (process, identity)
                ):
                    raise ValueError("Windows creation identity absent")
                valid = same_identity(process, identity)
                if not valid:
                    parent = record.get("parent", {})
                    valid = (
                        record.get("parent_live_during_capture") is True
                        and same_identity(parent, identity)
                        and os.path.normcase(parent.get("image", ""))
                        == os.path.normcase(str(Path(row["argv"][0]).resolve()))
                        and os.path.normcase(identity.get("image", ""))
                        == os.path.normcase(parent.get("image", ""))
                        and process["birth_filetime"] >= parent.get("birth_filetime", 0)
                    )
            if valid:
                matches.append(process["pid"])
        if len(matches) != 1 or matches[0] in used:
            raise ValueError("Unbound/duplicate native CLI identity")
        used.add(matches[0])
        bound[matches[0]] = identity
    if used != {record["process"]["pid"] for record in native} or len(native) != len(
        used
    ):
        raise ValueError("Unbound/duplicate native CLI records")
    return bound
