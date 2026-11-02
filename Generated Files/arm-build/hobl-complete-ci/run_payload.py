import argparse
import dataclasses
import hashlib
import importlib.util
import json
import os
import re
import statistics
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def snapshot(source, manifest):
    return {name: digest(source / name) for name in manifest}


def phase(command, source, env, folder, name):
    stdout, stderr = folder / f"{name}.stdout", folder / f"{name}.stderr"
    with stdout.open("wb") as out, stderr.open("wb") as err:
        start = time.perf_counter_ns()
        try:
            result = subprocess.run(
                command, cwd=source, env=env, stdout=out, stderr=err, timeout=1200
            )
        finally:
            stop = time.perf_counter_ns()
    value = {
        "command": command,
        "start_ns": start,
        "stop_ns": stop,
        "elapsed_ns": stop - start,
        "seconds": (stop - start) / 1e9,
        "hobl_rounded_seconds": round((stop - start) / 1e9, 2),
        "exitcode": result.returncode,
        "stdout_sha256": digest(stdout),
        "stderr_sha256": digest(stderr),
    }
    save(folder / f"{name}.json", value)
    return value


def worker(args):
    source, output = args.source.resolve(), args.output.resolve()
    manifest = json.loads(args.manifest.read_bytes())
    before = snapshot(source, manifest)
    require(before == manifest, "canonical source payload mismatch")
    env = os.environ.copy()
    for key in (
        "PYTHONPYCACHEPREFIX",
        "PYTEST_ADDOPTS",
        "COVERAGE_FILE",
        "COVERAGE_RCFILE",
        "COVERAGE_PROCESS_START",
        "SOURCE_DATE_EPOCH",
        "PIP_NO_INDEX",
        "PIP_FIND_LINKS",
        "PIP_CONSTRAINT",
        "COVERAGE_CORE",
    ):
        env.pop(key, None)
    env.update(
        {
            "PYTHONPATH": "./docs_src",
            "PYTHONIOENCODING": "utf-8",
            "PIP_INDEX_URL": args.index,
            "CONTEXT": "",
        }
    )
    for folder in ("home", "config", "cache", "temp"):
        (output / folder).mkdir()
    env.update(
        {
            "HOME": str(output / "home"),
            "USERPROFILE": str(output / "home"),
            "APPDATA": str(output / "config"),
            "LOCALAPPDATA": str(output / "cache"),
            "XDG_CONFIG_HOME": str(output / "config"),
            "XDG_CACHE_HOME": str(output / "cache"),
            "PIP_CACHE_DIR": str(output / "cache" / "pip"),
            "TEMP": str(output / "temp"),
            "TMP": str(output / "temp"),
            "TMPDIR": str(output / "temp"),
        }
    )
    env["PATH"] = str(args.python.parent) + os.pathsep + env["PATH"]
    identity_code = (
        "import sys,platform,struct,importlib.metadata as m,json,fastapi;"
        "print(json.dumps({'python':sys.version,'executable':sys.executable,"
        "'machine':platform.machine(),'pointer_bits':struct.calcsize('P')*8,"
        "'fastapi_version':fastapi.__version__,'fastapi_origin':fastapi.__file__,"
        "'packages':{d.metadata['Name']:d.version for d in m.distributions()}},indent=2))"
    )
    identity = subprocess.run(
        [str(args.python), "-c", identity_code],
        cwd=source,
        env=env,
        capture_output=True,
        text=True,
    )
    (output / "identity.stdout").write_text(identity.stdout, encoding="utf-8")
    (output / "identity.stderr").write_text(identity.stderr, encoding="utf-8")
    require(identity.returncode == 0, "identity probe failed; stderr retained")
    data = json.loads(identity.stdout)
    require(
        data["machine"].lower() in {"arm64", "aarch64"} and data["pointer_bits"] == 64,
        "native ARM64 required",
    )
    require(
        Path(data["fastapi_origin"]).resolve()
        == (source / "fastapi" / "__init__.py").resolve(),
        "wrong FastAPI origin",
    )
    save(output / "identity.json", data)
    rows = []
    for number in range(1, args.loops + 1):
        folder = output / f"loop-{number}"
        folder.mkdir()
        build = phase([str(args.python), "-m", "build"], source, env, folder, "build")
        require(build["exitcode"] == 0, "build failed; raw logs retained")
        test_command = (
            ["bash", "scripts/test.sh"]
            if args.style == "macos"
            else [str(args.python), "-m", "coverage", "run", "-m", "pytest", "tests"]
        )
        test = phase(test_command, source, env, folder, "test")
        text = (folder / "test.stdout").read_text(encoding="utf-8", errors="replace")
        text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
        summaries = re.findall(r"^=+.*\d+ passed.*=+$", text, flags=re.MULTILINE)
        summary = summaries[-1] if summaries else None
        outcome = {
            kind: int(count)
            for count, kind in re.findall(
                r"(\d+) (passed|failed|skipped|xfailed|xpassed|errors?)", summary or ""
            )
        }
        row = {
            "loop": number,
            "build_seconds": build["seconds"],
            "test_seconds": test["seconds"],
            "scenario_runtime_seconds": build["seconds"] + test["seconds"],
            "hobl_rounded_scenario_runtime": round(
                build["hobl_rounded_seconds"] + test["hobl_rounded_seconds"], 2
            ),
            "test_exitcode": test["exitcode"],
            "pytest_summary": summary,
            "outcomes": outcome,
        }
        rows.append(row)
        save(output / "loops.json", rows)
        print(json.dumps(row), flush=True)
        require(
            test["exitcode"] == 0 and outcome.get("passed", 0) > 0,
            "full covered tests failed; not a valid score",
        )
        require(snapshot(source, manifest) == before, "canonical source changed")
        archives = {}
        for path in sorted((source / "dist").glob("*")):
            if path.suffix == ".whl":
                with zipfile.ZipFile(path) as archive:
                    archives[path.name] = {
                        "sha256": digest(path),
                        "members": len(archive.namelist()),
                    }
            elif path.name.endswith(".tar.gz"):
                with tarfile.open(path) as archive:
                    archives[path.name] = {
                        "sha256": digest(path),
                        "regular_files": sum(m.isfile() for m in archive.getmembers()),
                    }
        require(
            any(name.endswith(".whl") for name in archives)
            and any(name.endswith(".tar.gz") for name in archives),
            "complete build artifacts missing",
        )
        save(folder / "artifacts.json", archives)
    result = {
        "status": "complete",
        "loops": rows,
        "versions": data,
        "median_build_seconds": statistics.median(r["build_seconds"] for r in rows),
        "median_test_seconds": statistics.median(r["test_seconds"] for r in rows),
        "median_scenario_runtime_seconds": statistics.median(
            r["scenario_runtime_seconds"] for r in rows
        ),
        "source_files_preserved": len(before),
        "under_10_seconds": all(r["scenario_runtime_seconds"] < 10 for r in rows),
        "metric": "build wall + full coverage pytest wall; setup excluded",
        "package_index": args.index,
        "prep_qualification": args.prep_qualification,
    }
    save(output / "result.json", result)


def main(args):
    args.source = args.source.resolve()
    args.python = Path(os.path.abspath(args.python))
    args.output = args.output.resolve()
    args.manifest = args.manifest.resolve()
    if args.worker:
        worker(args)
        return
    require(not args.output.exists(), "new output directory required")
    args.output.mkdir(parents=True)
    spec = importlib.util.spec_from_file_location("hobl_guardian", args.guardian)
    guard = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = guard
    spec.loader.exec_module(guard)
    require(
        digest(args.guardian)
        == "45d6db4f6452c4f7116ca23c6e2aa74cda90a15548bd5c9bb3b3574973ef458e",
        "guardian identity",
    )
    command = [
        sys.executable,
        "-I",
        "-B",
        str(Path(__file__).resolve()),
        "--worker",
        "--source",
        str(args.source),
        "--python",
        str(args.python),
        "--output",
        str(args.output),
        "--manifest",
        str(args.manifest),
        "--loops",
        str(args.loops),
        "--index",
        args.index,
        "--style",
        args.style,
        "--prep-qualification",
        args.prep_qualification,
    ]
    receipt = guard.run_owned(
        command,
        cwd=str(args.source),
        env=os.environ.copy(),
        stdout_path=args.output / "driver.stdout",
        stderr_path=args.output / "driver.stderr",
        timeout=args.loops * 2400 + 120,
    )
    save(args.output / "ownership.json", dataclasses.asdict(receipt))
    save(
        args.output / "ownership-summary.json",
        {
            "returncode": receipt.returncode,
            "timed_out": receipt.timed_out,
            "ownership_established": receipt.ownership_established,
            "survivors": receipt.survivors,
            "cleanup_complete": receipt.cleanup_complete,
            "error_count": len(receipt.errors),
            "succeeded": receipt.succeeded,
        },
    )
    require(
        receipt.succeeded, "complete workload failed; inspect retained logs/receipt"
    )
    print((args.output / "result.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--guardian", type=Path)
    parser.add_argument("--loops", type=int, default=5, choices=range(1, 6))
    parser.add_argument(
        "--index", default="https://packagefeedproxy.microsoft.io/pypi/simple"
    )
    parser.add_argument("--style", choices=["windows", "macos"], default="windows")
    parser.add_argument(
        "--prep-qualification",
        default="Timed HOBL payload with controlled test/runtime dependencies; docs-only prep tools omitted.",
    )
    parser.add_argument("--worker", action="store_true")
    main(parser.parse_args())
