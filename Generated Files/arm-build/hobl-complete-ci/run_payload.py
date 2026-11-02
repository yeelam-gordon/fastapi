import argparse
import dataclasses
import hashlib
import importlib.util
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import runtime_pair
from artifact_gate import artifact_set, equivalent
from prepare_uv import attest


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


def schedule(paired, loops):
    if not paired:
        return [("stock", True)] * loops
    return [("stock", False), ("uv", False)] + [
        (arm, True)
        for pair in (
            ("stock", "uv"),
            ("uv", "stock"),
            ("stock", "uv"),
            ("uv", "stock"),
            ("stock", "uv"),
        )
        for arm in pair
    ]


def build_command(args, arm):
    if arm == "stock":
        return [str(args.python), "-m", "build"]
    return [
        str(args.paired_uv),
        "build",
        "--python",
        str(args.python),
        "--no-python-downloads",
        "--default-index",
        args.index,
        "--build-constraints",
        str(Path(__file__).with_name("build-constraints.txt")),
    ]


def paired_summary(rows, arms=("stock", "uv")):
    groups = {}
    for arm in arms:
        measured = [row for row in rows if row["arm"] == arm and row["measured"]]
        require(
            len(measured) == 5, "five measured complete iterations per arm required"
        )
        groups[arm] = {
            "measured_iterations": len(measured),
            **{
                f"median_{metric}": statistics.median(row[metric] for row in measured)
                for metric in (
                    "build_seconds",
                    "test_seconds",
                    "scenario_runtime_seconds",
                )
            },
        }
    return groups


def worker(args):
    source, output = args.source.resolve(), args.output.resolve()
    paired = getattr(args, "paired_uv", None) is not None
    runtime = getattr(args, "candidate_python", None) is not None
    analysis = getattr(args, "phase_analysis", False)
    require(
        not analysis or (not runtime and not paired), "analysis is single-runtime only"
    )
    require(not runtime or paired, "runtime pair requires common uv")
    manifest = json.loads(args.manifest.read_bytes())
    if paired:
        require(
            len(manifest) == 2557, "paired canonical source must contain 2557 files"
        )
        require(not (source / "dist").exists(), "paired source dist must start absent")
        save(output / "uv-identity.json", attest(args.paired_uv))
        constraints = Path(__file__).with_name("build-constraints.txt")
        require(constraints.read_text().strip() == "pdm-backend==2.5.0", "backend pin")
        owned_constraints = output / "build-constraints.txt"
        shutil.copyfile(constraints, owned_constraints)
        require(
            owned_constraints.read_bytes() == constraints.read_bytes(),
            "owned backend constraints bytes",
        )
        save(
            output / "paired-config.json",
            {
                "schedule": schedule(True, 5),
                "source_manifest_sha256": digest(args.manifest),
                "build_constraints": constraints.read_text(),
                "build_constraints_sha256": digest(constraints),
                "pip_constraint": owned_constraints.as_uri(),
                "cache_preparation": "Initially empty pip/uv caches; one complete warmup each",
                "artifact_qualification": (
                    "Same-host complete member content/mode/type/RECORD equality; "
                    "archive timestamp/compression identity is not required"
                ),
            },
        )
        if runtime:
            config = json.loads((output / "paired-config.json").read_bytes())
            config.pop("pip_constraint")
            config["schedule"] = [
                ("candidate" if arm == "uv" else arm, measured)
                for arm, measured in schedule(True, 5)
            ]
            config["frontend"] = "common uv 0.13.6 isolated sdist -> wheel from sdist"
            config["runtimes"] = {
                "stock": str(args.python),
                "candidate": str(args.candidate_python),
            }
            config["helper_hashes"] = {
                name: digest(Path(__file__).with_name(name))
                for name in (
                    "run_payload.py",
                    "runtime_pair.py",
                    "artifact_gate.py",
                    "prepare_uv.py",
                    "owned_process.py",
                    "build-constraints.txt",
                    "runtime-constraints.txt",
                    "common-guard.patch",
                )
            }
            save(output / "paired-config.json", config)
    before = snapshot(source, manifest)
    require(before == manifest, "canonical source payload mismatch")
    if analysis:
        require(len(manifest) == 2557, "analysis common-source file count")
        require(
            runtime_pair.sha(
                (source / "tests" / "utils.py").read_bytes().replace(b"\r\n", b"\n")
            )
            == runtime_pair.NEW_SHA,
            "analysis requires corrected common source",
        )
    env = os.environ.copy()
    if runtime or analysis:
        for key in list(env):
            if key.startswith(
                ("PYTHON", "PYTEST_", "PIP_", "UV_", "COVERAGE_", "COV_CORE_")
            ):
                env.pop(key)
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
    if paired:
        env.pop("PIP_BUILD_CONSTRAINT", None)
        for key in list(env):
            if key.startswith("UV_"):
                env.pop(key)
        env["UV_CACHE_DIR"] = str(output / "cache" / "uv")
    identity_code = (
        "import sys,os,platform,struct,importlib.metadata as m,json,fastapi;"
        "print(json.dumps({'python':sys.version,'executable':sys.executable,"
        "'machine':platform.machine(),'pointer_bits':struct.calcsize('P')*8,"
        "'logical_cpu_count':os.cpu_count(),'os':platform.system(),"
        "'os_release':platform.release(),'processor':platform.processor() or None,"
        "'hardware_qualification':'Logical CPU count is not physical core count; "
        "processor model may be unavailable; no matched hardware claim.',"
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
    if analysis:
        import phase_analysis

        identity = runtime_pair.probe(
            args.python, "identity", source, "3.13.15", env, output
        )
        save(output / "candidate-runtime-identity.json", identity)
        phase_analysis.run(args, env, before)
        return
    runtime_identities = {}
    baseline_coverage = None
    if runtime:
        for arm, python, version in (
            ("stock", args.python, "3.12.10"),
            ("candidate", args.candidate_python, "3.13.15"),
        ):
            runtime_identities[arm] = runtime_pair.probe(
                python, "identity", source, version, env, output
            )
            require(
                Path(runtime_identities[arm]["executable"])
                == Path(os.path.abspath(python)),
                "runtime probe escaped lexical venv",
            )
            save(output / f"{arm}-runtime-identity.json", runtime_identities[arm])
        runtime_pair.compare_pins(
            runtime_identities["stock"]["packages"],
            runtime_identities["candidate"]["packages"],
        )
    if paired:
        require(
            data["fastapi_version"] == "0.119.1"
            and data["packages"].get("build") == "1.6.1"
            and data["packages"].get("pip") == "25.0.1",
            "paired FastAPI/build/pip runtime versions",
        )
    rows = []
    baseline_artifacts = None
    for number, (arm, measured) in enumerate(schedule(paired, args.loops), 1):
        if runtime and arm == "uv":
            arm = "candidate"
        folder = output / f"loop-{number}"
        folder.mkdir()
        iteration_env = env
        if runtime:
            python = args.python if arm == "stock" else args.candidate_python
            iteration_env = env.copy()
            state = output / "state" / arm
            for name in ("home", "config", "cache", "temp", "bytecode"):
                (state / name).mkdir(parents=True, exist_ok=True)
            for key, name in {
                "HOME": "home",
                "USERPROFILE": "home",
                "APPDATA": "config",
                "LOCALAPPDATA": "cache",
                "XDG_CONFIG_HOME": "config",
                "XDG_CACHE_HOME": "cache",
                "TEMP": "temp",
                "TMP": "temp",
                "TMPDIR": "temp",
                "PYTHONPYCACHEPREFIX": "bytecode",
            }.items():
                iteration_env[key] = str(state / name)
            iteration_env["PATH"] = str(python.parent) + os.pathsep + env["PATH"]
            (folder / "private").mkdir()
            iteration_env["COVERAGE_FILE"] = str(folder / "private" / ".coverage")
        if paired:
            require(snapshot(source, manifest) == before, "canonical source changed")
        row = {"loop": number}
        if paired:
            row.update({"arm": arm, "measured": measured, "status": "started"})
            rows.append(row)
            save(output / "loops.json", rows)
        build_env = iteration_env
        if paired and arm == "stock" and not runtime:
            build_env = env.copy()
            # pip splits this environment option on whitespace, not shell quotes.
            build_env["PIP_CONSTRAINT"] = owned_constraints.as_uri()
        build_args = args
        if runtime:
            build_args = argparse.Namespace(**vars(args))
            build_args.python = python
        build = phase(
            build_command(build_args, "uv" if runtime else arm),
            source,
            build_env,
            folder,
            "build",
        )
        if paired:
            row["build"] = build
            save(output / "loops.json", rows)
            if build["exitcode"] != 0 and (source / "dist").exists():
                shutil.move(str(source / "dist"), folder / "artifacts")
        require(build["exitcode"] == 0, "build failed; raw logs retained")
        test_command = (
            ["bash", "scripts/test.sh"]
            if args.style == "macos"
            else [
                str(python if runtime else args.python),
                "-m",
                "coverage",
                "run",
                "-m",
                "pytest",
                "tests",
            ]
        )
        test = phase(test_command, source, iteration_env, folder, "test")
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
        row.update(
            {
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
        )
        if not paired:
            rows.append(row)
        save(output / "loops.json", rows)
        print(json.dumps(row), flush=True)
        if paired and not runtime and (source / "dist").exists():
            shutil.move(str(source / "dist"), folder / "artifacts")
        require(
            test["exitcode"] == 0
            and (
                outcome == {"passed": 2513, "skipped": 130}
                if paired
                else outcome.get("passed", 0) > 0
            ),
            "full covered tests failed; not a valid score",
        )
        require(snapshot(source, manifest) == before, "canonical source changed")
        if runtime:
            shutil.move(str(source / "dist"), folder / "artifacts")
            current = runtime_pair.probe(
                python, "oracle", source, folder, iteration_env, folder
            )
            save(folder / "coverage-oracle.json", current)
            require(
                len(current["files"]) == 863 and len(current["contexts"]) == 1409,
                "complete coverage file/context counts",
            )
            baseline_coverage = (
                current if baseline_coverage is None else baseline_coverage
            )
            differences = runtime_pair.compare(baseline_coverage, current)
            save(folder / "coverage-differences.json", differences)
            require(
                all(d["excluded"] for d in differences),
                "reportable coverage difference",
            )
        if paired:
            archives = artifact_set(folder / "artifacts", source, manifest)
            save(folder / "artifacts.json", archives)
            if baseline_artifacts is None:
                require(
                    arm == "stock", "first paired build must establish stock artifacts"
                )
                baseline_artifacts = archives
            equivalent(archives, baseline_artifacts)
            row["status"] = "valid"
            save(output / "loops.json", rows)
            continue
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
    measured_rows = [row for row in rows if row.get("measured", True)]
    result = {
        "status": "complete",
        "loops": rows,
        "versions": data,
        "median_build_seconds": statistics.median(
            r["build_seconds"] for r in measured_rows
        ),
        "median_test_seconds": statistics.median(
            r["test_seconds"] for r in measured_rows
        ),
        "median_scenario_runtime_seconds": statistics.median(
            r["scenario_runtime_seconds"] for r in measured_rows
        ),
        "source_files_preserved": len(before),
        "under_10_seconds": all(
            r["scenario_runtime_seconds"] < 10 for r in measured_rows
        ),
        "metric": "build wall + full coverage pytest wall; setup excluded",
        "package_index": args.index,
        "prep_qualification": args.prep_qualification,
    }
    if paired:
        result["arms"] = paired_summary(
            rows, ("stock", "candidate") if runtime else ("stock", "uv")
        )
        for metric in (
            "median_build_seconds",
            "median_test_seconds",
            "median_scenario_runtime_seconds",
            "under_10_seconds",
        ):
            result.pop(metric)
        result["preparation"] = (
            "One excluded complete stock warmup then one excluded complete uv warmup; "
            "same source/bytecode/runtime closure, home and scratch throughout. "
            "Separate initially empty pip and uv dependency caches, warmed by their "
            "own complete warmups. Source/test bytecode and OS cache evolve in fixed "
            "AB/BA/AB/BA/AB order; they are not reset or asserted identically warm. "
            "dist is moved to per-iteration evidence after each complete iteration."
        )
    if runtime:
        result["status"] = "pending-owned-lifecycle"
        result["labels"] = {"stock": "stock 3.12.10", "candidate": "candidate 3.13.15"}
        result["preparation"] = (
            "Common uv 0.13.6 and PDM 2.5.0; one excluded complete warmup/runtime; "
            "five AB/BA pairs; separate arm HOME/config/temp/version-tagged bytecode; "
            "initially empty shared pip/uv caches warmed in fixed order; OS warmth not equal. "
            "Common corrected source, not unpatched tag; no overlays/hooks/observers."
        )
    save(output / "result.json", result)


def main(args):
    args.source = args.source.resolve()
    if getattr(args, "candidate_python", None) is not None:
        require(args.python.is_absolute(), "stock Python must be absolute")
    args.python = Path(os.path.abspath(args.python))
    args.output = args.output.resolve()
    args.manifest = args.manifest.resolve()
    if getattr(args, "candidate_python", None) is not None:
        require(
            args.candidate_python.is_absolute(), "candidate Python must be absolute"
        )
        args.candidate_python = Path(os.path.abspath(args.candidate_python))
    if getattr(args, "paired_uv", None) is not None:
        require(args.paired_uv.is_absolute(), "paired uv must be absolute")
        require(args.loops == 5, "paired mode requires five pairs")
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
    if getattr(args, "paired_uv", None) is not None:
        command.extend(["--paired-uv", str(args.paired_uv)])
    if getattr(args, "candidate_python", None) is not None:
        command.extend(["--candidate-python", str(args.candidate_python)])
    if getattr(args, "phase_analysis", False):
        command.append("--phase-analysis")
    receipt = guard.run_owned(
        command,
        cwd=str(args.source),
        env=os.environ.copy(),
        stdout_path=args.output / "driver.stdout",
        stderr_path=args.output / "driver.stderr",
        timeout=600
        if getattr(args, "phase_analysis", False)
        else 1100
        if getattr(args, "candidate_python", None) is not None
        else 1000
        if getattr(args, "paired_uv", None) is not None
        else args.loops * 2400 + 120,
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
    if (
        getattr(args, "paired_uv", None) is not None
        or getattr(args, "phase_analysis", False)
    ) and not receipt.succeeded:
        result_path = args.output / "result.json"
        if result_path.exists():
            invalid = json.loads(result_path.read_bytes())
            invalid["status"] = "invalid-owned-lifecycle"
            save(result_path, invalid)
    require(
        receipt.succeeded, "complete workload failed; inspect retained logs/receipt"
    )
    if getattr(args, "phase_analysis", False):
        result_path = args.output / "result.json"
        result = json.loads(result_path.read_bytes())
        require(
            result["status"] == "awaiting-owned-natural-drain",
            "analysis result not ready",
        )
        result["status"] = "analysis-complete"
        save(result_path, result)
    if getattr(args, "candidate_python", None) is not None:
        result_path = args.output / "result.json"
        result = json.loads(result_path.read_bytes())
        require(
            result["status"] == "pending-owned-lifecycle", "runtime result not ready"
        )
        result["status"] = "complete"
        save(result_path, result)
    print((args.output / "result.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--guardian", type=Path)
    parser.add_argument("--paired-uv", type=Path)
    parser.add_argument("--candidate-python", type=Path)
    parser.add_argument("--phase-analysis", action="store_true")
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
