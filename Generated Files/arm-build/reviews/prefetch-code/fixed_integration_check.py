"""Pending full-source gates; run only after the committed fix is supplied."""

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

from build import build
from validate import compare, inventory


def main():
    root = Path("scratch/fixed-integration").resolve()
    root.mkdir()
    prepared = Path("scratch/candidate/scratch").resolve()
    manifest = root / "manifest.json"
    shutil.copyfile(prepared / "source-manifest.json", manifest)
    original_manifest = manifest.read_bytes()
    expected_source = json.loads(original_manifest)
    tools = Path(r"Q:\fastapi\Generated Files\arm-build")
    reference = (
        tools
        / "results"
        / "ci-40814588064"
        / "macos"
        / "ci"
        / "artifacts"
        / "prepare-baseline"
    )
    expected_artifacts = inventory(reference)
    receipts = {}

    def checked_build(source, name, workers):
        result = build(source, manifest, root / name, workers)
        verdict = compare(expected_artifacts, inventory(root / name / "artifacts"))
        if not verdict["strict_pass"]:
            raise ValueError(verdict)
        if manifest.read_bytes() != original_manifest:
            raise AssertionError("Canonical manifest changed")
        for path, entry in expected_source.items():
            digest = hashlib.sha256((source / path).read_bytes()).hexdigest()
            if digest != entry["sha256"]:
                raise AssertionError(f"Canonical source changed: {path}")
        receipts[name] = result | verdict | {"source_and_manifest_unchanged": True}

    for family in ("sdk", "baseline"):
        source = root / f"{family}-source"
        source.mkdir()
        with tarfile.open(prepared / "source.tar") as archive:
            archive.extractall(source, filter="data")
        if family == "sdk":
            checked_build(source, "s1", 1)
        else:
            child_scratch = root / "child-scratch"
            child_scratch.mkdir()
            command = [
                str(tools / "tools" / "uv.exe"),
                "build",
                str(source),
                "--python",
                str(
                    tools
                    / "tools"
                    / "official-tool-environment"
                    / "Scripts"
                    / "python.exe"
                ),
                "--offline",
                "--no-index",
                "--find-links",
                str(tools / "wheelhouse"),
                "--cache-dir",
                str(root / "uv-cache"),
                "--out-dir",
                str(root / "baseline-output"),
            ]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                env=os.environ
                | dict.fromkeys(("TEMP", "TMP", "TMPDIR"), str(child_scratch)),
            )
            Path("fixed-baseline.log").write_text(result.stdout + result.stderr)
            receipts["baseline"] = {
                "command": command,
                "exit": result.returncode,
                "artifact_correctness": "not waived; baseline is not SDK oracle",
            }
            result.check_returncode()
        checked_build(source, f"s3-after-{family}", 3)
    Path("fixed-integration.json").write_text(json.dumps(receipts, indent=2))
    print(json.dumps(receipts))


if __name__ == "__main__":
    main()
