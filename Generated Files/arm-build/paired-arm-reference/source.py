"""Pinned Git-object archive preparation, never a Windows checkout copy."""

import hashlib
import json
import os
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


def generated_cache(root, proof):
    """Portable P47 exact-cache proof; compile for comparison, never execute."""
    import importlib.util
    import io
    import marshal
    import struct
    import types

    import tomllib

    cache_name = "__pycache__/pdm_build.cpython-312.pyc"
    expected = set(proof["files"]) | {
        cache_name,
        "dist/fastapi-0.119.1.tar.gz",
        "dist/fastapi-0.119.1-py3-none-any.whl",
        ".pdm-build/.gitignore",
        ".pdm-build/pyproject.toml",
    }
    files = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    require(files == expected, "Unexpected/missing generated source payload")
    for path in root.rglob("*"):
        require(
            not path.is_symlink() and not path.is_junction(), "Linked source output"
        )
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project["project"]["version"] = "0.119.1"
    project["project"]["dynamic"].remove("version")
    require(
        (root / ".pdm-build" / ".gitignore").read_bytes() == ("*" + os.linesep).encode()
        and tomllib.loads(
            (root / ".pdm-build" / "pyproject.toml").read_text(encoding="utf-8")
        )
        == project,
        "Unexpected generated PDM metadata",
    )
    source, cache = root / "pdm_build.py", root / cache_name
    data = cache.read_bytes()
    require(
        sha(source)
        == "dd68c065e895097ab395f00cb05e58456b72e963295003f6934a741e4a1aab46"
        and len(data) > 16
        and data[:4] == importlib.util.MAGIC_NUMBER
        and data[:4].hex() == "cb0d0d0a",
        "Wrong canonical source/native CPython 3.12 cache",
    )
    flags, timestamp, size = struct.unpack("<III", data[4:16])
    require(
        flags == 0
        and timestamp == (int(source.stat().st_mtime) & 0xFFFFFFFF)
        and size == source.stat().st_size,
        "Cache source header mismatch",
    )
    stream = io.BytesIO(data[16:])
    code = marshal.load(stream)
    require(
        isinstance(code, types.CodeType) and not stream.read(), "Invalid cache code"
    )

    def filenames(value):
        require(value.co_filename == str(source), "Cache code filename mismatch")
        for constant in value.co_consts:
            if isinstance(constant, types.CodeType):
                filenames(constant)

    filenames(code)
    expected_code = compile(
        source.read_bytes(), str(source), "exec", dont_inherit=True, optimize=0
    )
    require(
        code == expected_code, "Cache code/source filename differs from exact source"
    )
    return {
        "path": cache_name,
        "sha256": sha(cache),
        "mode": cache.stat().st_mode,
        "source_sha256": sha(source),
        "exact_code_and_header": True,
        "cache_executed_by_validator": False,
    }


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
