"""Portable extraction of existing P23 validators/statistics; no experiment on import."""

import base64
import csv
import hashlib
import io
import json
import statistics
import tarfile
import zipfile

from guards import SCHEDULE, require


def verify_record(archive):
    names = archive.namelist()
    require(len(names) == len(set(names)), "Duplicate wheel member")
    records = [n for n in names if n.endswith(".dist-info/RECORD")]
    require(len(records) == 1, "Wrong RECORD count")
    record = records[0]
    seen = set()
    for row in csv.reader(io.StringIO(archive.read(record).decode()), strict=True):
        require(len(row) == 3, "Malformed RECORD")
        name, digest, size = row
        require(name not in seen and name in names, "Invalid RECORD membership")
        seen.add(name)
        if name == record:
            require(digest == size == "", "Invalid self RECORD")
        else:
            data = archive.read(name)
            expected = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(
                b"="
            )
            require(
                digest == "sha256=" + expected.decode() and size == str(len(data)),
                "RECORD corruption",
            )
    require(seen == set(names), "Incomplete RECORD")


def full_inventory(directory):
    result = {"sdist": {}, "wheel": {}}
    require(len(list(directory.iterdir())) == 2, "Unexpected output files")
    with tarfile.open(next(directory.glob("*.tar.gz"))) as archive:
        for entry in archive:
            require(
                entry.isfile() and entry.name not in result["sdist"],
                "Duplicate/nonregular tar member",
            )
            result["sdist"][entry.name] = {
                "sha256": hashlib.sha256(archive.extractfile(entry).read()).hexdigest(),
                **{
                    k: getattr(entry, k)
                    for k in (
                        "mode",
                        "uid",
                        "gid",
                        "uname",
                        "gname",
                        "size",
                        "mtime",
                        "linkname",
                        "pax_headers",
                        "devmajor",
                        "devminor",
                    )
                },
                "type": entry.type.decode(),
            }
    with zipfile.ZipFile(next(directory.glob("*.whl"))) as archive:
        verify_record(archive)
        for entry in archive.infolist():
            result["wheel"][entry.filename] = {
                "sha256": hashlib.sha256(archive.read(entry)).hexdigest(),
                **{
                    k: getattr(entry, k)
                    for k in (
                        "date_time",
                        "compress_type",
                        "create_system",
                        "create_version",
                        "extract_version",
                        "flag_bits",
                        "volume",
                        "internal_attr",
                        "external_attr",
                        "file_size",
                        "CRC",
                    )
                },
                "extra": entry.extra.hex(),
                "comment": entry.comment.hex(),
            }
    return json.loads(json.dumps(result))


def summary(rows):
    valid = [r for r in rows if r.get("valid") and r["timed"]]
    require(len(valid) == 12, "Summary requires all twelve valid measured samples")
    arms = {}
    for arm in "AB":
        values = [r["wall_seconds"] for r in valid if r["arm"] == arm]
        median = statistics.median(values)
        arms[arm] = {
            "n": len(values),
            "values_seconds": values,
            "median_seconds": median,
            "min_seconds": min(values),
            "max_seconds": max(values),
            "range_seconds": max(values) - min(values),
            "range_percent_of_median": 100 * (max(values) - min(values)) / median,
            "stdev_seconds": statistics.stdev(values),
            "mad_seconds": statistics.median(abs(v - median) for v in values),
        }
    pairs = []
    for number, order in enumerate(SCHEDULE, 1):
        times = {r["arm"]: r["wall_seconds"] for r in valid if r["pair"] == number}
        delta = times["A"] - times["B"]
        pairs.append(
            {
                "pair": number,
                "order": order,
                **times,
                "A_minus_B_seconds": delta,
                "B_saving_percent": 100 * delta / times["A"],
            }
        )
    groups = {}
    for order in ("AB", "BA"):
        group = [p for p in pairs if p["order"] == order]
        groups[order] = {
            "A_median_seconds": statistics.median(p["A"] for p in group),
            "B_median_seconds": statistics.median(p["B"] for p in group),
            "paired_delta_median_seconds": statistics.median(
                p["A_minus_B_seconds"] for p in group
            ),
            "paired_saving_median_percent": statistics.median(
                p["B_saving_percent"] for p in group
            ),
            "B_wins": sum(p["A"] > p["B"] for p in group),
        }
        a, b = groups[order]["A_median_seconds"], groups[order]["B_median_seconds"]
        groups[order].update(
            median_delta_seconds=a - b, median_saving_percent=100 * (a - b) / a
        )
    a, b = arms["A"]["median_seconds"], arms["B"]["median_seconds"]
    wins = sum(p["A"] > p["B"] for p in pairs)
    return {
        "arms": arms,
        "pairs": pairs,
        "order_groups": groups,
        "median_delta_seconds": a - b,
        "median_saving_percent": 100 * (a - b) / a,
        "paired_delta_median_seconds": statistics.median(
            p["A_minus_B_seconds"] for p in pairs
        ),
        "paired_saving_median_percent": statistics.median(
            p["B_saving_percent"] for p in pairs
        ),
        "order_effect_AB_minus_BA_seconds": groups["AB"]["paired_delta_median_seconds"]
        - groups["BA"]["paired_delta_median_seconds"],
        "order_effect_AB_minus_BA_percentage_points": groups["AB"][
            "paired_saving_median_percent"
        ]
        - groups["BA"]["paired_saving_median_percent"],
        "B_wins": wins,
        "invalid_samples": [r["label"] for r in rows if not r.get("valid")],
        "advance": (
            100 * (a - b) / a >= 5
            and wins >= 5
            and all(g["median_delta_seconds"] > 0 for g in groups.values())
        ),
    }
