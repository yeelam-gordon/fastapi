"""Pinned Git-object archive preparation, never a Windows checkout copy."""

import hashlib
import json
import subprocess
import tarfile

from guards import require, sha


def git(repo, *args):
    return subprocess.check_output(
        [
            "git",
            "-c",
            "core.autocrlf=false",
            "-c",
            "core.eol=lf",
            "-C",
            str(repo),
            *args,
        ]
    )


def fetch(root, name, url, revision, run):
    repo = root / (name + "-objects")
    repo.mkdir()
    run(name + "-init", ["git", "init", str(repo)])
    run(
        name + "-fetch",
        [
            "git",
            "-C",
            str(repo),
            "fetch",
            "--depth=1",
            "--no-tags",
            url,
            revision,
        ],
    )
    require(
        git(repo, "rev-parse", "FETCH_HEAD").decode().strip() == revision,
        "Fetched revision mismatch",
    )
    archive = root / (name + ".tar")
    run(
        name + "-archive",
        [
            "git",
            "-c",
            "core.autocrlf=false",
            "-c",
            "core.eol=lf",
            "-C",
            str(repo),
            "archive",
            "--format=tar",
            "--output=" + str(archive),
            revision,
        ],
    )
    return archive, prove(repo, revision, archive)


def prove(repo, revision, archive):
    entries = {}
    for row in git(repo, "ls-tree", "-r", "-z", revision).split(b"\0"):
        if not row:
            continue
        meta, name = row.split(b"\t", 1)
        mode, kind, oid = meta.decode().split()
        require(
            kind == "blob" and mode in ("100644", "100755"), "Unsupported Git entry"
        )
        entries[name.decode()] = (mode, oid)
    verified = {}
    with tarfile.open(archive) as tar:
        require(
            tar.pax_headers.get("comment") == revision, "Missing Git archive identity"
        )
        for member in tar:
            if member.isdir():
                continue
            require(
                member.isfile() and member.name not in verified,
                "Unsafe/duplicate member",
            )
            require(member.name in entries, "Archive payload outside Git tree")
            mode, oid = entries[member.name]
            data = tar.extractfile(member).read()
            blob = hashlib.sha1(
                b"blob " + str(len(data)).encode() + b"\0" + data
            ).hexdigest()
            require(blob == oid, "Archive bytes differ from raw Git blob")
            require(
                member.mode == (0o775 if mode == "100755" else 0o664),
                "Raw archive mode differs from Git flag",
            )
            verified[member.name] = {
                "blob": oid,
                "sha256": hashlib.sha256(data).hexdigest(),
                "git_mode": mode,
                "archive_mode": member.mode,
                "mtime": member.mtime,
            }
    require(set(entries) == set(verified), "Git/archive payload set mismatch")
    return {"revision": revision, "archive_sha256": sha(archive), "files": verified}


def extract(archive, target, proof):
    require(sha(archive) == proof["archive_sha256"], "Pinned Git archive drift")
    target.mkdir()
    with tarfile.open(archive) as tar:
        tar.extractall(target, filter="data")
    inventory = {name: tree_entry(target / name) for name in proof["files"]}
    for name, row in inventory.items():
        require(
            row["sha256"] == proof["files"][name]["sha256"], "Extraction hash drift"
        )
        require(
            row["mtime_ns"] == int(proof["files"][name]["mtime"] * 1_000_000_000),
            "Extraction mtime drift",
        )
    return inventory


def tree_entry(path):
    stat = path.stat()
    return {"sha256": sha(path), "mtime_ns": stat.st_mtime_ns, "mode": stat.st_mode}


def unchanged(target, before):
    require(
        all(tree_entry(target / name) == row for name, row in before.items()),
        "Source bytes/mtime/mode drift",
    )


def mode_receipt(inventory, proof):
    return {
        "status": "UNRESOLVED_CROSS_PLATFORM_MODE_GATE",
        "policy": "Normal tar data_filter; never chmod, normalize or waive.",
        "members": {
            name: {
                "git": proof["files"][name]["git_mode"],
                "archive": proof["files"][name]["archive_mode"],
                "data_filter": 0o755
                if proof["files"][name]["git_mode"] == "100755"
                else 0o644,
                "observed_stat": row["mode"] & 0o777,
            }
            for name, row in inventory.items()
        },
    }


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
