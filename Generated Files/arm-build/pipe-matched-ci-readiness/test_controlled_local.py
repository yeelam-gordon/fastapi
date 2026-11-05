"""Metadata-only control attestations and explicit local/CI separation."""

import inspect
from types import SimpleNamespace
from unittest.mock import patch

import controlled_local as profile
import execution
import pytest


@pytest.mark.parametrize(
    "sha,version", [("wrong", "3.8.0"), (profile.CONTROL, "3.7.0")]
)
def test_wrong_control_hash_or_version_rejects(sha, version):
    with (
        patch.object(profile, "digest", return_value=sha),
        patch.object(profile.importlib.metadata, "version", return_value=version),
    ):
        with pytest.raises(ValueError, match="hash/xdist"):
            profile.control()


def test_both_arms_have_same_explicit_fixed_plugin_and_no_case_selection():
    command = profile.commands("python", "uv", "source", "out", 4)["test"]
    assert command[-2:] == ["-p", "fixed_worker"]
    assert command[command.index("pytest") + 1] == "tests"
    assert "-k" not in command


def test_local_runtime_callback_does_not_weaken_default_ci_readiness():
    assert (
        inspect.signature(execution.worker).parameters["readiness_check"].default
        is None
    )
    with patch.object(
        profile, "local_metadata", side_effect=ValueError("not exact local83")
    ):
        with pytest.raises(ValueError, match="local83"):
            profile.readiness(None)
    assert "identity(args)" in inspect.getsource(execution.readiness)


def test_wrong_dispatch_source_proof_rejects(tmp_path):
    control = profile.control()
    collection = [f"test_g{i}.py::test_case" for i in range(4)]
    for i in range(4):
        profile.save(tmp_path / f"collection-gw{i}.json", collection)
        (tmp_path / f"phases-gw{i}.jsonl").write_text("")
    profile.save(
        tmp_path / "fixed-worker-plan.json",
        {
            "status": "EXACT_DISPATCH",
            "exitstatus": 0,
            "collected_cases": 4,
            "scheduled_cases": 4,
            "source_hashes": control.SOURCE_HASHES,
            "group_owners": {},
            "sent_by_worker": {},
        },
    )
    with pytest.raises(ValueError, match="dispatch/order"):
        profile.dispatch(tmp_path, 4)


def test_small_readiness_never_accepts_changed_runtime(tmp_path):
    args = SimpleNamespace(output=tmp_path)
    with (
        patch.object(profile, "readiness"),
        patch.object(
            profile.base,
            "runtime_snapshot",
            side_effect=[{"a": "old"}, {"a": "changed"}],
        ),
        patch.object(profile.base, "owned"),
        patch.object(profile, "dispatch", return_value={}),
        patch.object(profile, "dispatch_inputs", return_value={}),
    ):
        with pytest.raises(ValueError, match="runtime/cache changed"):
            profile.small_readiness(args)
    assert not (tmp_path / "controlled-readiness.json").exists()


def test_full_consumer_rejects_corrupted_readiness_objective(tmp_path):
    receipt = {
        "returncode": 0,
        "timed_out": False,
        "survivors": False,
        "ownership_established": True,
        "cleanup_complete": True,
        "errors": [],
    }
    path = tmp_path / "four-group-control-receipt.json"
    profile.save(path, receipt)
    profile.save(
        tmp_path / "controlled-readiness.json",
        {
            "pending_sha256": profile.digest(profile.HERE / "CONTROLLED-PENDING.json"),
            "receipt_sha256": profile.digest(path),
            "runtime_preserved": True,
            "evidence_sha256": {"input": "hash"},
            "dispatch": {"corrupted": True},
        },
    )
    with (
        patch.object(profile, "dispatch_inputs", return_value={"input": "hash"}),
        patch.object(profile, "dispatch", return_value={"actual": True}),
        patch.object(profile, "readiness") as readiness,
    ):
        with pytest.raises(ValueError, match="objective/evidence changed"):
            profile.run_worker(SimpleNamespace(control_ready=tmp_path))
    readiness.assert_not_called()


def test_dispatch_evidence_rejects_an_extra_worker(tmp_path):
    for index in range(4):
        (tmp_path / f"collection-gw{index}.json").write_text("[]")
        (tmp_path / f"phases-gw{index}.jsonl").write_text("")
    (tmp_path / "fixed-worker-plan.json").write_text("{}")
    before = profile.dispatch_inputs(tmp_path)
    (tmp_path / "phases-gw4.jsonl").write_text("")
    with pytest.raises(ValueError, match="evidence inventory"):
        profile.dispatch_inputs(tmp_path)
    assert len(before) == 9
