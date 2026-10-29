import base64
import csv
import hashlib
import io
import tarfile
import zipfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(directory):
    with tarfile.open(next(directory.glob("*.tar.gz"))) as archive:
        entries = archive.getmembers()
        assert len(entries) == 1269 and all(m.isfile() for m in entries)
        sdist = {m.name: dict(sha256=hashlib.sha256(archive.extractfile(m).read()).hexdigest(),
                             mode=m.mode, uid=m.uid, gid=m.gid,
                             uname=m.uname, gname=m.gname, size=m.size)
                 for m in entries}
        assert len(sdist) == len(entries)
    with zipfile.ZipFile(next(directory.glob("*.whl"))) as archive:
        entries = archive.infolist()
        assert len(entries) == 65 and all(not m.is_dir() for m in entries)
        data = {m.filename: archive.read(m) for m in entries}
        assert len(data) == len(entries)
        wheel = {m.filename: dict(sha256=hashlib.sha256(data[m.filename]).hexdigest(),
                                 full_mode=m.external_attr >> 16)
                 for m in entries}
    record = next(n for n in data if n.endswith(".dist-info/RECORD"))
    seen = set()
    for name, digest, size in csv.reader(io.StringIO(data[record].decode())):
        assert name not in seen and name in data
        seen.add(name)
        if name == record:
            assert digest == size == ""
        else:
            encoded = base64.urlsafe_b64encode(hashlib.sha256(data[name]).digest()).rstrip(b"=").decode()
            assert digest == "sha256=" + encoded and size == str(len(data[name]))
    assert seen == set(data)
    return dict(sdist=sdist, wheel=wheel)


def compare(expected, actual):
    differences = []
    for kind in expected:
        if expected[kind].keys() != actual[kind].keys():
            differences.append(dict(kind=kind, members=False))
        for name in expected[kind].keys() & actual[kind].keys():
            if expected[kind][name] != actual[kind][name]:
                differences.append(dict(kind=kind, name=name,
                                        expected=expected[kind][name], actual=actual[kind][name]))
    return dict(strict_pass=not differences, differences=differences)
