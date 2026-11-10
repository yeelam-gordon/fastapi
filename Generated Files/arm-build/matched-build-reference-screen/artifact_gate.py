"""Complete same-host archive equivalence for the optional paired treatment."""

import base64
import csv
import hashlib
import io
import tarfile
import tomllib
import zipfile


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def archive_members(path, source, canonical):
    members = {}
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            require(
                len(entries) == len(set(archive.namelist())), "duplicate wheel members"
            )
            for entry in entries:
                data = archive.read(entry)
                members[entry.filename] = {
                    "sha256": digest(data),
                    "bytes": len(data),
                    "mode": entry.external_attr >> 16,
                    "directory": entry.is_dir(),
                }
                if entry.filename in canonical:
                    require(
                        digest(data) == canonical[entry.filename],
                        f"wheel source tie: {entry.filename}",
                    )
            wheels = [name for name in members if name.endswith(".dist-info/WHEEL")]
            require(len(wheels) == 1, "unique WHEEL required")
            require(
                "Generator: pdm-backend (2.5.0)" in archive.read(wheels[0]).decode(),
                "installed backend Generator must be pdm-backend (2.5.0)",
            )
            records = [name for name in members if name.endswith(".dist-info/RECORD")]
            require(len(records) == 1, "unique RECORD required")
            rows = list(csv.reader(io.StringIO(archive.read(records[0]).decode())))
            require(
                len(rows) == len(members) and {row[0] for row in rows} == set(members),
                "RECORD member coverage",
            )
            for name, recorded, size in rows:
                if name == records[0]:
                    require(not recorded and not size, "RECORD self entry")
                else:
                    data = archive.read(name)
                    expected = (
                        "sha256="
                        + base64.urlsafe_b64encode(hashlib.sha256(data).digest())
                        .rstrip(b"=")
                        .decode()
                    )
                    require(
                        recorded == expected and int(size) == len(data),
                        f"RECORD mismatch: {name}",
                    )
    else:
        with tarfile.open(path) as archive:
            entries = archive.getmembers()
            require(
                len(entries) == len({entry.name for entry in entries}),
                "duplicate sdist members",
            )
            pyprojects = []
            for entry in entries:
                data = archive.extractfile(entry).read() if entry.isfile() else b""
                members[entry.name] = {
                    "sha256": digest(data),
                    "bytes": len(data),
                    "mode": entry.mode,
                    "type": entry.type.decode(),
                    "linkname": entry.linkname,
                }
                relative = entry.name.split("/", 1)[-1]
                if relative == "pyproject.toml":
                    expected = tomllib.loads(
                        (source / relative).read_text(encoding="utf-8")
                    )
                    expected["project"]["dynamic"] = []
                    expected["project"]["version"] = "0.119.1"
                    require(
                        tomllib.loads(data.decode("utf-8")) == expected,
                        "unexpected generated pyproject metadata",
                    )
                    pyprojects.append(entry.name)
                elif relative in canonical:
                    require(
                        digest(data) == canonical[relative],
                        f"sdist source tie: {relative}",
                    )
            require(len(pyprojects) == 1, "unique generated pyproject required")
    return members


def artifact_set(folder, source, canonical):
    paths = sorted(folder.iterdir())
    paths = [path for path in paths if path.name.endswith((".whl", ".tar.gz"))]
    require(
        len(paths) == 2 and sum(path.suffix == ".whl" for path in paths) == 1,
        "complete sdist and wheel required",
    )
    return {
        path.name: {
            "sha256": digest(path.read_bytes()),
            "bytes": path.stat().st_size,
            "members": archive_members(path, source, canonical),
        }
        for path in paths
    }


def equivalent(actual, baseline):
    require(actual.keys() == baseline.keys(), "archive names differ")
    for name in baseline:
        require(
            actual[name]["members"] == baseline[name]["members"],
            f"archive member content/mode/type differs: {name}",
        )
