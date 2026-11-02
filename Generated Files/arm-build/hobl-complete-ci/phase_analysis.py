"""Analysis-only adapter; ordinary baseline clocks and schedules are untouched."""

import copy
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

OBSERVER_SHA256 = "ef98604a41f7a9f0a49d9552e84107d53e5b393f874888d51b1b75cf96ca6352"
CPU_WALL_TOLERANCE_NS = 20_000_000


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def account(raw):
    events = raw["events"]
    children = defaultdict(list)
    roots = []
    for index, event in enumerate(events):
        require(
            all(
                type(event[key]) is int
                for key in (
                    "id",
                    "start_ns",
                    "end_ns",
                    "elapsed_ns",
                    "thread_id",
                    "cpu_start_ns",
                    "cpu_end_ns",
                    "cpu_elapsed_ns",
                )
            ),
            "integer span fields",
        )
        require(event["id"] == index, "span identity")
        require(event["thread_id"] == raw["caller_thread_id"], "caller thread")
        require(
            event["end_ns"] >= event["start_ns"]
            and event["elapsed_ns"] == event["end_ns"] - event["start_ns"],
            "span duration",
        )
        parent = event["parent"]
        require(
            event["cpu_end_ns"] >= event["cpu_start_ns"]
            and event["cpu_elapsed_ns"] == event["cpu_end_ns"] - event["cpu_start_ns"],
            "CPU duration",
        )
        require(
            event["cpu_elapsed_ns"] <= event["elapsed_ns"] + CPU_WALL_TOLERANCE_NS,
            "CPU exceeds wall clock quantization tolerance",
        )
        if parent is None:
            roots.append(index)
        else:
            require(0 <= parent < index, "span parent")
            children[parent].append(event)
    require(len(roots) == 1 and events[roots[0]]["kind"] == "pytest_command", "root")
    result = []
    for event in events:
        end, child_ns = event["start_ns"], 0
        cpu_end, child_cpu = event["cpu_start_ns"], 0
        for child in sorted(children[event["id"]], key=lambda row: row["start_ns"]):
            require(
                end <= child["start_ns"] <= child["end_ns"] <= event["end_ns"],
                "overlapping children",
            )
            end = child["end_ns"]
            child_ns += child["elapsed_ns"]
            require(
                cpu_end
                <= child["cpu_start_ns"]
                <= child["cpu_end_ns"]
                <= event["cpu_end_ns"],
                "CPU children not nested/monotonic; no negative clamping",
            )
            cpu_end = child["cpu_end_ns"]
            child_cpu += child["cpu_elapsed_ns"]
        exclusive_cpu = event["cpu_elapsed_ns"] - child_cpu
        require(exclusive_cpu >= 0, "negative exclusive CPU; no clamping")
        result.append(
            {
                **event,
                "exclusive_ns": event["elapsed_ns"] - child_ns,
                "exclusive_cpu_ns": exclusive_cpu,
                "wall_minus_caller_cpu_ns": event["elapsed_ns"]
                - event["cpu_elapsed_ns"],
            }
        )
    require(
        sum(row["exclusive_ns"] for row in result) == events[0]["elapsed_ns"],
        "integer conservation",
    )
    require(
        sum(row["exclusive_cpu_ns"] for row in result) == events[0]["cpu_elapsed_ns"],
        "integer CPU conservation",
    )
    return result


def outcomes(raw, passed=2513, skipped=130):
    nodes = raw["collected_nodeids"]
    require(len(nodes) == len(set(nodes)) == passed + skipped, "collection")
    reports = raw["reports"]
    require(set(nodes) == {row["nodeid"] for row in reports}, "report collection")
    by_node = defaultdict(dict)
    for row in reports:
        require(row["when"] not in by_node[row["nodeid"]], "duplicate report")
        require(not row["wasxfail"], "unexpected xfail")
        by_node[row["nodeid"]][row["when"]] = row["outcome"]
    expected = Counter()
    for phases in by_node.values():
        require(
            phases
            in (
                {"setup": "passed", "call": "passed", "teardown": "passed"},
                {"setup": "skipped", "teardown": "passed"},
            ),
            "invalid complete report outcomes",
        )
        expected["passed" if "call" in phases else "skipped"] += 1
    require(
        expected == Counter({"passed": passed, "skipped": skipped}), "outcome counts"
    )
    return dict(expected)


def public_file(filename, source, python):
    if filename is None:
        return None
    path = Path(filename).resolve()
    roots = [
        ("source", source.resolve()),
        ("runtime", python.parent.parent.resolve()),
    ]
    for label, root in roots:
        if path.is_relative_to(root):
            return label + "/" + path.relative_to(root).as_posix()
    # Never publish a user's absolute path.
    return "external/" + path.name


def summarize(raw, source, python, passed=2513, skipped=130):
    events = account(raw)
    counts = outcomes(raw, passed, skipped)
    hook_counts = Counter(row["kind"] for row in events)
    lifecycle = (
        "pytest_command",
        "session_start",
        "collection",
        "test_loop",
        "session_finish",
    )
    for kind in lifecycle:
        require(hook_counts[kind] == 1, f"exactly one lifecycle span: {kind}")
    ordered = [
        next(row for row in events if row["kind"] == kind) for kind in lifecycle[1:]
    ]
    require(all(row["parent"] == 0 for row in ordered), "lifecycle root parent")
    require(
        all(
            left["end_ns"] <= right["start_ns"]
            for left, right in zip(ordered, ordered[1:], strict=False)
        ),
        "lifecycle order",
    )
    for kind in ("protocol", "setup", "teardown"):
        require(hook_counts[kind] == passed + skipped, "complete phase spans")
    require(hook_counts["call"] == passed, "call spans")
    require(
        hook_counts["make_report"]
        == hook_counts["log_report"]
        == 3 * passed + 2 * skipped,
        "report spans",
    )
    collected = Counter(raw["collected_nodeids"])
    for kind in ("protocol", "setup", "teardown"):
        require(
            Counter(row["nodeid"] for row in events if row["kind"] == kind)
            == collected,
            f"{kind} node attribution",
        )
    passing = Counter(
        row["nodeid"]
        for row in raw["reports"]
        if row["when"] == "call" and row["outcome"] == "passed"
    )
    require(
        Counter(row["nodeid"] for row in events if row["kind"] == "call") == passing,
        "call node attribution",
    )
    reported = Counter((row["nodeid"], row["when"]) for row in raw["reports"])
    for kind in ("make_report", "log_report"):
        require(
            Counter(
                (row["nodeid"], row["report_when"])
                for row in events
                if row["kind"] == kind
            )
            == reported,
            f"{kind} report attribution",
        )
    allowed_parents = {
        "session_start": {"pytest_command"},
        "collection": {"pytest_command"},
        "test_loop": {"pytest_command"},
        "session_finish": {"pytest_command"},
        "terminal_summary": {"session_finish"},
        "protocol": {"test_loop"},
        "setup": {"protocol"},
        "call": {"protocol"},
        "teardown": {"protocol"},
        "make_report": {"protocol"},
        "log_report": {"protocol"},
        "fixture_setup": {"setup", "call", "teardown", "fixture_setup"},
    }
    for row in events[1:]:
        parent = events[row["parent"]]
        require(
            parent["kind"] in allowed_parents.get(row["kind"], set()), "hook nesting"
        )
        if row["kind"] in {"setup", "call", "teardown", "make_report", "log_report"}:
            require(row["nodeid"] == parent["nodeid"], "phase node nesting")
    totals = defaultdict(lambda: {"inclusive_ns": 0, "exclusive_ns": 0, "count": 0})
    fixtures = defaultdict(lambda: {"inclusive_ns": 0, "exclusive_ns": 0, "count": 0})
    partitions = defaultdict(lambda: defaultdict(int))
    for row in events:
        partitions[row["kind"]]["self_residual_ns"] += row["exclusive_ns"]
        partitions[row["kind"]]["self_residual_cpu_ns"] += row["exclusive_cpu_ns"]
        if row["parent"] is not None:
            parent_kind = events[row["parent"]]["kind"]
            partitions[parent_kind][row["kind"] + "_subset_ns"] += row["elapsed_ns"]
            partitions[parent_kind][row["kind"] + "_subset_cpu_ns"] += row[
                "cpu_elapsed_ns"
            ]
        targets = [totals[row["kind"]]]
        if row["kind"] == "fixture_setup":
            key = (
                row["fixture"],
                row["fixture_scope"],
                public_file(row["file"], source, python),
                row["line"],
            )
            targets.append(fixtures[key])
        for target in targets:
            target["inclusive_ns"] += row["elapsed_ns"]
            target["exclusive_ns"] += row["exclusive_ns"]
            target["count"] += 1
            target["inclusive_cpu_ns"] = (
                target.get("inclusive_cpu_ns", 0) + row["cpu_elapsed_ns"]
            )
            target["exclusive_cpu_ns"] = (
                target.get("exclusive_cpu_ns", 0) + row["exclusive_cpu_ns"]
            )
            target["wall_minus_caller_cpu_ns"] = (
                target.get("wall_minus_caller_cpu_ns", 0)
                + row["wall_minus_caller_cpu_ns"]
            )
    return {
        "performance_eligible": False,
        "cpu_clock": "time.thread_time_ns: caller thread only, not process/worker CPU",
        "clock_boundary_policy": "wall start, CPU start, CPU end, wall end; exact integer CPU tree conservation; reject negative exclusive CPU without clamping",
        "cpu_wall_quantization_tolerance_ns": CPU_WALL_TOLERANCE_NS,
        "cpu_exceeds_wall_within_tolerance_count": sum(
            row["cpu_elapsed_ns"] > row["elapsed_ns"] for row in events
        ),
        "clock_info": {
            name: vars(time.get_clock_info(name))
            for name in ("thread_time", "perf_counter")
        },
        "waiting_qualification": "wall minus caller CPU is waiting, other-thread handoff, I/O or unmeasured work; not automatically overhead or removable",
        "outcomes": counts,
        "phase_walls": dict(totals),
        "phase_seconds": {
            kind: {
                "inclusive_s": value["inclusive_ns"] / 1e9,
                "exclusive_s": value["exclusive_ns"] / 1e9,
                "inclusive_cpu_s": value["inclusive_cpu_ns"] / 1e9,
                "exclusive_cpu_s": value["exclusive_cpu_ns"] / 1e9,
            }
            for kind, value in totals.items()
        },
        "direct_child_partitions_ns": {
            kind: dict(parts) for kind, parts in partitions.items()
        },
        "integer_exclusive_conservation": True,
        "fixture_setup_is_nested_subset_not_additive": True,
        "fixture_finalizers": "Included in teardown/session finish; no private fixture-finalizer hook",
        "fixtures": [
            {"fixture": k[0], "scope": k[1], "file": k[2], "line": k[3], **v}
            for k, v in sorted(
                fixtures.items(), key=lambda pair: pair[1]["exclusive_ns"], reverse=True
            )
        ],
        "top_nodes": {
            kind: [
                {
                    "nodeid": row["nodeid"],
                    "inclusive_ns": row["elapsed_ns"],
                    "exclusive_ns": row["exclusive_ns"],
                    "inclusive_cpu_ns": row["cpu_elapsed_ns"],
                    "exclusive_cpu_ns": row["exclusive_cpu_ns"],
                    "wall_minus_caller_cpu_ns": row["wall_minus_caller_cpu_ns"],
                }
                for row in sorted(
                    (r for r in events if r["kind"] == kind),
                    key=lambda r: r["elapsed_ns"],
                    reverse=True,
                )[:20]
            ]
            for kind in ("setup", "call", "teardown")
        },
    }


def diagnostic_env(env, folder, helper, style):
    env = env.copy()
    env["PYTHONPATH"] = str(helper) + os.pathsep + env["PYTHONPATH"]
    plugins = env.get("PYTEST_PLUGINS", "")
    env["PYTEST_PLUGINS"] = ",".join(filter(None, (plugins, "hobl_phase_observer")))
    env["HOBL_BOUNDARY_OUTPUT"] = str(folder / "private")
    env["COVERAGE_FILE"] = str(folder / "private" / ".coverage")
    if style == "macos":
        # test.sh exports PYTHONPATH itself. Reapply only observer search at the
        # existing coverage executable boundary, keeping its arguments unchanged.
        shim = folder / "private" / "observer-env.bash"
        shim.write_text(
            'coverage() { PYTHONPATH="$HOBL_OBSERVER_PATH:$PYTHONPATH" command coverage "$@"; }\n',
            encoding="utf-8",
        )
        env["BASH_ENV"] = str(shim)
        env["HOBL_OBSERVER_PATH"] = str(helper)
    return env


def coverage_stats(private):
    from coverage import CoverageData

    paths = sorted(private.glob(".coverage*"))
    require(bool(paths), "saved coverage shards missing")
    combined = CoverageData(no_disk=True)
    shards = []
    for path in paths:
        part = CoverageData(basename=str(path))
        part.read()
        combined.update(part)
        shards.append(
            {
                "bytes": path.stat().st_size,
                "files": len(part.measured_files()),
                "contexts": len(part.measured_contexts()),
            }
        )
    mapping = {
        name: {
            str(line): sorted(contexts)
            for line, contexts in sorted(combined.contexts_by_lineno(name).items())
        }
        for name in sorted(combined.measured_files())
    }
    save(private / "saved-contexts.json", mapping)
    return {
        "shards": shards,
        "files": len(mapping),
        "contexts": len(combined.measured_contexts()),
        "line_context_associations": sum(
            len(contexts) for lines in mapping.values() for contexts in lines.values()
        ),
        "saved_contexts_sha256": hashlib.sha256(
            (private / "saved-contexts.json").read_bytes()
        ).hexdigest(),
        "cross_os_exact_associations_compared": False,
        "qualification": "No cross-OS equality claim: timestamps/async excluded pragma line 79 can differ. Raw SQLite/context paths remain private.",
    }


def run(args, env, before):
    from run_payload import digest, snapshot

    folder = args.output.resolve() / "analysis"
    (folder / "private").mkdir(parents=True)
    helper = Path(__file__).resolve().parent
    observer = helper / "hobl_phase_observer.py"
    require(digest(observer) == OBSERVER_SHA256, "observer strict identity")
    manifest_sha256 = digest(args.manifest)
    env = diagnostic_env(env, folder, helper, args.style)
    command = (
        ["bash", "scripts/test.sh"]
        if args.style == "macos"
        else [str(args.python), "-m", "coverage", "run", "-m", "pytest", "tests"]
    )
    save(
        folder / "started.json",
        {
            "performance_eligible": False,
            "observer_sha256": digest(observer),
            "source_manifest_sha256": manifest_sha256,
            "child_timeout_s": 300,
            "outer_timeout_s": 600,
            "command_kind": args.style,
        },
    )
    start = time.perf_counter_ns()
    with (
        (folder / "test.stdout").open("wb") as out,
        (folder / "test.stderr").open("wb") as err,
    ):
        child = subprocess.run(
            command, cwd=args.source, env=env, stdout=out, stderr=err, timeout=300
        )
    wall = time.perf_counter_ns() - start
    raw = json.loads((folder / "private" / "raw-boundaries.json").read_bytes())
    public = copy.deepcopy(raw)
    for event in public["events"]:
        event["thread_id"] = 0
        if "file" in event:
            event["file"] = public_file(event["file"], args.source, args.python)
    public["caller_thread_id"] = 0
    save(folder / "boundaries.json", public)
    save(folder / "private" / "accounted-nodes.json", account(raw))
    result = summarize(raw, args.source, args.python)
    require(child.returncode == 0, "covered test exit; retain failures")
    require(snapshot(args.source, before) == before, "protected source changed")
    require(digest(observer) == OBSERVER_SHA256, "observer changed")
    require(digest(args.manifest) == manifest_sha256, "source manifest changed")
    require(wall >= raw["events"][0]["elapsed_ns"], "outer clock containment")
    # Coverage is installed in the payload venv, not the guardian coordinator.
    post = subprocess.run(
        [
            str(args.python),
            "-I",
            "-B",
            str(Path(__file__).resolve()),
            str(folder / "private"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    (folder / "postprocess.stderr").write_text(post.stderr, encoding="utf-8")
    (folder / "postprocess.stdout").write_text(post.stdout, encoding="utf-8")
    require(post.returncode == 0, "saved coverage postprocess failed")
    require(not post.stderr, "saved coverage postprocess diagnostics; stderr retained")
    saved_coverage = json.loads(post.stdout)
    require(
        len(saved_coverage["shards"]) == 2 and saved_coverage["contexts"] > 1,
        "full main/CLI dynamic coverage shards",
    )
    import runtime_pair

    canonical = runtime_pair.probe(
        args.python, "oracle", args.source, folder, env, folder
    )
    save(folder / "private" / "canonical-coverage.json", canonical)
    require(
        len(canonical["files"]) == 863 and len(canonical["contexts"]) == 1409,
        "current complete canonical coverage file/context sets",
    )
    result.update(
        {
            "status": "awaiting-owned-natural-drain",
            "outer_wall_ns": wall,
            "outside_pytest_command_ns": wall - raw["events"][0]["elapsed_ns"],
            "source_files_preserved": len(before),
            "source_manifest_sha256": manifest_sha256,
            "observer_sha256": OBSERVER_SHA256,
            "helper_sha256": {
                name: digest(helper / name)
                for name in (
                    "phase_analysis.py",
                    "run_payload.py",
                    "runtime_pair.py",
                    "owned_process.py",
                    "runtime-constraints.txt",
                    "common-guard.patch",
                )
            },
            "coverage": saved_coverage,
            "iterations": 1,
            "qualification": "First-cold Python 3.13 diagnostic, not warm-distribution explanation; common corrected source and current service classes only.",
        }
    )
    save(folder / "summary.json", result)
    save(args.output / "result.json", result)


def compare_coverage(left, right):
    import runtime_pair

    differences = runtime_pair.compare(left, right)
    return {
        "performance_eligible": False,
        "complete_file_context_sets_equal": True,
        "reportable_associations_equal": all(row["excluded"] for row in differences),
        "raw_differences": differences,
        "qualification": "Original analysis2 exclusions classify raw differences; no unexcluded cross-OS tracing equality claim.",
    }


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--compare":
        print(
            json.dumps(
                compare_coverage(
                    json.loads(Path(sys.argv[2]).read_bytes()),
                    json.loads(Path(sys.argv[3]).read_bytes()),
                )
            )
        )
    else:
        print(json.dumps(coverage_stats(Path(sys.argv[1]))))
