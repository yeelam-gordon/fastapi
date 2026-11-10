"""On-target read-only verification of the three fixed case profiles."""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bootstrap  # noqa: E402
import case_contract as contract  # noqa: E402
import raw_checks  # noqa: E402

ORIGINAL_SHA = "60a91039345826be0af10e4fb99f12a1bf710029c290073b23b4ba2181f993ec"
LOCAL_BASE = Path(r"Q:\fastapi\Generated Files\arm-build\matched-build-reference-20261110")
TARGET = r"C:\fastapi-matched-reference-prep05-20261110\runtime\Scripts\python.exe"
HOSTED_READY = True


def local_descriptor(root):
    bootstrap.require(sys.executable == TARGET, "exact retained SDK05 target")
    bootstrap.require(root.is_relative_to(LOCAL_BASE / "hosted-source")
                      and ".." not in root.parts, "new parent evidence only")
    root.mkdir()
    parent = LOCAL_BASE / "local-readiness-04"
    config = json.loads((parent / "configuration.json").read_bytes())
    paths = {
        "release": HERE / "RELEASE.json", "configuration": parent / "configuration.json",
        "admission": parent / "admission.json", "core_marker": parent / "CORE-ATTEMPT-ONCE",
        "launch_marker": parent / "LAUNCH-ONCE", "outer_command": parent / "outer-command.json",
        "outer_receipt": parent / "outer-owned-receipt.json", "outer_result": parent / "LAUNCH-RESULT.json",
        "creation_receipt": Path(config["creation_receipt"]),
    }
    descriptor = root / "case.json"
    bootstrap.save(descriptor, {
        "schema": 1, "profile": "LOCAL_WINDOWS_READINESS", "platform": "win32",
        "preparation_origin": "installed-copy", "descriptor_path": str(descriptor),
        "case_root": str(parent), "core_root": str(LOCAL_BASE / "reference-prototype"),
        "preparation_root": str(LOCAL_BASE / "local-preparation-05"),
        "output": config["output"], "verification_output": str(root / "verification"),
        "core_sourcepins_sha256": bootstrap.PIN, "release_root": str(HERE.parents[2]),
        "bindings": {name: contract.binding(path) for name, path in paths.items()},
        "records": [], "run_number": None,
    })
    return descriptor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path)
    parser.add_argument("--case-sha256")
    parser.add_argument("--local04-output", type=Path)
    args = parser.parse_args()
    bootstrap.require(sys.flags.isolated == 1 and sys.dont_write_bytecode, "mandatory -I -B")
    bootstrap.require(bootstrap.sha(HERE / "verify_readiness04.source") == ORIGINAL_SHA,
                      "frozen original verifier")
    path = local_descriptor(args.local04_output) if args.local04_output else args.case
    bootstrap.require(path and (args.local04_output or bootstrap.sha(path) == args.case_sha256),
                      "bound actual descriptor")
    case = json.loads(path.read_bytes())
    output = Path(case["verification_output"])
    bootstrap.require(output.is_absolute() and ".." not in output.parts, "fixed verification prefix")
    if case["profile"] == "LOCAL_WINDOWS_READINESS":
        bootstrap.require(sys.executable == TARGET
                          and output.is_relative_to(LOCAL_BASE / "hosted-source")
                          and path.is_relative_to(LOCAL_BASE / "hosted-source"),
                          "local replay confined to new parent evidence")
    else:
        bootstrap.require(path.parent.name == "matched-case"
                          and output == path.parent.parent / "matched-verification",
                          "hosted verification output prefix")
    config = json.loads(Path(case["bindings"]["configuration"]["path"]).read_bytes())
    for name in ("sdk_root", "venv_root", "source", "cache", "wheels", "output"):
        root = Path(config[name])
        bootstrap.require(not output.is_relative_to(root) and not root.is_relative_to(output),
                          "verification writes disjoint from all raw/runtime inputs")
    try:
        raw_checks.configure(path, output)
        return raw_checks.main()
    except Exception as error:
        output.mkdir(exist_ok=True)
        bootstrap.save(output / "INITIALIZATION-FAILURE.json",
                       {"status": "NOT_VERIFIED", "error": str(error), "case": str(path)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
