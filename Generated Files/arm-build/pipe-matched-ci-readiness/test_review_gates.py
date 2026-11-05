"""Sparse-source and exact cached-proof inventory regressions; metadata only."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import local_preflight
import matched
import matched_audit
import pytest
import yaml
from matched import HERE
from screen import digest, load


def test_sparse_checkout_materializes_every_sourcepin_before_setup():
    root = HERE.parents[2]
    workflow = yaml.load(
        (root / ".github" / "workflows" / "pipe-matched-ci.yml").read_bytes(),
        Loader=yaml.BaseLoader,
    )
    steps = workflow["jobs"]["matched"]["steps"]
    patterns = steps[1]["with"]["sparse-checkout"].splitlines()
    pins = load(HERE / "SOURCEPINS.json")["files"]

    def missing(selected):
        return [
            name
            for name in pins
            if not any(
                name == pattern.lstrip("/")
                or pattern.endswith("/")
                and name.startswith(pattern.lstrip("/"))
                for pattern in selected
            )
        ]

    assert missing(patterns) == []
    assert set(
        missing(
            [pattern for pattern in patterns if not pattern.startswith("/.github/")]
        )
    ) == {
        ".github/workflows/pipe-matched-ci.yml",
        ".github/workflows/arm-build-diagnostics.yml",
    }
    assert "verify_sourcepins.ps1" in steps[2]["run"]
    for name, metadata in pins.items():
        path = root / name
        assert path.is_file() and path.stat().st_size == metadata["bytes"]
        assert digest(path) == metadata["sha256"]


@pytest.fixture
def payload_proof(tmp_path):
    (tmp_path / "artifacts").mkdir()
    for name in (".coverage.host.pid11.token", "source-before.json"):
        (tmp_path / name).write_bytes(b"input")
    (tmp_path / "artifacts" / "app.whl").write_bytes(b"wheel")
    (tmp_path / "artifacts" / "app.tar.gz").write_bytes(b"sdist")
    proof = {
        "inventory": matched_audit.inventory(tmp_path),
        "input_hashes": matched_audit.inputs(
            tmp_path, {"manifest": str(tmp_path / "source-before.json")}
        ),
    }
    return tmp_path, proof


@pytest.mark.parametrize("name", [".coverage.host.pid22.extra", "artifacts/extra.whl"])
def test_added_native_shard_or_archive_invalidates_cached_proof(payload_proof, name):
    folder, proof = payload_proof
    (folder / name).write_bytes(b"new")
    with pytest.raises(ValueError, match="inventory changed"):
        matched_audit.verify_bound(proof)


@pytest.mark.parametrize("name", [".coverage.host.pid11.token", "artifacts/app.whl"])
def test_missing_native_shard_or_archive_invalidates_cached_proof(payload_proof, name):
    folder, proof = payload_proof
    (folder / name).unlink()
    with pytest.raises(ValueError, match="inventory changed"):
        matched_audit.verify_bound(proof)


def test_duplicate_and_case_collision_inventory_names_reject(payload_proof):
    _, proof = payload_proof
    for extra in (
        proof["inventory"]["native_shards"][0],
        proof["inventory"]["native_shards"][0].upper(),
    ):
        changed = copy.deepcopy(proof)
        changed["inventory"]["native_shards"].append(extra)
        with pytest.raises(ValueError, match="Duplicate/colliding"):
            matched_audit.verify_bound(changed)


def test_source_defined_audit_outputs_allowed_but_new_inputs_reject(payload_proof):
    folder, proof = payload_proof
    for name in matched_audit.AUDIT_OUTPUTS:
        (folder / name).write_text("{}")
    matched_audit.verify_bound(proof)
    (folder / "unexpected.json").write_text("{}")
    with pytest.raises(ValueError, match="inventory changed"):
        matched_audit.verify_bound(proof)


def test_new_native_audit_copy_invalidates_final_proof_inventory(payload_proof):
    folder, proof = payload_proof
    (folder / "native-audit-copies").mkdir()
    (folder / "native-audit-copies" / ".coverage.extra").write_bytes(b"extra")
    with pytest.raises(ValueError, match="inventory changed"):
        matched_audit.verify_bound(proof)


def test_cached_full_final_proof_checks_inventory_without_raw_reparse(payload_proof):
    folder, proof = payload_proof
    (folder / "full-proof.json").write_text(json.dumps(proof))
    (folder / ".coverage.new").write_bytes(b"late")
    with patch.object(matched_audit, "full") as full:
        with pytest.raises(ValueError, match="inventory changed"):
            matched_audit.final([{"folder": str(folder)}])
    full.assert_not_called()


def test_local_preflight_is_guarded_without_ci_admission(tmp_path):
    output = HERE.parents[4] / "arm-build" / "pipe-matched-ci-readiness" / "mock-output"
    with (
        patch.object(Path, "mkdir"),
        patch.object(local_preflight, "owned", return_value="receipt") as owned,
    ):
        assert local_preflight.run(output) == "receipt"
    assert "--worker" in owned.call_args.args[0]
    assert owned.call_args.args[-1] == 75


@pytest.mark.parametrize(
    "name",
    ["portable_lifetime.py", "local-coverage.toml", "qualified-local83.json"],
)
def test_local_source_changes_reject_before_owned_child(tmp_path, name):
    helper = tmp_path / "Generated Files" / "arm-build" / "preflight"
    helper.mkdir(parents=True)
    source = helper / name
    source.write_bytes(b"qualified")
    (helper / "SOURCEPINS.json").write_text(
        json.dumps(
            {
                "files": {
                    str(source.relative_to(tmp_path)): {
                        "bytes": source.stat().st_size,
                        "sha256": digest(source),
                    }
                }
            }
        )
    )
    source.write_bytes(b"modified")
    with (
        patch.object(matched, "HERE", helper),
        patch.object(local_preflight, "owned") as owned,
    ):
        with pytest.raises(RuntimeError, match="reviewed source changed"):
            local_preflight.run(tmp_path / "unused-output")
    owned.assert_not_called()
    assert not (tmp_path / "unused-output").exists()


def test_local83_baseline_is_exact_ci82_plus_only_qualified_fastapi():
    baseline = load(HERE / "qualified-local83.json")["packages"]
    common = dict(
        line.split("==")
        for line in (HERE / "requirements.txt").read_text().splitlines()
    )

    def normalize(name):
        return name.lower().replace("_", "-").replace(".", "-")

    assert len(baseline) == 83 and baseline["fastapi"] == "0.119.1"
    assert {name: pin for name, pin in baseline.items() if name != "fastapi"} == {
        normalize(name): pin for name, pin in common.items()
    }


def test_local83_does_not_allow_arbitrary_extra_distribution():
    packages = load(HERE / "qualified-local83.json")["packages"]
    distributions = [
        SimpleNamespace(metadata={"Name": name}, version=version)
        for name, version in packages.items()
    ]
    distributions.append(
        SimpleNamespace(metadata={"Name": "unqualified-extra"}, version="1")
    )
    with patch.object(
        local_preflight.importlib.metadata, "distributions", return_value=distributions
    ):
        with pytest.raises(ValueError, match="Exact qualified local83 baseline"):
            local_preflight.local_metadata()
