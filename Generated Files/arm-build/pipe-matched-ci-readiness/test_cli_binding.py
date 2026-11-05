"""Metadata-only validation of canonical CLI Popen object binding."""

from types import SimpleNamespace
from unittest.mock import patch

import matched_policy
import pytest


def test_cli_observer_returns_original_popen_object_and_restores_constructor():
    actual = SimpleNamespace(
        pid=731,
        args=[
            "python",
            "-m",
            "coverage",
            "run",
            "-m",
            "fastapi",
            "dev",
            "non_existent_file.py",
        ],
        returncode=1,
    )
    events = []
    with (
        patch.object(
            matched_policy.subprocess, "Popen", return_value=actual
        ) as original,
        patch.object(
            matched_policy,
            "emit",
            side_effect=lambda kind, **values: events.append((kind, values)),
        ),
    ):
        hook = matched_policy.pytest_runtest_call(
            SimpleNamespace(
                nodeid="tests/test_fastapi_cli.py::test_fastapi_cli@tests/test_fastapi_cli.py"
            )
        )
        next(hook)
        assert matched_policy.subprocess.Popen(actual.args) is actual
        with pytest.raises(StopIteration):
            next(hook)
        assert matched_policy.subprocess.Popen is original
    assert [row[0] for row in events] == ["actual_cli_popen", "actual_cli_waited"]
    assert (
        events[0][1]["native_popen_object_id"] == events[1][1]["native_popen_object_id"]
    )
