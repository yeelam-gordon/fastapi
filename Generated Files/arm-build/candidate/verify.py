"""Untimed coordinator: canonical source copy and strict Mac oracle comparison."""

import argparse
import hashlib
import json
import subprocess
import sys
import tarfile
from pathlib import Path

from validate import compare, inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    scratch = here / "scratch"
    scratch.mkdir(exist_ok=True)
    source = scratch / "source"
    source.mkdir()
    revision = subprocess.check_output(
        ["git", "-C", str(args.source_repo), "rev-parse", "HEAD"], text=True
    ).strip()
    archive_path = scratch / "source.tar"
    subprocess.run(
        [
            "git",
            "-c",
            "core.autocrlf=false",
            "-C",
            str(args.source_repo),
            "archive",
            "--format=tar",
            f"--output={archive_path}",
            revision,
        ],
        check=True,
    )
    with tarfile.open(archive_path) as archive:
        archive.extractall(source, filter="data")
    tree = subprocess.check_output(
        ["git", "-C", str(args.source_repo), "ls-tree", "-rz", revision]
    )
    manifest = {}
    for row in tree.split(b"\0"):
        if not row:
            continue
        metadata, raw_name = row.split(b"\t", 1)
        mode, kind, _ = metadata.split()
        if kind != b"blob" or mode not in (b"100644", b"100755"):
            raise ValueError(f"Unsupported Git entry: {row!r}")
        name = raw_name.decode("utf-8")
        manifest[name] = {
            "mode": 0o755 if mode == b"100755" else 0o644,
            "sha256": hashlib.sha256((source / name).read_bytes()).hexdigest(),
        }
    manifest_path = scratch / "source-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    command = [
        sys.executable,
        str(here / "build.py"),
        "--source",
        str(source),
        "--source-manifest",
        str(manifest_path),
        "--out-dir",
        str(scratch / "build"),
        "--workers",
        "3",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    (here / "functional.log").write_text(
        result.stdout + result.stderr, encoding="utf-8"
    )
    if result.returncode:
        raise RuntimeError(f"Build failed ({result.returncode}); see functional.log")
    expected, actual = (
        inventory(args.reference),
        inventory(scratch / "build" / "artifacts"),
    )
    (here / "actual-manifest.json").write_text(
        json.dumps(actual, indent=2), encoding="utf-8"
    )
    verdict = compare(expected, actual)
    receipt = {
        "source_revision": revision,
        "command": command,
        "build_exit": result.returncode,
        "sdist_members": len(actual["sdist"]),
        "wheel_members": len(actual["wheel"]),
        "comparison": verdict,
    }
    (here / "verification.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
    if not verdict["strict_pass"]:
        raise ValueError("Strict Mac archive comparison failed")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
