"""Named shared complete-build collectors; no standalone execution authority."""

import ctypes
import dataclasses
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
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
from metadata_time import utc_window_ns  # noqa: E402

REVISION = "864b569cf8453654fc3bc2c64108c0f644e2918c"


WHEEL = "pdm_backend-2.5.0-py3-none-any.whl"


WHEEL_SHA = "5b8746b567a16a1fd506ce66ee28e89d46374526f52238aa1b96cc2c08245c63"


COMMAND_SECONDS = 30


GUARDIAN_ALLOWANCE = 25


AUDIT_RESERVE = 45
SOURCE_RESET_POLICY = {
    "platform": "win32",
    "winerror": 32,
    "additional_filesystem_attempts": 3,
    "delays_ms": [50, 100, 200],
    "maximum_planned_wait_ms": 350,
    "budget_scope": "Per reset, shared across every onexc callback.",
    "scope": "Only failing os.unlink/os.rmdir within the owned canonical-source; outside native clocks; no build/controller retry.",
}
ROW_EVIDENCE = (
    ("command", "command.json"),
    ("ownership", "ownership.json"),
    ("native", "native.json"),
    ("headers", "full-headers.json"),
    ("content", "content-record.json"),
    ("source_before", "source-before.json"),
    ("source_after", "source-after.json"),
    ("generated_metadata", "generated-metadata-proof.json"),
    ("source_reset", "source-reset.json"),
)


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
    # C/D are the unchanged RuntimeGuard's phase tokens, never cache treatments.
    return [("C", False, "WA"), ("D", False, "WB")] + [
        ("R", True, sample) for sample in range(1, 7)
    ]


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
            key: env[key]
            for key in ("UV_CACHE_DIR", "TEMP", "TMP", "TMPDIR")
            if key in env
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
    require(sys.platform in ("win32", "darwin"), "native Windows/Darwin only")
    require(sys.version_info[:3] == (3, 13, 15), "Python 3.13.15 required")
    require(
        sysconfig.get_platform() == "win-arm64"
        if sys.platform == "win32"
        else sysconfig.get_platform().endswith("-arm64"),
        "native ARM64 runtime",
    )
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
    if sys.platform == "darwin":
        import platform

        require(platform.machine() == "arm64", "native Mac ARM64")
        macho_arm64(Path(sys.executable))
        return {
            "executable": sys.executable,
            "version": sys.version,
            "platform": sysconfig.get_platform(),
            "gil": True,
            "jit": False,
            "bytecode": "default",
            "cpu_count": os.cpu_count(),
            "runtime_roots": list(dict.fromkeys([sys.prefix, sys.base_prefix])),
        }
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
                    (source / name).read_bytes() == pdm_ignore_bytes(sys.platform),
                    "native stock PDM ignore file",
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


def generated_metadata_proof(inventory, folder, *, platform=None):
    platform = sys.platform if platform is None else platform
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
        all(type(value) is int for value in (start, end, process["pid"]))
        and 0 < end - start <= COMMAND_SECONDS * 1_000_000_000
        and process["pid"] > 0,
        "invalid generated metadata native clock/identity",
    )
    require(
        native["start_ns"] == start
        and native["end_ns"] == end
        and associated_process(process, native, command_row["argv"][0], platform)
        and native["argv"] == command_row["argv"]
        and command_row["argv"][1] == "build"
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
    lower, upper = utc_window_ns(process, start, end, platform=platform)
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
        "native_QPC_ns" if platform == "win32" else "native_monotonic_ns": [start, end],
        "UTC_window_ns": [lower, upper],
        "platform": platform,
        "clock_basis": "Explicit platform birth UTC plus owned native duration; Darwin quantization only.",
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
    from archive_headers import NATIVE_EXECUTABLE_SCRIPTS

    require(
        all(
            member["create_system"] == (0 if sys.platform == "win32" else 3)
            for member in inventory["wheel"].values()
        )
        and all(
            inventory["sdist"][name]["mode"]
            == (0o644 if sys.platform == "win32" else 0o755)
            for name in NATIVE_EXECUTABLE_SCRIPTS
        ),
        "declared native archive header policy",
    )
    require_generated_headers(inventory, reference, folder, reference_folder)
    content = artifact_set(artifacts, source, canonical)
    return inventory, content


def reset_path(path, root):
    require(
        path.is_absolute() and ".." not in path.parts and path.is_relative_to(root),
        "source reset outside owned root",
    )
    for ancestor in (path, *path.parents):
        require(
            not ancestor.is_symlink() and not ancestor.is_junction(),
            "source reset link/junction",
        )
        if ancestor.exists():
            require(
                not (getattr(ancestor.lstat(), "st_file_attributes", 0) & 0x400),
                "source reset reparse point",
            )
    require(path.resolve(strict=False) == path, "source reset noncanonical path")


def reset_error(error):
    # Code locations avoid source-line readers and lazy imports after the WB seal.
    frames, current = [], error.__traceback__
    while current is not None:
        frames.append(
            {
                "filename": current.tb_frame.f_code.co_filename,
                "line": current.tb_lineno,
                "function": current.tb_frame.f_code.co_name,
            }
        )
        current = current.tb_next
    return {
        "type": type(error).__name__,
        "message": str(error),
        "repr": repr(error),
        "errno": getattr(error, "errno", None),
        "winerror": getattr(error, "winerror", None),
        "filename": getattr(error, "filename", None),
        "traceback_frames": frames,
    }


def verify_row_evidence(output, row):
    folder = output / row["folder"]
    require(folder.parent == output, "row evidence outside output")
    for field, filename in ROW_EVIDENCE:
        require(
            digest(folder / filename) == row[field + "_sha256"],
            f"evidence changed after audit: {folder.name}/{filename}",
        )


def reset_source(output, folder, rows, receipt, deadline):
    live = output / "canonical-source"
    require(
        output.is_absolute()
        and output.resolve(strict=True) == output
        and len(rows) < len(schedule())
        and folder == output / f"build-{len(rows):02}-{schedule()[len(rows)][0]}",
        "exact owned source-reset namespace required",
    )
    reset_path(folder, output)
    record = {
        "policy": SOURCE_RESET_POLICY,
        "platform": sys.platform,
        "path": str(live),
        "started_ns": time.perf_counter_ns(),
        "completed": False,
        "performed": False,
        "extra_attempts": 0,
        "planned_wait_ms": 0,
        "previous_proved_rows": len(rows),
        "events": [],
    }
    log = folder / "source-reset.json"
    save(log, record)

    def onexc(function, name, error):
        event = {
            "action": getattr(function, "__name__", type(function).__name__),
            "path": str(name),
            "at_ns": time.perf_counter_ns(),
            "initial_error": reset_error(error),
            "attempts": [],
        }
        record["events"].append(event)
        save(log, record)
        while True:
            if (
                sys.platform != "win32"
                or not isinstance(error, OSError)
                or type(getattr(error, "winerror", None)) is not int
                or error.winerror != 32
            ):
                raise error
            require(
                function is os.unlink or function is os.rmdir,
                "source reset incorrect deletion callback",
            )
            path = Path(name)
            reset_path(path, live)
            require(
                path != live or function is os.rmdir, "source root unlink forbidden"
            )
            require(
                path.is_dir() if function is os.rmdir else path.is_file(),
                "source reset callback target type",
            )
            target_identity = (path.stat().st_dev, path.stat().st_ino)
            if "target_identity" not in event:
                event["target_identity"] = target_identity
            require(
                target_identity == event["target_identity"],
                "source reset target identity changed",
            )
            require(
                (output.stat().st_dev, output.stat().st_ino) == output_identity
                and (live.stat().st_dev, live.stat().st_ino) == live_identity,
                "source reset root identity changed",
            )
            if (
                record["extra_attempts"]
                == SOURCE_RESET_POLICY["additional_filesystem_attempts"]
            ):
                raise error
            pause_ms = SOURCE_RESET_POLICY["delays_ms"][record["extra_attempts"]]
            room(
                deadline,
                COMMAND_SECONDS + GUARDIAN_ALLOWANCE + AUDIT_RESERVE + pause_ms / 1000,
            )
            attempt = {
                "number": record["extra_attempts"] + 1,
                "delay_ms": pause_ms,
                "wait_start_ns": time.perf_counter_ns(),
                "action_called": False,
                "completed": False,
            }
            event["attempts"].append(attempt)
            record["planned_wait_ms"] += pause_ms
            save(log, record)
            time.sleep(pause_ms / 1000)
            attempt["wait_end_ns"] = time.perf_counter_ns()
            attempt["delay_monotonic_ns"] = (
                attempt["wait_end_ns"] - attempt["wait_start_ns"]
            )
            room(deadline, COMMAND_SECONDS + GUARDIAN_ALLOWANCE + AUDIT_RESERVE)
            reset_path(path, live)
            require(
                (path.stat().st_dev, path.stat().st_ino) == event["target_identity"],
                "source reset target identity changed",
            )
            require(
                (output.stat().st_dev, output.stat().st_ino) == output_identity
                and (live.stat().st_dev, live.stat().st_ino) == live_identity,
                "source reset root identity changed",
            )
            record["extra_attempts"] += 1
            attempt["action_called"] = True
            attempt["action_start_ns"] = time.perf_counter_ns()
            try:
                function(name)
            except OSError as next_error:
                attempt["error"] = reset_error(next_error)
                error = next_error
            else:
                attempt["completed"] = True
                return
            finally:
                attempt["action_end_ns"] = time.perf_counter_ns()
                save(log, record)

    try:
        reset_path(live, output)
        output_identity = (output.stat().st_dev, output.stat().st_ino)
        if live.exists():
            require(
                rows
                and all(row["status"] == "VALID" for row in rows)
                and isinstance(receipt, owned_process.Receipt)
                and receipt.succeeded,
                "source reset requires fully proved rows and previous naturally drained receipt",
            )
            previous = output / rows[-1]["folder"]
            reset_path(previous, output)
            verify_row_evidence(output, rows[-1])
            require(
                load(previous / "ownership.json")
                == json.loads(json.dumps(dataclasses.asdict(receipt))),
                "source reset previous receipt binding differs",
            )
            record["previous_ownership_sha256"] = rows[-1]["ownership_sha256"]
            record["previous_receipt_succeeded"] = True
            require(live.is_dir(), "source reset requires owned directory")
            live_identity = (live.stat().st_dev, live.stat().st_ino)
            record["performed"] = True
            save(log, record)
            shutil.rmtree(live, onexc=onexc)
            require(
                not live.exists() and not live.is_symlink() and not live.is_junction(),
                "source reset incomplete",
            )
        else:
            require(
                not rows and receipt is None,
                "source reset unexpectedly missing previous source",
            )
        record["completed"] = True
    finally:
        record["ended_ns"] = time.perf_counter_ns()
        if sys.exception() is not None:
            record["terminal_error"] = reset_error(sys.exception())
        save(log, record)


def execute(args, canonical, deadline, envs, argv, runtime_guard):
    rows, reference, reference_folder, receipt = [], None, None, None
    live = args.output / "canonical-source"
    for index, (arm, measured, pair) in enumerate(schedule()):
        row_started = time.perf_counter()
        room(deadline, COMMAND_SECONDS + GUARDIAN_ALLOWANCE + AUDIT_RESERVE)
        folder = args.output / f"build-{index:02}-{arm}"
        folder.mkdir()
        runtime_guard.before_row(arm, measured, pair, folder)
        reset_source(args.output, folder, rows, receipt, deadline)
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
            associated_process(
                receipt.actual_process, native, str(args.uv), sys.platform
            ),
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
                "prelaunch_seconds": started - row_started,
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
                "source_reset_sha256": digest(folder / "source-reset.json"),
                "generated_metadata_sha256": digest(
                    folder / "generated-metadata-proof.json"
                ),
            }
        )
        save(args.output / "rows.json", rows)
        room(deadline, GUARDIAN_ALLOWANCE)
    return rows


def pdm_ignore_bytes(platform):
    require(platform in ("win32", "darwin"), "explicit ignore platform")
    require(
        digest(HERE / "pdm-hooks-base.source")
        == "36c34abc6bd9e204a647d9b16c0edf37465865c37689afb216bd7d0aa6a9bc41",
        "pinned stock backend source",
    )
    return b"*\r\n" if platform == "win32" else b"*\n"


def associated_process(process, native, executable, platform):
    require(platform in ("win32", "darwin"), "explicit identity platform")
    keys = (
        ("pid", "image", "birth_filetime")
        if platform == "win32"
        else (
            "pid",
            "parent_pid",
            "observed_executable",
            "executable",
            "start_unix_interval_us",
        )
    )
    require(set(process) == set(keys), "native identity schema")
    require(type(process["pid"]) is int and process["pid"] > 0, "native PID")
    if platform == "darwin":
        require(
            type(process["parent_pid"]) is int
            and process["parent_pid"] > 0
            and process["parent_pid"] != process["pid"]
            and Path(process["observed_executable"]).is_absolute()
            and Path(process["observed_executable"]).resolve(strict=True)
            == Path(process["executable"])
            == Path(executable).resolve(strict=True),
            "Darwin raw/canonical/parent association",
        )
    else:
        require(
            Path(process["image"]).is_absolute()
            and Path(process["image"]) == Path(executable),
            "Windows image association",
        )
    return all(native.get(key) == process[key] for key in keys)


def macho_arm64(path):
    # Thin native ARM64 only: reject fat/x86 images instead of trusting a suffix.
    data = path.read_bytes()
    require(
        len(data) >= 32
        and data[:4] == b"\xcf\xfa\xed\xfe"
        and struct.unpack_from("<I", data, 4)[0] == 0x0100000C
        and struct.unpack_from("<I", data, 12)[0] == 2,
        "native ARM64 Mach-O executable",
    )


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


def seal_rows(output, rows):
    for row in rows:
        folder = output / row["folder"]
        verify_row_evidence(output, row)
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
