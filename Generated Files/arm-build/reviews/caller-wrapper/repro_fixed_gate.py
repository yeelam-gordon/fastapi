"""Isolate compatibility of the new flags with the committed PP001 gate."""

import copy
import importlib.util
import json
import sys
from pathlib import Path

PROTOCOL = Path(__file__).resolve().parents[2] / "protocol"
sys.path.insert(0, str(PROTOCOL))
spec = importlib.util.spec_from_file_location("pair_fixtures", PROTOCOL / "test_pairs.py")
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)

report = fixtures.report("Windows")
sample = report["samples"][1]
results = []
for case in ("old_control", "additive_identity_field", "fixed_identity", "fixed_sdk"):
    candidate = copy.deepcopy(sample)
    receipt = candidate["wrapper_report"]
    if case != "old_control":
        receipt["environment"]["identity"]["dont_write_bytecode"] = True
    if case == "fixed_identity":
        receipt["phases"][2]["argv"].insert(1, "-B")
    if case == "fixed_sdk":
        receipt["phases"][3]["argv"].insert(1, "-B")
    try:
        fixtures.measure.validate_wrapper(candidate, report, set())
        outcome = "accepted"
    except ValueError as error:
        outcome = str(error)
    results.append({"case": case, "outcome": outcome})
if [r["outcome"] == "accepted" for r in results] != [True, True, False, False]:
    raise RuntimeError(f"Unexpected compatibility behavior: {results!r}")
print(json.dumps(results, indent=2))
