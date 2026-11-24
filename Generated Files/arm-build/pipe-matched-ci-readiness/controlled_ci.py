"""Explicit CI-common82 fixed-group profile; default/local profiles unchanged."""

import argparse
import json
import os
from pathlib import Path

import execution as base
from build_readiness import copy_uv_archives
from controlled_local import commands, control
from matched import HERE, admit
from screen import load, save

PROFILE = "pipe-fixed-groups-ci82-v1"


def readiness(args):
    if args.workers not in (3, 4):
        raise ValueError("Controlled ARM CI workers must be three or four")
    result = base.readiness(args)
    control()
    result["profile"] = PROFILE
    save(args.output / "readiness.json", result)
    return result


def dispatch(folder, workers, cases=2643):
    module = control()
    names = [f"gw{i}" for i in range(workers)]
    raw = load(folder / "collection-gw0.json")
    if workers not in (3, 4):
        raise ValueError("Controlled worker count invalid")
    if (
        len(raw) != cases
        or len(set(raw)) != cases
        or any(load(folder / f"collection-{name}.json") != raw for name in names)
    ):
        raise ValueError("Controlled collections differ")

    def split(node):
        return module.FixedLoadGroup._split_scope(None, node)

    owners = module.group_plan(raw, names, split, True)
    sent = {
        name: [
            node
            for scope, owner in owners.items()
            if owner == name
            for node in raw
            if split(node) == scope
        ]
        for name in names
    }
    actual = {
        name: [
            row["nodeid"]
            for row in map(
                json.loads, (folder / f"phases-{name}.jsonl").read_text().splitlines()
            )
            if row["when"] == "setup"
        ]
        for name in names
    }
    plan = load(folder / "fixed-worker-plan.json")
    if (
        plan["status"] != "EXACT_DISPATCH"
        or plan["exitstatus"] != 0
        or plan["collected_cases"] != cases
        or plan["scheduled_cases"] != cases
        or plan["source_hashes"] != module.SOURCE_HASHES
        or plan["group_owners"] != owners
        or plan["sent_by_worker"] != sent
        or actual != sent
    ):
        raise ValueError("Controlled dispatch/source/order mismatch")
    return {
        "group_owners": owners,
        "sent_by_worker": sent,
        "source_hashes": module.SOURCE_HASHES,
    }


def audit_command(args, action):
    command = base.audit_command(args, action)
    command[2] = str(Path(__file__))
    return command


def main(args):
    admit()
    if args.action == "run":
        command = audit_command(args, "worker") + [
            "--seconds",
            str(max(1, args.seconds - 35)),
        ]
        base.owned(
            command,
            HERE,
            os.environ.copy(),
            args.output,
            "controlled-ci-owner",
            args.seconds,
        )
    elif args.action == "worker":
        base.worker(
            args,
            readiness_check=readiness,
            commands=commands,
            audit_commands=audit_command,
            archive_copy=copy_uv_archives,
        )
    else:
        rows = load(args.output / "audit-rows.json")
        proofs = [dispatch(Path(row["folder"]), args.workers) for row in rows]
        if any(proof != proofs[0] for proof in proofs):
            raise ValueError("Controlled dispatch changed across payloads")
        if args.action == "cheap":
            save(Path(rows[0]["folder"]) / "controlled-dispatch-proof.json", proofs[0])
        base.audit(args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=["run", "worker", "cheap", "first-pair", "final"]
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--seconds", type=float, default=420)
    args = parser.parse_args()
    for name in ("source", "output", "uv"):
        setattr(args, name, getattr(args, name).resolve())
    main(args)
