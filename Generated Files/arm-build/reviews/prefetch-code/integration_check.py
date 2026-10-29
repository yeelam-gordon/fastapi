"""Reproduce shared-source readiness on canonical 79cab inputs, without timing."""

import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

from build import build
from validate import compare, inventory


def main():
    root = Path("scratch/integration").resolve()
    root.mkdir()
    prepared = Path("scratch/candidate/scratch").resolve()
    manifest = root / "manifest.json"
    shutil.copyfile(prepared / "source-manifest.json", manifest)
    receipts = {}
    for family in ("sdk", "baseline"):
        source = root / f"{family}-source"
        source.mkdir()
        with tarfile.open(prepared / "source.tar") as archive:
            archive.extractall(source, filter="data")
        if family == "sdk":
            result = build(source, manifest, root / "s1", 1)
            reference = Path(
                r"Q:\fastapi\Generated Files\arm-build\results"
                r"\ci-40814588064\macos\ci\artifacts\prepare-baseline"
            )
            verdict = compare(inventory(reference), inventory(root / "s1/artifacts"))
            if not verdict["strict_pass"]:
                raise ValueError(verdict)
            receipts["s1"] = result | verdict
        else:
            tools = Path(r"Q:\fastapi\Generated Files\arm-build")
            child_scratch = root / "child-scratch"
            child_scratch.mkdir()
            command = [
                str(tools / "tools/uv.exe"),
                "build",
                str(source),
                "--python",
                str(tools / "tools/official-tool-environment/Scripts/python.exe"),
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
            Path("baseline.log").write_text(result.stdout + result.stderr)
            receipts["baseline"] = {"command": command, "exit": result.returncode}
            result.check_returncode()
        generated = [
            p.relative_to(source).as_posix()
            for p in (source / ".pdm-build").rglob("*")
            if p.is_file()
        ]
        try:
            build(source, manifest, root / f"after-{family}", 3)
        except ValueError as error:
            if str(error) != "Source files must exactly match canonical manifest paths":
                raise
            receipts[f"after-{family}"] = {
                "error": str(error),
                "generated_files": generated,
                "manifest_unchanged": manifest.read_bytes()
                == (prepared / "source-manifest.json").read_bytes(),
            }
        else:
            raise AssertionError("Expected reproduced shared-source rejection")
    Path("integration.json").write_text(json.dumps(receipts, indent=2))
    print(json.dumps(receipts))


if __name__ == "__main__":
    main()
