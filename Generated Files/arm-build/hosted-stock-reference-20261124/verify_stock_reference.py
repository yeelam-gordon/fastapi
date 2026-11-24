"""Verify a single attempt offline; emit an eight-row JSON report to stdout.

Inputs are the original GitHub REST run, attempt-1 jobs, and run-artifacts
responses, plus the two original GitHub download ZIPs (not repacked/extracted).
The caller supplies the reviewed commit and requested run ID independently.
The response files are trusted captures, not authenticated by this tool.
"""

import argparse
import hashlib
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from statistics import median
from zipfile import BadZipFile, ZipFile

REPOSITORY = "yeelam-gordon/fastapi"
WORKFLOW_ID = 400482741
WORKFLOW_PATH = ".github/workflows/arm-build-diagnostics.yml"
PROFILE = "stock-hobl-storage-ci82-v1"
MATRIX = {
    "windows": ("windows-11-arm", 4, "win32", "PE-ARM64", PureWindowsPath),
    "macos": ("macos-15", 3, "darwin", "MachO-arm64", PurePosixPath),
}
QUEUE_SECONDS = 300
JOB_SECONDS = 600
ROOT = "stock-evidence/"
REVIEW_PATH = (
    "tools/Generated Files/arm-build/hosted-devdrive-hobl-source-20261111/"
    "PARENT-REVIEW.json"
)
METRICS = ("build_seconds", "test_seconds", "total_seconds")
# Sorted (classname, name, outcome) from all eight prior common82 JUnit
# files in pipe-matched-ci-readiness/ci-41972551771. Ordering/time are not outcomes.
JUNIT_SHA = "0ac50640b3bad72617051f18a482ca2bd598a5cc788f532160f56654aa9ff362"
OUTCOMES_SHA = "3e7495fffce90562a404aebf2160fb7132d6240166230048eceae6230cdba171"
EXPECTED_ARCHIVES = {
    "fastapi-0.119.1-py3-none-any.whl": 58,
    "fastapi-0.119.1.tar.gz": 1196,
}
MIB = 1024**2


def require(condition, message):
    if not condition:
        raise ValueError(message)


def is_int(value):
    return type(value) is int


def is_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def is_sha(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value)


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, f"duplicate JSON key: {key}")
        obj[key] = value
    return obj


def decode(data):
    def reject_constant(value):
        raise ValueError(f"nonfinite JSON value: {value}")

    return json.loads(data, object_pairs_hook=unique_object, parse_constant=reject_constant)


def canonical_sha(value):
    return sha(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def timestamp(value):
    require(
        re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value),
        f"expected UTC REST timestamp, got {value!r}",
    )
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def completed(record):
    return record["status"] == "completed" and record["conclusion"] == "success"


def exact_records(response, key, names):
    records = response[key]
    require(
        response["total_count"] == len(records) == len(names)
        and {record["name"] for record in records} == set(names)
        and all(is_int(record["id"]) and record["id"] > 0 for record in records)
        and len({record["id"] for record in records}) == len(names),
        f"unexpected {key} count, names, or IDs",
    )
    return {record["name"]: record for record in records}


def metadata(run, jobs, artifacts, run_id, commit, workflow_name):
    require(is_int(run_id) and run_id > 0, "positive requested run ID required")
    require(re.fullmatch(r"[a-f0-9]{40}", commit), "expected full lowercase commit SHA")
    require(
        run["id"] == run_id
        and run["head_sha"] == commit
        and run["run_attempt"] == 1
        and run["workflow_id"] == WORKFLOW_ID
        and run["path"] == WORKFLOW_PATH
        and run["name"] == workflow_name
        and run["event"] == "workflow_dispatch"
        and completed(run)
        and run["repository"]["full_name"] == REPOSITORY
        and run["head_repository"]["full_name"] == REPOSITORY,
        "run is not the expected successful manual attempt 1",
    )
    created = timestamp(run["created_at"])
    job_names = {
        p: f"stock-reference ({runner}, {p}, {workers})"
        for p, (runner, workers, *_) in MATRIX.items()
    }
    artifact_names = {p: f"stock-hobl-reference-{p}" for p in MATRIX}
    job_records = exact_records(jobs, "jobs", job_names.values())
    artifact_records = exact_records(artifacts, "artifacts", artifact_names.values())
    result = {}
    for p, (runner, workers, *_) in MATRIX.items():
        job = job_records[job_names[p]]
        artifact = artifact_records[artifact_names[p]]
        require(
            job["run_id"] == run_id
            and job["run_attempt"] == 1
            and job["head_sha"] == commit
            and job["workflow_name"] == workflow_name
            and job["labels"] == [runner]
            and completed(job),
            f"{p}: job identity or conclusion differs",
        )
        started = timestamp(job["started_at"])
        queue = (started - created).total_seconds()
        wall = (timestamp(job["completed_at"]) - started).total_seconds()
        require(0 <= queue <= QUEUE_SECONDS, f"{p}: run-created to job-start exceeds queue bound or is negative")
        require(0 < wall <= JOB_SECONDS, f"{p}: invalid job wall time")
        owner = artifact["workflow_run"]
        digest = artifact["digest"]
        require(
            owner["id"] == run_id
            and owner["head_sha"] == commit
            and owner["repository_id"] == run["repository"]["id"]
            and owner["head_repository_id"] == run["head_repository"]["id"]
            and digest.startswith("sha256:")
            and is_sha(digest[7:]),
            f"{p}: artifact run/commit or digest differs",
        )
        result[p] = {
            "job_id": job["id"],
            "job_name": job["name"],
            "runner": runner,
            "workers": workers,
            "queue_seconds": queue,
            "job_wall_seconds": wall,
            "artifact_id": artifact["id"],
            "artifact_name": artifact["name"],
            "artifact_sha256": digest[7:],
        }
    return result


class Evidence:
    def __init__(self, archive):
        self.archive = archive
        entries = archive.infolist()
        require(
            len(entries) <= 12000 and sum(item.file_size for item in entries) <= 1024 * MIB,
            "ZIP exceeds bounded stock evidence allocation",
        )
        self.files = {}
        names = set()
        for item in entries:
            name = item.orig_filename.rstrip("/")
            require(
                item.filename == item.orig_filename
                and "\\" not in name
                and ":" not in name
                and all(part not in ("", ".", "..") for part in name.split("/"))
                and name.casefold() not in names,
                f"invalid or duplicate ZIP entry: {name}",
            )
            names.add(name.casefold())
            if not item.is_dir():
                self.files[name] = item

    def read(self, name, limit=8 * MIB):
        require(name in self.files, f"missing artifact member: {name}")
        item = self.files[name]
        require(item.file_size <= limit, f"artifact member too large: {name}")
        return self.archive.read(item)

    def json(self, name):
        return decode(self.read(name))


def review_options(review):
    allocation = review["ci_execution"]
    require(
        review["approved"] is True
        and review["cli_identity_qualified"] is True
        and review["profile"] == PROFILE
        and is_sha(review["sourcepins_sha256"])
        and allocation["question"] == "hosted-stock-ntfs-mac-reference"
        and allocation["jobs"] == 2
        and allocation["job_seconds"] == JOB_SECONDS
        and allocation["hobl_rows"] == "AAAA"
        and all(is_sha(allocation[key]) for key in ("workflow_sha256", "gate_sha256"))
        and set(allocation["queue_sha256"])
        == {"queue_readiness.ps1", "required-backend-ci-readiness/queue_clock.ps1"}
        and all(is_sha(value) for value in allocation["queue_sha256"].values()),
        "retained reviewed workflow options differ",
    )


def junit_outcomes(data):
    require(b"<!" not in data and b"\0" not in data, "unsupported JUnit markup")
    root = ET.fromstring(data)
    require(root.tag == "testsuites" and [item.tag for item in root] == ["testsuite"], "expected one pytest JUnit suite")
    suite = root[0]
    expected = {"tests": "2643", "skipped": "130", "failures": "0", "errors": "0"}
    require(all(suite.get(key) == value for key, value in expected.items()), "JUnit suite counts differ")
    outcomes = []
    seen = set()
    for case in suite:
        key = (case.get("classname"), case.get("name"))
        require(case.tag == "testcase" and all(key) and key not in seen, "invalid or duplicate JUnit testcase")
        seen.add(key)
        tags = [item.tag for item in case]
        require(set(tags) <= {"skipped", "system-out", "system-err", "properties"} and tags.count("skipped") <= 1, "unexpected JUnit testcase outcome")
        outcomes.append((*key, "skipped" if "skipped" in tags else "passed"))
    require(
        Counter(row[2] for row in outcomes) == {"passed": 2513, "skipped": 130}
        and canonical_sha(sorted(outcomes)) == JUNIT_SHA,
        "JUnit canonical outcomes differ",
    )
    return {"passed": 2513, "skipped": 130, "failures": 0, "errors": 0}


def phase_receipt(receipt, reported, last_end):
    require(
        is_int(receipt["returncode"])
        and receipt["returncode"] == 0
        and receipt["timed_out"] is False
        and receipt["ownership_established"] is True
        and receipt["survivors"] is False
        and receipt["cleanup_complete"] is True
        and receipt["errors"] == receipt["liveness"] == [],
        "native receipt does not attest a successful natural drain",
    )
    start, end = receipt["native_start_ns"], receipt["native_end_ns"]
    require(
        is_int(start) and is_int(end) and 0 <= last_end <= start < end,
        "native clock boundaries are missing, reversed, or overlap",
    )
    seconds = (end - start) / 1e9
    require(
        is_number(reported) and seconds == reported and seconds <= JOB_SECONDS
        and is_number(receipt["command_wall"]) and 0 < receipt["command_wall"] <= JOB_SECONDS
        and is_number(receipt["infrastructure_wall"]) and 0 <= receipt["infrastructure_wall"] <= JOB_SECONDS,
        "native receipt arithmetic or wall time differs",
    )
    return seconds, end


def raw_map(data):
    raw = decode(data)
    require(
        set(raw) == {"files", "contexts"}
        and isinstance(raw["files"], dict) and raw["files"]
        and isinstance(raw["contexts"], list) and raw["contexts"]
        and all(isinstance(context, str) for context in raw["contexts"]),
        "invalid raw map",
    )
    for path, entry in raw["files"].items():
        require(
            set(entry) == {"lines", "contexts_by_lineno"}
            and isinstance(entry["lines"], list)
            and all(is_int(line) and line >= 0 for line in entry["lines"])
            and isinstance(entry["contexts_by_lineno"], dict)
            and all(
                line.isascii() and line.isdecimal()
                and isinstance(contexts, list)
                and all(isinstance(value, str) for value in contexts)
                for line, contexts in entry["contexts_by_lineno"].items()
            ),
            f"invalid raw map file associations: {path}",
        )
    return raw


def validate_host(evidence, platform, job_wall):
    runner, workers, native_platform, native_image, host_path = MATRIX[platform]
    result = evidence.json(ROOT + "result.json")
    rows = result["rows"]
    readiness = result["readiness"]
    identity = readiness["identity"]
    require(
        result["status"] == "VALIDATED_NO_PARITY_CLAIM"
        and result["failures"] == []
        and result["comparison"]["profile"] == PROFILE
        and result["comparison"]["parity_claim"] is False
        and result["comparison"]["adoption"] is False
        and readiness == evidence.json(ROOT + "readiness.json")
        and readiness["accepted"] is True
        and readiness["profile"] == PROFILE
        and readiness["mac_runtime_accepted"] is (platform == "macos")
        and identity["python"].split()[0] == "3.13.15"
        and identity["machine"].lower() in {"arm64", "aarch64"}
        and identity["logical_cpu_count"] == workers
        and identity["python_native"] == identity["coverage_native"] == native_image
        and identity["normal_gil"] is True
        and identity["jit"] is False,
        f"{platform}: {runner} result/profile/readiness differs",
    )
    final = evidence.json(ROOT + "final-audit.json")
    require(
        final["status"] == "PASS_STOCK_REPLAY_FOUR_SHA_BOUND"
        and final["raw_maps"] == final["archive_inventories"] == 4
        and final["cross_os_raw_equality_claim"] is False
        and final["final_runtime_and_sources_preserved"] is True,
        f"{platform}: final stock audit or producer preservation flag differs",
    )
    require(
        len(rows) == 4 and all(is_int(row["index"]) for row in rows)
        and [row["index"] for row in rows] == [1, 2, 3, 4]
        and [row["arm"] for row in rows] == ["A"] * 4
        and evidence.json(ROOT + "audit-rows.json") == rows,
        f"{platform}: expected exactly four ordered audited A rows",
    )
    expected_names = {f"payload-{i:02}-A" for i in range(1, 5)}
    actual_names = {
        name.removeprefix(ROOT).split("/")[0] for name in evidence.files
        if name.startswith(ROOT + "payload-")
    }
    require(actual_names == expected_names, f"{platform}: unexpected retained payloads")
    last_end = 0
    output = []
    baseline_raw = baseline_members = None
    for row in rows:
        name = f"payload-{row['index']:02}-A"
        prefix = ROOT + name + "/"
        folder = host_path(row["folder"])
        require(folder.is_absolute() and folder.name == name and folder.parent.name == "stock-evidence", f"{platform}: wrong producer payload path")
        proof = evidence.json(prefix + "full-proof.json")
        require(
            proof["inventory"]["folder"] == row["folder"]
            and proof["header_platform"] == native_platform
            and proof["header_policy"] == "source-defined-native-creator-only-v1",
            f"{platform}/{name}: full proof row/header identity differs",
        )
        hashes = proof["input_hashes"]

        def bound(relative, limit=8 * MIB):
            data = evidence.read(prefix + relative, limit)
            require(sha(data) == hashes[str(folder.joinpath(*relative.split("/")))], f"{platform}/{name}: full proof hash mismatch: {relative}")
            return data

        raw_data = bound("full-raw-map.json", 64 * MIB)
        archive_data = bound("archive-inventory.json")
        raw_digest, archive_digest = sha(raw_data), sha(archive_data)
        require(raw_digest == proof["raw_sha256"] and archive_digest == proof["archive_sha256"], f"{platform}/{name}: derived hash mismatch")
        raw = raw_map(raw_data)
        del raw_data
        if baseline_raw is None:
            baseline_raw = raw
        else:
            require(raw == baseline_raw, f"{platform}/{name}: full raw associations differ within host")
        del raw
        archives = decode(archive_data)
        require(set(archives) == set(EXPECTED_ARCHIVES), f"{platform}/{name}: missing wheel or sdist")
        members = {}
        for archive_name, count in EXPECTED_ARCHIVES.items():
            contents = bound("artifacts/" + archive_name)
            entry = archives[archive_name]
            require(
                len(contents) == entry["bytes"] and sha(contents) == entry["sha256"]
                and len(entry["members"]) == count,
                f"{platform}/{name}: retained archive binding or member count differs",
            )
            members[archive_name] = entry["members"]
        if baseline_members is None:
            baseline_members = members
        else:
            require(members == baseline_members, f"{platform}/{name}: archive members differ within host")
        cheap = decode(bound("cheap-proof.json"))
        require(cheap["row"] == row and canonical_sha(cheap["outcomes"]) == OUTCOMES_SHA, f"{platform}/{name}: canonical producer outcomes or row differ")
        outcomes = junit_outcomes(bound("junit.xml"))
        timings = {}
        for phase in ("build", "test"):
            key = phase + "_seconds"
            timings[key], last_end = phase_receipt(decode(bound(phase + "-receipt.json")), row[key], last_end)
        total = timings["build_seconds"] + timings["test_seconds"]
        require(is_number(row["total_seconds"]) and total == row["total_seconds"], f"{platform}/{name}: total arithmetic differs")
        output.append({
            "position": row["index"],
            "arm": row["arm"],
            **timings,
            "total_seconds": total,
            "junit_outcomes": outcomes,
            "raw_sha256": raw_digest,
            "archive_sha256": archive_digest,
        })
    require(sum(row["total_seconds"] for row in output) <= job_wall, f"{platform}: measured time exceeds job wall")
    return output


def verify(run, jobs, artifacts, zip_streams, *, run_id, commit, workflow_name):
    platforms = metadata(run, jobs, artifacts, run_id, commit, workflow_name)
    review_bytes = None
    for p, job in platforms.items():
        stream = zip_streams[p]
        stream.seek(0, 2)
        require(0 < stream.tell() <= 512 * MIB, f"{p}: ZIP exceeds compressed size limit")
        stream.seek(0)
        require(hashlib.file_digest(stream, "sha256").hexdigest() == job["artifact_sha256"], f"{p}: ZIP differs from REST artifact digest")
        stream.seek(0)
        with ZipFile(stream) as archive:
            evidence = Evidence(archive)
            data = evidence.read(REVIEW_PATH)
            review_options(decode(data))
            require(review_bytes is None or data == review_bytes, "platform review receipts differ")
            review_bytes = data
            rows = validate_host(evidence, p, job["job_wall_seconds"])
        job["rows"] = rows
        job["medians_seconds"] = {metric: median(row[metric] for row in rows) for metric in METRICS}

    positions = []
    for win, mac in zip(platforms["windows"]["rows"], platforms["macos"]["rows"], strict=True):
        positions.append({
            "position": win["position"],
            "windows_minus_macos_seconds": {metric: win[metric] - mac[metric] for metric in METRICS},
            "windows_total_no_greater_than_macos": win["total_seconds"] <= mac["total_seconds"],
        })
    return {
        "run_id": run_id,
        "head_sha": commit,
        "attempt": 1,
        "event": "workflow_dispatch",
        "workflow_id": WORKFLOW_ID,
        "workflow_name": workflow_name,
        "profile": PROFILE,
        "review_sha256": sha(review_bytes),
        "run_created_at": run["created_at"],
        "queue_definition": "Original run creation to each job start, inclusive 300-second bound; distinct from the in-job point-in-time check.",
        "platforms": platforms,
        "matched_positions": positions,
        "position_parity": all(row["windows_total_no_greater_than_macos"] for row in positions),
        "scope": "Eight rows on these standard hosted runners only; no physical-machine, Dev Drive, or causal claim and no cross-OS raw-map comparison.",
        "offline_evidence_scope": "Verified retained raw maps, archive inventory and container hashes, canonical JUnit outcomes, and native phase receipts; did not rerun producer coverage or archive-member audit.",
        "preservation": "Producer final audit attests runtime and source preservation; omitted producer trees were not independently revalidated.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--workflow-name", default="ARM build diagnostics (analysis only)")
    for name in ("run", "jobs", "artifacts", "windows-zip", "macos-zip"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        metadata_inputs = []
        for path in (args.run, args.jobs, args.artifacts):
            with path.open("rb") as stream:
                data = stream.read(8 * MIB + 1)
            require(len(data) <= 8 * MIB, f"REST response too large: {path.name}")
            metadata_inputs.append(decode(data))
        with args.windows_zip.open("rb") as windows, args.macos_zip.open("rb") as macos:
            report = verify(
                *metadata_inputs,
                {"windows": windows, "macos": macos},
                run_id=args.run_id,
                commit=args.commit,
                workflow_name=args.workflow_name,
            )
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, OSError,
            OverflowError, RecursionError, ET.ParseError, BadZipFile, RuntimeError) as error:
        print(f"NoParityClaim: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
