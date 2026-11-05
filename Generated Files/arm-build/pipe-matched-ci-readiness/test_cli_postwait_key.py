"""Terminated retained handles permit key checks, not image provenance queries."""

import ctypes
from ctypes import wintypes
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cli_identity
import matched_policy
import pytest


def api_with_terminated_image(pid=731, birth=9):
    def times(handle, created, *unused):
        value = ctypes.cast(created, ctypes.POINTER(wintypes.FILETIME)).contents
        value.dwLowDateTime = birth
        value.dwHighDateTime = 0
        return 1

    return SimpleNamespace(
        GetProcessTimes=Mock(side_effect=times),
        GetProcessId=Mock(return_value=pid),
        QueryFullProcessImageNameW=Mock(
            side_effect=OSError(31, "terminated image unavailable")
        ),
        WaitForSingleObject=Mock(
            side_effect=AssertionError("Postwait key must not require liveness")
        ),
    )


def test_postwait_retained_handle_does_not_query_terminated_image():
    api = api_with_terminated_image()
    with patch.object(cli_identity, "windows_api", return_value=api):
        assert cli_identity.popen_key(SimpleNamespace(pid=731, _handle=44)) == {
            "pid": 731,
            "birth_filetime": 9,
        }
    api.QueryFullProcessImageNameW.assert_not_called()
    api.WaitForSingleObject.assert_not_called()


@pytest.mark.parametrize(
    "key", [{"pid": 732, "birth_filetime": 9}, {"pid": 731, "birth_filetime": 10}]
)
def test_postwait_pid_or_birth_mismatch_still_fails(key):
    process = SimpleNamespace(pid=731, args=["python"], returncode=1)
    with (
        patch.object(matched_policy.subprocess, "Popen", return_value=process),
        patch.object(matched_policy, "emit"),
        patch.object(
            matched_policy,
            "popen_identity",
            return_value={"pid": 731, "birth_filetime": 9, "image": "live.exe"},
        ) as initial,
        patch.object(matched_policy, "popen_key", return_value=key),
    ):
        hook = matched_policy.pytest_runtest_call(
            SimpleNamespace(nodeid="tests/test_fastapi_cli.py::test_fastapi_cli")
        )
        next(hook)
        matched_policy.subprocess.Popen(["python"])
        with pytest.raises(RuntimeError, match="creation identity changed"):
            next(hook)
        initial.assert_called_once_with(process)
