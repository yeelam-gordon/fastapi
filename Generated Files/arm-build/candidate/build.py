"""Portable experiment; run in a provisioned Python 3.13/PDM 2.5 environment."""

import argparse
import importlib.metadata
import json
import os
import stat
import tarfile
from pathlib import Path

import tomllib
from selector import configuration, safe_path, select


def checked_children(directory):
    for path in directory.iterdir():
        attributes = path.lstat()
        if stat.S_ISLNK(attributes.st_mode) or (
            getattr(attributes, "st_file_attributes", 0) & 0x400
        ):
            raise ValueError(f"Source link/reparse point unsupported: {path}")
        yield path


def source_files(source):
    files = []
    for path in checked_children(source):
        relative = path.relative_to(source).as_posix()
        if path.name.casefold() == ".pdm-build":
            if path.name != ".pdm-build":
                raise ValueError("Ambiguous backend state spelling")
            # Only PDM 2.5's known, flat generated state is owned by its cleaner.
            if not path.is_dir():
                raise ValueError("Invalid backend state directory")
            children = list(checked_children(path))
            if any(
                not p.is_file() or p.name not in {".gitignore", "pyproject.toml"}
                for p in children
            ):
                raise ValueError("Unrecognized backend state")
            sentinel = path / ".gitignore"
            if not sentinel.is_file() or sentinel.read_text(encoding="utf-8") != "*\n":
                raise ValueError("Unrecognized backend state sentinel")
            continue
        if path.is_dir():
            files.extend(f"{relative}/{name}" for name in source_files_nested(path))
        elif path.is_file():
            files.append(relative)
        else:
            raise ValueError(f"Nonregular source input: {path}")
    return files


def source_files_nested(directory):
    for path in checked_children(directory):
        if path.is_dir():
            yield from (f"{path.name}/{name}" for name in source_files_nested(path))
        elif path.is_file():
            yield path.name
        else:
            raise ValueError(f"Nonregular source input: {path}")


def build(source, manifest, output, workers):
    if importlib.metadata.version("pdm-backend") != "2.5.0":
        raise ValueError("Private PDM API requires pdm-backend==2.5.0")
    if workers not in (1, 3):
        raise ValueError("workers must be 1 or 3")
    if os.environ.get("PDM_BUILD_NO_CLEAN", "0").lower() not in ("0", "false", "no"):
        raise ValueError("Disabling backend state cleanup is unsupported")
    source, output = source.resolve(), output.resolve()
    if output == source or output.is_relative_to(source):
        raise ValueError("Output must be outside source")
    modes = json.loads(manifest.read_text(encoding="utf-8"))
    for name, info in modes.items():
        safe_path(name)
        if name.split("/")[0].casefold() == ".pdm-build":
            raise ValueError("Canonical inputs cannot own backend state")
        if not isinstance(info["mode"], int) or info["mode"] not in (
            0o644,
            0o664,
            0o755,
            0o775,
        ):
            raise ValueError(f"Unsupported canonical mode: {name}")
    # Inspect before PDM can load a project hook; never execute arbitrary config.
    files = source_files(source)
    configuration(
        tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8")), files
    )
    if set(files) != set(modes):
        raise ValueError("Source files must exactly match canonical manifest paths")

    from ops import BufferedSdistBuilder, extract_selected
    from pdm.backend.wheel import WheelBuilder

    output.mkdir(parents=True, exist_ok=False)
    artifacts, extracted = output / "artifacts", output / "extracted"
    artifacts.mkdir()
    extracted.mkdir()
    with BufferedSdistBuilder(source) as builder:
        builder.workers, builder.modes = workers, modes
        sdist = builder.build(str(artifacts))
    with tarfile.open(sdist) as archive:
        selected = select(archive)
        extract_selected(archive, extracted, selected)
    roots = list(extracted.iterdir())
    if len(roots) != 1:
        raise ValueError("Expected exactly one extracted project")
    with WheelBuilder(roots[0]) as builder:
        wheel = builder.build(str(artifacts))
    return {"sdist": str(sdist), "wheel": str(wheel), "selected_files": len(selected)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=(1, 3), default=3)
    args = parser.parse_args()
    print(
        json.dumps(build(args.source, args.source_manifest, args.out_dir, args.workers))
    )


if __name__ == "__main__":
    main()
