"""Compare retained validated host artifacts; never schedules or runs workloads."""

import argparse
import json
from pathlib import Path

from execution import compare
from screen import load, save


def phases(folder):
    mapping = load(folder / "raw-to-canonical.json")
    result = {}
    for path in folder.glob("phases-gw*.jsonl"):
        for line in path.read_text().splitlines():
            row = json.loads(line)
            node = mapping[row["nodeid"]]
            key = (node, row["when"])
            if key in result:
                raise ValueError(f"Duplicate phase: {key}")
            result[key] = row["duration_seconds"]
    return result


def report(windows, macos):
    win, mac = load(windows / "result.json"), load(macos / "result.json")
    result = compare(win, mac)
    comparisons = []
    for index in (1, 2):
        # Artifact extraction relocates outputs; use retained folder basename,
        # not producer-machine absolute source paths.
        left = phases(
            windows / Path(win["rows"][index]["folder"].replace("\\", "/")).name
        )
        right = phases(
            macos / Path(mac["rows"][index]["folder"].replace("\\", "/")).name
        )
        if left.keys() != right.keys():
            raise ValueError("Host canonical node/phase sets differ")
        comparisons.append(
            [
                {
                    "nodeid": node,
                    "phase": phase,
                    "windows_seconds": left[(node, phase)],
                    "macos_seconds": right[(node, phase)],
                    "gap_seconds": left[(node, phase)] - right[(node, phase)],
                }
                for node, phase in sorted(left)
            ]
        )
    result["per_case_B_orders"] = comparisons
    result["windows_within_host"] = win["comparison"]
    result["macos_within_host_identity_control"] = mac["comparison"]
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--macos", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    save(args.output, report(args.windows, args.macos))
