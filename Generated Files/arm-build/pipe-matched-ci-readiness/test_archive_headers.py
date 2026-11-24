"""Metadata-only regressions; no build, test payload or native execution."""

import copy
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from archive_headers import require_reference
from build_readiness import copy_uv_archives
from execution import environment
from matched import HERE
from screen import load


@pytest.mark.parametrize(
    "kind,field,value",
    [
        ("wheel", "date_time", [2016, 1, 1, 0, 0, 0]),
        ("sdist", "pax_headers", {"mtime": "1700000001"}),
        ("sdist", "mode", 0o777),
        ("sdist", "uid", 999),
    ],
)
def test_frozen_full_header_drift_fails(kind, field, value):
    reference = load(HERE / "reference-artifacts.json")
    candidate = copy.deepcopy(reference)
    member = next(iter(candidate[kind]))
    candidate[kind][member][field] = value
    with pytest.raises(ValueError, match="header metadata differs"):
        require_reference(candidate, reference)


@pytest.mark.parametrize(
    "change", ["unknown-field", "missing-field", "extra-member", "missing-member"]
)
def test_no_unknown_field_defaults_or_partial_inventory(change):
    reference = load(HERE / "reference-artifacts.json")
    candidate = copy.deepcopy(reference)
    member = next(iter(candidate["wheel"]))
    if change == "unknown-field":
        candidate["wheel"][member]["unknown"] = 0
    elif change == "missing-field":
        del candidate["wheel"][member]["CRC"]
    elif change == "extra-member":
        candidate["wheel"]["extra"] = copy.deepcopy(candidate["wheel"][member])
    else:
        del candidate["wheel"][member]
    with pytest.raises(ValueError):
        require_reference(candidate, reference)


def test_new_route_explicitly_restores_control_epoch(tmp_path):
    args = SimpleNamespace(output=tmp_path)
    row = {
        "folder": str(tmp_path),
        "source": str(tmp_path / "source"),
        "helper": str(tmp_path / "helper"),
        "arm": "A",
    }
    with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "1"}):
        assert environment(args, row)["SOURCE_DATE_EPOCH"] == "1700000000"


@pytest.mark.parametrize("change", ["none", "wrong-control", "extra-file"])
def test_uv_control_file_is_explicit_and_archives_are_copied_exactly(tmp_path, change):
    source = tmp_path / "dist"
    source.mkdir()
    (source / "package.whl").write_bytes(b"wheel")
    (source / "package.tar.gz").write_bytes(b"sdist")
    (source / ".gitignore").write_bytes(b"wrong" if change == "wrong-control" else b"*")
    if change == "extra-file":
        (source / "unexpected.txt").write_bytes(b"extra")
    destination = tmp_path / "audit"
    if change != "none":
        with pytest.raises(ValueError, match="distribution output"):
            copy_uv_archives(source, destination)
        assert not destination.exists()
    else:
        assert copy_uv_archives(source, destination) == destination
        assert sorted(path.name for path in destination.iterdir()) == [
            "package.tar.gz",
            "package.whl",
        ]
        for path in destination.iterdir():
            assert path.read_bytes() == (source / path.name).read_bytes()
