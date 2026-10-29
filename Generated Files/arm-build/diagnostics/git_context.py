"""Read-only Git command context, separate from package-build measurements."""

import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import time
from pathlib import Path


def collect(repo: Path, repeats: int) -> dict:
    if not 1 <= repeats <= 5:
        raise ValueError("Git context repeats must be between one and five")
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("Git executable is required")
    environment = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    commands = {
        "version": ["--version"],
        "local_config_read": [
            "config",
            "--local",
            "--get",
            "core.repositoryformatversion",
        ],
        "submodule_foreach_noop": ["submodule", "foreach", "--recursive", "exit 0"],
    }
    report = {
        "schema": "arm-analysis-git-context-v1",
        "purpose": "analysis-only",
        "performance_eligible": False,
        "scope": "standalone read-only commands; not checkout/auth subprocess timers",
        "git": {
            "path": git,
            "sha256": hashlib.sha256(Path(git).read_bytes()).hexdigest(),
        },
        "repo": str(repo.resolve()),
        "gitmodules_present": (repo / ".gitmodules").exists(),
        "environment_changes": {"GIT_TERMINAL_PROMPT": "0"},
        "commands": [],
        "summary": {},
    }
    for phase, arguments in commands.items():
        samples = []
        for iteration in range(repeats):
            argv = [git, "-C", str(repo), *arguments]
            started = time.perf_counter()
            result = subprocess.run(
                argv, env=environment, capture_output=True, timeout=15, check=False
            )
            wall = time.perf_counter() - started
            record = {
                "phase": phase,
                "iteration": iteration,
                "argv": argv,
                "wall_seconds": wall,
                "returncode": result.returncode,
                "stdout": result.stdout.decode("utf-8", errors="replace"),
                "stderr": result.stderr.decode("utf-8", errors="replace"),
            }
            report["commands"].append(record)
            if result.returncode:
                report["status"] = "failed"
                report["error"] = f"{phase} returned {result.returncode}"
                return report
            samples.append(wall)
        report["summary"][phase] = {
            "median_seconds": statistics.median(samples),
            "min_seconds": min(samples),
            "max_seconds": max(samples),
            "samples": len(samples),
        }
    report["status"] = "measured"
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Refusing to overwrite an existing context receipt")
    result = collect(args.repo, args.repeats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "summary": result["summary"]}))
    if result["status"] != "measured":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
