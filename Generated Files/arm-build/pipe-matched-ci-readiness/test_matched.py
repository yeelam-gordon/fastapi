"""Pure metadata tests: never start a build, suite, loop, or native workload."""

import importlib
import io
import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import matched
import pytest


def test_frozen_sources_and_counterbalanced_budget():
    result = matched.static_check()
    assert result["schedule"] == ["A1", "B1", "B2", "A2"]
    assert result["commands_total"] == {"build": 8, "covered_test": 8}
    assert not result["admission"]


def test_unqualified_owned_fork_stays_closed():
    with patch.dict(
        os.environ,
        {"GITHUB_REPOSITORY": "yeelam-gordon/fastapi", "GITHUB_RUN_ATTEMPT": "1"},
    ):
        with pytest.raises(RuntimeError, match="NoParityClaim"):
            matched.admit()


def test_full_test_command_has_no_selection_and_same_workers():
    commands = matched.command_plan("python", "uv", "source", "payload", 3)
    assert commands["test"][commands["test"].index("-n") + 1] == "3"
    assert commands["test"][commands["test"].index("-m") + 1 :][:2] == [
        "pytest",
        "tests",
    ]
    assert "--offline" in commands["build"]
    pytest_args = commands["test"][commands["test"].index("pytest") + 1 :]
    assert "-k" not in pytest_args and "-m" not in pytest_args


def test_undefined_host_workers_rejected():
    with pytest.raises(ValueError, match="worker counts"):
        matched.command_plan("python", "uv", "source", "payload", 2)


def test_buffered_phase_rows_preserve_node_and_measurements():
    with patch.dict(os.environ, {"CORRECTNESS_OUTPUT": ".", "CORRECTNESS_SOURCE": "."}):
        observer = importlib.import_module("observer")
    stream = io.StringIO()
    report = SimpleNamespace(
        nodeid="tests/test_example.py::test_case",
        when="teardown",
        outcome="passed",
        duration=0.125,
    )
    with patch.object(observer, "PHASE_STREAM", stream):
        observer.pytest_runtest_logreport(report)
    row = json.loads(stream.getvalue())
    assert row["nodeid"] == report.nodeid
    assert row["duration_seconds"] == report.duration
    assert row["completion_monotonic_ns"] > 0
    assert row["pid"] == os.getpid()


def test_macos_identity_hook_never_imports_windows_private_api():
    import builtins

    import matched_policy

    original_import = builtins.__import__

    def platform_import(name, *args, **kwargs):
        if name in ("prototype", "_winapi", "asyncio.windows_utils"):
            raise AssertionError("Windows API import on Mac identity path")
        return original_import(name, *args, **kwargs)

    with (
        patch.dict(os.environ, {"OWNER_ARM": "B"}),
        patch.object(matched_policy.sys, "platform", "darwin"),
        patch("builtins.__import__", side_effect=platform_import),
        patch.dict(os.environ, {"MATCHED_READINESS": "not-admitted.json"}),
        patch.object(
            matched_policy.Path, "read_text", return_value='{"accepted":false}'
        ),
    ):
        with pytest.raises(RuntimeError, match="readiness required"):
            matched_policy.pytest_load_initial_conftests(None, None, [])
