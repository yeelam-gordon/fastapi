"""Fail-closed paired-v4 analysis; unmet performance targets are not job failures."""

import argparse
import json
import statistics
from pathlib import Path

from measure_pairs import (
    ORDERS,
    SCHEMA,
    SOURCE,
    correct,
    known_baseline_failure,
    succeeded,
    validate_identities,
    validate_wrapper,
)


def validate(report, system):
    if report.get("schema") != SCHEMA or report.get("status") != "complete":
        raise ValueError("Incomplete or incompatible experiment")
    validate_identities(report)
    if report["system"] != system or report["source"]["revision"] != SOURCE:
        raise ValueError("Wrong OS/source identity")
    runtime = report["runtime"]
    if runtime["version"] != "3.13.15" or not runtime["native_arm64"]:
        raise ValueError("Wrong runtime")
    if not runtime.get("executable_sha256") or not runtime.get("shared_library_sha256"):
        raise ValueError("Missing runtime receipts")
    if report["uv"]["version"] != "0.13.6":
        raise ValueError("Wrong uv")
    if report["scopes"] != {
        "B": "standard_uv_isolated_wall",
        "S1": "sdk_caller_isolated_wall",
        "S3": "sdk_caller_isolated_wall",
    }:
        raise ValueError("Wrong isolation scopes")
    expected = [(-1, v) for v in ("B", "S1", "S3")] + [
        (i, v) for i, order in enumerate(ORDERS) for v in order
    ]
    if [(s["block"], s["variant"]) for s in report["samples"]] != expected:
        raise ValueError("Missing/reordered/replacement samples")
    seen_environments = set()
    for sample in report["samples"]:
        if sample["timed"] != (sample["block"] >= 0):
            raise ValueError("Wrong timing scope")
        if not succeeded(sample):
            raise ValueError("Invalid/failed/timed-out sample")
        check = sample["correctness"]
        if sample["variant"] != "B":
            validate_wrapper(sample, report, seen_environments)
        if not correct(check) and not known_baseline_failure(
            sample["variant"], system, check
        ):
            raise ValueError("Unexpected correctness failure")


def summarize(report):
    result = {}
    for variant in ("B", "S1", "S3"):
        samples = [
            s for s in report["samples"] if s["variant"] == variant and s["timed"]
        ]
        walls = [s["wall"] for s in samples]
        infrastructure = [s["infrastructure_wall"] for s in samples]
        result[variant] = {
            "raw": walls,
            "median": statistics.median(walls),
            "min": min(walls),
            "max": max(walls),
            "correct": all(correct(s["correctness"]) for s in samples),
            "scope": report["scopes"][variant],
            "ownership_infrastructure": {
                "raw": infrastructure,
                "median": statistics.median(infrastructure),
                "min": min(infrastructure),
                "max": max(infrastructure),
                "scope": "pre-command supervisor/ownership setup, excluded from command ratios",
            },
        }
    return result


def compare(windows, mac):
    validate(windows, "Windows")
    validate(mac, "Darwin")
    for field in ("source", "tool_hashes", "harness_revision", "scopes"):
        if windows[field] != mac[field]:
            raise ValueError(f"Cross-OS {field} mismatch")
    # Validate canonical RECORD independently of permissible physical row ordering.
    records = {
        s["correctness"]["canonical_record_sha256"]
        for report in (windows, mac)
        for s in report["samples"]
    }
    if len(records) != 1:
        raise ValueError("Cross-OS RECORD payload mismatch")
    summaries = {"Windows": summarize(windows), "Darwin": summarize(mac)}
    best = {
        system: min(("S1", "S3"), key=lambda v: summary[v]["median"])
        for system, summary in summaries.items()
    }
    ratio = (
        summaries["Windows"][best["Windows"]]["median"]
        / summaries["Darwin"][best["Darwin"]]["median"]
    )
    deltas = {}
    for report in (windows, mac):
        samples = {
            (s["block"], s["variant"]): s["wall"]
            for s in report["samples"]
            if s["timed"]
        }
        deltas[report["system"]] = [
            samples[(i, "S1")] - samples[(i, "S3")] for i in range(5)
        ]
    return {
        "schema": SCHEMA,
        "complete": True,
        "summaries": summaries,
        "variant_ratios_windows_over_mac": {
            v: summaries["Windows"][v]["median"] / summaries["Darwin"][v]["median"]
            for v in ("B", "S1", "S3")
        },
        "within_block_S1_minus_S3": deltas,
        "best_correct_sdk": best,
        "best_sdk_ratio_windows_over_mac": ratio,
        "sdk_caller_isolated_sample_parity": ratio <= 1,
        "goal": "sample parity" if ratio <= 1 else "goal not met",
        "baseline_eligible": {
            system: summary["B"]["correct"]
            and summary["B"]["scope"] == summary[best[system]]["scope"]
            for system, summary in summaries.items()
        },
        "scope": "SDK caller isolation; not per-hook parity, durable parity or release adoption",
        "cpu_seconds": None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("windows", type=Path)
    parser.add_argument("mac", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = compare(
        json.loads(args.windows.read_text()), json.loads(args.mac.read_text())
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
