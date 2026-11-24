"""Sparse-source and exact cached-proof inventory regressions; metadata only."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import build_readiness
import cli_readiness
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


@pytest.mark.parametrize("name", ["full-raw-map.json", "archive-inventory.json"])
def test_derived_output_changes_invalidate_cached_full_proof(payload_proof, name):
    folder, proof = payload_proof
    for field, output in (
        ("raw_sha256", "full-raw-map.json"),
        ("archive_sha256", "archive-inventory.json"),
    ):
        (folder / output).write_text("{}")
        proof[field] = digest(folder / output)
    (folder / name).write_text('{"changed": true}')
    with pytest.raises(ValueError, match="derived output changed"):
        matched_audit.verify_bound(proof, require_derived=True)


def test_identical_raw_map_tampering_cannot_pass_pair_equality(payload_proof):
    folder, proof = payload_proof
    for field, output in (
        ("raw_sha256", "full-raw-map.json"),
        ("archive_sha256", "archive-inventory.json"),
    ):
        (folder / output).write_text("{}")
        proof[field] = digest(folder / output)
    (folder / "full-proof.json").write_text(json.dumps(proof))
    (folder / "full-raw-map.json").write_text('{"same tampering": true}')
    with pytest.raises(ValueError, match="derived output changed"):
        matched_audit.equal_pair(folder, folder)


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


@pytest.mark.parametrize("module", [build_readiness, cli_readiness])
def test_local_readiness_uses_current_sourcepins_before_any_work(module):
    with (
        patch.object(
            module, "verify_sourcepins", side_effect=RuntimeError("source changed")
        ),
        patch.object(module, "runtime_snapshot") as snapshot,
        patch.object(module, "owned") as owned,
    ):
        with pytest.raises(RuntimeError, match="source changed"):
            module.worker(SimpleNamespace())
    snapshot.assert_not_called()
    owned.assert_not_called()


def test_build_logging_is_explicit_and_drops_ambient_observers():
    with patch.dict(
        build_readiness.os.environ,
        {
            "RUST_LOG": "trace",
            "UV_LOG_CONTEXT": "true",
            "PYTHONPROFILEIMPORTTIME": "1",
            "PYTHONPATH": "observer",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": "redirected",
        },
        clear=True,
    ):
        env = build_readiness.build_environment(HERE, HERE)
    assert env == {
        "SOURCE_DATE_EPOCH": "1700000000",
        "UV_CACHE_DIR": str(HERE / "uv-cache"),
        "UV_FIND_LINKS": HERE.as_uri(),
        "PIP_FIND_LINKS": HERE.as_uri(),
        "PIP_NO_INDEX": "1",
        "PIP_CONSTRAINT": (HERE / "build-constraints.txt").as_uri(),
        "TEMP": str(HERE / "temp"),
        "TMP": str(HERE / "temp"),
        "TMPDIR": str(HERE / "temp"),
    }


def test_build_log_context_adds_only_fixed_timestamp_logging_environment():
    with patch.dict(build_readiness.os.environ, {"RUST_LOG": "trace"}, clear=True):
        baseline = build_readiness.build_environment(HERE, HERE)
        enabled = build_readiness.build_environment(HERE, HERE, log_context=True)
    assert enabled == {
        **baseline,
        "UV_LOG_CONTEXT": "true",
        "RUST_LOG": "uv_build_frontend=debug,uv_distribution=debug,uv=debug",
    }


def test_build_log_context_cannot_combine_with_import_profiling():
    argv = [
        "--source-repo",
        str(HERE),
        "--output",
        str(HERE),
        "--uv",
        str(HERE / "uv.exe"),
        "--wheel-dir",
        str(HERE),
    ]
    assert not build_readiness.argument_parser().parse_args(argv).log_context
    assert (
        build_readiness.argument_parser()
        .parse_args([*argv, "--log-context"])
        .log_context
    )
    with pytest.raises(SystemExit) as error:
        build_readiness.argument_parser().parse_args(
            [*argv, "--log-context", "--profile-imports"]
        )
    assert error.value.code == 2
    with pytest.raises(ValueError, match="mutually exclusive"):
        build_readiness.build_environment(
            HERE, HERE, log_context=True, profile_imports=True
        )


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


@pytest.fixture
def native_log_row(tmp_path):
    source, helper, folder = (
        tmp_path / name for name in ("source", "helper", "payload")
    )
    for path in (source, helper, folder):
        path.mkdir()
    (helper / "copied.py").write_bytes(b"source")
    manifest, rewrite = tmp_path / "manifest.json", tmp_path / "rewrite.py"
    manifest.write_text("{}")
    rewrite.write_bytes(b"qualified writer")
    row = {
        "source": str(source),
        "helper": str(helper),
        "folder": str(folder),
        "manifest": str(manifest),
        "helper_sources": {"copied.py": digest(helper / "copied.py")},
    }
    return row, {"path": str(rewrite), "sha256": digest(rewrite)}


@pytest.mark.parametrize(
    "platform,newline,size,sha",
    [
        (
            "win32",
            "\r\n",
            93,
            "fb2707ae6c5e112087fe74eaaa41173f74bfe7129998dd5d882f6df9d8bb15a9",
        ),
        (
            "darwin",
            "\n",
            91,
            "ae838d85e7ea572eb7f048b1792eb39b8905cd5c58fe3a9e12160ebc38cd739f",
        ),
    ],
)
def test_native_log_byte_gate_accepts_only_source_pinned_crlf_or_lf(
    native_log_row, platform, newline, size, sha
):
    row, rewrite = native_log_row
    path = Path(row["source"]) / "log.txt"
    with path.open("w", encoding="utf-8", newline=newline) as stream:
        stream.write(
            "found query: some-query\nmessage to foo@example.com\nApplication shutdownApplication shutdown"
        )
    original = path.read_bytes()
    assert len(original) == size and digest(path) == sha
    with patch.object(matched_audit.sys, "platform", platform):
        matched_audit.source_gate(row, set(), rewrite)
    assert path.read_bytes() == original


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_wrong_native_log_bytes_fail_but_exact_generated_evidence_is_retained(
    native_log_row, platform
):
    row, rewrite = native_log_row
    path = Path(row["source"]) / "log.txt"
    path.write_bytes(b"unexpected log bytes\n")
    original = path.read_bytes()
    with patch.object(matched_audit.sys, "platform", platform):
        matched_audit.retain_source_log(row)
        with pytest.raises(ValueError, match="Unexpected log output"):
            matched_audit.source_gate(row, set(), rewrite)
    folder = Path(row["folder"])
    assert (folder / "source-log.bin").read_bytes() == original == path.read_bytes()
    proof = load(folder / "source-log.json")
    assert proof["size"] == len(original) and proof["sha256"] == digest(path)


def test_native_log_has_no_unsupported_platform_fallback(native_log_row):
    row, rewrite = native_log_row
    with patch.object(matched_audit.sys, "platform", "linux"):
        with pytest.raises(ValueError, match="Unsupported native log platform"):
            matched_audit.source_gate(row, set(), rewrite)
