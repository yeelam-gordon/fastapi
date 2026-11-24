"""Verify one hosted collection diagnostic offline from original REST captures and ZIPs.

The caller supplies the reviewed commit and requested run ID independently.
REST captures are trusted inputs, not authenticated by this tool.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

import verify_stock_reference as stock
from verify_stock_reference import decode, is_int, is_number, is_sha, require, sha

QUESTION = "hosted-stock-collection-boundaries"
SCHEDULE = ("OFF", "ON", "ON", "OFF")
STAGES = ("precollection", "collection", "finish_to_first_report")
MODE_PROOF = "early-timing-validation.json"


def review_options(review):
    # The pinned stock check deliberately admits a different question.
    allocation = review["ci_execution"]
    require(
        review["approved"] is True
        and review["cli_identity_qualified"] is True
        and review["profile"] == stock.PROFILE
        and is_sha(review["sourcepins_sha256"])
        and allocation["question"] == QUESTION
        and allocation["observation_schedule"] == list(SCHEDULE)
        and allocation["jobs"] == 2
        and allocation["job_seconds"] == stock.JOB_SECONDS
        and allocation["hobl_rows"] == "AAAA"
        and all(is_sha(allocation[key]) for key in ("workflow_sha256", "gate_sha256"))
        and set(allocation["queue_sha256"])
        == {"queue_readiness.ps1", "required-backend-ci-readiness/queue_clock.ps1"}
        and all(is_sha(value) for value in allocation["queue_sha256"].values()),
        "retained reviewed collection diagnostic options differ",
    )


def role_intervals(role, pid, sidecar, receipt, reports):
    label = f"{role}:"
    expected = {
        "schema_version": 2,
        "pid": pid,
        "worker": role,
        "clock": "time.monotonic_ns",
        "clock_scope": "same-host-only",
        "cpu_scope": "current-process-all-threads/no-children",
        "sample_order": "CPU-then-wall/non-atomic",
    }
    require(
        set(sidecar) == {*expected, "events"}
        and all(sidecar[key] == value for key, value in expected.items())
        and is_int(sidecar["schema_version"])
        and is_int(sidecar["pid"]),
        f"{label} exact ABI2 identity/scope differs",
    )
    names = [
        "pytest_configure.entry",
        "pytest_configure.exit",
        "pytest_sessionstart.entry",
        "pytest_sessionstart.exit",
        "pytest_collection.entry",
    ]
    finish = "pytest_collection_finish.entry"
    collection_exit = "pytest_collection.exit"
    if role != "controller":
        names += [finish, "pytest_collection_finish.exit"]
    first_report = "pytest_runtest_logreport.first_entry"
    names += [
        collection_exit,
        first_report,
        "pytest_sessionfinish.entry",
        "pytest_sessionfinish.exit",
    ]
    events = sidecar["events"]
    require(
        isinstance(events, list) and [event["name"] for event in events] == names,
        f"{label} complete natural hook sequence differs",
    )
    start, end = receipt["native_start_ns"], receipt["native_end_ns"]
    cpu = ("cpu_user_seconds", "cpu_system_seconds")
    for event in events:
        require(
            set(event) == {"name", "monotonic_ns", *cpu}
            and is_int(event["monotonic_ns"])
            and start <= event["monotonic_ns"] <= end
            and all(
                type(event[key]) is float and is_number(event[key]) and event[key] >= 0
                for key in cpu
            ),
            f"{label} invalid CPU sample or native wall bounds",
        )
    require(
        all(
            a["monotonic_ns"] < b["monotonic_ns"]
            and all(a[key] <= b[key] for key in cpu)
            for a, b in zip(events, events[1:], strict=False)
        ),
        f"{label} nonmonotonic role counters",
    )
    ticks = {event["name"]: event["monotonic_ns"] for event in events}
    require(
        reports
        and all(
            row["worker"] == role
            and is_int(row["pid"])
            and row["pid"] == pid
            and is_int(row["completion_monotonic_ns"])
            and ticks[first_report]
            <= row["completion_monotonic_ns"]
            <= ticks["pytest_sessionfinish.entry"]
            for row in reports
        ),
        f"{label} first-report/sessionfinish role ordering or identity differs",
    )
    # The xdist controller does not emit collection-finish; its exit is descriptive only.
    boundary = collection_exit if role == "controller" else finish
    entry = ticks["pytest_collection.entry"]
    return {
        "pid": pid,
        "collection_end_hook": boundary,
        "intervals_ns": dict(
            zip(
                STAGES,
                (
                    entry - start,
                    ticks[boundary] - entry,
                    ticks[first_report] - ticks[boundary],
                ),
                strict=True,
            )
        ),
    }


def validate_boundary_rows(evidence, platform, rows):
    _, workers, _, native_image, host_path = stock.MATRIX[platform]
    roles = ("controller", *(f"gw{i}" for i in range(workers)))
    last_end = 0
    for row, observation in zip(rows, SCHEDULE, strict=True):
        position = row["position"]
        prefix = f"{stock.ROOT}payload-{position:02}-A/"
        proof = evidence.json(prefix + "full-proof.json")
        folder = host_path(proof["inventory"]["folder"])
        hashes = proof["input_hashes"]

        def bound(
            leaf, *, prefix=prefix, hashes=hashes, folder=folder, position=position
        ):
            data = evidence.read(prefix + leaf)
            require(
                sha(data) == hashes.get(str(folder / leaf)),
                f"{platform}/{position}: full proof hash mismatch: {leaf}",
            )
            return data

        mode = decode(bound(MODE_PROOF))
        require(
            is_int(mode["position"])
            and is_int(mode["workers"])
            and mode
            == {
                "position": position,
                "observation": observation,
                "status": "VALIDATED",
                "workers": workers,
            },
            f"{platform}/{position}: collection boundary mode proof differs",
        )
        leaves = [
            member.removeprefix(prefix)
            for member in evidence.files
            if member.startswith(prefix)
        ]
        for stem, expected in (
            ("identity-", {f"identity-{role}.json" for role in roles}),
            (
                "early-boundaries-",
                {f"early-boundaries-{role}.json" for role in roles}
                if observation == "ON"
                else set(),
            ),
        ):
            actual = {
                leaf
                for leaf in leaves
                if leaf.rsplit("/", 1)[-1].casefold().startswith(stem)
            }
            require(
                actual == expected,
                f"{platform}/{position}: exact {stem} inventory differs",
            )

        native = {}
        for phase in ("build", "test"):
            receipt = decode(bound(f"{phase}-receipt.json"))
            _, last_end = stock.phase_receipt(
                receipt, row[f"{phase}_seconds"], last_end
            )
            native[phase] = {
                "start_ns": receipt["native_start_ns"],
                "end_ns": last_end,
                "elapsed_ns": last_end - receipt["native_start_ns"],
            }
        pids = {}
        for role in roles:
            identity = decode(bound(f"identity-{role}.json"))
            pid = identity["pid"]
            require(
                identity["worker"] == role
                and is_int(pid)
                and pid > 0
                and pid not in pids.values()
                and identity["trace_type"] == "CTracer"
                and identity["native_machine"] == native_image,
                f"{platform}/{position}/{role}: invalid or duplicate native role identity",
            )
            pids[role] = pid
        row.update(
            observation=observation,
            native=native,
            total_ns=sum(p["elapsed_ns"] for p in native.values()),
        )
        if observation == "ON":
            row["roles"] = {
                role: role_intervals(
                    role,
                    pids[role],
                    decode(bound(f"early-boundaries-{role}.json")),
                    receipt,
                    [
                        decode(line)
                        for line in bound(f"phases-{role}.jsonl").splitlines()
                    ],
                )
                for role in roles
            }


def interpretation(platforms):
    pairs = {}
    for platform, host in platforms.items():
        pairs[platform] = []
        for off, on in ((0, 1), (3, 2)):
            off_ns = host["rows"][off]["native"]["test"]["elapsed_ns"]
            on_ns = host["rows"][on]["native"]["test"]["elapsed_ns"]
            delta = on_ns - off_ns
            pairs[platform].append(
                {
                    "off_position": off + 1,
                    "on_position": on + 1,
                    "on_minus_off_test_ns": delta,
                    "fraction_of_off": delta / off_ns,
                    "within_limits": abs(delta) <= 1_500_000_000
                    and 20 * abs(delta) <= off_ns,
                }
            )
    comparison_safe = all(
        pair["within_limits"] for host in pairs.values() for pair in host
    )
    positions = []
    winners = []
    for index in (1, 2):
        maxima = {
            host: {
                stage: max(
                    roles["intervals_ns"][stage]
                    for role, roles in job["rows"][index]["roles"].items()
                    if role != "controller"
                )
                for stage in STAGES
            }
            for host, job in platforms.items()
        }
        deltas = {
            stage: maxima["windows"][stage] - maxima["macos"][stage] for stage in STAGES
        }
        largest = max(deltas.values())
        leaders = [
            stage for stage, delta in deltas.items() if delta == largest and delta > 0
        ]
        winners.append(leaders[0] if len(leaders) == 1 else None)
        positions.append(
            {
                "position": index + 1,
                "longest_worker_intervals_ns": maxima,
                "windows_minus_macos_ns": deltas,
            }
        )
    return {
        "paired_test_elapsed_differences": pairs,
        "comparison_safe": comparison_safe,
        "on_positions": positions,
        "prioritized_stage": winners[0]
        if comparison_safe and winners[0] == winners[1]
        else None,
    }


def verify(run, jobs, artifacts, zip_streams, *, run_id, commit, workflow_name):
    platforms = stock.metadata(run, jobs, artifacts, run_id, commit, workflow_name)
    review_bytes = None
    for platform, job in platforms.items():
        # Match the pinned verifier's original ZIP byte, limit and evidence checks.
        stream = zip_streams[platform]
        stream.seek(0, 2)
        require(
            0 < stream.tell() <= 512 * stock.MIB,
            f"{platform}: ZIP exceeds compressed size limit",
        )
        stream.seek(0)
        require(
            hashlib.file_digest(stream, "sha256").hexdigest() == job["artifact_sha256"],
            f"{platform}: ZIP differs from REST artifact digest",
        )
        stream.seek(0)
        with ZipFile(stream) as archive:
            evidence = stock.Evidence(archive)
            data = evidence.read(stock.REVIEW_PATH)
            review_options(decode(data))
            require(
                review_bytes is None or data == review_bytes,
                "platform review receipts differ",
            )
            review_bytes = data
            rows = stock.validate_host(evidence, platform, job["job_wall_seconds"])
            validate_boundary_rows(evidence, platform, rows)
            job["rows"] = rows
    return {
        "run_id": run_id,
        "head_sha": commit,
        "attempt": 1,
        "workflow_id": stock.WORKFLOW_ID,
        "workflow_name": workflow_name,
        "profile": stock.PROFILE,
        "question": QUESTION,
        "review_sha256": sha(review_bytes),
        "observation_schedule": list(SCHEDULE),
        "platforms": platforms,
        **interpretation(platforms),
        "scope": (
            "Adjacent observed differences are not a causal overhead bound. A null stage is inconclusive. "
            "Only worker intervals enter the stage comparison; the controller uses collection exit. "
            "Native ticks are same-host only; concurrent intervals are not summed. No parity or speedup claim."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument(
        "--workflow-name", default="ARM build diagnostics (analysis only)"
    )
    for name in ("run", "jobs", "artifacts", "windows-zip", "macos-zip"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        inputs = []
        for path in (args.run, args.jobs, args.artifacts):
            with path.open("rb") as stream:
                data = stream.read(8 * stock.MIB + 1)
            require(len(data) <= 8 * stock.MIB, f"REST response too large: {path.name}")
            inputs.append(decode(data))
        with args.windows_zip.open("rb") as windows, args.macos_zip.open("rb") as macos:
            report = verify(
                *inputs,
                {"windows": windows, "macos": macos},
                run_id=args.run_id,
                commit=args.commit,
                workflow_name=args.workflow_name,
            )
    except (
        ValueError,
        KeyError,
        TypeError,
        IndexError,
        AttributeError,
        OSError,
        OverflowError,
        RecursionError,
        ParseError,
        BadZipFile,
        RuntimeError,
    ) as error:
        print(f"Collection diagnostic not verified: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
