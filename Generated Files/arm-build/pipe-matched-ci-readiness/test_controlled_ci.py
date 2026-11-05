"""Opt-in routing/common82 and fixed-dispatch metadata regressions."""

import copy
import hashlib
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import controlled_ci as profile
import matched
import pytest
import yaml
from matched import HERE
from screen import save


def test_fifteen_routes_preserve_exact_existing_fourteen():
    root = HERE.parents[2]
    route = ".github/workflows/arm-build-diagnostics.yml"
    before = yaml.load(
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "show",
                f"832fb3f7a58830bcc226fb83ef711d0d7505adce:{route}",
            ],
            check=True,
            capture_output=True,
        ).stdout,
        Loader=yaml.BaseLoader,
    )
    after = yaml.load((root / route).read_bytes(), Loader=yaml.BaseLoader)
    inputs = after["on"]["workflow_dispatch"]["inputs"]["platform"]
    assert len(inputs["options"]) == 15
    assert inputs["options"] == before["on"]["workflow_dispatch"]["inputs"]["platform"][
        "options"
    ] + ["pipe-controlled-ci"]
    restored = copy.deepcopy(after)
    restored["on"]["workflow_dispatch"]["inputs"]["platform"]["options"].pop()
    del restored["jobs"]["pipe-controlled-ci"]
    restored["jobs"]["complete"]["if"] = restored["jobs"]["complete"][
        "if"
    ].removeprefix("inputs.platform != 'pipe-controlled-ci' && ")
    assert restored == before
    workflow = yaml.load(
        (root / ".github/workflows/pipe-matched-ci.yml").read_bytes(),
        Loader=yaml.BaseLoader,
    )
    assert (
        workflow["on"]["workflow_call"]["inputs"]["controlled-groups"]["default"]
        == "false"
    )
    assert workflow["jobs"]["matched"]["timeout-minutes"] == (
        "${{ inputs.controlled-groups && 10 || 8 }}"
    )
    assert workflow["jobs"]["matched"]["env"]["MATCHED_JOB_SECONDS"] == (
        "${{ inputs.controlled-groups && 600 || 480 }}"
    )


def test_ci_callback_uses_actual_common82_not_local_metadata():
    args = SimpleNamespace(workers=3, output=Path("."))
    with (
        patch.object(
            profile.base, "readiness", return_value={"accepted": True}
        ) as common82,
        patch.object(profile, "control"),
        patch.object(profile, "save"),
    ):
        assert profile.readiness(args)["profile"] == profile.PROFILE
    common82.assert_called_once_with(args)


@pytest.mark.parametrize("workers", [3, 4])
def test_native_host_control_supports_three_and_four_workers_and_rejects_order(
    tmp_path, workers
):
    module = profile.control()
    names = [f"gw{i}" for i in range(workers)]
    raw = [f"test_g{i}.py::test_case" for i in range(6)]

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
    plan = {
        "status": "EXACT_DISPATCH",
        "exitstatus": 0,
        "collected_cases": 6,
        "scheduled_cases": 6,
        "source_hashes": module.SOURCE_HASHES,
        "group_owners": owners,
        "sent_by_worker": sent,
    }
    for name in names:
        save(tmp_path / f"collection-{name}.json", raw)
        (tmp_path / f"phases-{name}.jsonl").write_text(
            "\n".join('{"when":"setup","nodeid":"' + node + '"}' for node in sent[name])
        )
    save(tmp_path / "fixed-worker-plan.json", plan)
    assert profile.dispatch(tmp_path, workers, 6)["sent_by_worker"] == sent
    plan["sent_by_worker"][names[0]] = list(reversed(sent[names[0]]))
    save(tmp_path / "fixed-worker-plan.json", plan)
    with pytest.raises(ValueError, match="dispatch/source/order"):
        profile.dispatch(tmp_path, workers, 6)


def test_wrong_control_hash_is_not_accepted_by_ci_profile():
    with patch("controlled_local.digest", return_value="wrong"):
        with pytest.raises(ValueError, match="control hash"):
            profile.control()


@pytest.mark.parametrize(
    "approved,qualified", [(False, False), (True, False), (True, True)]
)
def test_retained_plan_requires_new_bound_cli_qualification(
    tmp_path, approved, qualified
):
    (tmp_path / "CLI-ASSOCIATION-PENDING.json").write_text("{}")
    manifest = tmp_path / "SOURCEPINS.json"
    manifest.write_text("{}")
    save(
        tmp_path / "PARENT-REVIEW.json",
        {
            "approved": approved,
            "cli_identity_qualified": qualified,
            "sourcepins_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        },
    )
    with (
        patch.object(matched, "HERE", tmp_path),
        patch.object(matched, "static_check"),
        patch.object(matched, "verify_sourcepins") as verify,
        patch.dict(
            matched.os.environ,
            {"GITHUB_REPOSITORY": "yeelam-gordon/fastapi", "GITHUB_RUN_ATTEMPT": "1"},
        ),
    ):
        if approved and qualified:
            matched.admit()
            verify.assert_called_once()
        else:
            with pytest.raises(RuntimeError, match="NoParityClaim"):
                matched.admit()
            verify.assert_not_called()


@pytest.mark.parametrize(
    "requested", ["pipe-matched-ci-v1", "pipe-fixed-groups-ci82-v1"]
)
def test_controlled_approval_cannot_authorize_default_profile(tmp_path, requested):
    manifest = tmp_path / "SOURCEPINS.json"
    manifest.write_text("{}")
    save(
        tmp_path / "PARENT-REVIEW.json",
        {
            "approved": True,
            "profile": "pipe-fixed-groups-ci82-v1",
            "sourcepins_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        },
    )
    with (
        patch.object(matched, "HERE", tmp_path),
        patch.object(matched, "static_check"),
        patch.object(matched, "verify_sourcepins") as verify,
        patch.dict(
            matched.os.environ,
            {
                "GITHUB_REPOSITORY": "yeelam-gordon/fastapi",
                "GITHUB_RUN_ATTEMPT": "1",
                "MATCHED_PROFILE": requested,
            },
        ),
    ):
        if requested == "pipe-fixed-groups-ci82-v1":
            matched.admit()
            verify.assert_called_once()
        else:
            with pytest.raises(RuntimeError, match="NoParityClaim"):
                matched.admit()
            verify.assert_not_called()
