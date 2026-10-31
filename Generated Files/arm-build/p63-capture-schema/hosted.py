"""Path-only hosted integration; no default collection or caller command strings."""

import contextlib
import importlib.util
import io
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("p63_collector", HERE / "collector.py")
collector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = collector
SPEC.loader.exec_module(collector)
SCOPE = "P63_ONE_EPHEMERAL_ATTEMPT"
UV_SHA = "ec27977d62b5f6091bce410a8e69d40d07541803314e0120905c0ad0affaa5cc"
PUBLIC_KEYS = {
    "status",
    "diagnostic_ready",
    "source_sha256",
    "category",
    "private_error_sha256",
    "raw_etl_sha256",
    "raw_report_sha256",
    "schema_sha256",
    "failure_evidence_persistence",
}


def public_result(value, pins):
    collector.require(
        type(value) is dict
        and set(value) <= PUBLIC_KEYS
        and value.get("status") == "UNKNOWN"
        and value.get("diagnostic_ready") is False
        and value.get("category") in pins["public_categories"]
        and value.get("source_sha256") == pins["source_sha256"]["collector.py"],
        "PUBLIC_RESULT_REJECTED",
    )
    for key, item in value.items():
        if key.endswith("_sha256"):
            collector.require(
                type(item) is str and re.fullmatch(r"[0-9a-f]{64}", item),
                "PUBLIC_RESULT_REJECTED",
            )
    collector.require(
        "failure_evidence_persistence" not in value
        or value["failure_evidence_persistence"] == "FAILED",
        "PUBLIC_RESULT_REJECTED",
    )
    return {**value, "stage": "CAPTURE_SCHEMA_UNKNOWN"}


def current_job(env, get=collector.http_json):
    endpoint = (
        "https://api.github.com/repos/yeelam-gordon/fastapi/actions/runs/"
        + env["GITHUB_RUN_ID"]
        + "/attempts/1/jobs?per_page=100"
    )
    response = get(endpoint, env["GH_TOKEN"])
    collector.require(
        response["total_count"] == 1 and len(response["jobs"]) == 1,
        "UNIQUE_CURRENT_JOB_REQUIRED",
    )
    job = response["jobs"][0]
    collector.require(
        type(job["id"]) is int
        and job["id"] > 0
        and job["name"] == "p63-capture-schema"
        and job["run_id"] == int(env["GITHUB_RUN_ID"])
        and job["run_attempt"] == 1
        and job["status"] == "in_progress"
        and job["runner_name"] == env["RUNNER_NAME"]
        and "windows-11-arm" in job["labels"]
        and "self-hosted" not in job["labels"],
        "UNIQUE_CURRENT_JOB_REQUIRED",
    )
    return job["id"]


def plan_for(root, uv):
    pins = collector.read_json(HERE / "source-pins.json")
    fixture_hashes = collector.read_json(HERE / "fixture-hashes.json")
    inputs = {}
    for relative, digest in fixture_hashes.items():
        path = (HERE / relative).resolve()
        collector.require(
            path.is_relative_to(HERE / "fixtures") and collector.sha(path) == digest,
            "PUBLIC_FIXTURE_HASH",
        )
        inputs[str(path)] = digest
    collector.require(collector.sha(uv) == UV_SHA, "NATIVE_UV_HASH")
    inputs[str(uv)] = UV_SHA
    helpers = HERE.parent / "paired-arm-reference"
    guardian = HERE.parent / "protocol" / "owned_process.py"
    collector.require(
        collector.sha(guardian) == collector.GUARDIAN_SHA, "GUARDIAN_HASH"
    )
    collector.require(
        all(
            collector.sha(helpers / name) == digest
            for name, digest in collector.HELPERS.items()
        ),
        "HELPER_HASH",
    )
    collector.require(
        all(
            collector.sha(HERE / name) == digest
            for name, digest in pins["source_sha256"].items()
        ),
        "SOURCE_HASH",
    )
    fixture = HERE / "fixtures"
    return {
        "job_workspace": str(Path(os.environ["GITHUB_WORKSPACE"]).resolve(strict=True)),
        "helper_directory": str(helpers),
        "published_guardian": str(guardian),
        "uv": str(uv),
        "source_archive": str(fixture / "fastapi-0.119.1-raw-git-lf.tar.gz"),
        "source_proof": str(fixture / "source-proof.json"),
        "stock_wheel": str(fixture / "pdm_backend-2.5.0-py3-none-any.whl"),
        "baseline_directory": str(fixture / "reference"),
        "input_sha256": inputs,
        "source_sha256": pins["source_sha256"],
    }, pins


def run(root, uv, output):
    result = {
        "status": "UNKNOWN",
        "diagnostic_ready": False,
        "category": "HOSTED_INTEGRATION_FAILED",
        "stage": "HOSTED_SETUP_UNKNOWN",
    }
    code = 2
    try:
        env = os.environ
        collector.require(
            env.get("P63_AUTHORIZATION") == SCOPE
            and env.get("GITHUB_REPOSITORY") == collector.REPOSITORY
            and env.get("GITHUB_REF") == "refs/heads/perf/arm-scan-schema"
            and env.get("GITHUB_RUN_ATTEMPT") == "1"
            and env.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
            and env.get("NoDefaultCurrentDirectoryInExePath") == "1"
            and sys.dont_write_bytecode,
            "HOSTED_INTEGRATION_CONTEXT",
        )
        plan, pins = plan_for(root, uv)
        plan_path = root / "plan.json"
        collector.durable(plan_path, plan)
        job_id = current_job(env)
        authority = {
            "approved": True,
            "scope": SCOPE,
            "repository": collector.REPOSITORY,
            "workflow_id": 400167398,
            "run_id": env["GITHUB_RUN_ID"],
            "job_id": job_id,
            "head_sha": env["GITHUB_SHA"],
            "ref": env["GITHUB_REF"],
            "run_attempt": "1",
            "job_timeout_minutes": 8,
            "accepted_transient_overshoot": True,
            "expires": int(time.time()) + 900,
            "plan_sha256": collector.sha(plan_path),
            "job_workspace": plan["job_workspace"],
        }
        authority_path = root / "authority.json"
        collector.durable(authority_path, authority)
        capture_stdout = io.StringIO()
        with (root / "controller-stderr.txt").open("x", encoding="utf-8") as stderr:
            with (
                contextlib.redirect_stdout(capture_stdout),
                contextlib.redirect_stderr(stderr),
            ):
                code = collector.main(
                    ["--collect", str(authority_path), str(plan_path)]
                )
        text = capture_stdout.getvalue()
        (root / "controller-stdout.txt").write_text(text, encoding="utf-8")
        result = public_result(json.loads(text), pins)
        collector.require(
            type(code) is int and code != 0, "COVERAGE_MUST_REMAIN_UNKNOWN"
        )
    except BaseException:
        (root / "integration-error.txt").write_text(
            traceback.format_exc(), encoding="utf-8"
        )
        code = 2
    collector.durable(root / "exit-code.json", {"exit_code": code})
    collector.durable(output, result)
    return code


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments:
        print('{"mode":"SOURCE_ONLY","collection_executed":false}')
        return 0
    if len(arguments) != 4 or arguments[0] != "--run":
        return 2
    return run(
        Path(arguments[1]).resolve(),
        Path(arguments[2]).resolve(),
        Path(arguments[3]).resolve(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
