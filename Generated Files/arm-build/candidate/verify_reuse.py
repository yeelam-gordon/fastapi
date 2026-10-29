"""Untimed full-source reuse regressions; retains original golden evidence."""

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

from build import build
from validate import compare, inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    args = parser.parse_args()
    root = Path("scratch/rev2-integration").resolve()
    root.mkdir()
    manifest = Path("scratch/source-manifest.json").resolve()
    original = manifest.read_bytes()
    expected = inventory(args.reference)
    receipt = {}
    for family in ("sdk", "stock"):
        source = root / family
        source.mkdir()
        with tarfile.open("scratch/source.tar") as archive:
            archive.extractall(source, filter="data")
        if family == "sdk":
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                build(source, manifest, root / "s1", 1)
            Path("rev2-s1.log").write_text(stream.getvalue(), encoding="utf-8")
            verdict = compare(expected, inventory(root / "s1/artifacts"))
            if not verdict["strict_pass"]:
                raise ValueError(verdict)
            receipt["s1"] = verdict
        else:
            child = root / "child"
            child.mkdir()
            command = [
                str(args.uv),
                "build",
                str(source),
                "--python",
                sys.executable,
                "--offline",
                "--no-index",
                "--find-links",
                str(args.wheelhouse),
                "--cache-dir",
                str(root / "cache"),
                "--out-dir",
                str(root / "baseline"),
            ]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                env=os.environ | dict.fromkeys(("TEMP", "TMP", "TMPDIR"), str(child)),
            )
            Path("rev2-stock.log").write_text(
                result.stdout + result.stderr, encoding="utf-8"
            )
            receipt["stock"] = {"command": command, "exit": result.returncode}
            result.check_returncode()
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            build(source, manifest, root / f"after-{family}", 3)
        Path(f"rev2-after-{family}.log").write_text(stream.getvalue(), encoding="utf-8")
        verdict = compare(expected, inventory(root / f"after-{family}/artifacts"))
        if not verdict["strict_pass"] or manifest.read_bytes() != original:
            raise ValueError(
                "Reuse changed canonical manifest or failed strict Mac oracle"
            )
        receipt[f"after-{family}"] = verdict | {"manifest_unchanged": True}
    Path("rev2-verification.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
