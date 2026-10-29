"""Recheck every retained artifact, including untimed diagnostics, on C:."""

import importlib.util
import json
from pathlib import Path

from measure import modes, pe, sha

ROOT = Path(r"C:\fastapi-arm-build-lab\runtime-ab-2a73e36a\attempt-2")


def main():
    spec = importlib.util.spec_from_file_location(
        "validator", ROOT / "code" / "validator.py"
    )
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    report = json.loads((ROOT / "evidence" / "results.json").read_text())
    assert report["status"] == "complete"
    assert report["harness_sha256"] == sha(ROOT / "launch" / "measure.py")
    assert len(report["trials"]) == 12
    expected = validator.artifact_manifest(ROOT / "reference")
    expected_modes = modes(ROOT / "reference")
    checked = {}
    for output in (ROOT / "outputs").iterdir():
        validator.compare_manifests(expected, validator.artifact_manifest(output))
        assert modes(output) == expected_modes
        checked[output.name] = {path.name: sha(path) for path in output.iterdir()}
    assert len(checked) == 20
    for row in report["trials"]:
        assert row["artifact_sha256"] == checked[row["label"]]
        assert len(row["mac_differences"]) == 5
    assert pe(ROOT / "tools" / "uv.exe") == "0xaa64"
    observations = json.loads((ROOT / "evidence" / "transient-pycs.json").read_text())
    assert len(observations) == 4
    assert all(row["peak_observed_pdm_pycs"] > 0 for row in observations)
    result = {
        "status": "passed",
        "artifact_pairs": checked,
        "assertions": [
            "same Windows reference contents, RECORD and full modes",
            "all measured hashes retained",
            "native uv PE",
            "executed harness fingerprint",
            "transient PDM pycs observed",
        ],
    }
    (ROOT / "evidence" / "verification.json").write_text(json.dumps(result, indent=2))
    print("PASS: 20 whole artifact pairs; hashes, RECORD, contents and full modes")


if __name__ == "__main__":
    main()
