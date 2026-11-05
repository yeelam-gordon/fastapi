"""Native creator expectation follows pinned source, not observed Mac artifacts."""

import copy
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from archive_headers import expected_headers, require_reference
from matched import HERE
from screen import load


@pytest.mark.parametrize("platform,creator", [("win32", 0), ("darwin", 3)])
def test_native_zipinfo_constructor_creator_under_controlled_platform(
    platform, creator
):
    with patch.object(zipfile, "sys", SimpleNamespace(platform=platform)):
        assert zipfile.ZipInfo("member").create_system == creator


@pytest.mark.parametrize("platform,wrong", [("win32", 3), ("darwin", 0)])
def test_wrong_actual_creator_rejects_for_every_platform(platform, wrong):
    reference = load(HERE / "reference-artifacts.json")
    expected = expected_headers(reference, platform)
    actual = copy.deepcopy(expected)
    for member in actual["wheel"].values():
        member["create_system"] = wrong
    with pytest.raises(ValueError, match="header metadata differs"):
        require_reference(actual, expected)


def test_mac_policy_changes_only_creator_and_keeps_original_reference_immutable():
    reference = load(HERE / "reference-artifacts.json")
    original = copy.deepcopy(reference)
    expected = expected_headers(reference, "darwin")
    assert expected["sdist"] == reference["sdist"]
    assert expected["wheel"].keys() == reference["wheel"].keys()
    for name in expected["wheel"]:
        assert expected["wheel"][name]["create_system"] == 3
        expected["wheel"][name]["create_system"] = 0
    assert expected == original == reference
    assert expected_headers(reference, "win32") == original


@pytest.mark.parametrize("platform", ["linux", "", None])
def test_unsupported_platform_has_no_default(platform):
    with pytest.raises(ValueError, match="Unsupported"):
        expected_headers(load(HERE / "reference-artifacts.json"), platform)


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_baseline_must_have_windows_creator_zero_before_any_transform(platform):
    reference = load(HERE / "reference-artifacts.json")
    reference["wheel"][next(iter(reference["wheel"]))]["create_system"] = 3
    with pytest.raises(ValueError, match="baseline must have creator 0"):
        expected_headers(reference, platform)
