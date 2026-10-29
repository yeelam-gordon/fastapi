"""Replay immutable wrapper receipts; only Git reads, never builds or installs."""

import copy
import hashlib
import json
import subprocess
from pathlib import Path

from test_fixed_gates import evidence, measure

REVISION = "a08208414c28b5bf3525345a65380e8b52538971"
PREFIX = "Generated Files/arm-build/protocol/wrapper-evidence/readiness-v2/"


def committed_bytes(name):
    return subprocess.check_output(
        ["git", "-C", str(Path(__file__).resolve().parents[4]),
         "show", f"{REVISION}:{PREFIX}{name}"]
    )


def main():
    summary_bytes = committed_bytes("summary.json")
    summary = json.loads(summary_bytes)
    if summary["revision"] != measure.SOURCE:
        raise ValueError("Wrong immutable source")
    seen = set()
    results = []
    for original in summary["samples"]:
        label = original["label"]
        raw = committed_bytes(label + ".json")
        receipt = json.loads(raw)
        report = evidence("Windows")
        identities = receipt["identities"]
        report["source"].update(
            archive_sha256=summary["receipts"]["source_archive_sha256"],
            manifest_sha256=identities["source_manifest_sha256"],
        )
        report["uv"].update(
            path=original["command"][3], sha256=identities["uv_sha256"]
        )
        create = receipt["phases"][0]["argv"]
        report["runtime"].update(
            executable=create[create.index("--python") + 1],
            executable_sha256=identities["base_python_sha256"],
        )
        for name, field in (
            ("protocol/backend.lock", "lock_sha256"),
            ("protocol/isolated_build.py", "wrapper_sha256"),
            ("candidate/build.py", "sdk_sha256"),
        ):
            report["tool_hashes"][measure.PREFIX + name] = identities[field]
        sample = {
            "variant": "S" + str(receipt["workers"]),
            "argv": original["command"],
            "wall": original["whole_invocation_wall_seconds"],
            "wrapper_report": receipt,
            "correctness": {"archive_sha256": copy.deepcopy(receipt["artifacts"])},
        }
        measure.validate_wrapper(sample, report, seen)
        results.append({
            "sample": label,
            "raw_receipt_sha256": hashlib.sha256(raw).hexdigest(),
            "lifecycle_gate": "accepted",
        })
    print(json.dumps({
        "immutable_receipt_commit": REVISION,
        "raw_summary_sha256": hashlib.sha256(summary_bytes).hexdigest(),
        "samples": results,
        "scope": "receipt-schema replay only; no new run or artifact re-verification",
    }, indent=2))


if __name__ == "__main__":
    main()
