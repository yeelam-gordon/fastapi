"""Round-2 selective.select, without that experiment's coordinator imports."""
import fnmatch
import importlib.metadata
from pathlib import PurePosixPath
import tomllib


def select(archive, destination):
    entries = archive.getmembers()
    assert all(m.isfile() or m.isdir() for m in entries)
    roots = {PurePosixPath(m.name).parts[0] for m in entries}
    assert len(roots) == 1
    root = roots.pop()
    files = {m.name.removeprefix(root + "/"): m for m in entries if m.isfile()}
    assert all(not PurePosixPath(n).is_absolute() and ".." not in PurePosixPath(n).parts
               for n in files)
    config = tomllib.loads(archive.extractfile(files["pyproject.toml"]).read().decode())
    assert config["build-system"]["build-backend"] == "pdm.backend"
    pdm = config.get("tool", {}).get("pdm", {})
    build = pdm.get("build", {})
    assert set(build) <= {"source-includes"}, "Unsupported PDM build configuration"
    assert "pdm_build.py" not in files
    assert not list(importlib.metadata.entry_points(group="pdm.build.hook"))
    assert not any(n.startswith("src/") for n in files), "src discovery unsupported"
    packages = {
        n.split("/")[0] for n in files if len(n.split("/")) == 2
        and (n.endswith("/__init__.py") or
             (n.split("/")[0].endswith("-stubs") and n.endswith("/__init__.pyi")))
    } - {"__pycache__", "__pypackages__"}
    assert packages, "Top-level module fallback unsupported"
    source_only = [n.rstrip("/") for n in build.get("source-includes", ["tests"])]
    assert all(not any(c in n for c in "*?[") for n in source_only)
    selected = {
        n for n in files if "/" not in n or n.split("/")[0] in packages
    }
    selected = {n for n in selected
                if not any(n == p or n.startswith(p + "/") for p in source_only)}
    project = config["project"]
    assert set(project.get("dynamic", [])) <= {"version"}
    version = pdm.get("version", {})
    assert not version or version.get("source") == "file"
    required = {"pyproject.toml"}
    if version:
        required.add(version["path"])
    readme = project.get("readme")
    if isinstance(readme, str):
        required.add(readme)
    elif isinstance(readme, dict) and "file" in readme:
        required.add(readme["file"])
    license = project.get("license")
    if isinstance(license, dict) and "file" in license:
        required.add(license["file"])
    for pattern in project.get("license-files", ["LICEN[CS]E*", "COPYING*", "NOTICE*"]):
        required.update(n for n in files if fnmatch.fnmatchcase(n, pattern))
    assert required <= selected, f"Metadata input not selected: {required - selected}"
    archive.extractall(destination, members=[files[n] for n in sorted(selected)], filter="data")
    return {"archive_files": len(files), "selected_files": len(selected),
            "packages": sorted(packages), "source_only": source_only,
            "required_metadata_inputs": sorted(required),
            "selected": sorted(selected)}
