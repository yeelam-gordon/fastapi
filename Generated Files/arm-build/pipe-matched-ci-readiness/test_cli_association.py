"""Direct and redirector creation-identity associations, no process execution."""

import copy
import os
from unittest.mock import patch

import pytest
from cli_coverage_identity import IdentityConfigurer
from cli_identity import associate


def records():
    process = {"pid": 20, "birth_filetime": 100, "image": "stub.exe"}
    actual = [
        {"process_identity": process, "native_popen_object_id": 7, "argv": ["stub.exe"]}
    ]
    waited = [
        {"process_identity": process, "native_popen_object_id": 7, "returncode": 1}
    ]
    return actual, waited


def test_direct_windows_creation_identity():
    actual, waited = records()
    assert set(
        associate(
            actual,
            waited,
            [{"platform": "win32", "process": actual[0]["process_identity"]}],
        )
    ) == {20}


def redirector():
    from pathlib import Path

    actual, waited = records()
    actual[0]["process_identity"]["image"] = str(Path("stub.exe").resolve())
    return (
        actual,
        waited,
        [
            {
                "platform": "win32",
                "process": {"pid": 30, "birth_filetime": 110, "image": "real.exe"},
                "parent": copy.deepcopy(actual[0]["process_identity"]),
                "parent_live_during_capture": True,
            }
        ],
    )


def test_windows_redirector_live_parent_creation_identity():
    actual, waited, native = redirector()
    assert set(associate(actual, waited, native)) == {30}


@pytest.mark.parametrize("field,value", [("pid", 999), ("birth_filetime", 999)])
def test_redirector_wrong_parent_identity_rejected(field, value):
    actual, waited, native = redirector()
    native[0]["parent"][field] = value
    with pytest.raises(ValueError, match="Unbound"):
        associate(actual, waited, native)


def test_duplicate_native_and_unbound_cli_rejected():
    actual, waited, native = redirector()
    with pytest.raises(ValueError, match="duplicate"):
        associate(actual, waited, native + native)
    with pytest.raises(ValueError, match="Unbound"):
        associate([], [], native)


def test_parent_capture_failure_is_not_pid_fallback():
    actual, waited, native = redirector()
    del native[0]["parent"]
    with pytest.raises(ValueError, match="Unbound"):
        associate(actual, waited, native)


def test_mac_direct_pid_has_no_windows_birth_requirement():
    actual = [
        {
            "process_identity": {"pid": 20},
            "native_popen_object_id": 7,
            "argv": ["python"],
        }
    ]
    waited = [
        {"process_identity": {"pid": 20}, "native_popen_object_id": 7, "returncode": 1}
    ]
    assert set(
        associate(actual, waited, [{"platform": "darwin", "process": {"pid": 20}}])
    ) == {20}


def test_native_configurer_retains_live_parent_proof_and_rejects_identity_change(
    tmp_path,
):
    import json

    identity = {
        "platform": "win32",
        "process": {"pid": os.getpid(), "birth_filetime": 8},
        "parent": {"pid": 3, "birth_filetime": 2},
        "parent_live_during_capture": True,
    }
    with patch.dict(os.environ, {"CORRECTNESS_OUTPUT": str(tmp_path)}):
        with patch("cli_coverage_identity.native_identity", return_value=identity):
            IdentityConfigurer().configure(None)
            IdentityConfigurer().configure(None)
        path = tmp_path / f"cli-native-identity-{os.getpid()}.json"
        assert json.loads(path.read_text())["parent"] == identity["parent"]
        changed = copy.deepcopy(identity)
        changed["parent"]["birth_filetime"] = 99
        with patch("cli_coverage_identity.native_identity", return_value=changed):
            with pytest.raises(RuntimeError, match="identity changed"):
                IdentityConfigurer().configure(None)
