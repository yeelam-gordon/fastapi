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
import sysconfig
import urllib.request
import uuid
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
COMMON = HERE.with_name("hobl-complete-ci")
sys.path.insert(0, str(COMMON))
from owned_process import run_owned
from decode import analyze, validate
from artifact_gate import artifact_set, equivalent
import typed_events
import module_map
import native_calibration
import build_scheduling

GUARDIAN = "45d6db4f6452c4f7116ca23c6e2aa74cda90a15548bd5c9bb3b3574973ef458e"
STAGES = {"preflight", "prepare", "calibration_start", "calibration_launch",
          "calibration_stop", "calibration_decode", "calibration_analysis", "warmup",
          "build_start", "build_launch", "build_stop", "build_decode", "build_analysis", "build_artifacts", "cleanup", "complete"}
STAGES |= {"reader_prepare", "reader_decode"}
STAGES |= {"calibration_modules", "build_modules"}
STAGES |= {"recorder_inventory"}
TOOLS = {"controller", "wpr", "python", "uv", "logman", "DOTNET"}
REASONS = {"none", "native_command", "host_context", "run_identity", "job_identity", "token",
           "disk", "tools", "guardian_hash", "existing_recording", "etl_size", "artifacts",
           "root_birth_window", "native_creation_mismatch", "unsupported_clock", "trace_loss",
           "incomplete_lifetime", "duplicate_owned_pid", "qpc_frequency_mismatch",
           "missing_known_child", "known_child_not_owned", "recording_window",
           "insufficient_owned_evidence", "schema", "unexpected", "missing_dotnet10"}
REASONS |= {"module_mapping"}
REASONS |= {"session_inventory"}
REASONS |= {"native_calibration"}
REASONS |= set(native_calibration.FAILURE_REASONS.values())
REASONS |= {"native_python"}
REASONS |= {"build_scheduling_invalid", "build_scheduling_requires_native_proof"}
REASONS |= set(build_scheduling.FAILURE_REASONS.values())
REASONS |= set(module_map.EXIT_REASONS.values())
EXCEPTION_TYPES = {"NONE", "NATIVE_FAILURE", "KEY_ERROR", "VALUE_ERROR", "TYPE_ERROR",
                   "XML_PARSE_ERROR", "FILE_NOT_FOUND", "OS_ERROR", "OTHER"}
MISSING_FIELDS = {"NONE", "OTHER", "ProcessId", "ParentId", "TThreadId", "ThreadId",
                  "RawTime", "PerfFreq", "ReservedFlags", "EventsLost", "BuffersLost",
                  "StartTime", "EndTime", "InstructionPointer", "ImageBase", "ImageSize",
                  "FileName", "FileObject", "qpc_frequency", "qpc_before", "qpc_after",
                  "qpc_end", "pid", "creation_filetime", "filetime_after"}


def safe_exception(error):
    kinds = ((Failure, "NATIVE_FAILURE"), (ET.ParseError, "XML_PARSE_ERROR"),
             (KeyError, "KEY_ERROR"), (ValueError, "VALUE_ERROR"), (TypeError, "TYPE_ERROR"),
             (FileNotFoundError, "FILE_NOT_FOUND"), (OSError, "OS_ERROR"))
    kind = next((name for cls, name in kinds if isinstance(error, cls)), "OTHER")
    field = "NONE"
    if isinstance(error, KeyError):
        key = error.args[0] if len(error.args) == 1 else None
        field = key if type(key) is str and key in MISSING_FIELDS else "OTHER"
    return kind, field


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
            or env.get("GITHUB_REF") != "refs/heads/perf/hobl-owned-stacks-20261104"):
        raise Failure("controller", 1)
    run = fetch("runs/" + env["GITHUB_RUN_ID"])
    if (run["head_sha"] != env["GITHUB_SHA"] or run["head_branch"] != "perf/hobl-owned-stacks-20261104"
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
    def __init__(self, private, public, source, uv, runner=run_owned,
                 wait_calibration=False, calibration_only=False, build_scheduling=False):
        if calibration_only and not wait_calibration:
            raise ValueError("calibration_only_requires_wait_calibration")
        if build_scheduling and (not wait_calibration or calibration_only):
            raise ValueError("build_scheduling_requires_wait_calibration_and_build")
        self.private, self.public, self.source, self.uv = private, public, source, uv
        self.runner, self.stage, self.owned = runner, "preflight", None
        self.residual = False
        self.wait_calibration = wait_calibration
        self.calibration_only = calibration_only
        self.build_scheduling = build_scheduling
        self.native_wait_proof = None
        self.wpr = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wpr.exe")
        self.dotnet = shutil.which("dotnet")
        self.reader_env = os.environ.copy()
        self.reader_env.update(
            DOTNET_CLI_HOME=str(private / "dotnet-home"), NUGET_PACKAGES=str(private / "nuget"),
            NUGET_HTTP_CACHE_PATH=str(private / "nuget-http"),
            DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1", DOTNET_GENERATE_ASPNET_CERTIFICATE="false",
            DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_CLI_USE_MSBUILD_SERVER="0",
            MSBUILDDISABLENODEREUSE="1", DOTNET_NOLOGO="1", NUGET_EXE_NO_PROMPT="true",
            DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE="true")
        self.reader_env.update(_NT_SYMBOL_PATH="", _NT_ALT_SYMBOL_PATH="")
        self.reader_dll = private / "reader-bin" / "traceevent-reader.dll"
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

    def report(self, tool="controller", code=0, status="RUNNING", reason="none",
               exception_type="NONE", missing_field="NONE"):
        if (self.stage not in STAGES or tool not in TOOLS or type(code) is not int
                or not -(2**31) <= code < 2**32 or status not in {"RUNNING", "PARTIAL", "FAILED"} or reason not in REASONS
                or exception_type not in EXCEPTION_TYPES or missing_field not in MISSING_FIELDS):
            raise ValueError("stage_schema")
        value = {"schema": 1, "stage": self.stage, "tool": tool, "native_code": code,
                 "status": status, "reason": reason, "exception_type": exception_type,
                 "missing_field": missing_field, "residual_buffers_possible": self.owned is not None or self.residual}
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

    def prepare_reader(self):
        self.stage = "reader_prepare"
        if self.dotnet is None:
            raise Failure("DOTNET", -1, "missing_dotnet10")
        project = HERE / "reader"
        try:
            self.command("DOTNET", [self.dotnet, "--version"], cwd=project, env=self.reader_env)
        except Failure as error:
            raise Failure("DOTNET", error.code, "missing_dotnet10") from error
        version = (self.private / f"{self.sequence}.stdout").read_text().strip()
        if re.fullmatch(r"10\.\d+\.\d+", version) is None:
            raise Failure("DOTNET", -1, "missing_dotnet10")
        self.command("DOTNET", [self.dotnet, "--list-runtimes"], cwd=project, env=self.reader_env)
        runtimes = (self.private / f"{self.sequence}.stdout").read_text()
        if re.search(r"(?m)^Microsoft\.NETCore\.App 10\.", runtimes) is None:
            raise Failure("DOTNET", -1, "missing_dotnet10")
        self.command("DOTNET", [self.dotnet, "restore", "traceevent-reader.csproj", "--locked-mode",
                               "--configfile", "NuGet.MicrosoftPublic.Config", "--disable-parallel",
                               "--verbosity", "quiet", "/nodeReuse:false", "/p:UseSharedCompilation=false"],
                     120, cwd=project, env=self.reader_env)
        self.command("DOTNET", [self.dotnet, "build", "traceevent-reader.csproj", "--no-restore",
                               "--disable-build-servers", "--output", str(self.reader_dll.parent),
                               "--verbosity", "quiet", "/nodeReuse:false", "/p:UseSharedCompilation=false"],
                     90, cwd=project, env=self.reader_env)

    def recorder_inventory(self):
        self.stage = "recorder_inventory"
        output = self.private / "session-names.json"
        try:
            self.command("DOTNET", [self.dotnet, str(self.reader_dll), "--sessions", str(output)],
                         cwd=HERE / "reader", env=self.reader_env)
        except Failure as error:
            raise Failure("DOTNET", error.code, "session_inventory") from error
        names = json.loads(output.read_text(encoding="utf-8"))
        if (not isinstance(names, list) or len(names) > 1024
                or any(type(name) is not str or not 0 < len(name) <= 1024 for name in names)):
            raise ValueError("schema")
        if any(marker in name.lower() for name in names
               for marker in ("wpr_", "buildattributionsystem", "hobl-", "nt kernel logger")):
            raise Failure("DOTNET", -1, "existing_recording")

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
        self.stage = "reader_decode"
        dto = folder / "events.jsonl"
        self.command("DOTNET", [self.dotnet, str(self.reader_dll), str(etl), str(dto),
                               str(folder / "reader-private-summary.json")],
                     60, cwd=HERE / "reader", env=self.reader_env)
        self.stage = phase + "_analysis"
        if phase == "calibration" and self.wait_calibration:
            self.qualify_wait(folder, dto, json.loads(anchor.read_text()))
        diagnostic = typed_events.proof(dto)
        (self.public / (phase + "-reader.json")).write_text(
            json.dumps(diagnostic, allow_nan=False), encoding="utf-8")
        child_anchor = json.loads((folder / "child-anchor.json").read_text()) if phase == "calibration" else None
        selected = []
        result = analyze(dto, json.loads(anchor.read_text()), calibration=phase == "calibration",
                         child_anchor=child_anchor, event_reader=typed_events.events,
                         sample_observer=lambda q, t, ip, i: selected.append([q, t, ip, i]))
        validate(result)
        (self.public / (phase + ".json")).write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
        if phase == "build" and self.build_scheduling:
            self.qualify_build_scheduling(folder, dto, json.loads(anchor.read_text()))
        self.stage = phase + "_modules"
        self.report()
        try:
            selection = folder / "verified-samples.json"
            selection.write_text(json.dumps(dict(schema=1,
                counts=[r["cpu_samples"] for r in result["lifetimes"]],
                samples=selected)), encoding="utf-8")
            output = folder / "modules-private.json"
            self.command("DOTNET", [self.dotnet, str(self.reader_dll), "--modules",
                         str(etl), str(folder / "capture.etlx"), str(selection), str(output)],
                         110, cwd=HERE / "reader", env=self.reader_env)
            if not 0 < (folder / "capture.etlx").stat().st_size <= 256 * 1024**2:
                raise ValueError("module_mapping")
            modules = json.loads(output.read_text(encoding="utf-8"))
            module_map.validate(modules, result)
            (self.public / (phase + "-modules.json")).write_text(
                json.dumps(modules, allow_nan=False), encoding="utf-8")
        except Exception as error:
            raise Failure("DOTNET", error.code if isinstance(error, Failure) else -1,
                          module_map.EXIT_REASONS.get(error.code, "module_mapping")
                          if isinstance(error, Failure) else "module_mapping") from error

    def run(self):
        hosted_gate()
        if not ctypes.windll.shell32.IsUserAnAdmin():
            raise Failure("controller", 5)
        if shutil.disk_usage(self.private).free < 8 * 1024**3:
            raise Failure("controller", 6)
        if hashlib.sha256((COMMON / "owned_process.py").read_bytes()).hexdigest() != GUARDIAN:
            raise Failure("controller", 7)
        if not Path(self.wpr).is_file():
            raise Failure("controller", 8)
        self.command("wpr", [self.wpr, "-status"])
        status = (self.private / f"{self.sequence}.stdout").read_text(encoding="utf-8", errors="replace")
        if "not recording" not in status.lower():
            raise Failure("wpr", 9, "existing_recording")
        self.prepare_reader()
        self.recorder_inventory()
        if self.calibration_only:
            self.validate_calibration_python()
            env = os.environ.copy()
            for key in list(env):
                if key.startswith(("PYTHON", "PYTEST_", "PIP_", "UV_", "COVERAGE_", "COV_CORE_")):
                    env.pop(key)
            self.calibration(Path(sys.executable), env)
            self.cleanup()
            self.stage = "complete"
            self.report(status="PARTIAL")
            return
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
        self.calibration(python, env)
        if self.build_scheduling and self.native_wait_proof is None:
            raise Failure("controller", -1, "build_scheduling_requires_native_proof")
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

    def calibration(self, python, env):
        self.native_wait_proof = None
        calibration_env = env.copy()
        calibration_env.pop("HOBL_PRIVATE_WAIT_CALIBRATION", None)
        if self.wait_calibration:
            calibration_env["HOBL_PRIVATE_WAIT_CALIBRATION"] = "1"
        self.trace("calibration", [str(python), "-I", "-B", str(HERE / "calibrate.py")],
                   calibration_env)

    def validate_calibration_python(self):
        if (sys.version_info[:3] != (3, 13, 15)
                or sysconfig.get_config_var("Py_GIL_DISABLED")
                or not getattr(sys, "_is_gil_enabled", lambda: False)()
                or sysconfig.get_config_var("PYTHON_JIT")
                or getattr(getattr(sys, "_jit", None), "is_enabled", lambda: False)()):
            raise Failure("controller", -1, "native_python")
        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.IsWow64Process2.argtypes = [ctypes.c_void_p,
                                         ctypes.POINTER(ctypes.c_ushort),
                                         ctypes.POINTER(ctypes.c_ushort)]
        process, native = ctypes.c_ushort(), ctypes.c_ushort()
        if (not kernel.IsWow64Process2(kernel.GetCurrentProcess(),
                                      ctypes.byref(process), ctypes.byref(native))
                or process.value != 0 or native.value != 0xAA64):
            raise Failure("controller", -1, "native_python")

    def qualify_wait(self, folder, dto, anchor):
        self.native_wait_proof = None
        try:
            handshake = json.loads((folder / "wait-handshake.json").read_text())
            summary = native_calibration.qualify(dto, anchor, handshake)
            native_calibration.validate_public(summary)
            (self.public / "calibration-wait.json").write_text(
                json.dumps(summary, allow_nan=False), encoding="utf-8")
            if summary["status"] != "PASS":
                raise ValueError("native_calibration")
            self.native_wait_proof = dict(summary)
        except Exception as error:
            raise Failure("controller", -1, native_calibration.failure_reason(error)) from error

    def qualify_build_scheduling(self, folder, dto, anchor):
        try:
            if self.native_wait_proof is None:
                raise ValueError("build_scheduling_requires_native_proof")
            summary, private = build_scheduling.qualify(dto, anchor, self.native_wait_proof)
            build_scheduling.validate_public(summary)
            (folder / "scheduling-private.json").write_text(
                json.dumps(private, allow_nan=False), encoding="utf-8")
            (self.public / "build-scheduling.json").write_text(
                json.dumps(summary, allow_nan=False), encoding="utf-8")
        except Exception as error:
            raise Failure("controller", -1, build_scheduling.failure_reason(error)) from error

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


def parse_args(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--private", type=Path, required=True)
    p.add_argument("--public", type=Path, required=True)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--uv", type=Path, required=True)
    p.add_argument("--wait-calibration", action="store_true")
    p.add_argument("--calibration-only", action="store_true")
    p.add_argument("--build-scheduling", action="store_true")
    a = p.parse_args(argv)
    if a.calibration_only and not a.wait_calibration:
        p.error("--calibration-only requires --wait-calibration")
    if a.build_scheduling and (not a.wait_calibration or a.calibration_only):
        p.error("--build-scheduling requires --wait-calibration and excludes --calibration-only")
    return a


def main(argv=None):
    a = parse_args(argv)
    c = Controller(a.private.resolve(), a.public.resolve(), a.source.resolve(), a.uv.resolve(),
                   wait_calibration=a.wait_calibration, calibration_only=a.calibration_only,
                   build_scheduling=a.build_scheduling)
    try:
        c.run()
    except Exception as error:
        (c.private / "failure.txt").write_text(repr(error), encoding="utf-8")
        c.report(error.tool if isinstance(error, Failure) else "controller",
                 error.code if isinstance(error, Failure) else -1, "FAILED", safe_reason(error),
                 *safe_exception(error))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
