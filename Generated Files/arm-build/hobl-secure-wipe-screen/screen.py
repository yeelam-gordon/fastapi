"""Finite portable whole-HOBL secure-wipe screen; never dispatches CI."""

import argparse
import dataclasses
import hashlib
import importlib.util
import json
import marshal
import os
import re
import shutil
import stat
import sys
import tarfile
import time
import zipfile
from importlib.metadata import distribution
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
HELPERS = HERE.with_name("hobl-parallel-screen")
COMMON = HERE.with_name("hobl-complete-ci")
sys.path.insert(0, str(HELPERS))
sys.path.insert(0, str(COMMON))
import audit  # noqa: E402
import screen as parallel  # noqa: E402
from native import native_machine  # noqa: E402
from owned_process import run_owned  # noqa: E402

GUARDIAN_SHA = "45d6db4f6452c4f7116ca23c6e2aa74cda90a15548bd5c9bb3b3574973ef458e"
OWNERS = {
    "tests/test_tutorial/test_security/test_tutorial004.py",
    "tests/test_tutorial/test_security/test_tutorial005.py",
}
BUILDER_EVIDENCE = (
    "build-plan.json",
    "source-proof.json",
    "library-resolution.json",
    "binding-proof.json",
    "reference-after.json",
    "compiler-version.stdout.txt",
    "candidate.stdout.txt",
    "reference.stdout.txt",
    "reference-probe.stdout.txt",
    "binding-head.receipt.json",
    "binding-tree.receipt.json",
    "libargon2-head.receipt.json",
    "libargon2-tree.receipt.json",
    "reference-probe.receipt.json",
    "vswhere.receipt.json",
    "compiler-version.receipt.json",
    "preparation.receipt.json",
    "reference.receipt.json",
    "candidate.receipt.json",
)


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def schedule():
    return [
        ("A", False),
        ("B", False),
        ("A", True),
        ("B", True),
        ("B", True),
        ("A", True),
    ]


def snapshot(source):
    hashes = parallel.source_snapshot(source)
    if (source / ".git").is_file():
        hashes[".git"] = digest(source / ".git")
    return {
        name: {
            "sha256": value,
            "mtime_ns": (source / name).stat().st_mtime_ns,
            "size": (source / name).stat().st_size,
            "mode": (source / name).stat().st_mode,
        }
        for name, value in hashes.items()
    }


def admit(bindings, crypto_workers, expected_hash, image, workers):
    expected_workers = {"controller", *(f"gw{i}" for i in range(workers))}
    assert len(bindings) == len(expected_workers)
    assert {row["worker"] for row in bindings} == expected_workers
    observed = set()
    for row in bindings:
        assert not row["dont_write_bytecode"] and row["pycache_prefix"] is None
        assert row["switch_interval"] == 0.005 and row["gil"]
        if row["status"] == "OBSERVED":
            assert (
                row["image_sha256"] == expected_hash
                and Path(row["image_path"]) == image
            )
            if row["worker"] != "controller":
                observed.add(row["worker"])
        else:
            assert (
                row["status"] == "NOT_IMPORTED" and row["worker"] not in crypto_workers
            )
    assert observed and crypto_workers <= observed
    return {
        "crypto_owner_workers": sorted(crypto_workers),
        "observed_workers": sorted(observed),
        "all_worker_receipts": True,
    }


def cache_state(source, manifest, allowed_pids):
    pending = []
    for folder in source.rglob("__pycache__"):
        for path in folder.iterdir():
            if path.name.endswith(".pyc"):
                assert path.is_file() and not path.is_symlink()
                continue
            relative = path.relative_to(source).as_posix()
            info = path.lstat()
            assert stat.S_ISREG(info.st_mode) and not path.is_symlink()
            assert not getattr(info, "st_file_attributes", 0) & 0x400
            for parent in path.parents:
                assert not parent.is_symlink()
                assert not getattr(parent.lstat(), "st_file_attributes", 0) & 0x400
                if parent == source:
                    break
            match = re.fullmatch(
                r"(.+)\."
                + re.escape(sys.implementation.cache_tag)
                + r"-pytest-8\.4\.2\.pyc\.(\d+)",
                path.name,
            )
            assert match and relative not in manifest, "Unknown cache input"
            assert match[2] in allowed_pids, "Unowned PID-temporary cache input"
            original = path.parent.parent / (match[1] + ".py")
            source_name = original.relative_to(source).as_posix()
            assert (
                source_name in manifest
                and digest(original) == manifest[source_name]["sha256"]
            )
            data = path.read_bytes()
            assert (
                16 < len(data) < 10_000_000 and data[:4] == importlib.util.MAGIC_NUMBER
            )
            assert int.from_bytes(data[4:8], "little") == 0
            original_stat = original.stat()
            assert (
                int.from_bytes(data[8:12], "little")
                == int(original_stat.st_mtime) & 0xFFFFFFFF
            )
            assert (
                int.from_bytes(data[12:16], "little")
                == original_stat.st_size & 0xFFFFFFFF
            )
            code = marshal.loads(data[16:])
            assert (
                isinstance(code, type((lambda: None).__code__))
                and Path(code.co_filename) == original
            )
            pending.append(
                {
                    "relative": relative,
                    "sha256": digest(path),
                    "size": info.st_size,
                    "mtime_ns": info.st_mtime_ns,
                    "mode": info.st_mode,
                    "pid": match[2],
                }
            )
    return pending


def candidate_package(proof, output, publisher_hash):
    assert proof["schema"] == 1 and proof["status"] == "PASS_FUNCTIONAL_PACKAGE"
    assert proof["reference_image_sha256"] == publisher_hash
    assert proof["candidate_image_sha256"] != publisher_hash
    assert proof["sdk_version"] == "10.0.26100.0"
    assert proof["target"] == "aarch64-pc-windows-msvc"
    assert Path(proof["candidate_package_root"]) == output / "candidate"
    return output / "candidate" / "_argon2_cffi_bindings"


def export_builder_evidence(builder_output, destination):
    destination.mkdir()
    copied = {}
    for name in BUILDER_EVIDENCE:
        original = builder_output / name
        if not original.exists():
            continue
        info = original.lstat()
        assert stat.S_ISREG(info.st_mode) and not original.is_symlink()
        assert not getattr(info, "st_file_attributes", 0) & 0x400
        target = destination / name
        shutil.copy2(original, target)
        assert digest(original) == digest(target)
        copied[name] = digest(target)
    receipts = {path.name for path in builder_output.glob("*.receipt.json")}
    assert receipts <= copied.keys(), (
        "Builder receipt missing from reviewed export allowlist"
    )
    save(
        destination / "manifest.json",
        {
            "copied_sha256": copied,
            "missing": sorted(set(BUILDER_EVIDENCE) - copied.keys()),
            "scope": "reviewed evidence only; no package/compiler tree/environment dumps",
        },
    )
    return copied


def readiness(source, output, manifest, index, allowed_pids):
    started = time.monotonic()
    ordinary = {
        path: (
            digest(path),
            path.stat().st_size,
            path.stat().st_mtime_ns,
            path.stat().st_mode,
        )
        for folder in source.rglob("__pycache__")
        for path in folder.iterdir()
        if path.is_file() and path.name.endswith(".pyc")
    }
    pending = cache_state(source, manifest, allowed_pids)
    ledger = {
        "policy": "new exact-ledger fixture readiness, not historical CI policy",
        "admitted": pending,
        "moves": [],
    }
    path = output / f"readiness-{index:02}.json"
    save(path, ledger)
    for row in pending:
        original = source / row["relative"]
        assert digest(original) == row["sha256"]
        target = output / "quarantine" / f"before-{index:02}" / row["relative"]
        target.parent.mkdir(parents=True, exist_ok=True)
        assert not target.exists()
        original.rename(target)
        info = target.stat()
        assert digest(target) == row["sha256"] and info.st_size == row["size"]
        assert info.st_mtime_ns == row["mtime_ns"] and info.st_mode == row["mode"]
        ledger["moves"].append(row["relative"])
        save(path, ledger)
    ledger["seconds_excluded"] = time.monotonic() - started
    assert all(
        (
            digest(path),
            path.stat().st_size,
            path.stat().st_mtime_ns,
            path.stat().st_mode,
        )
        == metadata
        for path, metadata in ordinary.items()
    )
    ledger["ordinary_completed_caches_preserved"] = len(ordinary)
    save(path, ledger)
    return ledger


def archives(folder, source, manifest):
    artifacts = folder / "artifacts"
    assert (artifacts / ".gitignore").read_bytes() == b"*"
    assert len(list(artifacts.iterdir())) == 3
    verification = folder / "verification"
    verification.mkdir()
    for path in artifacts.iterdir():
        if path.name.endswith((".whl", ".tar.gz")):
            shutil.copyfile(path, verification / path.name)
    canonical = {name: row["sha256"] for name, row in manifest.items()}
    proof = audit.artifact_set(verification, source, canonical)
    result = {"sdist": {}, "wheel": {}}
    with tarfile.open(next(verification.glob("*.tar.gz"))) as archive:
        for entry in archive:
            assert entry.isfile() and entry.name not in result["sdist"]
            result["sdist"][entry.name] = {
                "sha256": hashlib.sha256(archive.extractfile(entry).read()).hexdigest(),
                **{
                    key: getattr(entry, key)
                    for key in (
                        "mode",
                        "uid",
                        "gid",
                        "uname",
                        "gname",
                        "size",
                        "mtime",
                        "linkname",
                        "pax_headers",
                        "devmajor",
                        "devminor",
                    )
                },
                "type": entry.type.decode(),
            }
    with zipfile.ZipFile(next(verification.glob("*.whl"))) as archive:
        for entry in archive.infolist():
            result["wheel"][entry.filename] = {
                "sha256": hashlib.sha256(archive.read(entry)).hexdigest(),
                **{
                    key: getattr(entry, key)
                    for key in (
                        "date_time",
                        "compress_type",
                        "create_system",
                        "create_version",
                        "extract_version",
                        "flag_bits",
                        "volume",
                        "internal_attr",
                        "external_attr",
                        "file_size",
                        "CRC",
                    )
                },
                "extra": entry.extra.hex(),
                "comment": entry.comment.hex(),
            }
    result = json.loads(json.dumps(result))
    save(folder / "archive-inventory.json", result)
    assert len(result["sdist"]) == 1196 and len(result["wheel"]) == 58
    save(
        folder / "archive-proof.json",
        {
            name: {"sha256": value["sha256"], "members": len(value["members"])}
            for name, value in proof.items()
        },
    )
    return result


def _command(context, label, argv, cwd, cap, overrides=None):
    context.result["stage"] = label
    save(context.output / "result.json", context.result)
    assert time.monotonic() + cap + 5 < context.deadline, "Deadline admission"
    receipt = run_owned(
        list(map(str, argv)),
        cwd=str(cwd),
        env=overrides or context.env,
        stdout_path=context.output / (label + ".stdout"),
        stderr_path=context.output / (label + ".stderr"),
        timeout=cap,
        native_clock=True,
    )
    save(context.output / (label + ".receipt.json"), dataclasses.asdict(receipt))
    assert receipt.succeeded, label + ": strict natural drain failed; no retry"
    return receipt.command_wall


def run_payload(context, index, arm, measured):
    """Run one complete payload using an already validated private context."""
    args, output, source = context.args, context.output, context.source
    before, env, images, result = (
        context.before,
        context.env,
        context.images,
        context.result,
    )
    folder = output / f"payload-{index:02}-{arm}"
    folder.mkdir()
    result["stage"] = f"{index:02}-readiness"
    readiness(source, output, before, index, context.owned_pids)
    assert snapshot(source) == before
    scratch = folder / "temp"
    scratch.mkdir()
    trial = dict(
        env,
        PYTHONPATH=os.pathsep.join(
            map(
                str,
                (HELPERS, HERE, images[arm].parent.parent, source, source / "docs_src"),
            )
        ),
        HOBL_BINDING_SHA256=digest(images[arm]),
        CORRECTNESS_OUTPUT=str(folder),
        COVERAGE_FILE=str(folder / ".coverage"),
        TEMP=str(scratch),
        TMP=str(scratch),
        TMPDIR=str(scratch),
    )
    build = [
        args.uv,
        "build",
        "--python",
        sys.executable,
        "--no-python-downloads",
        "--default-index",
        "https://pypi.org/simple",
        "--build-constraints",
        output / "build-constraints.txt",
        "--out-dir",
        folder / "artifacts",
    ]
    test = parallel.test_command(
        SimpleNamespace(output=output, workers=args.workers), folder, "parallel"
    )
    test[0] = sys.executable
    test.extend(["-p", "binding_runtime"])
    save(folder / "commands.json", {"build": list(map(str, build)), "test": test})
    build_seconds = _command(context, f"{index:02}-build", build, source, 60, trial)
    log = (output / f"{index:02}-build.stderr").read_text(encoding="utf-8")
    assert (
        "Building source distribution" in log
        and "Building wheel from source distribution" in log
    )
    result["stage"] = f"{index:02}-archive-before-tests"
    audit_start = time.monotonic()
    inventory = archives(folder, source, before)
    if context.inventories is None:
        context.inventories = inventory
    assert inventory == context.inventories
    archive_seconds = time.monotonic() - audit_start
    test_seconds = _command(context, f"{index:02}-test", test, source, 150, trial)
    result["stage"] = f"{index:02}-case-coverage-audit"
    collected = [load(path) for path in folder.glob("collection-gw*.json")]
    if context.cases is None:
        assert collected and len(collected[0]) == 2643
        context.cases = [node.rsplit("@", 1)[0] for node in collected[0]]
    outcomes, identities = audit.execution(folder, context.cases, True, args.workers)
    if context.outcomes_reference is None:
        context.outcomes_reference = outcomes
    assert outcomes == context.outcomes_reference
    counts = audit.tiny_outcome(folder)
    mapping = load(folder / "raw-to-canonical.json")
    crypto_workers = set()
    for path in folder.glob("phases-gw*.jsonl"):
        for line in path.read_text().splitlines():
            phase = json.loads(line)
            if (
                phase["when"] == "call"
                and mapping[phase["nodeid"]].split("::")[0] in OWNERS
            ):
                crypto_workers.add(phase["worker"])
    bindings = [
        load(folder / ("binding-" + worker + ".json"))
        for worker in ["controller", *(f"gw{i}" for i in range(args.workers))]
    ]
    save(
        folder / "binding-admission.json",
        admit(bindings, crypto_workers, digest(images[arm]), images[arm], args.workers),
    )
    context.coverages[index] = audit.combined(folder, identities, source)
    context.owned_pids = {
        str(row["pid"]) for row in identities if row["worker"] != "controller"
    }
    assert snapshot(source) == before
    row = {
        "index": index,
        "arm": arm,
        "measured": measured,
        "build_seconds": build_seconds,
        "test_seconds": test_seconds,
        "whole_seconds": build_seconds + test_seconds,
        "counts": counts,
        "coverage_files": 863,
        "coverage_contexts": 1409,
        "sdist_members": 1196,
        "wheel_members": 58,
        "archive_audit_seconds_excluded": archive_seconds,
    }
    result["rows"].append(row)
    save(output / "result.json", result)
    return row


def execute(args):
    started = time.monotonic()
    deadline = started + 480
    output, source = args.output.resolve(), args.source.resolve()
    assert not output.exists(), "Output must be new; no retry"
    output.mkdir(parents=True)
    result = {
        "status": "STOP",
        "scope": "Windows treatment / macOS NOOP noise control",
        "rows": [],
        "main_goal": "OPEN",
        "mac_is_noop": sys.platform == "darwin",
    }
    before = None
    references = None
    try:
        assert sys.platform in {"win32", "darwin"}
        assert digest(COMMON / "owned_process.py") == GUARDIAN_SHA
        assert not sys.dont_write_bytecode and sys.pycache_prefix is None
        assert sys.getswitchinterval() == 0.005
        identity = parallel.identity(SimpleNamespace(workers=args.workers))
        save(output / "native-identity.json", identity)
        assert args.workers == (4 if sys.platform == "win32" else 3)
        assert os.cpu_count() == args.workers
        before = snapshot(source)
        save(output / "source-freeze.json", before)
        prepared = args.prepared.resolve()
        assert load(prepared / "preparation.json")["status"] == "complete"
        assert digest(args.uv) == load(prepared / "uv-identity.json")["sha256"]
        native_machine(args.uv)
        assert load(prepared / "source-before.json") == {
            name: row["sha256"] for name, row in before.items() if name != ".git"
        }
        for name in ("full-coverage.toml", "build-constraints.txt"):
            shutil.copyfile(prepared / name, output / name)
        site = Path(distribution("argon2-cffi-bindings").locate_file(""))
        references = {
            str(path.relative_to(site)): digest(path)
            for package in ("_argon2_cffi_bindings", "argon2", "pwdlib")
            for path in (site / package).rglob("*")
            if path.is_file()
        }
        save(output / "reference-before.json", references)
        save(
            output / "input-plan.json",
            {
                "schedule": schedule(),
                "workers": args.workers,
                "deadline_seconds": 480,
                "script_sha256": digest(Path(__file__)),
                "plugin_sha256": digest(HERE / "binding_runtime.py"),
                "guardian_sha256": GUARDIAN_SHA,
                "helper_sha256": {
                    name: digest(HELPERS / name)
                    for name in (
                        "screen.py",
                        "bootstrap.py",
                        "observer.py",
                        "resource_observer.py",
                        "identity_map.py",
                        "native.py",
                        "audit.py",
                        "full-coverage.toml",
                        "requirements.txt",
                        "source-manifest.json",
                    )
                },
                "uv_sha256": digest(args.uv),
                "sdk": "10.0.26100.0",
                "source_revision": "864b569cf8453654fc3bc2c64108c0f644e2918c",
                "bindings_revision": "fb50afcbb80aee5e87d6f8b1d15e7238321387c9",
                "vendor_revision": "f57e61e19229e23c4445b85494dbf7c07de721cb",
            },
        )
        env = os.environ.copy()
        for key in list(env):
            if key.startswith(
                ("PYTHON", "PYTEST", "COVERAGE", "COV_CORE", "UV_", "PIP_")
            ):
                del env[key]
        env.update(
            PYTHONNOUSERSITE="1",
            PYTHONIOENCODING="utf-8",
            CONTEXT="",
            SOURCE_DATE_EPOCH="1700000000",
            CORRECTNESS_SOURCE=str(source),
            CHECK_COVERAGE="1",
            CHECK_FIXTURE="1",
            FULL_SUITE="1",
            UV_CACHE_DIR=str(prepared / "uv-cache"),
        )

        context = SimpleNamespace(
            args=args,
            output=output,
            source=source,
            before=before,
            env=env,
            result=result,
            deadline=deadline,
        )

        publisher = site / "_argon2_cffi_bindings"
        image_name = Path(
            next(
                path
                for path in publisher.iterdir()
                if path.name.startswith("_ffi.") and path.suffix in {".pyd", ".so"}
            ).name
        )
        publisher_hash = digest(publisher / image_name)
        candidate = publisher
        if sys.platform == "win32":
            assert args.bindings_source is not None
            builder_output = output / "binding-build"
            try:
                _command(
                    context,
                    "binding-build",
                    [
                        sys.executable,
                        HERE / "bindings.py",
                        "--source",
                        args.bindings_source,
                        "--python",
                        sys.executable,
                        "--output",
                        builder_output,
                        "--sdk-version",
                        "10.0.26100.0",
                    ],
                    HERE,
                    120,
                )
            finally:
                if builder_output.exists():
                    export_builder_evidence(builder_output, output / "builder-evidence")
            proof = load(builder_output / "binding-proof.json")
            candidate = candidate_package(proof, builder_output, publisher_hash)
            assert digest(candidate / image_name) == proof["candidate_image_sha256"]
            assert proof["candidate_image_sha256"] != publisher_hash
            save(
                output / "binding-proof.json",
                {
                    key: proof[key]
                    for key in (
                        "schema",
                        "status",
                        "reference_image_sha256",
                        "candidate_image_sha256",
                        "sdk_version",
                        "compiler",
                        "target",
                    )
                },
            )
        images = {}
        for arm, package in (("A", publisher), ("B", candidate)):
            destination = output / (arm + "-root") / "_argon2_cffi_bindings"
            shutil.copytree(package, destination)
            images[arm] = destination / image_name
            native_machine(images[arm])
        save(
            output / "plan.json",
            {
                "schedule": schedule(),
                "workers": args.workers,
                "runtime": "native3.13.15/default bytecode/5ms normal GIL/no JIT",
                "mac_treatment": "NOOP mirrored publisher",
                "image_sha256": {arm: digest(path) for arm, path in images.items()},
                "script_sha256": digest(Path(__file__)),
                "plugin_sha256": digest(HERE / "binding_runtime.py"),
                "guardian_sha256": GUARDIAN_SHA,
                "caps": {"build": 60, "test": 150, "total": 480},
                "gate": "Windows both order pairs >=0.5s AND >=2%; all contracts; no parity/adoption claim",
                "fixture": "new explicit PID-temp quarantine; initially none; only current owned worker IDs later",
            },
        )
        coverages = {}
        context.images = images
        context.cases = None
        context.outcomes_reference = None
        context.inventories = None
        context.coverages = coverages
        context.owned_pids = set()
        for index, (arm, measured) in enumerate(schedule(), 1):
            observed = [row["whole_seconds"] for row in result["rows"]]
            assert (
                time.monotonic() + (7 - index) * (max(observed, default=45) + 10) + 65
                < deadline
            )
            run_payload(context, index, arm, measured)
        for label, control, candidate_index in (("AB", 3, 4), ("BA", 6, 5)):
            comparison = audit.coverage_compare(
                coverages[control],
                coverages[candidate_index],
                source,
                output / "full-coverage.toml",
            )
            save(output / (label + "-coverage-delta.json"), comparison)
            assert comparison["reportable_removed_triples"] == 0
        result["pairs"] = {}
        for label, control, treatment in (("AB", 2, 3), ("BA", 5, 4)):
            left, right = (
                result["rows"][control]["whole_seconds"],
                result["rows"][treatment]["whole_seconds"],
            )
            result["pairs"][label] = {
                "publisher_seconds": left,
                "candidate_seconds": right,
                "saving_seconds": left - right,
                "saving_fraction": (left - right) / left,
            }
        result["windows_value_gate"] = not result["mac_is_noop"] and all(
            row["saving_seconds"] >= 0.5 and row["saving_fraction"] >= 0.02
            for row in result["pairs"].values()
        )
        result["status"] = "COMPLETE_COHORT_NOT_ADOPTION"
    except Exception as error:
        result["failure"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        if before is not None:
            try:
                result["source_unchanged"] = snapshot(source) == before
            except (AssertionError, OSError) as error:
                result["source_unchanged"] = False
                result["preservation_failure"] = str(error)
        if references is not None:
            after = {
                str(path.relative_to(site)): digest(path)
                for package in ("_argon2_cffi_bindings", "argon2", "pwdlib")
                for path in (site / package).rglob("*")
                if path.is_file()
            }
            save(output / "reference-after.json", after)
            result["reference_unchanged"] = references == after
        if not result.get("source_unchanged", True) or not result.get(
            "reference_unchanged", True
        ):
            result["status"] = "STOP_PRESERVATION_FAILURE"
        result["elapsed_seconds"] = time.monotonic() - started
        save(output / "result.json", result)
        save(
            output / "summary.json",
            {
                key: result[key]
                for key in (
                    "status",
                    "scope",
                    "mac_is_noop",
                    "rows",
                    "main_goal",
                    "elapsed_seconds",
                    "pairs",
                    "windows_value_gate",
                )
                if key in result
            },
        )
        assert result.get("source_unchanged", True) and result.get(
            "reference_unchanged", True
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "output", "uv", "prepared"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=[3, 4], required=True)
    parser.add_argument("--bindings-source", type=Path)
    execute(parser.parse_args())
