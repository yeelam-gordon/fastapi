"""Portable experiment; run in a provisioned Python 3.13/PDM 2.5 environment."""

import argparse
import importlib.metadata
import json
import tarfile
from pathlib import Path

import tomllib
from selector import configuration, safe_path, select


def build(source, manifest, output, workers):
    if importlib.metadata.version("pdm-backend") != "2.5.0":
        raise ValueError("Private PDM API requires pdm-backend==2.5.0")
    if workers not in (1, 3):
        raise ValueError("workers must be 1 or 3")
    source, output = source.resolve(), output.resolve()
    if output == source or output.is_relative_to(source):
        raise ValueError("Output must be outside source")
    modes = json.loads(manifest.read_text(encoding="utf-8"))
    for name, info in modes.items():
        safe_path(name)
        if not isinstance(info["mode"], int) or info["mode"] not in (
            0o644,
            0o664,
            0o755,
            0o775,
        ):
            raise ValueError(f"Unsupported canonical mode: {name}")
    # Inspect before PDM can load a project hook; never execute arbitrary config.
    files = []
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Source symlink unsupported: {path}")
        if path.is_file():
            files.append(path.relative_to(source).as_posix())
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
