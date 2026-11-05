"""SHA-bound payload proofs; raw maps are parsed once and reused at final audit."""

import base64
import collections
import json
import re
import shutil
import sqlite3
import sys
import unicodedata
from pathlib import Path

from audit import combined, execution
from cli_identity import associate
from matched import HERE
from screen import COMMON, digest, load, save, tiny_outcome

sys.path.insert(0, str(COMMON))
from archive_headers import expected_headers, full_inventory, require_reference
from artifact_gate import artifact_set, equivalent


def require(value, message):
    if not value:
        raise ValueError(message)


def resource(folder, identities, workers):
    streams = list(folder.glob("events-*.jsonl"))
    require(len(streams) == workers + 1, "Missing policy streams")
    pids = {row["pid"] for row in identities}
    for path in streams:
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        require(
            all(row["pid"] in pids and row["namespace"] == str(folder) for row in rows),
            "Foreign policy identity",
        )
        installed = [row for row in rows if row["kind"] == "policy_install"]
        restored = [row for row in rows if row["kind"] == "policy_restore"]
        created = [row["loop_id"] for row in rows if row["kind"] == "worker_loop"]
        closed = [row for row in rows if row["kind"] == "first_close"]
        require(len(installed) == len(restored) == 1, "Incomplete policy lifetime")
        require(not any("failure" in row["kind"] for row in rows), "Resource failure")
        require(
            len(created) == len(closed) == restored[0]["created"], "Loop count mismatch"
        )
        require(
            set(created) == {row["loop_id"] for row in closed}, "Missing close proof"
        )
        require(
            restored[0]["main_closed"] and not restored[0]["failures"],
            "Main/final failure",
        )
        for row in closed:
            proof = row["certificate"]
            require(
                proof["api_close_success"]
                and proof["released_numeric_id_queries"] == 0,
                "Invalid close meaning",
            )
            require(
                not proof["instant_kernel_reclamation_claim"],
                "Invalid reclamation claim",
            )
        native_name = Path(installed[0]["data_filename"]).name
        require(
            any(
                path.name.startswith(native_name) for path in folder.glob(".coverage.*")
            ),
            "Native filename/PID binding absent",
        )


def source_gate(row, worker_pids, rewrite_pin):
    source = Path(row["source"])
    manifest = load(Path(row["manifest"]))
    helper = Path(row["helper"])
    require(
        all(
            digest(helper / name) == sha for name, sha in row["helper_sources"].items()
        ),
        "Owned helper source changed",
    )
    require(
        all(
            path.name in row["helper_sources"]
            or path.suffix == ".pyc"
            and "__pycache__" in path.parts
            for path in helper.rglob("*")
            if path.is_file()
        ),
        "Unexpected helper output",
    )
    require(
        all(digest(source / name) == sha for name, sha in manifest.items()),
        "Source bytes changed",
    )
    require(
        digest(Path(rewrite_pin["path"])) == rewrite_pin["sha256"],
        "Pytest writer changed",
    )
    extras = collections.Counter()
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        name = relative.as_posix()
        if name in manifest or name == ".git":
            continue
        if relative.parts[0] in {"dist", ".pdm-build", ".pytest_cache"}:
            extras[relative.parts[0]] += 1
        elif path.suffix == ".pyc" and "__pycache__" in relative.parts:
            extras["pyc"] += 1
        elif name == "log.txt":
            require(
                path.stat().st_size == 93
                and digest(path)
                == "fb2707ae6c5e112087fe74eaaa41173f74bfe7129998dd5d882f6df9d8bb15a9",
                "Unexpected log output",
            )
        else:
            match = re.fullmatch(r"(.+\.pyc)\.(\d+)", str(path))
            require(
                match
                and "__pycache__" in relative.parts
                and int(match[2]) in worker_pids,
                f"Unexpected output: {relative}",
            )
            require(
                Path(match[1]).is_file()
                and path.read_bytes() == Path(match[1]).read_bytes(),
                "Residual pyc differs",
            )
    return dict(extras)


def inputs(folder, row):
    paths = [
        path
        for path in folder.iterdir()
        if path.is_file() and path.name not in {"cheap-proof.json", "full-proof.json"}
    ]
    paths += list((folder / "artifacts").iterdir())
    paths += [Path(row["manifest"])]
    return {str(path): digest(path) for path in paths if path.is_file()}


AUDIT_OUTPUTS = frozenset(
    {
        "cheap-proof.json",
        "full-proof.json",
        "full-raw-map.json",
        "archive-inventory.json",
        "full-reference-headers.json",
    }
)


def exact_names(names):
    normalized = [unicodedata.normalize("NFC", name).casefold() for name in names]
    require(
        len(normalized) == len(set(normalized)), "Duplicate/colliding inventory names"
    )
    return sorted(names)


def file_names(paths):
    paths = list(paths)
    require(
        all(path.is_file() and not path.is_symlink() for path in paths),
        "Nonregular inventory member",
    )
    return exact_names([path.name for path in paths])


def inventory(folder):
    return {
        "folder": str(folder),
        "native_shards": file_names(folder.glob(".coverage.*")),
        "archives": file_names((folder / "artifacts").iterdir()),
        "native_audit_copies": file_names((folder / "native-audit-copies").iterdir())
        if (folder / "native-audit-copies").exists()
        else [],
        "payload_inputs": file_names(
            path
            for path in folder.iterdir()
            if path.is_file() and path.name not in AUDIT_OUTPUTS
        ),
    }


def verify_inventory(expected):
    for key in ("native_shards", "archives", "payload_inputs", "native_audit_copies"):
        exact_names(expected[key])
    require(
        inventory(Path(expected["folder"])) == expected,
        "Exact payload inventory changed",
    )


def cheap(row, workers, rewrite_pin):
    folder = Path(row["folder"])
    expected = load(HERE / "reference-cases.json")
    outcomes, identities = execution(folder, expected, True, workers)
    require(
        outcomes == load(HERE / "reference-outcomes.json"), "Canonical outcomes differ"
    )
    tiny_outcome(folder)
    resource(folder, identities, workers)
    pids = {item["pid"] for item in identities if item["worker"] != "controller"}
    extras = source_gate(row, pids, rewrite_pin)
    proof = {
        "identities": identities,
        "outcomes": outcomes,
        "source_extras": extras,
        "input_hashes": inputs(folder, row),
        "inventory": inventory(folder),
        "row": row,
    }
    save(folder / "cheap-proof.json", proof)
    return proof


def native_copies(folder):
    target = folder / "native-audit-copies"
    target.mkdir()
    proof = []
    for path in sorted(folder.glob(".coverage.*")):
        before = digest(path)
        destination = target / path.name
        shutil.copy2(path, destination)
        require(digest(destination) == digest(path) == before, "Native copy mismatch")
        with sqlite3.connect(
            destination.resolve().as_uri() + "?mode=ro&immutable=1", uri=True
        ) as db:
            stamp = dict(db.execute("SELECT key,value FROM meta"))["hash"]
        token = base64.b64encode(bytes.fromhex(stamp), altchars=b"01").decode()[:10]
        require(
            path.name.endswith(".H" + token + "h"),
            "Native streaming stamp/filename mismatch",
        )
        proof.append({"name": path.name, "sha256": before, "stored_stamp": stamp})
    require(proof, "No native coverage files")
    save(target / "copy-proof.json", proof)
    return target


def raw_map(data, source):
    source = Path(source).resolve()
    files = {}
    for filename in data.measured_files():
        path = Path(filename).resolve()
        require(path.is_relative_to(source), f"Foreign coverage file: {filename}")
        name = str(path.relative_to(source))
        require(name not in files, "Source-root mapping collision")
        files[name] = {
            "lines": sorted(data.lines(filename) or ()),
            "contexts_by_lineno": {
                str(line): sorted(contexts)
                for line, contexts in sorted(data.contexts_by_lineno(filename).items())
            },
        }
    return {"files": files, "contexts": sorted(data.measured_contexts())}


def verify_bound(proof):
    require("inventory" in proof, "Missing exact inventory proof")
    verify_inventory(proof["inventory"])
    for name, expected in proof["input_hashes"].items():
        require(digest(Path(name)) == expected, f"SHA-bound input changed: {name}")


def full(row):
    folder, source = Path(row["folder"]), Path(row["source"])
    cheap_proof = load(folder / "cheap-proof.json")
    verify_bound(cheap_proof)
    data = combined(native_copies(folder), cheap_proof["identities"], source)
    identities = {item["pid"] for item in cheap_proof["identities"]}
    flush = load(folder / "native-audit-copies" / "native-flush-proof.json")
    native_cli = {item["pid"] for item in flush["cli"] if item["pid"] not in identities}
    actual, waited = [], []
    for path in folder.glob("events-*.jsonl"):
        for line in path.read_text().splitlines():
            event = json.loads(line)
            if event["kind"] == "actual_cli_popen":
                actual.append(event)
            elif event["kind"] == "actual_cli_waited":
                waited.append(event)
    records = [
        load(folder / f"cli-native-identity-{pid}.json") for pid in sorted(native_cli)
    ]
    require(
        all(record["namespace"] == str(folder) for record in records),
        "Foreign native namespace",
    )
    require(
        native_cli and set(associate(actual, waited, records)) == native_cli,
        "Actual CLI Popen/native creation-identity binding differs",
    )
    for event in actual:
        require(
            event["argv"][1:]
            == [
                "-m",
                "coverage",
                "run",
                "-m",
                "fastapi",
                "dev",
                "non_existent_file.py",
            ],
            "Canonical CLI argv differs",
        )
    mapping = raw_map(data, source)
    save(folder / "full-raw-map.json", mapping)
    archives = artifact_set(folder / "artifacts", source, load(Path(row["manifest"])))
    reference = load(HERE / "reference-artifacts.json")
    full_headers = full_inventory(folder / "artifacts")
    require_reference(full_headers, expected_headers(reference, sys.platform))
    for name, value in archives.items():
        kind = "wheel" if name.endswith(".whl") else "sdist"
        require(
            len(value["members"]) == (58 if kind == "wheel" else 1196),
            "Archive member count",
        )
        expected = reference[kind]
        require(set(value["members"]) == set(expected), "Reference member names differ")
        for member, actual in value["members"].items():
            baseline = expected[member]
            require(
                actual["sha256"] == baseline["sha256"]
                and actual["bytes"] == baseline.get("size", baseline.get("file_size")),
                f"Reference member payload differs: {member}",
            )
    save(folder / "archive-inventory.json", archives)
    save(folder / "full-reference-headers.json", full_headers)
    current = inventory(folder)
    for key in ("native_shards", "archives", "payload_inputs"):
        require(
            current[key] == cheap_proof["inventory"][key],
            "Input inventory changed during full audit",
        )
    for name, expected in cheap_proof["input_hashes"].items():
        require(
            digest(Path(name)) == expected, f"Input changed during full audit: {name}"
        )
    bound = inputs(folder, row)
    bound[str(folder / "cheap-proof.json")] = digest(folder / "cheap-proof.json")
    for path in (folder / "native-audit-copies").iterdir():
        bound[str(path)] = digest(path)
    proof = {
        "input_hashes": bound,
        "inventory": inventory(folder),
        "raw_sha256": digest(folder / "full-raw-map.json"),
        "archive_sha256": digest(folder / "archive-inventory.json"),
        "header_platform": sys.platform,
        "header_policy": "source-defined-native-creator-only-v1",
    }
    save(folder / "full-proof.json", proof)
    return proof


def equal_pair(left, right):
    left, right = Path(left), Path(right)
    for folder in (left, right):
        verify_bound(load(folder / "full-proof.json"))
    require(
        load(left / "full-raw-map.json") == load(right / "full-raw-map.json"),
        "Entire raw association maps differ; STOP",
    )
    equivalent(
        load(left / "archive-inventory.json"), load(right / "archive-inventory.json")
    )


def final(rows):
    for row in rows:
        folder = Path(row["folder"])
        if not (folder / "full-proof.json").exists():
            full(row)
        verify_bound(load(folder / "full-proof.json"))
    for row in rows[1:]:
        equal_pair(rows[0]["folder"], row["folder"])
    return {
        "status": "PASS_ALL_FOUR_SHA_BOUND",
        "raw_maps": 4,
        "archive_inventories": 4,
        "cross_os_raw_equality_claim": False,
    }
