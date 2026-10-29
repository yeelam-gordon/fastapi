"""Deliberately narrow PDM 2.5 package discovery, from current archive bytes."""

import fnmatch
import importlib.metadata
from pathlib import PurePosixPath

import tomllib


def safe_path(name):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ValueError(f"Unsafe path: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in ("", ".", "..") for p in name.split("/")):
        raise ValueError(f"Unsafe path: {name!r}")
    return name


def configuration(config, files):
    if config.get("build-system", {}).get("build-backend") != "pdm.backend":
        raise ValueError("Only pdm.backend is supported")
    if set(config["build-system"]) - {"requires", "build-backend"}:
        raise ValueError("Custom backend paths unsupported")
    pdm = config.get("tool", {}).get("pdm", {})
    if set(pdm) - {"build", "version", "distribution"}:
        raise ValueError("Unsupported PDM configuration")
    build = pdm.get("build", {})
    if set(build) - {"source-includes"}:
        raise ValueError("Unsupported PDM build configuration")
    if "pdm_build.py" in files or importlib.metadata.entry_points(
        group="pdm.build.hook"
    ):
        raise ValueError("Build hooks unsupported")
    if any(n.startswith("src/") for n in files):
        raise ValueError("src discovery unsupported")
    source_only = build.get("source-includes", ["tests"])
    if not isinstance(source_only, list) or not all(
        isinstance(n, str) for n in source_only
    ):
        raise ValueError("source-includes must be a list of paths")
    source_only = [safe_path(n.rstrip("/")) for n in source_only]
    if any(any(c in n for c in "*?[") for n in source_only):
        raise ValueError("Source globs unsupported")
    project = config["project"]
    if set(project.get("dynamic", [])) - {"version"}:
        raise ValueError("Only file-based dynamic version supported")
    version = pdm.get("version", {})
    if version and (
        set(version) - {"source", "path"} or version.get("source") != "file"
    ):
        raise ValueError("Only file-based version supported")
    required = {"pyproject.toml"}
    if version:
        required.add(safe_path(version["path"]))
    for field in ("readme", "license"):
        value = project.get(field)
        if field == "readme" and isinstance(value, str):
            required.add(safe_path(value))
        elif isinstance(value, dict) and "file" in value:
            required.add(safe_path(value["file"]))
    for pattern in project.get("license-files", ["LICEN[CS]E*", "COPYING*", "NOTICE*"]):
        safe_path(pattern)
        required.update(n for n in files if fnmatch.fnmatchcase(n, pattern))
    return source_only, required


def select(archive):
    entries = archive.getmembers()
    names = [safe_path(m.name.rstrip("/") if m.isdir() else m.name) for m in entries]
    if len(set(names)) != len(names) or any(
        not (m.isfile() or m.isdir()) for m in entries
    ):
        raise ValueError("Duplicate or nonregular archive entries")
    roots = {n.split("/")[0] for n in names}
    if len(roots) != 1:
        raise ValueError("Expected one archive root")
    root = roots.pop()
    files = {m.name[len(root) + 1 :]: m for m in entries if m.isfile()}
    if "" in files or any("/" not in m.name for m in entries if m.isfile()):
        raise ValueError("Files must be beneath archive root")
    with archive.extractfile(files["pyproject.toml"]) as stream:
        config = tomllib.loads(stream.read().decode("utf-8"))
    source_only, required = configuration(config, files)
    packages = {
        n.split("/")[0]
        for n in files
        if len(n.split("/")) == 2
        and (
            n.endswith("/__init__.py")
            or (n.split("/")[0].endswith("-stubs") and n.endswith("/__init__.pyi"))
        )
    } - {"__pycache__", "__pypackages__"}
    if not packages:
        raise ValueError("Top-level module fallback unsupported")
    selected = {
        n
        for n in files
        if ("/" not in n or n.split("/")[0] in packages)
        and not any(n == p or n.startswith(p + "/") for p in source_only)
    }
    if not required <= selected:
        raise ValueError(f"Metadata inputs excluded: {required - selected}")
    return [files[n].name for n in sorted(selected)]
