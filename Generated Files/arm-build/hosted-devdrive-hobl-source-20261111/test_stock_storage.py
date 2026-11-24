"""Metadata-only prospective storage replay; no workload or runtime preparation."""

import ast
import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import controlled_ci
import execution
import matched
import matched_audit
import pytest
import source_closure


def rows(schedule):
    return [
        {"index": index, "arm": arm, "folder": str(index)}
        for index, arm in enumerate(schedule, 1)
    ]


def test_stock_runs_every_original_phase_and_gate_without_b():
    events = []
    result = execution.orchestrate(
        rows(execution.STOCK),
        time.monotonic() + 600,
        lambda row, name, budget: events.append((row["index"], name)) or 2,
        lambda row, budget: events.append((row["index"], "cheap")),
        lambda measured, budget: events.append((len(measured), "first-pair")),
        lambda measured, budget: events.append((len(measured), "final")),
        schedule=execution.STOCK,
    )
    assert [row["arm"] for row in result] == ["A"] * 4
    assert [row["total_seconds"] for row in result] == [4] * 4
    assert events == [
        (1, "build"),
        (1, "test"),
        (1, "cheap"),
        (2, "build"),
        (2, "test"),
        (2, "cheap"),
        (2, "first-pair"),
        (3, "build"),
        (3, "test"),
        (3, "cheap"),
        (4, "build"),
        (4, "test"),
        (4, "cheap"),
        (4, "final"),
    ]


@pytest.mark.parametrize("schedule", [execution.ABBA, execution.STOCK[:3]])
def test_stock_rejects_b_or_incomplete_rows_before_any_phase(schedule):
    with pytest.raises(ValueError, match="selected schedule"):
        execution.orchestrate(
            rows(schedule),
            time.monotonic() + 600,
            lambda *args: pytest.fail("No phase may start"),
            lambda *args: pytest.fail("No cheap audit"),
            lambda *args: pytest.fail("No pair audit"),
            lambda *args: pytest.fail("No final audit"),
            schedule=execution.STOCK,
        )


def test_stock_final_preserves_every_full_hash_and_equality_gate():
    measured = rows(execution.STOCK)
    with (
        patch.object(Path, "exists", return_value=False),
        patch.object(matched_audit, "full") as full,
        patch.object(matched_audit, "load", return_value={}),
        patch.object(matched_audit, "verify_bound") as bound,
        patch.object(matched_audit, "equal_pair") as equal,
    ):
        proof = matched_audit.final(measured, schedule=execution.STOCK)
    assert full.call_args_list == [((row,), {}) for row in measured]
    assert bound.call_count == 4
    assert all(
        call.kwargs == {"require_derived": True} for call in bound.call_args_list
    )
    assert equal.call_args_list == [
        (("1", "2"), {}),
        (("1", "3"), {}),
        (("1", "4"), {}),
    ]
    assert proof["status"] == "PASS_STOCK_REPLAY_FOUR_SHA_BOUND"
    assert proof["raw_maps"] == proof["archive_inventories"] == 4
    assert not proof["cross_os_raw_equality_claim"]
    with pytest.raises(ValueError, match="selected four-payload"):
        matched_audit.final(rows(execution.ABBA), schedule=execution.STOCK)


def test_stock_is_never_accepted_by_pipe_comparison():
    result = {
        "status": "VALIDATED_NO_PARITY_CLAIM",
        "rows": rows(execution.STOCK),
        "comparison": {"profile": execution.STOCK_PROFILE},
    }
    with pytest.raises(ValueError, match="not a pipe B"):
        execution.compare(result, result)


def test_preparation_profile_and_audit_subprocess_argv_are_explicit():
    args = SimpleNamespace(
        source=Path("source"),
        output=Path("evidence"),
        uv=Path("uv.exe"),
        workers=4,
        profile=execution.STOCK_PROFILE,
    )
    assert execution.sequence(args) == execution.STOCK
    assert execution.sequence(SimpleNamespace()) == execution.ABBA
    command = controlled_ci.audit_command(args, "final")
    assert Path(command[2]).resolve() == Path(controlled_ci.__file__).resolve()
    assert command[-2:] == ["--profile", execution.STOCK_PROFILE]
    assert "--workers" in command


def test_profile_mismatch_denies_before_any_admission_or_preparation():
    args = SimpleNamespace(profile=execution.STOCK_PROFILE, action="prepare")
    with (
        patch.dict(
            controlled_ci.os.environ, {"MATCHED_PROFILE": controlled_ci.PROFILE}
        ),
        patch.object(controlled_ci, "admit") as admit,
        patch.object(controlled_ci.base, "main") as main,
    ):
        with pytest.raises(ValueError, match="allocation"):
            controlled_ci.main(args)
    admit.assert_not_called()
    main.assert_not_called()


def test_execution_default_cannot_use_stock_review_to_run_b():
    args = SimpleNamespace(action="run", profile="pipe-matched-ci-v1")
    with (
        patch.dict(matched.os.environ, {"MATCHED_PROFILE": execution.STOCK_PROFILE}),
        patch.object(matched, "admit") as admit,
    ):
        with pytest.raises(ValueError, match="allocation"):
            execution.main(args)
    admit.assert_not_called()


def test_stock_cannot_inherit_reference_review():
    with patch.dict(
        matched.os.environ,
        {
            "MATCHED_PROFILE": execution.STOCK_PROFILE,
            "GITHUB_REPOSITORY": "yeelam-gordon/fastapi",
            "GITHUB_RUN_ATTEMPT": "1",
        },
    ):
        with pytest.raises(RuntimeError, match="parent source review"):
            matched.admit()


def test_stock_preparation_and_worker_bind_existing_single_runtime_apis():
    args = SimpleNamespace(profile=execution.STOCK_PROFILE, action="prepare")
    with (
        patch.dict(controlled_ci.os.environ, {"MATCHED_PROFILE": args.profile}),
        patch.object(controlled_ci, "admit"),
        patch.object(execution, "main") as main,
    ):
        controlled_ci.main(args)
    main.assert_called_once_with(args)
    args.action = "worker"
    with (
        patch.dict(controlled_ci.os.environ, {"MATCHED_PROFILE": args.profile}),
        patch.object(controlled_ci, "admit"),
        patch.object(execution, "worker") as worker,
    ):
        controlled_ci.main(args)
    assert worker.call_args.kwargs == {
        "readiness_check": controlled_ci.readiness,
        "commands": controlled_ci.commands,
        "audit_commands": controlled_ci.audit_command,
        "archive_copy": controlled_ci.copy_uv_archives,
        "schedule": execution.STOCK,
    }


@pytest.mark.parametrize("workers", [3, 4])
def test_stock_argv_keeps_full_covered_fixed_dispatch_on_both_hosts(workers):
    command = controlled_ci.commands("python", "uv", "source", "evidence", workers)[
        "test"
    ]
    assert command[command.index("-n") + 1] == str(workers)
    assert "fixed_worker" in command
    assert "matched_policy" in command
    assert "--dist=loadgroup" in command
    assert "--max-worker-restart=0" in command
    assert command[command.index("-m") + 1] == "pytest"
    assert "tests" in command


def test_prepare_worker_selects_stock_before_any_preparation():
    args = SimpleNamespace(
        action="prepare-worker",
        source=Path("source"),
        output=Path("evidence"),
        uv=Path("uv.exe"),
        profile=execution.STOCK_PROFILE,
    )
    with patch.object(matched, "admit"), patch.object(execution, "prepare") as prepare:
        execution.main(args)
    prepare.assert_called_once_with(args, schedule=execution.STOCK)


def test_stock_worker_saves_no_abba_or_within_host_comparison():
    args = SimpleNamespace(seconds=600, output=Path("evidence"))
    measured = rows(execution.STOCK)
    with (
        patch.object(execution, "runtime_snapshot", return_value={}),
        patch.object(execution, "save") as save,
        patch.object(execution, "load", return_value=measured),
        patch.object(execution, "orchestrate", return_value=measured),
        patch.object(execution, "within_host") as within_host,
    ):
        execution.worker(
            args,
            schedule=execution.STOCK,
            readiness_check=lambda args: {"accepted": True},
        )
    within_host.assert_not_called()
    result = save.call_args.args[1]
    assert result["comparison"] == {
        "profile": execution.STOCK_PROFILE,
        "parity_claim": False,
        "adoption": False,
    }


def test_closure_and_unchanged_correctness_functions_are_exact():
    source_closure.verify()
    original = source_closure.SOURCE_ROOT
    for filename, names in {
        "execution.py": [
            "owned",
            "readiness",
            "environment",
            "runtime_snapshot",
            "runtime_preserved",
        ],
        "matched_audit.py": [
            "cheap",
            "full",
            "source_gate",
            "equal_pair",
            "resource",
            "raw_map",
            "verify_bound",
            "retain_source_log",
            "native_copies",
        ],
        "controlled_ci.py": ["dispatch"],
        "matched.py": ["command_plan", "static_check"],
    }.items():
        before = ast.parse((original / filename).read_bytes())
        after = ast.parse((Path(__file__).parent / filename).read_bytes())
        for name in names:
            left = next(
                node
                for node in before.body
                if isinstance(node, ast.FunctionDef) and node.name == name
            )
            right = next(
                node
                for node in after.body
                if isinstance(node, ast.FunctionDef) and node.name == name
            )
            assert ast.dump(left) == ast.dump(right), (filename, name)
    manifest = json.loads((Path(__file__).parent / "SOURCEPINS.json").read_text())
    pin = manifest["reference"]["hobl-complete-ci/owned_process.py"]
    assert pin == execution.GUARD_SHA
    assert (
        hashlib.sha256(
            (original.parent / "hobl-complete-ci" / "owned_process.py").read_bytes()
        ).hexdigest()
        == pin
    )
