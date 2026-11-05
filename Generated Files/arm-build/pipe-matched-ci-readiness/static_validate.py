"""Read-only AST/YAML/router checks; no workflow, workload or network calls."""

import ast
import copy
import json
import re
import subprocess

import yaml
from matched import HERE, static_check

BASE = "e5aaf9a566b4dd9c8fd07e98b3cd5c629a3511b7"
ROUTER = ".github/workflows/arm-build-diagnostics.yml"


def main():
    root = HERE.parents[2]
    original = subprocess.run(
        ["git", "-C", str(root), "show", f"{BASE}:{ROUTER}"],
        check=True,
        capture_output=True,
        timeout=15,
    ).stdout
    before = yaml.load(original, Loader=yaml.BaseLoader)
    after = yaml.load((root / ROUTER).read_bytes(), Loader=yaml.BaseLoader)
    options = before["on"]["workflow_dispatch"]["inputs"]["platform"]["options"]
    revised = after["on"]["workflow_dispatch"]["inputs"]["platform"]["options"]
    assert len(options) == 13 and revised in (
        options + ["pipe-matched-ci"],
        options + ["pipe-matched-ci", "pipe-controlled-ci"],
    )
    restored = copy.deepcopy(after)
    restored["on"]["workflow_dispatch"]["inputs"]["platform"]["options"] = options
    del restored["jobs"]["pipe-matched-ci"]
    if "pipe-controlled-ci" in restored["jobs"]:
        del restored["jobs"]["pipe-controlled-ci"]
        restored["jobs"]["complete"]["if"] = restored["jobs"]["complete"][
            "if"
        ].removeprefix("inputs.platform != 'pipe-controlled-ci' && ")
    restored["jobs"]["complete"]["if"] = restored["jobs"]["complete"][
        "if"
    ].removeprefix("inputs.platform != 'pipe-matched-ci' && ")
    assert restored == before, "Existing routes/defaults changed"
    workflow = yaml.load(
        (root / ".github" / "workflows" / "pipe-matched-ci.yml").read_bytes(),
        Loader=yaml.BaseLoader,
    )
    job = workflow["jobs"]["matched"]
    assert job["timeout-minutes"] == "8"
    assert job["strategy"]["matrix"]["include"] == [
        {"runner": "windows-11-arm", "platform": "windows", "workers": "4"},
        {"runner": "macos-14", "platform": "macos", "workers": "3"},
    ]
    assert "github.repository == 'yeelam-gordon/fastapi'" in job["if"]
    assert "github.run_attempt == '1'" in job["if"]
    for step in job["steps"]:
        if "uses" in step:
            assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", step["uses"])
    paths = sorted(HERE.glob("*.py"))
    for path in paths:
        ast.parse(path.read_bytes(), filename=str(path))
    result = static_check()
    print(
        json.dumps(
            {
                "status": "PASS_STATIC_ONLY_NOT_READY",
                "ast_files": len(paths),
                "routes_preserved": 13,
                "routes_total": len(revised),
                "frozen_prototype_and_fixture": True,
                "yaml": True,
                "execution_admitted": result["admission"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
