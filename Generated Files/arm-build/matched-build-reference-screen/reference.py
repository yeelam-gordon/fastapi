"""Unadmitted, source-bound native ARM complete-build reference coordinator."""

import argparse
import hashlib
import json
import math
import shutil
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import screen as shared  # noqa: E402
from runtime_bytecode import RuntimeGuard  # noqa: E402
from runtime_links import ARCHIVE_SHA256, DarwinRuntimeLinks, runtime_input_hashes  # noqa: E402

VERSION = 3
UV_REVISION = "329bf9448afd9f9088d14a4d57fbc61eb454f117"
QUALIFIED_UV = {
    "win32": {
        "sha256": "ec27977d62b5f6091bce410a8e69d40d07541803314e0120905c0ad0affaa5cc",
        "qualification_source": "local-inputs.source",
    },
    "darwin": {
        "sha256": "3996850e6d85e60b0142b40af4bd984822d65f736b52209921c47312450685cb",
        "qualification_source": "mac-uv-identity.source",
    },
}
PROFILES = {
    "HOSTED_WINDOWS_REFERENCE": {
        "platform": "win32",
        "checkout_drive": "C:",
        "cache_drive": "D:",
        "classification": "HOSTED_WINDOWS_REFERENCE",
    },
    "LOCAL_WINDOWS_READINESS": {
        "platform": "win32",
        "checkout_drive": "Q:",
        "cache_drive": "Q:",
        "classification": "LOCAL_READINESS_NONCOMPARATIVE",
    },
    "DARWIN_REFERENCE": {
        "platform": "darwin",
        "classification": "DARWIN_REFERENCE",
    },
}
QUESTION = {
    "revision": shared.REVISION,
    "blobs": 2557,
    "uv": "0.13.6",
    "uv_source_revision": UV_REVISION,
    "qualified_uv": QUALIFIED_UV,
    "profiles": PROFILES,
    "local_scope": "LOCAL_READINESS_NONCOMPARATIVE; no hosted/Mac/gain claim",
    "entry_prerequisites": "Target ISA/runtime/bootstrap only; coordinator/libproc/archive acceptance must be observed in WA/WB, not supplied as prior success.",
    "python": "3.13.15 normal GIL/no JIT/default bytecode",
    "backend": "PDM 2.5.0 pinned wheel",
    "backend_wheel_sha256": shared.WHEEL_SHA,
    "darwin_sdk_archive_sha256": ARCHIVE_SHA256,
    "darwin_sdk_archive_bytes": 25207202,
    "runtime_profile": "separate declared SDK plus patch-request venv; no bare substitution",
    "metadata_profile": "stock default timestamps; reject SOURCE_DATE_EPOCH; exact remaining headers",
    "semantics": "isolated offline full sdist then wheel-from-sdist",
    "schedule": shared.schedule(),
    "max_build_commands": 8,
    "controller_cap_seconds": 600,
    "command_cap_seconds": 30,
    "cleanup_reserve_seconds": 25,
    "audit_reserve_seconds": 45,
    "source_reset_policy": shared.SOURCE_RESET_POLICY,
    "cache": "one fixed private cache under the explicit profile; no default/fallback",
    "source": "fixed raw Git extraction cwd/output; Windows always C, separate audit checkout per profile; all rows retained; no tests",
}


def qualified_uv_identity(executable, *, platform):
    shared.require(platform in QUALIFIED_UV, "explicit qualified UV platform")
    shared.require(
        executable.is_absolute()
        and executable.is_file()
        and not executable.is_symlink()
        and not executable.is_junction(),
        "regular absolute native UV executable",
    )
    expected = QUALIFIED_UV[platform]
    actual = shared.digest(executable)
    shared.require(
        actual == expected["sha256"], "qualified UV binary/source identity differs"
    )
    if platform == "win32":
        shared.pe_arm64(executable)
    else:
        shared.macho_arm64(executable)
    return {
        "executable": str(executable),
        "sha256": actual,
        "qualified_version": "0.13.6",
        "qualified_source_revision": UV_REVISION,
        "native_arm64_static": True,
        "version_observed": False,
        "identity_basis": "Exact independently qualified bytes and static ISA; version/source binding retained, not freshly executed.",
        "qualification_source": expected["qualification_source"],
        "qualification_source_sha256": shared.digest(
            HERE / expected["qualification_source"]
        ),
    }


def selected_profile(configuration):
    name = configuration.get("profile")
    shared.require(
        name in PROFILES and PROFILES[name]["platform"] == configuration["platform"],
        "explicit platform-bound profile required",
    )
    return PROFILES[name]


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def source_preflight():
    pins = shared.load(HERE / "SOURCEPINS.json")
    shared.require(
        pins["version"] == VERSION
        and pins["question"] == json.loads(json.dumps(QUESTION)),
        "source protocol differs",
    )
    shared.require(
        set(pins["files"])
        == {
            path.name
            for path in HERE.iterdir()
            if path.suffix in (".py", ".source")
            or path.name in ("build-constraints.txt", "ORIGINS.json")
        },
        "source pin closure differs",
    )
    shared.require(
        all(
            shared.digest(HERE / name) == digest
            for name, digest in pins["files"].items()
        ),
        "source pins differ",
    )
    return shared.digest(HERE / "SOURCEPINS.json")


def admission_check(admission, configuration, source_pin, now):
    selected_profile(configuration)
    shared.require(
        type(now) in (float, int) and math.isfinite(now), "finite current UTC"
    )
    issued, expires = admission["issued_unix"], admission["expires_unix"]
    shared.require(
        all(
            type(value) in (float, int) and math.isfinite(value)
            for value in (issued, expires)
        )
        and issued <= now < expires
        and 0 < expires - issued <= 600,
        "fresh finite admission required",
    )
    shared.require(
        admission["authority"] == "separate-parent-native-readiness"
        and admission["version"] == VERSION
        and admission["profile"] == configuration["profile"]
        and admission["sourcepins_sha256"] == source_pin
        and admission["question_sha256"] == canonical_hash(QUESTION)
        and admission["configuration_sha256"] == canonical_hash(configuration)
        and admission["max_build_commands"] == 8
        and admission["bootstrap_receipt_qualified"] is True
        and admission["target_isa_runtime_prerequisites_qualified"] is True
        and "native_platform_qualified" not in admission
        and admission["fixed_paths_and_cache_qualified"] is True,
        "separate source-bound admission required",
    )
    shared.require(
        type(configuration["seconds"]) in (int, float)
        and math.isfinite(configuration["seconds"])
        and 0 < configuration["seconds"] <= min(600, expires - now),
        "finite controller cap within admission",
    )


def configuration_paths(config):
    profile = selected_profile(config)
    names = (
        "source",
        "python",
        "uv",
        "cache",
        "wheels",
        "output",
        "sdk_root",
        "venv_root",
    )
    args = argparse.Namespace(**{name: Path(config[name]) for name in names})
    shared.require(
        config["platform"] == sys.platform in ("win32", "darwin"),
        "explicit host platform",
    )
    for path in vars(args).values():
        shared.require(
            path.is_absolute() and ".." not in path.parts, "absolute fixed paths"
        )
    shared.require(
        str(args.python) == sys.executable, "invoke lexical target venv Python"
    )
    shared.require(
        args.sdk_root != args.venv_root
        and Path(sys.prefix) == args.venv_root
        and Path(sys.base_prefix) == args.sdk_root,
        "venv plus SDK required",
    )
    for path in (
        args.source,
        args.uv,
        args.wheels,
        args.output,
        args.cache,
        args.sdk_root,
        args.venv_root,
    ):
        for ancestor in (path, *path.parents):
            shared.require(
                not ancestor.is_symlink() and not ancestor.is_junction(),
                "fixed paths cannot use aliases",
            )
    disjoint = (
        args.source,
        args.wheels,
        args.output,
        args.cache,
        args.sdk_root,
        args.venv_root,
    )
    for index, path in enumerate(disjoint):
        shared.require(
            all(
                not path.is_relative_to(other) and not other.is_relative_to(path)
                for other in disjoint[index + 1 :]
            ),
            "disjoint fixed roots",
        )
    shared.require(
        not args.output.exists() and not args.cache.exists(), "fresh output/cache"
    )
    shared.require(
        args.source.resolve(strict=True) == args.source,
        "canonical declared audit checkout",
    )
    if sys.platform == "win32":
        shared.require(
            args.source.drive.upper() == profile["checkout_drive"],
            "profile Windows audit checkout drive",
        )
        shared.require(
            all(
                path.drive.upper() == "C:"
                for path in (
                    args.python,
                    args.uv,
                    args.wheels,
                    args.output,
                    args.sdk_root,
                    args.venv_root,
                )
            ),
            "Windows C native source/output/runtime/UV/wheels",
        )
        shared.require(
            args.cache.drive.upper() == profile["cache_drive"],
            "profile Windows cache drive",
        )
        shared.require(
            shared.volume_identity(args.cache)["filesystem"].upper() == "REFS",
            "profile ReFS cache",
        )
    else:
        shared.require(args.cache.parent.is_dir(), "existing Mac cache filesystem")
    return args


def creation_policy(config, args):
    receipt_path = Path(config["creation_receipt"])
    shared.require(
        receipt_path.is_absolute()
        and shared.digest(receipt_path) == config["creation_receipt_sha256"],
        "actual future bootstrap receipt required",
    )
    receipt = shared.load(receipt_path)
    expected = {
        "kind": "observed-uv-venv-creation",
        "uv_version": "0.13.6",
        "python_request": "3.13.15",
        "variant": "normal",
        "sdk_root": str(args.sdk_root),
        "venv_root": str(args.venv_root),
        "base_python": config["base_python"],
        "publisher_sha256": config["publisher_sha256"],
    }
    shared.require(
        all(receipt.get(key) == value for key, value in expected.items()),
        "creation provenance association",
    )
    if sys.platform == "darwin":
        shared.require(config["publisher_sha256"] == ARCHIVE_SHA256, "publisher digest")
        return DarwinRuntimeLinks(
            args.sdk_root,
            args.venv_root,
            config["base_python"],
            config["publisher_sha256"],
        )
    shared.require(
        Path(config["base_python"]).resolve(strict=True)
        == Path(sys._base_executable).resolve(strict=True),
        "Windows base compiler",
    )
    return None


def nonruntime_inputs(args, names, configuration):
    uv_digest = shared.digest(args.uv)
    shared.require(
        uv_digest == QUALIFIED_UV[configuration["platform"]]["sha256"],
        "UV qualified input seal differs",
    )
    return {
        "python": shared.digest(args.python),
        "uv": uv_digest,
        "source_checkout": shared.hash_files(args.source, names),
        "source_archive": shared.digest(args.output / "source.tar"),
        "source_manifest": shared.digest(args.output / "source-manifest.json"),
        "wheels": shared.manifest(args.wheels),
        "sourcepins": source_preflight(),
        "configuration": canonical_hash(configuration),
        "creation_receipt": shared.digest(Path(configuration["creation_receipt"])),
        "constraints": shared.digest(args.output / "build-constraints.txt"),
    }


def initial_runtime_guard(args, runtime, policy, snapshot):
    before = snapshot()
    before["runtime"] = runtime_input_hashes(runtime["runtime_roots"], policy)
    shared.save(args.output / "inputs-before.json", before)
    guard = RuntimeGuard(
        args.python, runtime, args.output, before, snapshot, link_policy=policy
    )
    return before, guard


def claim_attempt(marker, source_pin, config):
    shared.require(marker.is_absolute(), "exclusive absolute one-attempt marker")
    # Never removed, including on failure: separate authority must review any retry.
    with marker.open("x", encoding="utf-8") as handle:
        json.dump(
            {"sourcepins": source_pin, "configuration": canonical_hash(config)}, handle
        )


def run(config, admission, source_pin):
    started = time.perf_counter()
    admission_check(admission, config, source_pin, time.time())
    deadline = started + config["seconds"]
    args = configuration_paths(config)
    claim_attempt(Path(admission["attempt_marker"]), source_pin, config)
    args.output.mkdir(parents=True)
    try:
        shared.save(args.output / "admission-used.json", admission)
        policy = creation_policy(config, args)
        runtime = shared.runtime_identity()
        shared.save(args.output / "runtime-identity.json", runtime)
        shared.save(
            args.output / "uv-identity.json",
            qualified_uv_identity(args.uv, platform=config["platform"]),
        )
        shared.require(
            shared.git(args.source, "rev-parse", "HEAD").decode().strip()
            == shared.REVISION
            and not shared.git(args.source, "status", "--porcelain"),
            "clean pinned source",
        )
        tree = shared.raw_tree(args.source)
        shared.save(args.output / "git-tree.json", tree)
        shared.git(
            args.source,
            "archive",
            "--format=tar",
            f"--output={args.output / 'source.tar'}",
            shared.REVISION,
        )
        initial = args.output / "initial-source"
        shared.extract(args.output / "source.tar", initial)
        shared.verify_git_payload(initial, tree)
        canonical = shared.manifest(initial)
        shared.save(args.output / "source-manifest.json", canonical)
        shutil.rmtree(initial)
        shared.require(
            list(args.wheels.iterdir()) == [args.wheels / shared.WHEEL]
            and shared.digest(args.wheels / shared.WHEEL) == shared.WHEEL_SHA,
            "pinned PDM-only wheelhouse",
        )
        with zipfile.ZipFile(args.wheels / shared.WHEEL) as wheel:
            shared.require(
                wheel.read("pdm/backend/hooks/base.py")
                == (HERE / "pdm-hooks-base.source").read_bytes(),
                "stock backend ignore writer",
            )
        constraints = args.output / "build-constraints.txt"
        shutil.copyfile(HERE / constraints.name, constraints)
        # Reject ambient overrides, including SDE; do not strip setup variables.
        env = shared.environment(args.cache)
        args.cache.mkdir(mode=0o700)
        shared.save(
            args.output / "path-profile.json",
            {
                "profile": config["profile"],
                "classification": selected_profile(config)["classification"],
                "audit_checkout": str(args.source),
                "native_source_cwd": str(args.output / "canonical-source"),
                "volumes": {
                    "audit_checkout": shared.volume_identity(args.source),
                    "native_source_output": shared.volume_identity(args.output),
                    "cache": shared.volume_identity(args.cache),
                }
                if sys.platform == "win32"
                else None,
            },
        )
        shared.save(
            args.output / "cache-filesystem.json",
            shared.volume_identity(args.cache)
            if sys.platform == "win32"
            else {
                "device": args.cache.stat().st_dev,
                "mode": args.cache.stat().st_mode,
                "existing_parent_device": args.cache.parent.stat().st_dev,
            },
        )
        snapshot = lambda: nonruntime_inputs(args, tree, config)
        before, guard = initial_runtime_guard(args, runtime, policy, snapshot)
        argv = shared.command(args, constraints)
        shared.save(
            args.output / "protocol.json",
            {
                "version": VERSION,
                "question": QUESTION,
                "configuration": config,
                "profile": config["profile"],
                "classification": selected_profile(config)["classification"],
                "sourcepins": source_pin,
                "argv": argv,
                "cwd": str(args.output / "canonical-source"),
                "environment": shared.environment_evidence(env),
                "warmup_tokens": "C/D are guardian phase tokens only; identical fixed cache",
            },
        )
        setup_seconds = time.perf_counter() - started
        rows = shared.execute(
            args, canonical, deadline, dict.fromkeys(("C", "D", "R"), env), argv, guard
        )
        shared.require(
            len(rows) == 8
            and [(r["arm"], r["measured"], r["pair"]) for r in rows]
            == shared.schedule(),
            "exact eight-row reference",
        )
        final_audit_started = time.perf_counter()
        shared.seal_rows(args.output, rows)
        guard.final()
        after = snapshot()  # Never re-enter the initial runtime/link-policy API.
        shared.save(args.output / "inputs-after.json", after)
        shared.require(
            after == {k: v for k, v in before.items() if k != "runtime"},
            "nonruntime final seal",
        )
        shared.room(deadline, 0)
        shared.save(
            args.output / "result.json",
            {
                "status": "COMPLETE",
                "profile": config["profile"],
                "classification": selected_profile(config)["classification"],
                "rows": rows,
                "setup_seconds": setup_seconds,
                "final_audit_seconds": time.perf_counter() - final_audit_started,
                "controller_seconds": time.perf_counter() - started,
                "native_seconds": [row["seconds"] for row in rows if row["measured"]],
                "runtime_final_sha256": shared.digest(
                    args.output / "runtime-final.json"
                ),
            },
        )
    except BaseException as error:
        shared.save(
            args.output / "failure.json",
            {
                "type": type(error).__name__,
                "error": str(error),
                "profile": config["profile"],
                "classification": selected_profile(config)["classification"],
                "sourcepins": source_pin,
                "source_reset_logs": {
                    str(path.relative_to(args.output)): shared.digest(path)
                    for path in sorted(args.output.glob("build-*/source-reset.json"))
                },
            },
        )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-preflight", action="store_true")
    parser.add_argument("--configuration", type=Path)
    parser.add_argument("--admission", type=Path)
    args = parser.parse_args()
    pin = source_preflight()
    if args.source_preflight:
        print(
            json.dumps(
                {"status": "NOTADMITTED", "nativeDarwin": "NOTREADY", "sourcepins": pin}
            )
        )
        return
    shared.require(
        args.configuration and args.admission,
        "NOTADMITTED: separate fresh admission required",
    )
    run(shared.load(args.configuration), shared.load(args.admission), pin)


if __name__ == "__main__":
    main()
