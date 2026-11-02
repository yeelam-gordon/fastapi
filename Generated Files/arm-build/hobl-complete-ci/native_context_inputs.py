"""Offline source staging only; this does not authorize or execute CI/builds."""

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path, PurePosixPath

REVISION = "393ac715ddae841a85452d97edeedd8be8f0cda8"
PATCH_SHA = "078af61b8610ec8f7d68106fbd34e77cd637e5681b7a2059f07a0de95b4bd003"
CHANGED = {
    "coverage/collector.py",
    "coverage/tracer.pyi",
    "coverage/ctracer/tracer.c",
    "coverage/ctracer/tracer.h",
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_inputs():
    manifest = json.loads(
        Path(__file__).with_name("native-context-inputs.json").read_bytes()
    )
    require(manifest["revision"] == REVISION, "owner revision")
    require(
        manifest["stock"].keys() == manifest["candidate"].keys(),
        "source member sets",
    )
    require(
        {
            name
            for name in manifest["stock"]
            if manifest["stock"][name] != manifest["candidate"][name]
        }
        == CHANGED,
        "four-file candidate scope",
    )
    for name in manifest["stock"]:
        path = PurePosixPath(name)
        require(
            not path.is_absolute()
            and ".." not in path.parts
            and "\\" not in name
            and ":" not in name,
            "unsafe source path",
        )
    return manifest


def patched(original, patch):
    """Apply the hash-pinned diff without git, preserving each input's EOL."""
    require(sha(patch) == PATCH_SHA, "patch transport hash")
    lines = patch.decode("utf-8").replace("\r\n", "\n").splitlines(keepends=True)
    result = {}
    i = 0
    while i < len(lines):
        require(lines[i].startswith("--- stock/"), "patch old path")
        name = lines[i][10:].strip()
        i += 1
        require(lines[i] == f"+++ candidate/{name}\n", "patch new path")
        require(name in CHANGED and name not in result, "patch scope")
        raw = original[name]
        source = raw.replace(b"\r\n", b"\n").decode("utf-8").splitlines(True)
        eol = b"\r\n" if b"\r\n" in raw else b"\n"
        target, position = [], 0
        i += 1
        while i < len(lines) and lines[i].startswith("@@ "):
            match = re.match(r"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@", lines[i])
            require(match is not None, "patch hunk header")
            start = int(match[1]) - 1
            require(start >= position, "overlapping patch hunks")
            target.extend(source[position:start])
            position = start
            i += 1
            while i < len(lines) and not lines[i].startswith(("@@ ", "--- ")):
                kind, text = lines[i][0], lines[i][1:]
                require(kind in " +-", "patch hunk line")
                if kind in " -":
                    require(
                        position < len(source) and source[position] == text,
                        "patch context mismatch",
                    )
                    position += 1
                if kind in " +":
                    target.append(text)
                i += 1
        target.extend(source[position:])
        result[name] = "".join(target).encode("utf-8").replace(b"\n", eol)
    require(result.keys() == CHANGED, "incomplete patch")
    return result


def inspect(source, arm, manifest):
    values = {}
    for name, expected in manifest[arm].items():
        path = source.joinpath(*PurePosixPath(name).parts)
        require(
            path.is_file()
            and not path.is_symlink()
            and path.resolve().is_relative_to(source.resolve()),
            f"missing/linked source input: {name}",
        )
        values[name] = sha(path.read_bytes())
        require(values[name] == expected, f"{arm} source hash: {name}")
    return values


def stage(source, output):
    manifest = load_inputs()
    before = inspect(source, "stock", manifest)
    patch = Path(__file__).with_name("native-context.patch").read_bytes()
    changes = patched(
        {
            name: source.joinpath(*PurePosixPath(name).parts).read_bytes()
            for name in CHANGED
        },
        patch,
    )
    require(
        all(sha(raw) == manifest["candidate"][name] for name, raw in changes.items()),
        "candidate result hash",
    )
    require(not output.exists(), "fresh staging output required")
    output.mkdir(parents=True)
    for arm in ("stock", "candidate"):
        root = output / arm
        for name in manifest[arm]:
            path = root.joinpath(*PurePosixPath(name).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            if arm == "candidate" and name in changes:
                path.write_bytes(changes[name])
            else:
                shutil.copyfile(source.joinpath(*PurePosixPath(name).parts), path)
        inspect(root, arm, manifest)
    require(inspect(source, "stock", manifest) == before, "source changed")
    receipt = {
        "status": "SOURCE_STAGED_NOT_CI_READY",
        "revision": REVISION,
        "patch_sha256": sha(patch),
        "manifest_sha256": sha(
            Path(__file__).with_name("native-context-inputs.json").read_bytes()
        ),
        "inputs": manifest,
        "source_unchanged": True,
        "executed_builds": 0,
    }
    (output / "source-receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stage(args.source, args.output)
