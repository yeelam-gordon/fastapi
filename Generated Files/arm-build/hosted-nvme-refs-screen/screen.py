"""Windows ARM64 build-only cache placement screen; no provisioning or downloads."""

import argparse
import ctypes
import dataclasses
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import statistics
import struct
import subprocess
import sys
import sysconfig
import tarfile
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import owned_process  # noqa: E402
from archive_headers import full_inventory, require_reference  # noqa: E402
from artifact_gate import artifact_set  # noqa: E402
from prepare_uv import attest  # noqa: E402
from runtime_bytecode import RuntimeGuard  # noqa: E402

REVISION = "864b569cf8453654fc3bc2c64108c0f644e2918c"
WHEEL = "pdm_backend-2.5.0-py3-none-any.whl"
WHEEL_SHA = "5b8746b567a16a1fd506ce66ee28e89d46374526f52238aa1b96cc2c08245c63"
SUPPORT = {
    "owned_process.py": "b20031881f39fb25b5da67c0bbd5e5fccbcd44630106958aa44caab629251530",
    "cli_identity.py": "16b1895a3b8234911877ad271324cece7e3b753c3d4d2cb2e58096360eb24d5f",
    "artifact_gate.py": "7074e6697002d0e21bb131f551a932e9a6cf1a4ed946cb7bac03daecfa5033be",
    "archive_headers.py": "f02711558e43a0d2592c403ffba88d6f2690e8b1350ddd38a2da88f361865b0c",
    "prepare_uv.py": "5bcf151447309807171760957df022c3ce240c7e8be96eca742bf4c5f3466163",
    "build-constraints.txt": "f729230cb9adc788c4a3a9096baf57735ec02c62033102622174d600fb1bc908",
}
COMMAND_SECONDS = 30
GUARDIAN_ALLOWANCE = 25
AUDIT_RESERVE = 45
GENERATED_PYPROJECT = "fastapi-0.119.1/pyproject.toml"
FILETIME_EPOCH = 116444736000000000
SETUP_UV_LOCATIONS = frozenset(
    {"UV_PYTHON_INSTALL_DIR", "UV_TOOL_BIN_DIR", "UV_TOOL_DIR"}
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def schedule():
    result = [("C", False, "WA"), ("D", False, "WB")]
    for pair, order in enumerate(("CD", "DC", "CD", "DC", "CD", "DC"), 1):
        result.extend((arm, True, pair) for arm in order)
    return result


def command(args, constraints):
    return [
        str(args.uv),
        "build",
        "--python",
        str(args.python),
        "--no-python-downloads",
        "--offline",
        "--build-constraints",
        str(constraints),
        "--find-links",
        str(args.wheels),
    ]


def setup_uv_handoff(inherited):
    removed = sorted(name for name in inherited if name.upper() in SETUP_UV_LOCATIONS)
    return (
        {name: value for name, value in inherited.items() if name not in removed},
        {
            "removed_location_variables": removed,
            "reason": "Builds use an explicit installed Python with downloads disabled; no uv tool commands.",
        },
    )


def environment(cache, inherited=None):
    env = dict(os.environ if inherited is None else inherited)
    forbidden = [
        name
        for name in env
        if (
            name.upper().startswith(
                ("UV_", "PYTHON", "PYTEST", "PIP_", "COVERAGE", "COV_CORE")
            )
            or name.upper() == "SOURCE_DATE_EPOCH"
        )
        and name.upper() != "UV_CACHE_DIR"
    ]
    require(not forbidden, f"ambient benchmark overrides forbidden: {forbidden}")
    for name in list(env):
        if name.upper() == "UV_CACHE_DIR":
            del env[name]
    env["UV_CACHE_DIR"] = str(cache)
    return env


def environment_delta(control, candidate):
    require(control.keys() == candidate.keys(), "environment variable sets differ")
    changed = [key for key in control if control[key] != candidate[key]]
    require(changed == ["UV_CACHE_DIR"], "cache-only environment delta")
    return {"changed_keys": changed, "all_non_cache_values_equal": True}


def environment_evidence(env):
    require(
        not any(name.upper() == "SOURCE_DATE_EPOCH" for name in env),
        "unsupported ambient metadata override: SOURCE_DATE_EPOCH",
    )
    return {
        "metadata_profile": {"SOURCE_DATE_EPOCH": "absent"},
        "values": {
            key: env[key] for key in ("UV_CACHE_DIR", "TEMP", "TMP") if key in env
        },
        "scope": "Whitelisted launch values only; complete environment delta checked in memory.",
    }


def room(deadline, seconds):
    require(time.perf_counter() + seconds <= deadline, "deadline prevents launch")


def pe_arm64(path):
    data = path.read_bytes()
    require(data[:2] == b"MZ" and len(data) >= 64, "native PE required")
    offset = struct.unpack_from("<I", data, 60)[0]
    require(data[offset : offset + 4] == b"PE\0\0", "PE signature")
    require(struct.unpack_from("<H", data, offset + 4)[0] == 0xAA64, "ARM64 PE")


def runtime_identity():
    require(sys.platform == "win32", "Windows only")
    require(sys.version_info[:3] == (3, 13, 15), "Python 3.13.15 required")
    require(sysconfig.get_platform() == "win-arm64", "native ARM64 runtime")
    require(not sysconfig.get_config_var("Py_GIL_DISABLED"), "normal GIL build")
    require(getattr(sys, "_is_gil_enabled", lambda: False)(), "GIL enabled")
    require(not sysconfig.get_config_var("PYTHON_JIT"), "no JIT build")
    require(
        not getattr(getattr(sys, "_jit", None), "is_enabled", lambda: False)(),
        "JIT disabled",
    )
    require(not sysconfig.get_config_var("Py_DEBUG"), "non-debug runtime")
    require(
        not sys.dont_write_bytecode and sys.pycache_prefix is None,
        "default bytecode settings",
    )
    pe_arm64(Path(sys.executable))
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.GetCurrentProcess.restype = ctypes.c_void_p
    api.GetProcessAffinityMask.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    process_mask, system_mask = ctypes.c_size_t(), ctypes.c_size_t()
    require(
        api.GetProcessAffinityMask(
            api.GetCurrentProcess(),
            ctypes.byref(process_mask),
            ctypes.byref(system_mask),
        ),
        "affinity unavailable",
    )
    require(
        process_mask.value == system_mask.value, "default process affinity required"
    )
    return {
        "executable": str(Path(sys.executable).resolve()),
        "version": sys.version,
        "platform": sysconfig.get_platform(),
        "gil": True,
        "jit": False,
        "bytecode": "default",
        "cpu_count": os.cpu_count(),
        "affinity_mask": process_mask.value,
        "runtime_roots": list(dict.fromkeys([sys.prefix, sys.base_prefix])),
    }


def run_native(argv, **kwargs):
    receipt = owned_process.run_owned(argv, **kwargs)
    observation = dict(receipt.actual_process or {})
    observation.update(
        argv=argv,
        cwd=str(kwargs["cwd"]),
        environment=kwargs["env"],
        start_ns=receipt.native_start_ns,
        end_ns=receipt.native_end_ns,
        returncode=receipt.returncode,
        status="COMPLETE" if receipt.succeeded and receipt.actual_process else "FAILED",
    )
    return receipt, observation


def git(source, *argv):
    return subprocess.run(
        ["git", "-C", str(source), *argv],
        check=True,
        capture_output=True,
        timeout=30,
    ).stdout


def raw_tree(source):
    entries = {}
    for row in git(source, "ls-tree", "-r", "-z", REVISION).split(b"\0"):
        if not row:
            continue
        metadata, filename = row.split(b"\t", 1)
        mode, kind, object_id = metadata.decode().split()
        require(
            kind == "blob" and mode in {"100644", "100755"},
            "regular Git blobs required",
        )
        entries[filename.decode()] = {"mode": mode, "git_blob": object_id}
    require(len(entries) == 2557, "raw Git policy requires 2557 tracked files")
    return entries


def verify_git_payload(root, tree):
    require(
        set(manifest(root)) == set(tree),
        "plain Git archive must contain complete source",
    )
    for name, metadata in tree.items():
        data = (root / name).read_bytes()
        blob = b"blob " + str(len(data)).encode() + b"\0" + data
        require(
            hashlib.sha1(blob).hexdigest() == metadata["git_blob"],
            f"raw Git blob differs: {name}",
        )


def manifest_entry(path, root):
    require(not path.is_symlink() and not path.is_junction(), "payload reparse point")
    return (path.relative_to(root).as_posix(), digest(path)) if path.is_file() else None


def manifest(root):
    with ThreadPoolExecutor(max_workers=4) as pool:
        entries = pool.map(
            lambda path: manifest_entry(path, root), sorted(root.rglob("*"))
        )
        return dict(entry for entry in entries if entry is not None)


def hash_files(root, names):
    names = sorted(names)
    with ThreadPoolExecutor(max_workers=4) as pool:
        hashes = pool.map(digest, (root / name for name in names))
        return dict(zip(names, hashes, strict=True))


def extract(archive_path, destination):
    destination.mkdir()
    with tarfile.open(archive_path) as archive:
        for entry in archive:
            relative = Path(entry.name)
            require(
                not relative.is_absolute() and ".." not in relative.parts,
                "unsafe Git archive member",
            )
            require(entry.isfile() or entry.isdir(), "nonregular Git archive member")
        archive.extractall(destination, filter="data")


def source_after(source, canonical, inventory, folder):
    actual = manifest(source)
    require(
        all(actual.get(name) == value for name, value in canonical.items()),
        "tracked source changed",
    )
    extras = {name: value for name, value in actual.items() if name not in canonical}
    pycs, retained = {}, {}
    for name in extras:
        if name.startswith("dist/"):
            require(
                name
                in {
                    "dist/fastapi-0.119.1.tar.gz",
                    "dist/fastapi-0.119.1-py3-none-any.whl",
                    "dist/.gitignore",
                },
                f"unexpected dist output: {name}",
            )
            if name == "dist/.gitignore":
                require(
                    (source / name).read_bytes() == b"*", "pinned UV dist ignore file"
                )
        elif name.startswith(".pdm-build/"):
            relative = name.removeprefix(".pdm-build/")
            if relative == ".gitignore":
                require(
                    (source / name).read_bytes() == b"*\r\n",
                    "native Windows PDM ignore file",
                )
            else:
                matches = [
                    value["sha256"]
                    for kind in inventory.values()
                    for member, value in kind.items()
                    if member == relative or member == "fastapi-0.119.1/" + relative
                ]
                require(
                    matches and all(value == extras[name] for value in matches),
                    f"PDM output must match exact archive member: {name}",
                )
        elif name.endswith(".pyc"):
            path = Path(name)
            require(path.parent.name == "__pycache__", f"untyped bytecode: {name}")
            original = (
                path.parent.parent / (path.name.split(".")[0] + ".py")
            ).as_posix()
            require(
                original in canonical and path.name.endswith(".cpython-313.pyc"),
                f"unexpected bytecode source/tag: {name}",
            )
            data = (source / name).read_bytes()
            require(
                data[:4] == importlib.util.MAGIC_NUMBER and len(data) >= 16,
                f"invalid bytecode: {name}",
            )
            require(
                struct.unpack_from("<I", data, 4)[0] == 0,
                f"non-default bytecode flags: {name}",
            )
            metadata = (source / original).stat()
            require(
                struct.unpack_from("<II", data, 8)
                == (int(metadata.st_mtime) & 0xFFFFFFFF, metadata.st_size & 0xFFFFFFFF),
                f"bytecode source association: {name}",
            )
            pycs[name] = {
                "source": original,
                "source_sha256": canonical[original],
                "source_mtime": int(metadata.st_mtime),
                "source_bytes": metadata.st_size,
                "pyc_sha256": extras[name],
                "retained": "generated/" + name,
                "magic": data[:4].hex(),
                "flags": 0,
            }
        else:
            raise RuntimeError(f"unqualified generated output: {name}")
        if not name.startswith("dist/"):
            target = folder / "generated" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, target)
            require(digest(target) == extras[name], "generated raw retention differs")
            retained[name] = extras[name]
    return {
        "tracked": canonical,
        "outputs": extras,
        "retained_generated": retained,
        "pyc_associations": pycs,
    }


def retain_archives(source, folder):
    dist = source / "dist"
    expected = {
        "fastapi-0.119.1.tar.gz",
        "fastapi-0.119.1-py3-none-any.whl",
        ".gitignore",
    }
    require(
        {path.name for path in dist.iterdir()} == expected,
        "exactly two archives and pinned UV ignore required",
    )
    require((dist / ".gitignore").read_bytes() == b"*", "pinned UV dist ignore file")
    artifacts = folder / "artifacts"
    artifacts.mkdir()
    retained = {}
    for name in sorted(expected):
        source_path = dist / name
        require(
            source_path.is_file()
            and not source_path.is_symlink()
            and not source_path.is_junction(),
            "regular dist outputs required",
        )
        target = folder / "dist.gitignore" if name == ".gitignore" else artifacts / name
        shutil.copyfile(source_path, target)
        require(digest(source_path) == digest(target), "raw archive retention differs")
        retained[name] = {
            "sha256": digest(target),
            "bytes": target.stat().st_size,
            "retained": str(target.relative_to(folder)),
        }
    save(folder / "dist-output.json", retained)
    return artifacts


def generated_metadata_proof(inventory, folder):
    receipt, native, command_row = (
        load(folder / name)
        for name in ("ownership.json", "native.json", "command.json")
    )
    process = receipt["actual_process"]
    start, end = receipt["native_start_ns"], receipt["native_end_ns"]
    require(
        owned_process.Receipt(**receipt).succeeded
        and native["status"] == "COMPLETE"
        and native["returncode"] == 0,
        "successful native lifetime required for generated metadata",
    )
    require(
        all(
            type(value) is int
            for value in (start, end, process["pid"], process["birth_filetime"])
        )
        and 0 < end - start <= COMMAND_SECONDS * 1_000_000_000
        and process["pid"] > 0
        and FILETIME_EPOCH < process["birth_filetime"] < 2**64,
        "invalid generated metadata native clock/identity",
    )
    require(
        native["start_ns"] == start
        and native["end_ns"] == end
        and all(
            native[key] == process[key] for key in ("pid", "image", "birth_filetime")
        )
        and native["argv"] == command_row["argv"]
        and command_row["argv"][1] == "build"
        and Path(process["image"]).is_absolute()
        and Path(process["image"]) == Path(command_row["argv"][0])
        and native["cwd"] == command_row["cwd"]
        and native["environment"] == command_row["environment"]
        and native["environment"]["metadata_profile"] == {"SOURCE_DATE_EPOCH": "absent"}
        and load(folder / "stdout.actual-process.json") == process,
        "generated metadata native evidence association differs",
    )
    require_reference(inventory, load(folder / "full-headers.json"))
    member = inventory["sdist"][GENERATED_PYPROJECT]
    pax, mtime = member["pax_headers"], member["mtime"]
    require(
        set(pax) == {"mtime"}
        and type(pax["mtime"]) is str
        and re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?", pax["mtime"])
        and type(mtime) in (float, int)
        and math.isfinite(mtime),
        "default generated pyproject PAX/finite mtime required",
    )
    decimal = Decimal(pax["mtime"])
    require(
        decimal.is_finite() and decimal == Decimal(str(mtime)),
        "generated pyproject PAX/parser mtime differs",
    )
    lower = (process["birth_filetime"] - FILETIME_EPOCH) * 100
    upper = lower + end - start
    numerator, denominator = decimal.as_integer_ratio()
    require(
        lower * denominator <= numerator * 1_000_000_000 <= upper * denominator,
        "generated pyproject mtime outside actual UV UTC lifetime",
    )
    retained = load(folder / "dist-output.json")
    paths = [
        "ownership.json",
        "native.json",
        "command.json",
        "stdout",
        "stderr",
        "stdout.actual-process.json",
        "full-headers.json",
        "dist-output.json",
    ]
    bindings = {
        name: digest(folder / name)
        for name in paths + [item["retained"] for item in retained.values()]
    }
    require(
        all(bindings[item["retained"]] == item["sha256"] for item in retained.values()),
        "generated metadata retained raw bytes differ",
    )
    return {
        "profile": "stock PDM 2.5.0 generated pyproject default timestamp only",
        "backend_wheel_sha256": WHEEL_SHA,
        "member": GENERATED_PYPROJECT,
        "raw_header": member,
        "actual_process": process,
        "native_QPC_ns": [start, end],
        "UTC_window_ns": [lower, upper],
        "clock_basis": "FILETIME birth UTC plus complete native QPC duration; zero added slack",
        "bindings": bindings,
    }


def require_generated_headers(actual, reference, folder, reference_folder):
    proof = generated_metadata_proof(actual, folder)
    save(folder / "generated-metadata-proof.json", proof)
    if reference is None:
        return
    require(
        generated_metadata_proof(reference, reference_folder)
        == load(reference_folder / "generated-metadata-proof.json"),
        "reference generated metadata proof changed",
    )
    require_reference(reference, reference)
    for kind, members in actual.items():
        if members.keys() != reference[kind].keys():
            raise ValueError("Full frozen archive names differ")
        for name, fields in members.items():
            for field, value in fields.items():
                generated_time = (
                    kind == "sdist"
                    and name == GENERATED_PYPROJECT
                    and field in ("mtime", "pax_headers")
                )
                if not generated_time and value != reference[kind][name][field]:
                    raise ValueError(
                        f"Full frozen archive member/header metadata differs: {kind}/{name}/{field}"
                    )


def archive_audit(source, canonical, reference, folder, reference_folder):
    artifacts = retain_archives(source, folder)
    inventory = full_inventory(artifacts)
    save(folder / "full-headers.json", inventory)
    require(
        len(inventory["sdist"]) == 1196 and len(inventory["wheel"]) == 58,
        "complete 1196-sdist/58-wheel membership required",
    )
    require_generated_headers(inventory, reference, folder, reference_folder)
    content = artifact_set(artifacts, source, canonical)
    return inventory, content


def summarize(rows):
    require(
        [(r["arm"], r["measured"], r["pair"]) for r in rows] == schedule(),
        "complete frozen schedule required",
    )
    require(all(row["status"] == "VALID" for row in rows), "invalid row")
    measured = [row for row in rows if row["measured"]]
    medians = {
        arm: statistics.median(row["seconds"] for row in measured if row["arm"] == arm)
        for arm in ("C", "D")
    }
    pairs = []
    for index in range(1, 7):
        members = [row for row in measured if row["pair"] == index]
        values = {row["arm"]: row["seconds"] for row in members}
        require(
            all(math.isfinite(value) and value > 0 for value in values.values()),
            "invalid native duration",
        )
        pairs.append(
            {
                "pair": index,
                "order": "".join("A" if row["arm"] == "C" else "B" for row in members),
                "gain": 1 - values["D"] / values["C"],
            }
        )
    arm_gain = 1 - medians["D"] / medians["C"]
    paired_gain = statistics.median(pair["gain"] for pair in pairs)
    strata = {
        order: statistics.median(
            pair["gain"] for pair in pairs if pair["order"] == order
        )
        for order in ("AB", "BA")
    }
    wins = sum(pair["gain"] > 0 for pair in pairs)
    return {
        "arm_medians_seconds": medians,
        "arm_median_gain": arm_gain,
        "paired_median_gain": paired_gain,
        "pairs": pairs,
        "wins": wins,
        "order_strata": strata,
        "material": arm_gain >= 0.05
        and paired_gain >= 0.05
        and wins >= 5
        and all(value > 0 for value in strata.values()),
    }


def execute(args, canonical, deadline, envs, argv, runtime_guard):
    rows, reference, reference_folder = [], None, None
    live = args.output / "canonical-source"
    for index, (arm, measured, pair) in enumerate(schedule()):
        room(deadline, COMMAND_SECONDS + GUARDIAN_ALLOWANCE + AUDIT_RESERVE)
        folder = args.output / f"build-{index:02}-{arm}"
        folder.mkdir()
        runtime_guard.before_row(arm, measured, pair, folder)
        if live.exists():
            shutil.rmtree(live)
        extract(args.output / "source.tar", live)
        before = manifest(live)
        save(folder / "source-before.json", before)
        require(before == canonical, "fresh source manifest differs")
        spec = folder / "command.json"
        save(
            spec,
            {
                "argv": argv,
                "cwd": str(live),
                "environment": environment_evidence(envs[arm]),
                "arm": arm,
                "measured": measured,
                "pair": pair,
            },
        )
        room(deadline, COMMAND_SECONDS + GUARDIAN_ALLOWANCE + AUDIT_RESERVE)
        started = time.perf_counter()
        receipt, native = run_native(
            argv,
            cwd=live,
            env=envs[arm],
            stdout_path=folder / "stdout",
            stderr_path=folder / "stderr",
            timeout=COMMAND_SECONDS,
            native_clock=True,
        )
        save(folder / "ownership.json", dataclasses.asdict(receipt))
        save(
            folder / "native.json",
            {
                **native,
                "environment": environment_evidence(native["environment"]),
            },
        )
        require(receipt.succeeded, "fatal receipt; no next command or value")
        require(
            native["status"] == "COMPLETE" and native["returncode"] == 0,
            "native command incomplete",
        )
        require(
            native["argv"] == argv
            and native["cwd"] == str(live)
            and native["environment"] == envs[arm],
            "actual CLI/environment differs",
        )
        require(
            native["birth_filetime"] > 0
            and native["pid"] > 0
            and Path(native["image"]) == args.uv,
            "native association failed",
        )
        require(
            receipt.native_start_ns
            == native["start_ns"]
            < native["end_ns"]
            == receipt.native_end_ns,
            "native clock not identical to owned clock",
        )
        seconds = (native["end_ns"] - native["start_ns"]) / 1e9
        require(seconds <= COMMAND_SECONDS, "native command cap exceeded")
        room(deadline, AUDIT_RESERVE)
        audit_started = time.perf_counter()
        inventory, content = archive_audit(
            live, canonical, reference, folder, reference_folder
        )
        source_proof = source_after(live, canonical, inventory, folder)
        save(folder / "source-after.json", source_proof)
        require(
            all(
                source_proof["outputs"].get("dist/" + name) == metadata["sha256"]
                for name, metadata in content.items()
            ),
            "source dist and retained raw archive association differs",
        )
        if reference is None:
            reference, reference_folder = inventory, folder
        save(folder / "full-headers.json", inventory)
        save(folder / "content-record.json", content)
        runtime_guard.after_row(arm, measured, pair, folder)
        rows.append(
            {
                "index": index,
                "folder": folder.name,
                "arm": arm,
                "measured": measured,
                "pair": pair,
                "seconds": seconds,
                "status": "VALID",
                "owned_wall_seconds": audit_started - started,
                "audit_seconds": time.perf_counter() - audit_started,
                "command_sha256": digest(spec),
                "ownership_sha256": digest(folder / "ownership.json"),
                "native_sha256": digest(folder / "native.json"),
                "headers_sha256": digest(folder / "full-headers.json"),
                "content_sha256": digest(folder / "content-record.json"),
                "source_before_sha256": digest(folder / "source-before.json"),
                "source_after_sha256": digest(folder / "source-after.json"),
                "generated_metadata_sha256": digest(
                    folder / "generated-metadata-proof.json"
                ),
            }
        )
        save(args.output / "rows.json", rows)
    return rows


def validate_paths(args):
    require(sys.platform == "win32", "Windows-only screen")
    for name in ("source", "python", "uv", "control_cache", "wheels", "output"):
        require(getattr(args, name).drive.upper() == "C:", f"{name} must remain on C:")
    require(args.candidate_cache.drive.upper() == "D:", "candidate cache must be D:")
    require(
        str(args.control_cache)[2:] == str(args.candidate_cache)[2:],
        "cache suffix and path lengths must match",
    )
    paths = [
        getattr(args, name)
        for name in (
            "source",
            "python",
            "uv",
            "control_cache",
            "candidate_cache",
            "wheels",
            "output",
        )
    ]
    for index, path in enumerate(paths):
        require(
            all(
                not path.is_relative_to(other) and not other.is_relative_to(path)
                for other in paths[index + 1 :]
            ),
            "paths must be disjoint",
        )
        for ancestor in (path, *path.parents):
            require(
                not ancestor.is_symlink() and not ancestor.is_junction(),
                "path reparse points forbidden",
            )
    for path in (args.output, args.control_cache, args.candidate_cache):
        require(not path.exists(), "fresh output and cache directories required")


def volume_identity(path):
    from ctypes import wintypes

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    filesystem, label = (
        ctypes.create_unicode_buffer(256),
        ctypes.create_unicode_buffer(256),
    )
    serial, length, flags = wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD()
    require(
        api.GetVolumeInformationW(
            str(path.anchor),
            label,
            256,
            ctypes.byref(serial),
            ctypes.byref(length),
            ctypes.byref(flags),
            filesystem,
            256,
        ),
        "volume identity unavailable",
    )
    return {
        "root": path.anchor,
        "filesystem": filesystem.value,
        "serial": serial.value,
        "label": label.value,
        "flags": flags.value,
    }


def input_hashes(args, runtime_roots, names):
    return {
        "python": digest(args.python),
        "uv": digest(args.uv),
        "runtime": {str(root): manifest(Path(root)) for root in runtime_roots},
        "source_checkout": hash_files(args.source, names),
        "source_archive": digest(args.output / "source.tar"),
        "source_manifest": digest(args.output / "source-manifest.json"),
        "wheels": manifest(args.wheels),
        "support": {name: digest(HERE / name) for name in SUPPORT},
        "driver": digest(HERE / "screen.py"),
        "runtime_audit": digest(HERE / "runtime_bytecode.py"),
        "build_constraints": digest(args.output / "build-constraints.txt"),
    }


def seal_rows(output, rows):
    for row in rows:
        folder = output / row["folder"]
        for field, filename in (
            ("command", "command.json"),
            ("ownership", "ownership.json"),
            ("native", "native.json"),
            ("headers", "full-headers.json"),
            ("content", "content-record.json"),
            ("source_before", "source-before.json"),
            ("source_after", "source-after.json"),
            ("generated_metadata", "generated-metadata-proof.json"),
        ):
            require(
                digest(folder / filename) == row[field + "_sha256"],
                f"evidence changed after audit: {folder.name}/{filename}",
            )
        archives = load(folder / "content-record.json")
        for name, expected in load(folder / "generated-metadata-proof.json")[
            "bindings"
        ].items():
            require(
                digest(folder / name) == expected, "generated metadata evidence changed"
            )
        require(
            {path.name for path in (folder / "artifacts").iterdir()} == set(archives),
            "retained archive set differs",
        )
        for name, metadata in archives.items():
            path = folder / "artifacts" / name
            require(
                digest(path) == metadata["sha256"]
                and path.stat().st_size == metadata["bytes"],
                f"retained raw archive changed: {folder.name}/{name}",
            )
        source_proof = load(folder / "source-after.json")
        require(
            manifest(folder / "generated") == source_proof["retained_generated"],
            "retained generated files changed",
        )
        ignore = load(folder / "dist-output.json")[".gitignore"]
        require(
            (folder / "dist.gitignore").read_bytes() == b"*"
            and digest(folder / "dist.gitignore") == ignore["sha256"],
            "retained UV ignore changed",
        )
    last = load(output / rows[-1]["folder"] / "source-after.json")
    remaining = last["tracked"] | last["outputs"]
    require(
        manifest(output / "canonical-source") == remaining,
        "last payload changed after audit",
    )


def main(args):
    validate_paths(args)
    require(math.isfinite(args.seconds) and 0 < args.seconds <= 600, "600s maximum")
    args.output.mkdir(parents=True)
    started = time.perf_counter()
    deadline = started + args.seconds
    try:
        require(
            {name: digest(HERE / name) for name in SUPPORT} == SUPPORT,
            "qualified support identity",
        )
        volumes = {
            arm: volume_identity(cache)
            for arm, cache in (("C", args.control_cache), ("D", args.candidate_cache))
        }
        save(args.output / "volumes.json", volumes)
        require(volumes["D"]["filesystem"].upper() == "REFS", "ordinary ReFS required")
        require(
            volumes["C"]["serial"] != volumes["D"]["serial"],
            "separate volumes required",
        )
        require(
            git(args.source, "rev-parse", "HEAD").decode().strip() == REVISION,
            "original source revision",
        )
        require(not git(args.source, "status", "--porcelain"), "clean source required")
        tree = raw_tree(args.source)
        names = set(tree)
        save(args.output / "git-tree.json", tree)
        git(
            args.source,
            "archive",
            "--format=tar",
            f"--output={args.output / 'source.tar'}",
            REVISION,
        )
        initial = args.output / "initial-source"
        extract(args.output / "source.tar", initial)
        canonical = manifest(initial)
        verify_git_payload(initial, tree)
        save(args.output / "source-manifest.json", canonical)
        shutil.rmtree(initial)
        require(
            list(args.wheels.iterdir()) == [args.wheels / WHEEL], "PDM-only wheelhouse"
        )
        require(digest(args.wheels / WHEEL) == WHEEL_SHA, "publisher wheel hash")
        pe_arm64(args.python)
        inherited, handoff = setup_uv_handoff(os.environ)
        save(args.output / "setup-uv-handoff.json", handoff)
        envs = {
            arm: environment(cache, inherited)
            for arm, cache in (("C", args.control_cache), ("D", args.candidate_cache))
        }
        delta_proof = environment_delta(envs["C"], envs["D"])
        identity = subprocess.run(
            [str(args.python), str(HERE / "screen.py"), "--identity"],
            env=envs["C"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        runtime = json.loads(identity.stdout)
        require(
            Path(runtime["executable"]) == args.python, "runtime executable association"
        )
        save(args.output / "runtime-identity.json", runtime)
        save(args.output / "uv-identity.json", attest(args.uv))
        constraints = args.output / "build-constraints.txt"
        shutil.copyfile(HERE / constraints.name, constraints)
        before = input_hashes(args, runtime["runtime_roots"], names)
        save(args.output / "inputs-before.json", before)
        runtime_guard = RuntimeGuard(
            args.python,
            runtime,
            args.output,
            before,
            lambda: {
                key: value
                for key, value in input_hashes(args, [], names).items()
                if key != "runtime"
            },
        )
        argv = command(args, constraints)
        for cache in (args.control_cache, args.candidate_cache):
            cache.mkdir(parents=True)
        save(
            args.output / "protocol.json",
            {
                "schedule": schedule(),
                "argv": argv,
                "environments": {
                    arm: environment_evidence(env) for arm, env in envs.items()
                },
                "environment_delta": delta_proof,
                "arm_labels": {
                    "A": "C control private cache",
                    "B": "D ordinary ReFS NVMe cache",
                },
                "source_policy": "Unmodified complete Git LF archive, 2557 files; no overlay.",
                "source_revision": REVISION,
                "source_archive_sha256": digest(args.output / "source.tar"),
                "support_origins": {
                    "owned_process.py": "pdm-function-attribution-execution-01/capsule/owned-helpers/hobl-complete-ci/owned_process.py",
                    "cli_identity.py": "pdm-function-attribution-execution-01/capsule/owned-helpers/hobl-complete-ci/cli_identity.py",
                    "artifact_gate.py": "hobl-complete-ci/artifact_gate.py",
                    "prepare_uv.py": "hobl-complete-ci/prepare_uv.py",
                    "archive_headers.py": "pipe-matched-ci-readiness/archive_headers.py",
                },
                "command_cap": COMMAND_SECONDS,
                "guardian_allowance": GUARDIAN_ALLOWANCE,
                "guardian_allowance_detail": "Qualified guardian T+25.",
                "audit_reserve": AUDIT_RESERVE,
                "overall_cap": args.seconds,
                "metric": "qualified native UV spawn through owned natural drain",
                "process_identity": "Qualified guardian Receipt.actual_process from held live Popen handle.",
                "generated_metadata_contract": "Only stock generated sdist pyproject mtime/PAX mtime may vary after independent held-UV UTC lifetime proofs; SOURCE_DATE_EPOCH absent; all other fields exact.",
                "runtime_contract": "Future-only: positive bytecode-output audit during WA/WB; full runtime seal after WB; exact measured/final preservation.",
                "limitations": [
                    "C versus D cache placement only, same canonical C source/output/runtime.",
                    "Parent must attest D unused NVMe ordinary ReFS and volume/cache factors.",
                    "No automatic trust/filter changes; no TEMP/HOME/workspace/global changes.",
                    "Warm-cache build-only; OS warmth not controlled; no HOBL/mode/Mac parity.",
                    "Single interleaved job, not whole-job baseline/candidate comparison.",
                    "First control full map is oracle; every field retained; no repairs.",
                    "No Defender causal claim; not the exact IronRDP treatment.",
                    "P55/P74 local transfer hypothesis; old storage epochs remain closed.",
                    "Provision/setup break-even requires parent-provided provisioning cost.",
                ],
            },
        )
        setup_seconds = time.perf_counter() - started
        rows = execute(args, canonical, deadline, envs, argv, runtime_guard)
        audit_started = time.perf_counter()
        after = input_hashes(args, runtime["runtime_roots"], names)
        save(args.output / "inputs-after.json", after)
        runtime_guard.final()
        require(
            {key: value for key, value in before.items() if key != "runtime"}
            == {key: value for key, value in after.items() if key != "runtime"},
            "nonruntime UV/wheel/source/support mutated",
        )
        seal_rows(args.output, rows)
        require(
            digest(constraints) == SUPPORT["build-constraints.txt"],
            "constraints changed",
        )
        require(
            git(args.source, "rev-parse", "HEAD").decode().strip() == REVISION
            and not git(args.source, "status", "--porcelain"),
            "original source changed",
        )
        require(time.perf_counter() <= deadline, "overall deadline exceeded")
        result = summarize(rows)
        save(
            args.output / "result.json",
            {
                "status": "COMPLETE_BUILD_ONLY_SCREEN",
                "baseline": "current first control, not project HOBL",
                "setup_seconds": setup_seconds,
                "final_audit_seconds": time.perf_counter() - audit_started,
                "elapsed_seconds": time.perf_counter() - started,
                "provision_break_even": "NOT_EVALUATED_PARENT_COST_REQUIRED",
                "adoption": False,
                **result,
            },
        )
    except Exception as error:
        save(
            args.output / "result.json",
            {
                "status": "FAILED",
                "error": str(error),
                "elapsed_seconds": time.perf_counter() - started,
            },
        )
        raise


if __name__ == "__main__":
    if sys.argv[1:] == ["--identity"]:
        print(json.dumps(runtime_identity()))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        for key in (
            "python",
            "uv",
            "source",
            "control-cache",
            "candidate-cache",
            "wheels",
            "output",
        ):
            parser.add_argument(
                "--" + key, type=lambda value: Path(value).resolve(), required=True
            )
        parser.add_argument("--seconds", type=float, default=600)
        main(parser.parse_args())
