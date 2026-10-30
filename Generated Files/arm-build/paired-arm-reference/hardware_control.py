"""Selected public CPU, process-resource and path-to-filesystem receipts."""

import ctypes
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

from guards import require


def query(argv):
    return subprocess.check_output(
        argv, stdin=subprocess.DEVNULL, timeout=30, text=True, encoding="utf-8"
    )


def windows_affinity(*, cap=False):
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.GetCurrentProcess.restype = ctypes.c_void_p
    process = api.GetCurrentProcess()
    api.GetProcessAffinityMask.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    current, system = ctypes.c_size_t(), ctypes.c_size_t()
    require(
        api.GetProcessAffinityMask(
            process, ctypes.byref(current), ctypes.byref(system)
        ),
        "Cannot establish process affinity",
    )
    original = current.value
    if cap:
        bits = [1 << n for n in range(64) if original & (1 << n)][:4]
        require(len(bits) == 4, "Need four usable CPUs for local correctness")
        api.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        require(
            api.SetProcessAffinityMask(process, sum(bits)), "Cannot cap own process"
        )
        require(
            api.GetProcessAffinityMask(
                process, ctypes.byref(current), ctypes.byref(system)
            ),
            "Cannot verify own process cap",
        )
    return {
        "original_mask": original,
        "mask": current.value,
        "usable": current.value.bit_count(),
    }


def cpu_receipt(*, local=False):
    system = platform.system()
    row = {
        "system": system,
        "machine": platform.machine(),
        "guest_logical": os.cpu_count(),
        "local_correctness_only": local,
    }
    if system == "Windows":
        row["affinity"] = windows_affinity(cap=local)
        row.update(
            json.loads(
                query(
                    [
                        "pwsh",
                        "-NoLogo",
                        "-NoProfile",
                        "-NonInteractive",
                        "-Command",
                        "$ErrorActionPreference='Stop'; "
                        "@{processors=@(Get-CimInstance Win32_Processor | "
                        "Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,Architecture); "
                        "midr=@(Get-ChildItem 'HKLM:\\HARDWARE\\DESCRIPTION\\System\\CentralProcessor' | "
                        "ForEach-Object { (Get-ItemProperty $_.PSPath).'CP 4000' }); "
                        "identifier=$env:PROCESSOR_IDENTIFIER} | ConvertTo-Json -Depth 5",
                    ]
                )
            )
        )
        row["models"] = [p["Name"] for p in row["processors"]]
        row["guest_cores"] = sum(p["NumberOfCores"] for p in row["processors"])
        row["usable"] = row["affinity"]["usable"]
        row["identities"] = [
            {"implementer": (int(midr) >> 24) & 255, "part": (int(midr) >> 4) & 4095}
            for midr in row["midr"]
        ]
    elif system == "Linux":
        require(not local, "Local exception is Windows correctness only")
        row["affinity"] = sorted(os.sched_getaffinity(0))
        row["usable"] = len(row["affinity"])
        blocks = [
            {
                key.strip(): value.strip()
                for line in block.splitlines()
                if ":" in line
                for key, value in [line.split(":", 1)]
            }
            for block in Path("/proc/cpuinfo").read_text().strip().split("\n\n")
        ]
        row["identities"] = [
            {"implementer": int(b["CPU implementer"], 0), "part": int(b["CPU part"], 0)}
            for b in blocks
            if "processor" in b
        ]
        fields = json.loads(query(["lscpu", "--json"]))["lscpu"]
        row["topology"] = {
            entry["field"]: entry["data"]
            for entry in fields
            if entry["field"]
            in (
                "Architecture:",
                "CPU(s):",
                "On-line CPU(s) list:",
                "Model name:",
                "Core(s) per socket:",
                "Socket(s):",
                "Thread(s) per core:",
            )
        }
        row["models"] = [row["topology"].get("Model name:", "")]
        row["guest_cores"] = int(row["topology"].get("Core(s) per socket:", 0)) * int(
            row["topology"].get("Socket(s):", 0)
        )
    else:
        raise RuntimeError("Only Windows/Linux are in this control")
    return row


def comparable(row):
    require(row["machine"].lower() in ("arm64", "aarch64"), "Non-ARM64 guest")
    local = row["local_correctness_only"]
    require(
        row["usable"] == 4
        and (local or row["guest_logical"] == row["guest_cores"] == 4),
        "Incomparable guest/usable core count",
    )
    require(
        len(row["identities"]) == row["guest_logical"]
        and all(i == {"implementer": 0x41, "part": 0xD49} for i in row["identities"]),
        "Missing/mixed/non-N2 actual CPU implementer/part",
    )
    require(
        row["models"]
        and all(
            re.fullmatch(r"cobalt\s*100|neoverse[- ]n2", model.strip(), re.I)
            for model in row["models"]
        ),
        "Ambiguous/mismatched CPU model",
    )
    if row["system"] == "Windows":
        require(
            all(p["Architecture"] == 12 for p in row["processors"])
            and all(re.fullmatch(r"cobalt\s*100", name, re.I) for name in row["models"])
            and re.search(r"\bModel D49\b", row["identifier"], re.I),
            "Missing Windows ARM64/D49 identity",
        )
    else:
        require(row["system"] == "Linux" and not local, "Invalid local exception")
    return {
        "comparable": not local,
        "family": "Arm implementer 0x41 / Neoverse N2 part 0xd49",
        "sku_identity_proven": False,
        "local_guest_not_four": local,
    }


def filesystem_context(paths):
    rows = {}
    for label, path in paths.items():
        path = Path(path).resolve(strict=True)
        row = {
            "path": str(path),
            "disk_usage": dict(
                zip(("total", "used", "free"), shutil.disk_usage(path), strict=True)
            ),
        }
        if os.name == "nt":
            api = ctypes.WinDLL("kernel32", use_last_error=True)
            api.GetVolumePathNameW.argtypes = [
                ctypes.c_wchar_p,
                ctypes.c_wchar_p,
                ctypes.c_uint32,
            ]
            api.GetVolumeInformationW.argtypes = [
                ctypes.c_wchar_p,
                ctypes.c_wchar_p,
                ctypes.c_uint32,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_wchar_p,
                ctypes.c_uint32,
            ]
            mount = ctypes.create_unicode_buffer(32768)
            require(
                api.GetVolumePathNameW(str(path), mount, len(mount)),
                "Cannot resolve volume mount",
            )
            filesystem = ctypes.create_unicode_buffer(256)
            require(
                api.GetVolumeInformationW(
                    mount.value, None, 0, None, None, None, filesystem, len(filesystem)
                ),
                "Cannot identify actual filesystem",
            )
            row.update(mount=mount.value, filesystem=filesystem.value)
        else:
            row["mount"] = json.loads(
                query(
                    [
                        "findmnt",
                        "--json",
                        "--target",
                        str(path),
                        "--output",
                        "TARGET,FSTYPE,SOURCE",
                    ]
                )
            )["filesystems"]
            row["device_number"] = path.stat().st_dev
        rows[label] = row
    return rows
