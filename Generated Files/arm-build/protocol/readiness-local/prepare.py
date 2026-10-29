"""Prepare private local inputs only; never execute a packaging campaign."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--harness-repo", type=Path, required=True)
    parser.add_argument("--harness-revision", required=True)
    parser.add_argument("--source-checkout", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--lab-parent", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    arm = Path("Generated Files") / "arm-build"
    root = args.lab_parent / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    evidence = repo / arm / "protocol" / "readiness-local" / "attempts" / root.name
    evidence.mkdir(parents=True, exist_ok=False)
    script = repo / arm / "protocol" / "readiness-local" / "prepare.py"
    started = time.perf_counter()
    receipt = {
        "schema": "local-paired-preparation-v1",
        "status": "preparing",
        "root": str(root),
        "commands": [],
        "samples_executed": 0,
        "cpu_seconds": None,
        "campaign_gate": "Root must approve the exact frozen commit and explicitly authorize execution",
    }
    env = os.environ.copy()
    for name in ("TEMP", "TMP", "TMPDIR"):
        env[name] = str(root / "scratch")
    env.update(
        UV_CACHE_DIR=str(root / "cache"),
        PIP_CACHE_DIR=str(root / "pip-cache"),
        UV_OFFLINE="1",
        UV_NO_INDEX="1",
        UV_NO_CONFIG="1",
        UV_PYTHON_DOWNLOADS="never",
        PYTHONDONTWRITEBYTECODE="1",
    )
    for name in ("scratch", "cache", "pip-cache", "logs"):
        (root / name).mkdir()
    receipt["environment_changes"] = {
        key: env[key]
        for key in (
            "TEMP",
            "TMP",
            "TMPDIR",
            "UV_CACHE_DIR",
            "PIP_CACHE_DIR",
            "UV_OFFLINE",
            "UV_NO_INDEX",
            "UV_NO_CONFIG",
            "UV_PYTHON_DOWNLOADS",
            "PYTHONDONTWRITEBYTECODE",
        )
    }

    def run(argv, label, cwd=root):
        begin = time.perf_counter()
        result = subprocess.run(
            [str(value) for value in argv],
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
        )
        log = evidence / f"{label}.log"
        log.write_bytes(result.stdout)
        receipt["commands"].append(
            {
                "argv": [str(value) for value in argv],
                "cwd": str(cwd),
                "returncode": result.returncode,
                "wall": time.perf_counter() - begin,
                "log": log.name,
            }
        )
        if result.returncode:
            raise RuntimeError(f"{label} exited {result.returncode}")
        return result.stdout.decode("utf-8", errors="replace")

    try:
        revision = run(
            ["git", "-C", args.harness_repo, "rev-parse", args.harness_revision],
            "harness-revision",
        ).strip()
        if revision != args.harness_revision or len(revision) != 40:
            raise ValueError("An exact full committed harness SHA is required")
        receipt["harness_revision"] = revision
        code = root / "code"
        run(
            [
                "git",
                "clone",
                "--no-checkout",
                "--no-hardlinks",
                args.harness_repo,
                code,
            ],
            "clone",
        )
        # Use precisely the workflow's non-cone allowlist, not the research tree.
        workflow = run(
            [
                "git",
                "-C",
                args.harness_repo,
                "show",
                revision + ":.github/workflows/arm-build-experiment.yml",
            ],
            "frozen-workflow",
        )
        section = workflow.split("sparse-checkout: |", 1)[1].split("      - uses:", 1)[
            0
        ]
        patterns = [line.strip() for line in section.splitlines() if line.strip()]
        run(["git", "-C", code, "config", "core.autocrlf", "false"], "autocrlf")
        run(["git", "-C", code, "sparse-checkout", "init", "--no-cone"], "sparse-init")
        pattern_file = code / ".git" / "info" / "sparse-checkout"
        pattern_file.write_text("\n".join(patterns) + "\n", newline="\n")
        run(["git", "-C", code, "checkout", "--detach", revision], "checkout")
        receipt["sparse_patterns"] = patterns
        uv = root / "uv.exe"
        shutil.copy2(args.uv, uv)
        receipt["uv_version"] = run([uv, "--version"], "uv-version").strip()
        receipt["uv_sha256"] = sha(uv)
        python = root / "env" / "Scripts" / "python.exe"
        run(
            [
                uv,
                "venv",
                "--no-config",
                "--offline",
                "--python",
                args.python,
                "--no-python-downloads",
                root / "env",
            ],
            "private-venv",
        )
        wheels = root / "wheelhouse"
        shutil.copytree(args.wheelhouse, wheels)
        run(
            [
                uv,
                "pip",
                "install",
                "--python",
                python,
                "--offline",
                "--no-index",
                "--only-binary",
                ":all:",
                "--find-links",
                wheels,
                "--require-hashes",
                "-r",
                code / arm / "tooling.lock",
            ],
            "locked-tooling",
        )
        protocol = code / arm / "protocol"
        for name, file in (
            ("controller-help", protocol / "measure_pairs.py"),
            ("wrapper-help", protocol / "isolated_build.py"),
            ("sdk-help", code / arm / "candidate" / "build.py"),
        ):
            run([python, "-B", file, "--help"], name)
        run([uv, "build", "--help"], "uv-build-help")
        # Producer fixture tests run from Q:, never a concurrent C: benchmark.
        for name in (
            "test_pairs.py",
            "test_owned_process.py",
            "test_isolated_build.py",
        ):
            run([python, "-B", repo / arm / "protocol" / name], name, repo)
        run([python, "-B", "-m", "ruff", "check", script], "local-static", repo)
        output = root / "evidence"
        output.mkdir()
        code_text = (
            "import sys,json; from pathlib import Path; "
            f"sys.path.insert(0,{str(protocol)!r}); import measure_pairs as m; "
            f"output=Path({str(output)!r}); "
            f"source=m.canonical_source(Path({str(args.source_checkout)!r}),output); "
            "m.save(output/'source-identity.json',source); "
            "m.save(output/'runtime.json',m.runtime_receipt()); "
            f"m.save(output/'volumes.json',m.volumes([Path({str(code)!r}),output,"
            f"Path(sys.executable),Path(sys.base_prefix),Path({str(uv)!r})])); "
            "print(json.dumps(source))"
        )
        run([python, "-B", "-c", code_text], "canonical-source")
        receipt["source"] = json.loads((output / "source-identity.json").read_text())
        receipt["runtime"] = json.loads((output / "runtime.json").read_text())
        receipt["volumes"] = json.loads((output / "volumes.json").read_text())
        receipt["wheels"] = {p.name: sha(p) for p in wheels.glob("*.whl")}
        names = run(
            [
                "git",
                "-C",
                code,
                "ls-tree",
                "--full-tree",
                "-r",
                "--name-only",
                revision,
            ],
            "full-tree-inventory",
        ).splitlines()
        selected = [name for name in names if (code / name).is_file()]
        receipt["materialized_files"] = {name: sha(code / name) for name in selected}
        receipt["additional_preflight_findings"] = [
            {
                "id": "LOCAL-UV-VERSION-002",
                "detail": "Controller requires exact 'uv 0.13.6'; actual version retained",
                "blocks_current_controller": receipt["uv_version"] != "uv 0.13.6",
            },
        ]
        receipt["controller_source_policy"] = (
            "One canonical source manifest; controller prepares per-sample source "
            "copies outside each command timer, all on C:, unchanged"
        )
        receipt["status"] = "prepared-blocked"
    except Exception as exc:
        receipt["status"] = "preparation-failed"
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        receipt["preparation_wall"] = time.perf_counter() - started
        (evidence / "preparation.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(json.dumps({"status": receipt["status"], "root": str(root)}))


if __name__ == "__main__":
    main()
