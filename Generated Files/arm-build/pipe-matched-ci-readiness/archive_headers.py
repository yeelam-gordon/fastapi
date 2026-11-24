"""Exact frozen member/header oracle for the new matched route only."""

import copy
import hashlib
import json
import tarfile
import zipfile

WHEEL_FIELDS = frozenset(
    {
        "CRC",
        "comment",
        "compress_type",
        "create_system",
        "create_version",
        "date_time",
        "external_attr",
        "extra",
        "extract_version",
        "file_size",
        "flag_bits",
        "internal_attr",
        "sha256",
        "volume",
    }
)
TAR_FIELDS = frozenset(
    {
        "devmajor",
        "devminor",
        "gid",
        "gname",
        "linkname",
        "mode",
        "mtime",
        "pax_headers",
        "sha256",
        "size",
        "type",
        "uid",
        "uname",
    }
)
NATIVE_EXECUTABLE_SCRIPTS = (
    "fastapi-0.119.1/scripts/lint.sh",
    "fastapi-0.119.1/scripts/test-cov-html.sh",
    "fastapi-0.119.1/scripts/format.sh",
    "fastapi-0.119.1/scripts/coverage.sh",
    "fastapi-0.119.1/scripts/test.sh",
)


def full_inventory(directory):
    paths = list(directory.iterdir())
    wheels = [path for path in paths if path.name.endswith(".whl")]
    sdists = [path for path in paths if path.name.endswith(".tar.gz")]
    if len(paths) != 2 or len(wheels) != 1 or len(sdists) != 1:
        raise ValueError("Exactly one sdist and one wheel required")
    result = {"sdist": {}, "wheel": {}}
    with tarfile.open(sdists[0]) as archive:
        for entry in archive:
            if not entry.isfile() or entry.name in result["sdist"]:
                raise ValueError("Duplicate/nonregular tar member")
            value = {
                name: getattr(entry, name) for name in TAR_FIELDS - {"sha256", "type"}
            }
            value["sha256"] = hashlib.sha256(
                archive.extractfile(entry).read()
            ).hexdigest()
            value["type"] = entry.type.decode()
            result["sdist"][entry.name] = value
    with zipfile.ZipFile(wheels[0]) as archive:
        for entry in archive.infolist():
            if entry.filename in result["wheel"]:
                raise ValueError("Duplicate wheel member")
            value = {
                name: getattr(entry, name)
                for name in WHEEL_FIELDS - {"sha256", "comment", "extra"}
            }
            value["sha256"] = hashlib.sha256(archive.read(entry)).hexdigest()
            value["comment"], value["extra"] = entry.comment.hex(), entry.extra.hex()
            result["wheel"][entry.filename] = value
    return json.loads(json.dumps(result))


def require_reference(actual, expected):
    for inventory in (actual, expected):
        if set(inventory) != {"sdist", "wheel"}:
            raise ValueError("Complete wheel/sdist inventory required")
        for kind, fields in (("wheel", WHEEL_FIELDS), ("sdist", TAR_FIELDS)):
            for name, value in inventory[kind].items():
                if set(value) != fields:
                    raise ValueError(f"Unknown/missing reference fields: {kind}/{name}")
    if actual != expected:
        raise ValueError("Full frozen archive member/header metadata differs")


def expected_headers(reference, platform):
    """Derive only source-defined ZIP creator and five native script modes."""
    if platform not in ("win32", "darwin"):
        raise ValueError(f"Unsupported header expectation platform: {platform}")
    require_reference(reference, reference)
    if not reference["wheel"] or any(
        member["create_system"] != 0 for member in reference["wheel"].values()
    ):
        raise ValueError("Frozen Windows baseline must have creator 0 for every member")
    if any(
        name not in reference["sdist"] or reference["sdist"][name]["mode"] != 0o644
        for name in NATIVE_EXECUTABLE_SCRIPTS
    ):
        raise ValueError(
            "Frozen 0.119.1 Windows script baseline must contain all five modes 0644"
        )
    expected = copy.deepcopy(reference)
    if platform == "darwin":
        for member in expected["wheel"].values():
            member["create_system"] = 3
        for name in NATIVE_EXECUTABLE_SCRIPTS:
            expected["sdist"][name]["mode"] = 0o755
    return expected
