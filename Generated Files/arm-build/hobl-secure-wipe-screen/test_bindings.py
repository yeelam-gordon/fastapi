from types import SimpleNamespace

import bindings
import pytest


def test_cli_requires_explicit_inputs_and_exact_sdk():
    with pytest.raises(SystemExit):
        bindings.parse_args(["--source", "source"])
    with pytest.raises(SystemExit):
        bindings.parse_args(
            [
                "--source",
                "source",
                "--python",
                "python.exe",
                "--output",
                "new",
                "--sdk-version",
                "latest",
            ]
        )


def test_output_cannot_reuse_or_modify_inputs(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    python = tmp_path / "venv" / "Scripts" / "python.exe"
    with pytest.raises(ValueError, match="NEW"):
        bindings.prepare_output(source, source, python)
    with pytest.raises(ValueError, match="source or reference"):
        bindings.prepare_output(source / "build", source, python)
    with pytest.raises(ValueError, match="source or reference"):
        bindings.prepare_output(python.parent.parent / "candidate", source, python)


def test_successful_command_cleanup_does_not_waive_survivors():
    with pytest.raises(RuntimeError, match="naturally drain"):
        bindings.require_receipt(
            SimpleNamespace(
                succeeded=False, returncode=0, survivors=True, cleanup_complete=True
            )
        )


@pytest.mark.parametrize(
    "failure", ["different-output", "wrong-origin", "changed-reference"]
)
def test_functional_schema_gate_rejects_incomplete_proof(failure):
    reference = {
        "cases": {"correct": True},
        "raw_hex": "01",
        "versions": {"binding": "26.1.0"},
    }
    candidate = {
        **reference,
        "candidate_loaded": True,
        "machine": 0xAA64,
        "pyinit": True,
    }
    before, after = {"reference.py": "same"}, {"reference.py": "same"}
    if failure == "different-output":
        candidate["raw_hex"] = "02"
    elif failure == "wrong-origin":
        candidate["candidate_loaded"] = False
    else:
        after["reference.py"] = "changed"
    with pytest.raises(ValueError):
        bindings.validate_functional(reference, candidate, before, after)


@pytest.mark.skipif(bindings.os.name != "nt", reason="Windows-only builder")
def test_cli_failed_build_publishes_only_unqualified_schema(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "new-output"

    def failed_build(args, private_output):
        raise RuntimeError("compiler family retained a live member")

    monkeypatch.setattr(bindings, "build", failed_build)
    code = bindings.main(
        [
            "--source",
            str(source),
            "--python",
            str(tmp_path / "venv" / "Scripts" / "python.exe"),
            "--output",
            str(output),
        ]
    )
    proof = bindings.json.loads((output / "binding-proof.json").read_text())
    assert code != 0
    assert proof["schema"] == 1
    assert proof["status"] == "UNQUALIFIED"
    assert "candidate_image_sha256" not in proof
