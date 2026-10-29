"""Validate saved receipts and compare static candidates; never execute Git."""

import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
base = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("probe", base / "probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
ci = json.loads((base / "ci-git-receipt.json").read_text())
items = [ci["binary"]] + [
    row["identity"] for row in ci["helpers"]["candidates"] if "path" in row["identity"]
]
rows = []
for receipt in items:
    local = probe.identity(receipt["path"])
    rows.append({
        "scope": "static candidate; not execution proof",
        "local": local,
        "ci_sha256": receipt.get("sha256"),
        "hash_equal": bool(local.get("sha256")) and local.get("sha256") == receipt.get("sha256"),
    })
(base / "local-ci-static-comparison.json").write_text(json.dumps(rows, indent=2) + "\n")
r = json.loads((base / "result.json").read_text())
assert r["exit_code"] == 0 and not r["timed_out"] and not r["errors"]
assert all(
    p.get("creation_time_100ns_since_1601")
    and isinstance(p.get("exe"), str)
    and isinstance(p.get("parent_pid"), int)
    for p in r["processes"]
)
assert all(p["IsWow64Process2"]["status"] == "measured" for p in r["processes"])
assert any(
    p["exe"].lower() == r"c:\program files\git\clangarm64\bin\git.exe"
    for p in r["processes"]
)
assert all(len(p["sha256"]) == 64 for p in r["unique_images"])
print(f"PASS: {len(r['processes'])} observed processes, {len(r['unique_images'])} images")
