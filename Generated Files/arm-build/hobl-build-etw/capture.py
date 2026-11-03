"""Exclusive hosted-only research controller. Never run capture on a shared host."""
import argparse
import ctypes
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import sys
import urllib.request
import uuid
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
COMMON = HERE.with_name("hobl-complete-ci")
sys.path.insert(0, str(COMMON))
from owned_process import run_owned
from decode import analyze, validate
from artifact_gate import artifact_set, equivalent

GUARDIAN = "45d6db4f6452c4f7116ca23c6e2aa74cda90a15548bd5c9bb3b3574973ef458e"
STAGES = {"preflight", "prepare", "calibration_start", "calibration_launch",
          "calibration_stop", "calibration_decode", "calibration_analysis", "warmup",
          "build_start", "build_launch", "build_stop", "build_decode", "build_analysis", "build_artifacts", "cleanup", "complete"}
TOOLS = {"controller", "wpr", "tracerpt", "python", "uv", "logman"}
REASONS = {"none", "native_command", "host_context", "run_identity", "job_identity", "token",
           "disk", "tools", "guardian_hash", "existing_recording", "etl_size", "artifacts",
           "root_birth_window", "native_creation_mismatch", "unsupported_clock", "trace_loss",
           "incomplete_lifetime", "duplicate_owned_pid", "qpc_frequency_mismatch",
           "missing_known_child", "known_child_not_owned", "recording_window",
           "insufficient_owned_evidence", "schema", "unexpected"}


def safe_reason(error):
    if isinstance(error, Failure):
        return error.reason
    if type(error) is ValueError and len(error.args) == 1 and type(error.args[0]) is str and error.args[0] in REASONS:
        return error.args[0]
    if isinstance(error, (ValueError, KeyError, TypeError, ET.ParseError)):
        return "schema"
    return "unexpected"


class Failure(Exception):
    def __init__(self, tool, code, reason="native_command"):
        self.tool, self.code = tool, code
        fixed = {1: "host_context", 2: "run_identity", 3: "job_identity", 5: "token",
                 6: "disk", 7: "guardian_hash", 8: "tools"}
        self.reason = fixed.get(code, reason) if tool == "controller" else reason


def api(suffix):
    req = urllib.request.Request(
        "https://api.github.com/repos/yeelam-gordon/fastapi/actions/" + suffix,
        headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"],
                 "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def hosted_gate(env=os.environ, fetch=api):
    if (env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_REPOSITORY") != "yeelam-gordon/fastapi"
            or env.get("GITHUB_RUN_ATTEMPT") != "1" or env.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or env.get("RUNNER_OS") != "Windows" or env.get("RUNNER_ARCH") != "ARM64"
            or env.get("GITHUB_REF") != "refs/heads/perf/hobl-build-etw-20261103"):
        raise Failure("controller", 1)
    run = fetch("runs/" + env["GITHUB_RUN_ID"])
    if (run["head_sha"] != env["GITHUB_SHA"] or run["head_branch"] != "perf/hobl-build-etw-20261103"
            or run["workflow_id"] != 400482741 or run["run_attempt"] != 1
            or run["event"] != "workflow_dispatch"):
        raise Failure("controller", 2)
    jobs = fetch("runs/" + env["GITHUB_RUN_ID"] + "/jobs?per_page=100")
    active = [j for j in jobs["jobs"] if j["status"] != "completed" or j["conclusion"] != "skipped"]
    if (jobs["total_count"] > 100 or len(active) != 1
            or active[0]["status"] != "in_progress"
            or active[0]["name"] != "build-etw / trace"
            or active[0]["runner_name"] != env["RUNNER_NAME"]
            or "windows-11-arm" not in active[0]["labels"]
            or any(x.lower() == "self-hosted" for x in active[0]["labels"])):
        raise Failure("controller", 3)


class Controller:
    def __init__(self, private, public, source, uv, runner=run_owned):
        self.private, self.public, self.source, self.uv = private, public, source, uv
        self.runner, self.stage, self.owned = runner, "preflight", None
        self.residual = False
        self.wpr = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wpr.exe")
        self.tracerpt = str(Path(self.wpr).with_name("tracerpt.exe"))
        self.sequence = 0
        self.capture_proof = {"schema": 1, "calibration": None, "build": None}

    def save_capture_proof(self, phase, etl):
        size = etl.stat().st_size
        row = {"etl_sha256": hashlib.sha256(etl.read_bytes()).hexdigest(),
               "bytes": size, "profile_sha256": hashlib.sha256((HERE / "BuildAttribution.wprp").read_bytes()).hexdigest()}
        if phase not in {"calibration", "build"} or type(size) is not int or not 0 < size <= 128 * 1024**2:
            raise Failure("controller", -1, "etl_size")
        if any(re.fullmatch("[0-9a-f]{64}", row[k]) is None for k in ("etl_sha256", "profile_sha256")):
            raise ValueError("schema")
        self.capture_proof[phase] = row
        self.public.mkdir(exist_ok=True)
        (self.public / "capture-proof.json").write_text(json.dumps(self.capture_proof), encoding="utf-8")

    def report(self, tool="controller", code=0, status="RUNNING", reason="none"):
        if (self.stage not in STAGES or tool not in TOOLS or type(code) is not int
                or not -(2**31) <= code < 2**32 or status not in {"RUNNING", "PARTIAL", "FAILED"} or reason not in REASONS):
            raise ValueError("stage_schema")
        value = {"schema": 1, "stage": self.stage, "tool": tool, "native_code": code,
                 "status": status, "reason": reason, "residual_buffers_possible": self.owned is not None or self.residual}
        self.public.mkdir(exist_ok=True)
        (self.public / "stage.json").write_text(json.dumps(value), encoding="utf-8")

    def command(self, tool, argv, timeout=30, cwd=None, env=None):
        self.report(tool)
        self.sequence += 1
        receipt = self.runner(argv, cwd=cwd or self.private, env=env or os.environ.copy(),
                              stdout_path=self.private / f"{self.sequence}.stdout",
                              stderr_path=self.private / f"{self.sequence}.stderr", timeout=timeout)
        (self.private / f"{self.sequence}.receipt.json").write_text(
            json.dumps(receipt.__dict__), encoding="utf-8")
        if not receipt.succeeded:
            raise Failure(tool, receipt.returncode if type(receipt.returncode) is int else -1)

    def cleanup(self):
        if self.owned is not None:
            self.stage = "cleanup"
            self.command("wpr", [self.wpr, "-cancel", "-instancename", self.owned], 60)
            self.owned = None
            self.residual = False

    def trace(self, phase, command, env):
        folder = self.private / phase
        folder.mkdir()
        instance = "hobl-" + phase + "-" + uuid.uuid4().hex
        self.stage = phase + "_start"
        # A failed start may have partially allocated buffers. Never cancel an
        # unproven session; the fresh hosted VM is the final containment boundary.
        self.residual = True
        self.command("wpr", [self.wpr, "-start", str(HERE / "BuildAttribution.wprp") + "!BuildAttribution",
                             "-instancename", instance])
        self.owned = instance
        anchor = folder / "anchor.json"
        try:
            self.stage = phase + "_launch"
            self.command("python", [sys.executable, "-I", "-B", str(HERE / "launch.py"),
                                   str(anchor), *command], 10, cwd=self.source if phase == "build" else folder, env=env)
            self.stage = phase + "_stop"
            etl = folder / "capture.etl"
            self.command("wpr", [self.wpr, "-stop", str(etl), "-skipPdbGen",
                                 "-instancename", instance], 60)
            self.owned = None
            self.residual = False
        finally:
            if self.owned:
                failed_stage = self.stage
                self.cleanup()
                self.stage = failed_stage
        if not 0 < etl.stat().st_size <= 128 * 1024 * 1024:
            raise Failure("wpr", 4, "etl_size")
        self.save_capture_proof(phase, etl)
        self.stage = phase + "_decode"
        xml = folder / "events.xml"
        self.command("tracerpt", [self.tracerpt, str(etl), "-o", str(xml), "-of", "XML", "-rts", "-y"], 60)
        self.stage = phase + "_analysis"
        child_anchor = json.loads((folder / "child-anchor.json").read_text()) if phase == "calibration" else None
        result = analyze(xml, json.loads(anchor.read_text()), calibration=phase == "calibration", child_anchor=child_anchor)
        validate(result)
        (self.public / (phase + ".json")).write_text(json.dumps(result, allow_nan=False), encoding="utf-8")

    def run(self):
        hosted_gate()
        if not ctypes.windll.shell32.IsUserAnAdmin():
            raise Failure("controller", 5)
        if shutil.disk_usage(self.private).free < 8 * 1024**3:
            raise Failure("controller", 6)
        if hashlib.sha256((COMMON / "owned_process.py").read_bytes()).hexdigest() != GUARDIAN:
            raise Failure("controller", 7)
        if not all(Path(x).is_file() for x in (self.wpr, self.tracerpt)):
            raise Failure("controller", 8)
        self.command("wpr", [self.wpr, "-status"])
        status = (self.private / f"{self.sequence}.stdout").read_text(encoding="utf-8", errors="replace")
        if "not recording" not in status.lower():
            raise Failure("wpr", 9, "existing_recording")
        logman = str(Path(self.wpr).with_name("logman.exe"))
        self.command("logman", [logman, "query", "-ets"])
        sessions = (self.private / f"{self.sequence}.stdout").read_text(encoding="utf-8", errors="replace").lower()
        if any(name in sessions for name in ("wpr_", "buildattributionsystem", "hobl-", "nt kernel logger")):
            raise Failure("logman", 10, "existing_recording")
        self.stage = "prepare"
        screen = HERE.with_name("hobl-parallel-screen") / "screen.py"
        preparation = self.private / "prepared"
        preparation.mkdir()
        self.command("python", [sys.executable, "-B", str(screen), "prepare", "--source", str(self.source),
                               "--output", str(preparation), "--uv", str(self.uv), "--workers", "4"], 180)
        python = preparation / "venv" / "Scripts" / "python.exe"
        env = os.environ.copy()
        for key in list(env):
            if key.startswith(("PYTHON", "PYTEST_", "PIP_", "UV_", "COVERAGE_", "COV_CORE_")):
                env.pop(key)
        env.update(PIP_INDEX_URL="https://pypi.org/simple",
                   PIP_CONSTRAINT=(preparation / "build-constraints.txt").as_uri(),
                   UV_CACHE_DIR=str(preparation / "uv-cache"))
        self.trace("calibration", [str(python), "-I", "-B", str(HERE / "calibrate.py")], env)
        command = [str(self.uv), "build", "--python", str(python), "--no-python-downloads",
                   "--default-index", "https://pypi.org/simple", "--build-constraints",
                   str(preparation / "build-constraints.txt")]
        self.stage = "warmup"
        self.command("uv", command, 60, cwd=self.source, env=env)
        shutil.move(str(self.source / "dist"), str(self.private / "warmup-artifacts"))
        self.trace("build", command, env)
        self.check_artifacts()
        self.stage = "complete"
        self.report(status="PARTIAL")

    def check_artifacts(self):
        self.stage = "build_artifacts"
        self.report()
        sys.path.insert(0, str(HERE.with_name("hobl-parallel-screen")))
        from screen import source_snapshot
        try:
            manifest = source_snapshot(self.source)
            baseline = None
            for folder in (self.private / "warmup-artifacts", self.source / "dist"):
                result = artifact_set(folder, self.source, manifest)
                if baseline is None:
                    baseline = result
                else:
                    equivalent(result, baseline)
                (self.private / (folder.name + "-verified.json")).write_text(json.dumps(result), encoding="utf-8")
        except Exception as error:
            raise Failure("controller", -1, "artifacts") from error


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--private", type=Path, required=True)
    p.add_argument("--public", type=Path, required=True)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--uv", type=Path, required=True)
    a = p.parse_args()
    c = Controller(a.private.resolve(), a.public.resolve(), a.source.resolve(), a.uv.resolve())
    try:
        c.run()
    except Exception as error:
        (c.private / "failure.txt").write_text(repr(error), encoding="utf-8")
        c.report(error.tool if isinstance(error, Failure) else "controller",
                 error.code if isinstance(error, Failure) else -1, "FAILED", safe_reason(error))
        sys.exit(1)
