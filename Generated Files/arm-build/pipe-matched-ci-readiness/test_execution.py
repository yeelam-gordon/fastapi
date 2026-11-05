"""Mocked orchestration and negative integrity gates; no child execution."""

import time
from pathlib import Path
from unittest.mock import patch

import execution
import matched_audit
import provenance
import pytest

ROWS = [
    {"index": index, "arm": arm, "folder": str(index)}
    for index, arm in enumerate(("A", "B", "B", "A"), 1)
]


def test_full_abba_native_phases_and_audit_order():
    events = []

    def phase(row, name, budget):
        events.append((row["index"], name))
        assert 0 < budget <= 180
        return 2.0

    result = execution.orchestrate(
        ROWS,
        time.monotonic() + 480,
        phase,
        lambda row, budget: events.append((row["index"], "cheap")),
        lambda rows, budget: events.append((len(rows), "first-pair")),
        lambda rows, budget: events.append((len(rows), "final")),
    )
    assert [row["total_seconds"] for row in result] == [4.0] * 4
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


def test_first_pair_failure_never_admits_b2():
    calls = []

    def reject(rows, budget):
        raise ValueError("raw mismatch")

    with pytest.raises(ValueError, match="raw mismatch"):
        execution.orchestrate(
            ROWS,
            time.monotonic() + 480,
            lambda row, name, budget: calls.append((row["index"], name)) or 1,
            lambda row, budget: None,
            reject,
            lambda rows, budget: pytest.fail("No final admission after bad first pair"),
        )
    assert calls == [(1, "build"), (1, "test"), (2, "build"), (2, "test")]


def test_cheap_resource_failure_stops_before_second_payload():
    calls = []

    def reject(row, budget):
        raise ValueError("resource failure")

    with pytest.raises(ValueError, match="resource failure"):
        execution.orchestrate(
            ROWS,
            time.monotonic() + 480,
            lambda row, name, budget: calls.append(row["index"]) or 1,
            reject,
            lambda *args: pytest.fail("No pair"),
            lambda *args: pytest.fail("No final"),
        )
    assert calls == [1, 1]


def test_remaining_budget_reserves_final_audit_before_any_command():
    with pytest.raises(TimeoutError, match="allocation exhausted"):
        execution.orchestrate(
            ROWS,
            time.monotonic() + 120,
            lambda *args: pytest.fail("No payload budget"),
            lambda *args: None,
            lambda *args: None,
            lambda *args: None,
        )


def test_final_audit_failure_is_not_a_validated_result():
    def reject(rows, budget):
        assert budget <= 120
        raise TimeoutError("audit cap")

    with pytest.raises(TimeoutError, match="audit cap"):
        execution.orchestrate(
            ROWS,
            time.monotonic() + 480,
            lambda *args: 1,
            lambda *args: None,
            lambda *args: None,
            reject,
        )


def test_modified_sha_bound_input_rejected_without_raw_reparse():
    with (
        patch.object(matched_audit, "digest", return_value="changed"),
        patch.object(matched_audit, "verify_inventory"),
    ):
        with pytest.raises(ValueError, match="SHA-bound input changed"):
            matched_audit.verify_bound(
                {"input_hashes": {"owned.json": "original"}, "inventory": {}}
            )


def test_comparison_requires_both_hosts_validated_and_both_orders():
    rows = [{"build_seconds": 1, "test_seconds": 2, "total_seconds": 3}] * 4
    result = {"status": "VALIDATED_NO_PARITY_CLAIM", "rows": rows}
    assert execution.compare(result, result)["primary_timing_threshold_both_orders"]
    with pytest.raises(ValueError, match="Both complete"):
        execution.compare({"status": "ERROR", "rows": rows}, result)


def test_exact_public_source_close_contract_is_available_without_mac_execution():
    pins = provenance.source_contract()
    assert all("/v3.13.15/" in value["url"] for value in pins.values())
    with patch.object(provenance.sys, "platform", "win32"):
        with pytest.raises(RuntimeError, match="Exact Mac"):
            provenance.mac_runtime()


def test_raw_root_normalization_rejects_foreign_source_identity():
    class Data:
        def measured_files(self):
            return ["foreign.py"]

    with pytest.raises(ValueError, match="Foreign coverage"):
        matched_audit.raw_map(Data(), Path("owned"))


def test_owned_guard_reserves_cleanup_and_distinguishes_validation_failure():
    receipt = execution.dataclasses.make_dataclass(
        "FakeReceipt",
        [
            ("returncode", int),
            ("timed_out", bool),
            ("ownership_established", bool),
            ("survivors", bool),
            ("cleanup_complete", bool),
            ("errors", tuple),
            ("succeeded", bool),
        ],
    )(2, False, True, False, True, (), False)
    with (
        patch.object(execution, "digest", return_value=execution.GUARD_SHA),
        patch.object(execution, "run_owned", return_value=receipt) as guard,
        patch.object(execution, "save"),
    ):
        with pytest.raises(ValueError, match="validation failed"):
            execution.owned(["audit"], ".", {}, Path("."), "final", 120)
    assert guard.call_args.kwargs["timeout"] == 105


def test_owned_guard_never_launches_when_cleanup_reserve_is_unavailable():
    with (
        patch.object(execution, "digest", return_value=execution.GUARD_SHA),
        patch.object(execution, "run_owned") as guard,
    ):
        with pytest.raises(TimeoutError, match="cleanup budget"):
            execution.owned(["audit"], ".", {}, Path("."), "final", 16)
    guard.assert_not_called()
