"""Single final-pair audit, outside timings and bounded by the parent to 60s."""

import collections
import json
import re
import sys
from pathlib import Path

from identity_map import exact_mapping, group_for
from screen import COMMON, load, save, tiny_outcome

import coverage

sys.path.insert(0, str(COMMON))
from artifact_gate import artifact_set, equivalent


def execution(folder, expected, parallel, workers):
    maps = []
    for path in sorted(folder.glob("collection-*.json")):
        raw = load(path)
        mapping = exact_mapping(expected, raw, parallel)
        assert [mapping[node] for node in raw] == expected
        maps.append(mapping)
    assert len(maps) == (workers if parallel else 1)
    assert all(mapping == maps[0] for mapping in maps)
    mapping = maps[0]
    save(folder / "raw-to-canonical.json", mapping)
    identities = [load(path) for path in folder.glob("identity-*.json")]
    assert len(identities) == (workers + 1 if parallel else 1)
    pids = {row["worker"]: row["pid"] for row in identities}
    for row in identities:
        assert row["trace_type"] == "CTracer"
        assert row["native_machine"] in {"PE-ARM64", "MachO-arm64"}
        assert row["coverage_version"] == "7.17.0"
        options = row["options"]
        assert options["branch"] is False
        assert options["dynamic_context"] == "test_function"
        assert options["patch"] == ["subprocess", "_exit"]
        assert options["parallel"] is True and options["context"] == ""
    paths = (
        sorted(folder.glob("phases-gw*.jsonl"))
        if parallel
        else [folder / "phases-controller.jsonl"]
    )
    phases, groups = collections.defaultdict(list), collections.defaultdict(list)
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            node = mapping[row["nodeid"]]
            phases[node].append(row)
            if row["when"] == "setup":
                groups[group_for(node)].append((node, pids[row["worker"]]))
    assert set(phases) == set(expected)
    outcomes = {}
    for node, rows in phases.items():
        by_phase = {row["when"]: row["outcome"] for row in rows}
        assert len(by_phase) == len(rows)
        assert len({row["worker"] for row in rows}) == 1
        assert by_phase["teardown"] == "passed"
        assert by_phase["setup"] in {"passed", "skipped"}
        outcomes[node] = (
            "skipped" if by_phase["setup"] == "skipped" else by_phase["call"]
        )
        assert outcomes[node] in {"passed", "skipped"}
    for group, rows in groups.items():
        assert len({pid for _, pid in rows}) == 1, ("Split resource", group)
        assert [node for node, _ in rows] == [
            node for node in expected if group_for(node) == group
        ], ("Resource order", group)
    assert {"workdir_lock", "shared-main-app"} <= groups.keys()
    for path in folder.glob("groups-*.json"):
        for row in load(path):
            node = mapping[row["raw_nodeid"]]
            assert row["xdist_group_marks"] == ([group_for(node)] if parallel else [])
    fixtures = [load(path) for path in folder.glob("fixture-final-*.json")]
    assert len(fixtures) == 2 and len({row["owned"] for row in fixtures}) == 2
    assert all(row["static_removed"] and row["cwd_restored"] for row in fixtures)
    save(folder / "resource-pid-order.json", groups)
    tiny_outcome(folder)
    return outcomes, identities


def combined(folder, identities, source):
    data = coverage.CoverageData(no_disk=True)
    shards, cli, native_pids = [], [], set()
    for path in sorted(folder.glob(".coverage.*")):
        part = coverage.CoverageData(basename=str(path))
        part.read()
        assert not part.has_arcs()
        match = re.search(r"\.pid(\d+)\.", path.name)
        assert match, f"Original shard PID label missing: {path.name}"
        pid = int(match[1])
        entries = sum(len(part.lines(name) or ()) for name in part.measured_files())
        if entries:
            native_pids.add(pid)
        for name in part.measured_files():
            if Path(name) == source / "fastapi" / "cli.py" and part.lines(name):
                cli.append({"pid": pid, "shard": path.name, "lines": part.lines(name)})
        shards.append({"name": path.name, "pid": pid, "line_entries": entries})
        data.update(part)
    worker_pids = {row["pid"] for row in identities if row["worker"] != "controller"}
    assert worker_pids <= native_pids, "Worker failed to flush nonempty shard"
    if not worker_pids:
        assert identities[0]["pid"] in native_pids
    assert any(row["pid"] not in {i["pid"] for i in identities} for row in cli)
    assert len(data.measured_files()) == 863
    assert len(data.measured_contexts()) == 1409
    save(folder / "native-flush-proof.json", {"shards": shards, "cli": cli})
    return data


def coverage_compare(old, new, source, config):
    assert old.measured_files() == new.measured_files()
    assert old.measured_contexts() == new.measured_contexts()
    cov = coverage.Coverage(config_file=str(config))
    changes, removed_reportable, added_reportable = [], 0, 0
    for filename in sorted(old.measured_files()):
        before, after = (
            old.contexts_by_lineno(filename),
            new.contexts_by_lineno(filename),
        )
        excluded = set(cov.analysis2(filename)[2])
        for line in sorted(before.keys() | after.keys()):
            removed = sorted(set(before.get(line, ())) - set(after.get(line, ())))
            added = sorted(set(after.get(line, ())) - set(before.get(line, ())))
            if not removed and not added:
                continue
            name = Path(filename).relative_to(source).as_posix()
            source_lines = Path(filename).read_text(encoding="utf-8").splitlines()
            changes.append(
                {
                    "file": name,
                    "line": line,
                    "excluded": line in excluded,
                    "removed_contexts": removed,
                    "added_contexts": added,
                    "source": source_lines[line - 1],
                }
            )
            if line not in excluded:
                removed_reportable += len(removed)
                added_reportable += len(added)
    return {
        "files": 863,
        "contexts": 1409,
        "reportable_removed_triples": removed_reportable,
        "reportable_added_triples": added_reportable,
        "changes": changes,
        "status": "PASS_NO_REPORTABLE_LOSS" if removed_reportable == 0 else "FAIL",
        "addition_explanation_scope": "Exact source sites/raw contexts retained; no relabeling",
    }


def main(source, output, workers):
    serial, parallel = output / "payload-06-serial", output / "payload-05-parallel"
    expected = load(serial / "collection-controller.json")
    assert len(expected) == 2643
    left, left_ids = execution(serial, expected, False, workers)
    right, right_ids = execution(parallel, expected, True, workers)
    assert left == right, "Canonical node/outcome mismatch"
    old, new = combined(serial, left_ids, source), combined(parallel, right_ids, source)
    coverage_result = coverage_compare(old, new, source, output / "full-coverage.toml")
    save(output / "coverage-delta.json", coverage_result)
    assert coverage_result["reportable_removed_triples"] == 0
    manifest = load(output / "source-before.json")
    before = artifact_set(serial / "artifacts", source, manifest)
    after = artifact_set(parallel / "artifacts", source, manifest)
    equivalent(after, before)
    save(
        output / "selected-archive-proof.json",
        {
            name: {
                "serial_sha256": value["sha256"],
                "parallel_sha256": after[name]["sha256"],
                "members": len(value["members"]),
                "equivalent": True,
            }
            for name, value in before.items()
        },
    )
    save(
        output / "final-audit.json",
        {
            "status": "PASS_SELECTED_PAIR_ONLY",
            "selected": [serial.name, parallel.name],
            "cases": 2643,
            "passed": 2513,
            "skipped": 130,
            "files": 863,
            "contexts": 1409,
            "archives_equivalent": True,
            "reportable_loss": 0,
            "resource_pid_order": True,
            "native_worker_cli_flush": True,
            "adoption": False,
        },
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]))
