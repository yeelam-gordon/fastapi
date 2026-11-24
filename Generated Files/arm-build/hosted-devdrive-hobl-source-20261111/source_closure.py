"""Explicit source-only binding; no runtime installation or workload admission."""

import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_ROOT = Path(
    os.environ.get(
        "HOBL_SOURCE_ROOT",
        r"Q:\fastapi\Generated Files\worktrees\windows-launch-component-source-20261111\Generated Files\arm-build\pipe-matched-ci-readiness",
    )
).resolve()
sys.path.append(str(SOURCE_ROOT))


def verify():
    manifest = json.loads((HERE / "SOURCEPINS.json").read_text())
    for group, root in (("successor", HERE), ("reference", SOURCE_ROOT.parent)):
        for name, pin in manifest[group].items():
            path = root / name
            if (
                not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != pin
            ):
                raise RuntimeError(f"NoParityClaim: source closure changed: {path}")
