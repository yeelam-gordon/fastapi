"""Finite delegated hosted preparation, one owned core and on-target verification."""

import argparse
import dataclasses
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bootstrap  # noqa: E402
import case_contract as contract  # noqa: E402
import controller_identity  # noqa: E402


def authorize(env):
    review = json.loads((HERE / "PARENT-REVIEW.json").read_bytes())
    bootstrap.require(review["approved"] is True
                      and review["delegated_native_admission"] is True, "NOTADMITTED: zero approved jobs")
    contract.reference_allocation(review, env.get("MATCHED_REFERENCE_HOST", "both"), sys.platform)
    bootstrap.require(all(env.get(name) == value for name, value in {
        "GITHUB_REPOSITORY": "yeelam-gordon/fastapi", "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_EVENT_NAME": "workflow_dispatch", "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_ARCH": "ARM64"}.items()), "exact manual fork/native hosted context")
    now = time.time()
    bootstrap.require(type(review["expected_run_number"]) is int
                      and str(review["expected_run_number"]) == env.get("GITHUB_RUN_NUMBER")
                      and 0 < review["expires_unix"] - review["issued_unix"] <= 1800
                      and review["issued_unix"] <= now < review["expires_unix"], "fresh one-run parent allocation")
    release = json.loads((HERE / "RELEASE.json").read_bytes())
    bootstrap.require(type(release["schema"]) is int and release["schema"] == 1
                      and release["hosted_raw_verifier_ready"] is True
                      and bootstrap.reference.source_preflight() == bootstrap.PIN, "source closure")
    bootstrap.require(sys.platform != "win32" or release["windows_controller_mode"] == "self-identity-existing-entry-unowned-startup",
                      "explicit Windows controller startup boundary required")
    for name, expected in release["files"].items():
        path = HERE.parents[2] / contract.release_member(name)
        bootstrap.require(bootstrap.sha(path) == expected, "combined release bytes")
    return review


def run(workspace):
    review = authorize(os.environ)
    paths = bootstrap.fixed_paths(workspace, sys.platform)
    clean, removed = bootstrap.handoff(os.environ)
    case_root = Path(workspace) / "matched-case"
    case_root.mkdir()
    bootstrap.save(case_root / "setup-location-handoff.json", removed)
    receipt_path = paths["evidence"] / "creation-receipt.json"
    receipt = json.loads(receipt_path.read_bytes())
    observed = json.loads((paths["evidence"] / "runtime-observed.json").read_bytes())
    found = (paths["evidence"] / "find.stdout").read_text().strip()
    associations = bootstrap.observe_runtime(observed, found, paths, sys.platform)
    bootstrap.require(all(receipt[key] == value for key, value in associations.items()),
                      "observed qualified preparation associations")
    for name, expected in receipt["evidence_sha256"].items():
        bootstrap.require(bootstrap.sha(paths["evidence"] / name) == expected, "preparation evidence bytes")
    bootstrap.reference.qualified_uv_identity(Path(json.loads(
        (paths["evidence"] / "uv-static-identity.json").read_bytes())["executable"]), platform=sys.platform)
    if sys.platform == "win32":
        storage = json.loads((Path(workspace) / "matched-job-evidence" / "storage.json").read_bytes())
        bootstrap.require(storage["Status"] == "Prepared" and storage["BenchmarkEligible"] is True
                          and storage["Reason"] == "OrdinaryReFS", "NONCOMPARISON: no eligible RAW NVMe")
        bootstrap.require(bootstrap.reference.shared.volume_identity(paths["cache"])["filesystem"].upper() == "REFS",
                          "D: ordinary ReFS cache prerequisite")
    for name in ("source", "output", "cache", "wheels", "venv", "install"):
        for ancestor in (paths[name], *paths[name].parents):
            bootstrap.require(not ancestor.is_symlink() and not ancestor.is_junction(), "no path alias")
    bootstrap.require(not paths["output"].exists() and not paths["cache"].exists(), "fresh fixed output/cache")
    bootstrap.require(paths["source"].resolve(strict=True) == paths["source"]
                      and paths["source"].is_dir() and paths["wheels"].is_dir(),
                      "observed canonical audit source and backend roots")
    bootstrap.require(bootstrap.reference.shared.git(paths["source"], "rev-parse", "HEAD").decode().strip()
                      == bootstrap.reference.shared.REVISION
                      and not bootstrap.reference.shared.git(paths["source"], "status", "--porcelain"), "pinned clean source")
    remaining = int(os.environ["MATCHED_JOB_START_MS"]) / 1000 + 900 - time.time()
    seconds = min(540, int(remaining - 355), int(review["expires_unix"] - time.time() - 50))
    bootstrap.require(seconds >= 400, "first prerequisite: insufficient complete core/verification reserve")
    config = {
        "platform": sys.platform,
        "profile": "HOSTED_WINDOWS_REFERENCE" if sys.platform == "win32" else "DARWIN_REFERENCE",
        "source": str(paths["source"]), "python": observed["executable"],
        "uv": json.loads((paths["evidence"] / "uv-static-identity.json").read_bytes())["executable"],
        "cache": str(paths["cache"]), "wheels": str(paths["wheels"]), "output": str(paths["output"]),
        **associations, "publisher_sha256": receipt["publisher_sha256"], "seconds": seconds,
        "creation_receipt": str(receipt_path), "creation_receipt_sha256": bootstrap.sha(receipt_path),
    }
    if sys.platform == "win32":
        bootstrap.require(Path(config["uv"]).drive.upper() == "C:", "observed qualified UV on C:")
    bootstrap.save(case_root / "configuration.json", config)
    release = contract.binding(HERE / "RELEASE.json")
    bootstrap.save(case_root / "LAUNCH-ONCE", {
        "configuration": contract.canonical(config), "release": release["sha256"],
        "created_unix": time.time(), "never_remove": True,
    })
    issued = time.time()
    admission = {
        "authority": "separate-parent-native-readiness", "version": 3,
        "profile": config["profile"], "sourcepins_sha256": bootstrap.PIN,
        "question_sha256": contract.canonical(bootstrap.reference.QUESTION),
        "configuration_sha256": contract.canonical(config), "max_build_commands": 8,
        "bootstrap_receipt_qualified": True, "target_isa_runtime_prerequisites_qualified": True,
        "fixed_paths_and_cache_qualified": True, "issued_unix": issued,
        "expires_unix": issued + seconds + 40, "attempt_marker": str(case_root / "CORE-ATTEMPT-ONCE"),
    }
    bootstrap.require(admission["expires_unix"] <= review["expires_unix"], "delegation still covers finite admission")
    bootstrap.save(case_root / "admission.json", admission)
    command = {
        "argv": [config["python"], "-I", str(bootstrap.CORE / "reference.py"),
                 "--configuration", str(case_root / "configuration.json"),
                 "--admission", str(case_root / "admission.json")],
        "cwd": str(case_root), "timeout_seconds": seconds + 25, "cleanup_reserve_seconds": 25,
        "clock_scope": "OUTER_METADATA_NOT_BUILD_SAMPLES", "scoped_git_override": {"core.autocrlf": "false"},
        "environment": bootstrap.reference.shared.environment_evidence(clean),
    }
    # Append only a process-scoped export override; preserve runner Git entries.
    count = int(clean.get("GIT_CONFIG_COUNT", "0"))
    clean.update({f"GIT_CONFIG_KEY_{count}": "core.autocrlf",
                  f"GIT_CONFIG_VALUE_{count}": "false", "GIT_CONFIG_COUNT": str(count + 1)})
    bootstrap.save(case_root / "outer-command.json", command)
    observed_unix = time.time()
    bootstrap.save(case_root / "preparation-total.json", {
        "observed_unix": observed_unix,
        "pre_outer_job_seconds": observed_unix - int(os.environ["MATCHED_JOB_START_MS"]) / 1000,
        "private_preparation_seconds": receipt["elapsed_seconds"],
        "scope": "ALL_PREREQUISITES_BEFORE_OUTER; queue/native/verification/publication excluded",
    })
    started = time.monotonic()
    owned = bootstrap.owned_process.run_owned(
        command["argv"], cwd=case_root, env=clean,
        stdout_path=case_root / "controller.stdout", stderr_path=case_root / "controller.stderr",
        timeout=command["timeout_seconds"], native_clock=True)
    bootstrap.save(case_root / "outer-owned-receipt.json", dataclasses.asdict(owned))
    bootstrap.save(case_root / "LAUNCH-RESULT.json", {
        "outer_succeeded": owned.succeeded, "outer_elapsed_seconds": time.monotonic() - started,
        "survivors": owned.survivors, "cleanup_complete": owned.cleanup_complete,
        "native_output_root": str(paths["output"]), "performance_gain_claim": False,
    })
    bootstrap.require(owned.cleanup_complete and owned.survivors is False, "no live output collection")
    roles = {name: case_root / filename for name, filename in {
        "configuration": "configuration.json", "admission": "admission.json",
        "core_marker": "CORE-ATTEMPT-ONCE", "launch_marker": "LAUNCH-ONCE",
        "outer_command": "outer-command.json", "outer_receipt": "outer-owned-receipt.json",
        "outer_result": "LAUNCH-RESULT.json"}.items()}
    roles.update(release=HERE / "RELEASE.json", creation_receipt=receipt_path)
    descriptor = case_root / "case.json"
    extras = list(case_root.iterdir()) + list(paths["evidence"].iterdir())
    extras += list((Path(workspace) / "matched-job-evidence").iterdir())
    bootstrap.save(descriptor, {
        "schema": 1, "profile": config["profile"], "platform": sys.platform,
        "preparation_origin": "uv-managed-install", "descriptor_path": str(descriptor),
        "case_root": str(case_root), "core_root": str(bootstrap.CORE),
        "preparation_root": str(paths["evidence"]), "output": str(paths["output"]),
        "verification_output": str(Path(workspace) / "matched-verification"),
        "core_sourcepins_sha256": bootstrap.PIN, "release_root": str(HERE.parents[2]),
        "bindings": {name: contract.binding(path) for name, path in roles.items() if path.is_file()},
        "missing_bindings": [name for name, path in roles.items() if not path.is_file()],
        "records": [contract.binding(path) for path in extras if path.is_file()
                    and path.name not in {"job-wall.json", "readiness.txt"}],
        "run_number": int(os.environ["GITHUB_RUN_NUMBER"]),
    })
    argv = [config["python"], "-I", "-B", str(HERE / "verify_raw.py"),
            "--case", str(descriptor), "--case-sha256", bootstrap.sha(descriptor)]
    timeout = min(240, int(os.environ["MATCHED_JOB_START_MS"]) / 1000 + 900 - time.time() - 25)
    bootstrap.require(timeout > 0, "verifier reserve exhausted")
    bootstrap.save(case_root / "verification-command.json",
                   {"argv": argv, "timeout_seconds": timeout, "scope": "READ_ONLY_ON_TARGET_METADATA"})
    verification = bootstrap.owned_process.run_owned(
        argv, cwd=case_root, env=clean, stdout_path=case_root / "verification.stdout",
        stderr_path=case_root / "verification.stderr", timeout=timeout, native_clock=True)
    bootstrap.save(case_root / "verification-owned-receipt.json", dataclasses.asdict(verification))
    bootstrap.require(owned.succeeded and verification.succeeded, "raw/outer verification failed; no retry")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("stage", "run"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--uv", type=Path)
    parser.add_argument("--controller-directory")
    parser.add_argument("--controller-version")
    args = parser.parse_args()
    bootstrap.require(sys.flags.isolated == 1 and sys.dont_write_bytecode, "controller -I -B")
    if sys.platform == "win32":
        bootstrap.require(args.controller_directory and args.controller_version, "explicit metadata-controller cache association")
        identity = controller_identity.observe_self(args.controller_directory, args.controller_version)
        bootstrap.save(args.workspace / "matched-job-evidence" / f"metadata-controller-{args.operation}.json",
                       {"operation": args.operation, "identity": identity,
                        "scope": "SELF_IDENTITY_ONLY_NOT_OWNERSHIP_OR_MEASURED_SDK"})
    authorize(os.environ)
    if args.operation == "stage":
        bootstrap.require(args.uv is not None, "explicit qualified UV location")
        bootstrap.prepare(args.workspace, args.uv)
        observed = json.loads((args.workspace / "matched-evidence" / "runtime-observed.json").read_bytes())
        print(json.dumps({"python": observed["executable"]}))
    else:
        run(args.workspace)


if __name__ == "__main__":
    main()
