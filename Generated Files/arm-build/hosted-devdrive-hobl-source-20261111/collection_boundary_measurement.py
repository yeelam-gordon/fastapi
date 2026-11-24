"""Bind observer mode and sidecar checks to the stock diagnostic payload."""

import json
import os
from pathlib import Path
from types import SimpleNamespace

from screen import load

MODE = "HOBL_COLLECTION_BOUNDARY_DIAGNOSTIC"
PROFILE = "stock-hobl-storage-ci82-v1"
SCHEDULE = ("OFF", "ON", "ON", "OFF")


def require_diagnostic_allocation(driver, profile):
    review = load(Path(driver).with_name("PARENT-REVIEW.json"))
    allocation = review["ci_execution"]
    if (
        os.environ.get(MODE) != "1"
        or profile != PROFILE
        or allocation.get("question") != "hosted-stock-collection-boundaries"
        or allocation.get("observation_schedule") != list(SCHEDULE)
    ):
        raise ValueError("Exact collection diagnostic mode and allocation required")


def require_order(profile, rows):
    if [row["index"] for row in rows] != [1, 2, 3, 4] or [
        observation_enabled(profile, row) for row in rows
    ] != [False, True, True, False]:
        raise ValueError("Collection diagnostic requires ordered OFF/ON/ON/OFF rows")


def observation_enabled(profile, row):
    setting = os.environ.get(MODE, "0")
    if setting not in ("0", "1"):
        raise ValueError(f"{MODE} must be 0 or 1")
    if setting == "0":
        return False
    index = row["index"]
    if (
        profile != PROFILE
        or row["arm"] != "A"
        or type(index) is not int
        or not 1 <= index <= 4
    ):
        raise ValueError("Collection diagnostic requires four ordered stock A rows")
    return SCHEDULE[index - 1] == "ON"


def audit_payload(profile, row, workers):
    enabled = observation_enabled(profile, row)
    if os.environ.get(MODE, "0") == "0":
        return
    from cpu_sidecars import validate

    folder = Path(row["folder"])
    identities = [load(path) for path in sorted(folder.glob("identity-*.json"))]
    receipt = SimpleNamespace(**load(folder / "test-receipt.json"))
    validate(folder, enabled, identities, receipt, workers=workers)
    with (folder / "collection-boundary-proof.json").open(
        "x", encoding="utf-8"
    ) as stream:
        json.dump(
            {
                "position": row["index"],
                "observation": SCHEDULE[row["index"] - 1],
                "status": "VALIDATED",
                "workers": workers,
            },
            stream,
        )
