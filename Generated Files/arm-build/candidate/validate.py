import base64
import csv
import hashlib
import io
import tarfile
import zipfile


def require(condition, message):
    if not condition:
        raise ValueError(message)


def inventory(directory):
    with tarfile.open(next(directory.glob("*.tar.gz"))) as archive:
        entries = archive.getmembers()
        require(
            len(entries) == 1269 and all(m.isfile() for m in entries),
            "Invalid sdist inventory",
        )
        sdist = {
            m.name: {
                "sha256": hashlib.sha256(archive.extractfile(m).read()).hexdigest(),
                "mode": m.mode,
                "uid": m.uid,
                "gid": m.gid,
                "uname": m.uname,
                "gname": m.gname,
                "size": m.size,
            }
            for m in entries
        }
        require(len(sdist) == len(entries), "Duplicate sdist member")
    with zipfile.ZipFile(next(directory.glob("*.whl"))) as archive:
        entries = archive.infolist()
        require(
            len(entries) == 65 and all(not m.is_dir() for m in entries),
            "Invalid wheel inventory",
        )
        data = {m.filename: archive.read(m) for m in entries}
        require(len(data) == len(entries), "Duplicate wheel member")
        wheel = {
            m.filename: {
                "sha256": hashlib.sha256(data[m.filename]).hexdigest(),
                "full_mode": m.external_attr >> 16,
            }
            for m in entries
        }
    record = next(n for n in data if n.endswith(".dist-info/RECORD"))
    seen = set()
    for name, digest, size in csv.reader(io.StringIO(data[record].decode())):
        require(name not in seen and name in data, "Invalid RECORD membership")
        seen.add(name)
        if name == record:
            require(digest == size == "", "Invalid RECORD self row")
        else:
            encoded = (
                base64.urlsafe_b64encode(hashlib.sha256(data[name]).digest())
                .rstrip(b"=")
                .decode()
            )
            require(
                digest == "sha256=" + encoded and size == str(len(data[name])),
                "Invalid RECORD hash/size",
            )
    require(seen == set(data), "Incomplete RECORD")
    return {"sdist": sdist, "wheel": wheel}


def compare(expected, actual):
    differences = []
    for kind in expected:
        if expected[kind].keys() != actual[kind].keys():
            differences.append({"kind": kind, "members": False})
        for name in expected[kind].keys() & actual[kind].keys():
            if expected[kind][name] != actual[kind][name]:
                differences.append(
                    {
                        "kind": kind,
                        "name": name,
                        "expected": expected[kind][name],
                        "actual": actual[kind][name],
                    }
                )
    return {"strict_pass": not differences, "differences": differences}
