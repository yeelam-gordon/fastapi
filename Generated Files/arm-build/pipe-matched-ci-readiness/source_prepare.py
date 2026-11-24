"""Cold complete tracked source preparation, outside native timing."""

import hashlib
import shutil
import subprocess
from pathlib import Path

from matched import FIXTURE, HERE, SOURCE
from screen import prepare_source, source_snapshot

FIXTURE_MEMBER = "tests/test_dependency_after_yield_websockets.py"
ORIGINAL_FIXTURE = "71b8e5bce55177263b50c8cb1b193e7f89511f990372432ea640cde066e6b5e6"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def overlay_fixture(source, manifest):
    target = source / FIXTURE_MEMBER
    fixture = HERE / "qualified-fixture.py"
    if digest(fixture) != FIXTURE or digest(target) != ORIGINAL_FIXTURE:
        raise RuntimeError("Frozen ExitStack overlay precondition failed")
    target.write_bytes(fixture.read_bytes())
    revised = {name: digest(source / name) for name in manifest}
    if [name for name in manifest if manifest[name] != revised[name]] != [
        FIXTURE_MEMBER
    ]:
        raise RuntimeError(
            "Only the frozen test fixture may differ from prepared source"
        )
    return revised


def fresh_payload(source_checkout, destination):
    """Local-object checkout; no fetch, copied pycs, filters, or source preload."""
    source_checkout, destination = Path(source_checkout), Path(destination)
    if destination.exists():
        raise RuntimeError("Fresh payload destination already exists")
    subprocess.run(
        [
            "git",
            "-c",
            "core.autocrlf=false",
            "-C",
            str(source_checkout),
            "worktree",
            "add",
            "--detach",
            str(destination),
            SOURCE,
        ],
        check=True,
        timeout=30,
        capture_output=True,
    )
    prepare_source(destination)
    manifest = source_snapshot(destination)
    revised = overlay_fixture(destination, manifest)
    if next(destination.rglob("*.pyc"), None) is not None:
        raise RuntimeError("Cold source contains bytecode")
    return revised


def owned_helpers(destination):
    """Copy source files only, never predecessor bytecode or runtime outputs."""
    destination = Path(destination)
    destination.mkdir(exist_ok=False)
    for path in HERE.iterdir():
        if path.is_file() and path.suffix in (".py", ".toml", ".txt", ".patch"):
            shutil.copyfile(path, destination / path.name)
