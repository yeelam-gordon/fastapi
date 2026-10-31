"""One hosted-only Engine/process memory capture; default is source-only."""

import base64
import contextlib
import dataclasses
import hashlib
import hmac
import importlib
import importlib.util
import json
import math
import os
import platform
import re
import secrets
import subprocess
import sys
import time
import traceback
import urllib.parse
import urllib.request
from pathlib import Path, PureWindowsPath


HERE = Path(__file__).resolve().parent
REPOSITORY = "yeelam-gordon/fastapi"
GUARDIAN_SHA = "45d6db4f6452c4f7116ca23c6e2aa74cda90a15548bd5c9bb3b3574973ef458e"
PROFILE_SHA = "8fd8f40086e86fceae92c6e765401607c2eb253b2467780f9a50a5681a7020d1"
MODULE_SHA = "a811d6b39943cd7f150287ac9b7f68ad9a6de8fd0c20d12cd10e59dfbb9c9921"
PROFILE_NAME = "OwnedEngineProcess.Light.Memory"
TOP_N = 4096
FILETIME_EPOCH = 116444736000000000
LIMIT = 128 * 1024 * 1024
HELPERS = {
    "frontend.py": "b46c75e1e2583e1ea74ced3d5c11a307910bfd0002368605d2487d2c3d628d51",
    "frozen.py": "2e1e357e8252834e57e451cda586018355374731d4017abc23194512ad766f17",
    "compare.py": "fd579d2b7b9a116667596ddc87e7cfc238c7e3ba81dfc9ec77c80ea7eba0bc8a",
    "guards.py": "95082e14caf4f151330beea1fd3633f4a4fb35b300b88dadcfb11cbfbe01be07",
    "driver.py": "e7eb40f0513607a0ee9efa2bfe4ee9629011f73e7feb8ddbafd5d68dc9ff6553",
    "installer.py": "6381f8db6bff618254bc9e59fd535163de8837ca4590ce0db1ff4bf6b72d7e9a",
    "source.py": "4f36cb1e784f0f08e3e9a8f599e172cee20a002afe1e3bf338e030a902455b71",
    "cpu_audit.py": "f2bcb087d5c268b5ca7086078f1ca81da7281c533d252b669b3c3c5797d3756a",
}


class Stop(Exception):
    pass


def require(condition, category):
    if not condition:
        raise Stop(category)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path, limit=LIMIT):
    require(Path(path).stat().st_size <= limit, "PRIVATE_INPUT_SIZE")

    def pairs(items):
        require(len(items) == len(dict(items)), "DUPLICATE_JSON_FIELD")
        return dict(items)

    def nonfinite(value):
        raise Stop("NONFINITE_JSON_VALUE")

    return json.loads(
        Path(path).read_text(encoding="utf-8-sig"),
        object_pairs_hook=pairs,
        parse_constant=nonfinite,
    )


def durable(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise Stop("AUTH_REDIRECT_REFUSED")


def http_json(url, token):
    opener = urllib.request.build_opener(NoRedirect())
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    with opener.open(request, timeout=10) as response:
        payload = response.read(2_000_001)
    require(len(payload) <= 2_000_000, "AUTH_RESPONSE_SIZE")
    return json.loads(payload)


def unbase64(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def signed_claims(token, jwks):
    header, payload, signature = token.split(".")
    meta = json.loads(unbase64(header))
    require(meta["alg"] == "RS256", "OIDC_ALGORITHM")
    keys = [
        key
        for key in jwks["keys"]
        if key.get("kid") == meta["kid"] and key.get("kty") == "RSA"
    ]
    require(len(keys) == 1, "OIDC_SIGNING_KEY")
    modulus, exponent = (
        int.from_bytes(unbase64(keys[0][name]), "big") for name in ("n", "e")
    )
    require(
        2048 <= modulus.bit_length() <= 4096 and exponent == 65537,
        "OIDC_KEY_PARAMETERS",
    )
    size = (modulus.bit_length() + 7) // 8
    raw_signature = unbase64(signature)
    require(
        len(raw_signature) == size and int.from_bytes(raw_signature, "big") < modulus,
        "OIDC_SIGNATURE",
    )
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420")
    digest_info += hashlib.sha256((header + "." + payload).encode("ascii")).digest()
    expected = (
        b"\x00\x01" + b"\xff" * (size - len(digest_info) - 3) + b"\x00" + digest_info
    )
    actual = pow(int.from_bytes(raw_signature, "big"), exponent, modulus).to_bytes(
        size, "big"
    )
    require(hmac.compare_digest(actual, expected), "OIDC_SIGNATURE")
    return json.loads(unbase64(payload))


def hosted_receipt(authority, env, get=http_json):
    require(
        platform.system() == "Windows" and platform.machine() == "ARM64",
        "NATIVE_ARM_REQUIRED",
    )
    require(
        type(authority) is dict
        and {
            "approved",
            "scope",
            "repository",
            "workflow_id",
            "run_attempt",
            "run_id",
            "job_id",
            "head_sha",
            "ref",
            "job_timeout_minutes",
            "accepted_transient_overshoot",
            "expires",
        }
        <= authority.keys(),
        "PARENT_AUTHORITY_REQUIRED",
    )
    require(
        type(authority.get("run_id")) is str
        and re.fullmatch(r"[1-9]\d*", authority["run_id"])
        and type(authority.get("job_id")) is int
        and authority["job_id"] > 0
        and re.fullmatch(r"[0-9a-f]{40}", authority.get("head_sha", "")),
        "PARENT_RUN_IDENTIFIERS",
    )
    require(
        authority["approved"] is True
        and authority["scope"] == "P63_ONE_EPHEMERAL_ATTEMPT"
        and authority["repository"] == REPOSITORY
        and authority["workflow_id"] == 400167398
        and authority["run_attempt"] == "1"
        and authority["job_timeout_minutes"] == 8
        and authority["accepted_transient_overshoot"] is True
        and time.time() < authority["expires"] <= time.time() + 1800,
        "PARENT_AUTHORITY_REQUIRED",
    )
    require(
        env.get("GITHUB_ACTIONS") == "true"
        and env.get("GITHUB_RUN_ID") == authority["run_id"]
        and env.get("GITHUB_RUN_ATTEMPT") == "1"
        and env.get("GITHUB_SHA") == authority["head_sha"],
        "CURRENT_RUN_CONTEXT_REQUIRED",
    )
    require(
        bool(env.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN"))
        and bool(env.get("GH_TOKEN") or env.get("GITHUB_TOKEN"))
        and bool(env.get("RUNNER_NAME")),
        "HOSTED_CREDENTIAL_OR_RUNNER_RECEIPT_REQUIRED",
    )
    url = urllib.parse.urlsplit(env.get("ACTIONS_ID_TOKEN_REQUEST_URL", ""))
    require(
        url.scheme == "https"
        and url.hostname is not None
        and url.hostname.endswith(".actions.githubusercontent.com")
        and url.port in (None, 443)
        and url.username is None
        and not url.fragment,
        "LIVE_HOSTED_IDENTITY_REQUIRED",
    )
    audience = "p63-" + authority["run_id"] + "-" + str(authority["job_id"])
    endpoint = (
        urllib.parse.urlunsplit(url)
        + ("&" if url.query else "?")
        + urllib.parse.urlencode({"audience": audience})
    )
    token = get(endpoint, env["ACTIONS_ID_TOKEN_REQUEST_TOKEN"])["value"]
    jwks = get("https://token.actions.githubusercontent.com/.well-known/jwks", None)
    claims = signed_claims(token, jwks)
    require(
        claims["iss"] == "https://token.actions.githubusercontent.com"
        and claims["aud"] == audience
        and claims["runner_environment"] == "github-hosted"
        and claims["repository"] == REPOSITORY
        and claims["run_id"] == authority["run_id"]
        and claims["run_attempt"] == "1"
        and claims["event_name"] == "workflow_dispatch"
        and claims["ref"] == authority["ref"]
        and claims["workflow_sha"] == authority["head_sha"]
        and claims["nbf"] <= time.time() < claims["exp"],
        "HOSTED_IDENTITY_MISMATCH",
    )
    api = "https://api.github.com/repos/" + REPOSITORY + "/actions/"
    credential = env.get("GH_TOKEN") or env["GITHUB_TOKEN"]
    run = get(api + "runs/" + authority["run_id"], credential)
    job = get(api + "jobs/" + str(authority["job_id"]), credential)
    require(
        run["workflow_id"] == 400167398
        and run["head_sha"] == authority["head_sha"]
        and run["event"] == "workflow_dispatch"
        and run["run_attempt"] == 1
        and run["path"] == ".github/workflows/arm-build-experiment.yml"
        and job["run_id"] == int(authority["run_id"])
        and job["run_attempt"] == 1
        and job["status"] == "in_progress"
        and job["check_run_url"].endswith("/" + str(claims["check_run_id"]))
        and job["runner_name"] == env["RUNNER_NAME"]
        and "windows-11-arm" in job["labels"]
        and "self-hosted" not in job["labels"]
        and (os.cpu_count() or 0) >= 2,
        "HOSTED_API_RECEIPT_MISMATCH",
    )
    return {
        "run_id": authority["run_id"],
        "job_id": authority["job_id"],
        "head_sha": authority["head_sha"],
    }


def named_status(profiles, collectors, instance, *, check_loss=True):
    dropped = re.findall(r"Dropped event\s*:\s*(\d+)", profiles)
    lost = re.findall(r"Events Lost\s*:\s*(\d+)", collectors)
    require(
        len(re.findall(r"^\s*Profile\s*:", profiles, re.M)) == 1
        and re.search(
            r"Profile\s*:\s*" + re.escape(PROFILE_NAME) + r"\s*$", profiles, re.M
        )
        and re.search(r"Logging mode\s*:\s*Memory\s*$", profiles, re.M)
        and len(dropped) == 1
        and (not check_loss or dropped == ["0"]),
        "NAMED_PROFILE_OR_LOSS_UNPROVEN",
    )
    names = re.findall(r"Collector Name\s*:\s*(.*?)\s*$", collectors, re.M)
    counts = re.findall(r"^\s*Number of Buffers\s*:\s*(.*?)\s*$", collectors, re.M)
    prefix = "WPR_initiated_" + instance + "_"
    require(
        sorted(names)
        == sorted([prefix + "WPR System Collector", prefix + "Owned Engine Memory"])
        and re.findall(r"Buffer Size \(KB\)\s*:\s*(\d+)", collectors)
        == ["1024", "1024"]
        and len(counts) <= 2
        and all(count == "32" for count in counts)
        and len(lost) == 2
        and (not check_loss or lost == ["0", "0"])
        and "Microsoft-Antimalware-Engine" in collectors
        and "ProcessThread" in collectors,
        "NAMED_COLLECTOR_CONTEXT_UNPROVEN",
    )
    return dropped == ["0"] and lost == ["0", "0"]


def descriptor(report):
    # Unknown names/values never become public strings.
    fields = set()

    def visit(value, prefix, depth):
        if depth > 8:
            return
        if type(value) is dict:
            for name, child in value.items():
                fields.add((prefix + "." + name, type(child).__name__))
                visit(child, prefix + "." + name, depth + 1)
        elif type(value) is list:
            for child in value:
                visit(child, prefix + "[]", depth + 1)

    visit(report, "", 0)
    return hashlib.sha256(json.dumps(sorted(fields)).encode()).hexdigest()


def project(report, root, begin, end, *, complete_coverage=False):
    require(
        type(report) is dict and set(report) == {"TopScans", "Overview"},
        "REPORT_SCHEMA",
    )
    rows = report["TopScans"]
    overview = report["Overview"]
    require(type(rows) is list and 0 < len(rows) < TOP_N, "MISSING_OR_TOP_N_COVERAGE")
    require(type(overview) is dict, "REPORT_SCHEMA")
    require(
        all(type(overview.get(k)) is int for k in ("StartTime", "EndTime"))
        and overview["StartTime"] <= begin < end <= overview["EndTime"],
        "REPORT_TIME_ENVELOPE_UNPROVEN",
    )
    durations = []
    allowed = {
        "StartTime",
        "EndTime",
        "Duration",
        "Path",
        "ScanType",
        "Reason",
        "SkipReason",
        "ProcessPath",
        "Image",
        "ProcessId",
        "ProcessName",
        "Comments",
    }
    for row in rows:
        require(type(row) is dict and set(row) <= allowed, "SCAN_SCHEMA")
        require(
            all(
                type(value) is str
                for key, value in row.items()
                if key
                in {
                    "Path",
                    "ScanType",
                    "Reason",
                    "SkipReason",
                    "ProcessPath",
                    "Image",
                    "ProcessName",
                }
            )
            and (
                "ProcessId" not in row
                or type(row["ProcessId"]) is int
                and 0 < row["ProcessId"] <= 2**31 - 1
            ),
            "SCAN_FIELD_TYPE",
        )
        require(
            "Comments" not in row
            or type(row["Comments"]) is list
            and all(type(value) is str for value in row["Comments"]),
            "SCAN_FIELD_TYPE",
        )
        require(
            all(
                type(row.get(k)) is int and 0 <= row[k] < 2**64
                for k in ("StartTime", "EndTime", "Duration")
            )
            and row["StartTime"] <= row["EndTime"]
            and row["Duration"] <= row["EndTime"] - row["StartTime"],
            "SCAN_TIME_TYPE_OR_RANGE",
        )
        path = row.get("Path")
        if type(path) is not str:
            continue
        owned = PureWindowsPath(path)
        require(
            ".." not in owned.parts and not path.startswith(("\\\\", "\\\\?")),
            "SCAN_PATH_SCHEMA",
        )
        if (
            owned.is_relative_to(PureWindowsPath(root))
            and begin <= row["StartTime"] <= row["EndTime"] <= end
            and row["Duration"] > 0
        ):
            durations.append(row["Duration"])
    require(bool(durations), "NO_OBSERVED_OWNED_PATH_SCANS")
    # A report envelope and zero WPR loss counters alone do not prove that both
    # circular collectors retained the complete build interval.
    require(complete_coverage is True, "COMPLETE_CAPTURE_COVERAGE_UNPROVEN")
    duration_ms = sum(durations) / 10000
    require(math.isfinite(duration_ms), "NONFINITE_AGGREGATE")
    return {
        "observed_owned_path_scans": len(durations),
        "observed_scan_duration_ms": duration_ms,
    }


class Controller:
    def __init__(self, root, run_owned, env, clock=time.monotonic):
        self.root, self.run_owned, self.env, self.clock = root, run_owned, env, clock
        self.context = read_json(root / "hosted-receipt.json")
        self.instance = "p63-" + secrets.token_hex(16)
        self.started = self.stopped = False
        self.used = False
        self.number = 0
        self.wpr = str(Path(env["SYSTEMROOT"]) / "System32" / "wpr.exe")
        self.profile = HERE / "ENGINE-PROCESS-MEMORY.wprp"

    def command(self, label, argv, timeout, *, cwd=None):
        self.number += 1
        stem = self.root / (str(self.number) + "-" + label)
        receipt = self.run_owned(
            argv,
            cwd=cwd or self.root,
            env=self.env,
            stdout_path=stem.with_suffix(".stdout"),
            stderr_path=stem.with_suffix(".stderr"),
            timeout=timeout,
        )
        durable(stem.with_suffix(".receipt.json"), dataclasses.asdict(receipt))
        require(receipt.succeeded, "OWNED_COMMAND_FAILED")
        return stem.with_suffix(".stdout")

    def wpr_command(self, label, arguments, timeout):
        return self.command(
            label, [self.wpr, *arguments, "-instancename", self.instance], timeout
        )

    def matching(self, *, check_loss=True):
        profiles = self.wpr_command("profiles-status", ["-status", "profiles"], 3)
        collectors = self.wpr_command(
            "collectors-status", ["-status", "collectors", "-details"], 3
        )
        lossless = named_status(
            profiles.read_text(errors="strict"),
            collectors.read_text(errors="strict"),
            self.instance,
            check_loss=check_loss,
        )
        require(
            read_json(self.root / "started.json") == self.lease,
            "DURABLE_OWNERSHIP_MISMATCH",
        )
        require(
            read_json(self.root / "hosted-receipt.json") == self.context,
            "CURRENT_RUN_RECEIPT_MISMATCH",
        )
        return lossless

    def start(self):
        require(sha(self.profile) == PROFILE_SHA, "PROFILE_HASH")
        self.deadline = self.clock() + 30
        self.wpr_command(
            "start", ["-start", str(self.profile) + "!OwnedEngineProcess.Light"], 10
        )
        self.lease = {
            "instance": self.instance,
            "profile_sha256": PROFILE_SHA,
            "context": self.context,
        }
        durable(self.root / "started.json", self.lease)
        self.started = True
        self.matching()
        durable(self.root / "ready.json", self.lease)

    def stop(self):
        if self.started and not self.stopped:
            lossless = self.matching(check_loss=False)
            self.stopped = True  # Never retry an ambiguous/failed stop.
            self.wpr_command(
                "stop", ["-stop", str(self.root / "raw.etl"), "-skipPdbGen"], 60
            )
            durable(self.root / "stopped.json", self.lease)
            require(lossless, "CAPTURE_LOSS_REPORTED")

    def capture(self, build):
        require(not self.used, "CAPTURE_ATTEMPT_ALREADY_USED")
        self.used = True
        primary = None
        try:
            self.start()
            remaining = self.deadline - self.clock() - 6
            require(remaining > 0, "RECORDING_BUDGET_EXHAUSTED")
            begin = time.time_ns() // 100 + FILETIME_EPOCH
            build(min(20, remaining))
            end = time.time_ns() // 100 + FILETIME_EPOCH
            durable(
                self.root / "build-window.json",
                {"begin_filetime": begin, "end_filetime": end},
            )
            require(
                self.clock() <= self.deadline, "REQUESTED_RECORDING_WINDOW_EXCEEDED"
            )
        except BaseException as error:
            primary = error
        try:
            self.stop()
        except BaseException:
            try:
                (self.root / "private-cleanup-error.txt").write_text(
                    traceback.format_exc(), encoding="utf-8"
                )
            except OSError:
                pass
            if primary is None:
                raise
        if primary is not None:
            raise primary
        trace = self.root / "raw.etl"
        require(
            trace.is_file() and 0 < trace.stat().st_size <= LIMIT,
            "POST_STOP_OUTPUT_REJECTED",
        )
        return begin, end


def load_guardian(path):
    require(sha(path) == GUARDIAN_SHA, "PUBLISHED_GUARDIAN_HASH")
    spec = importlib.util.spec_from_file_location("p63_published_guardian", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.run_owned


def prepare(plan, root):
    helper = Path(plan["helper_directory"]).resolve()
    require(
        all(sha(helper / name) == digest for name, digest in HELPERS.items()),
        "FROZEN_HELPER_HASH",
    )
    require(
        not any(name[:-3] in sys.modules for name in HELPERS), "HELPER_IMPORT_COLLISION"
    )
    require(sys.dont_write_bytecode, "CONTROLLER_REQUIRES_B_FLAG")
    sys.path.insert(0, str(helper))
    frontend = importlib.import_module("frontend")
    source = importlib.import_module("source")
    frozen = importlib.import_module("frozen")
    compare = importlib.import_module("compare")
    require(platform.python_version() == "3.12.10", "PYTHON_VERSION")
    frontend.installer.native_uv(Path(plan["uv"]).resolve())
    frontend.native_guard()
    for path, digest in plan["input_sha256"].items():
        require(sha(path) == digest, "PINNED_OFFLINE_INPUT_HASH")
    proof = read_json(plan["source_proof"])
    require(
        proof["revision"] == frontend.REV and len(proof["files"]) == 2557,
        "CANONICAL_SOURCE_PROOF",
    )
    baseline = Path(plan["baseline_directory"]).resolve()
    require(
        sorted(p.name for p in baseline.iterdir())
        == ["fastapi-0.119.1-py3-none-any.whl", "fastapi-0.119.1.tar.gz"],
        "BASELINE_ORACLE_FILES",
    )
    required_inputs = [
        plan["source_archive"],
        plan["source_proof"],
        plan["stock_wheel"],
        plan["uv"],
        *(str(path) for path in baseline.iterdir()),
    ]
    require(
        all(path in plan["input_sha256"] for path in required_inputs),
        "INPUT_HASH_CLOSURE",
    )
    require(
        frontend.sha(Path(plan["stock_wheel"])) == frontend.STOCK, "STOCK_BACKEND_HASH"
    )
    frozen.full_inventory(baseline)
    work = root / "work"
    work.mkdir()
    for name in ("scratch", "uv-cache", "pip-cache", "home"):
        (work / name).mkdir()
    source_dir = work / "source"
    before = source.extract(Path(plan["source_archive"]), source_dir, proof)
    wheel = work / frontend.WHEEL
    wheel.write_bytes(Path(plan["stock_wheel"]).read_bytes())
    constraint = work / "constraints.txt"
    constraint.write_text(
        frontend.constraint_text(wheel), encoding="utf-8", newline="\n"
    )
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "COMSPEC")}
    env.update(
        PATH=os.pathsep.join(
            [
                str(Path(plan["uv"]).parent),
                str(Path(sys.executable).parent),
                str(Path(env["SYSTEMROOT"]) / "System32"),
            ]
        ),
        TEMP=str(work / "scratch"),
        TMP=str(work / "scratch"),
        TMPDIR=str(work / "scratch"),
        USERPROFILE=str(work / "home"),
        HOME=str(work / "home"),
        APPDATA=str(work / "home"),
        LOCALAPPDATA=str(work / "home"),
        UV_CACHE_DIR=str(work / "uv-cache"),
        PIP_CACHE_DIR=str(work / "pip-cache"),
        UV_OFFLINE="1",
        UV_NO_INDEX="1",
        UV_NO_CONFIG="1",
        UV_NO_MANAGED_PYTHON="1",
        UV_PYTHON_DOWNLOADS="never",
        UV_BUILD_CONSTRAINT=str(constraint),
        PIP_NO_INDEX="1",
        NoDefaultCurrentDirectoryInExePath="1",
        SOURCE_DATE_EPOCH="1700000000",
        COLUMNS="4096",
        TERM="dumb",
    )
    argv = frontend.argv_for("B", Path(sys.executable), Path(plan["uv"]), constraint)

    def build(controller, timeout):
        log = controller.command("canonical-build", argv, timeout, cwd=source_dir)
        text = log.read_text(encoding="utf-8") + log.with_suffix(".stderr").read_text(
            encoding="utf-8"
        )
        frontend.verify_log(text, wheel, Path(plan["uv"]))

    def oracle():
        source.unchanged(source_dir, before)
        frozen.full_inventory(source_dir / "dist")
        compare.compare_outputs(baseline, source_dir / "dist")
        require(
            all(sha(helper / name) == digest for name, digest in HELPERS.items()),
            "HELPER_DRIFT",
        )

    return env, build, oracle


def execute(authority, plan, root, run_owned):
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "COMSPEC")}
    env.update(
        PATH=str(Path(env["SYSTEMROOT"]) / "System32"),
        USERPROFILE=str(root),
        HOME=str(root),
        APPDATA=str(root),
        LOCALAPPDATA=str(root),
        NoDefaultCurrentDirectoryInExePath="1",
    )
    controller = Controller(root, run_owned, env)
    powershell = str(
        Path(env["SYSTEMROOT"])
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )
    base = [
        powershell,
        "-NoProfile",
        "-NonInteractive",
        "-File",
        str(HERE / "private_report.ps1"),
        "-Root",
        str(root),
    ]
    controller.command("preflight", [*base, "-Phase", "Preflight"], 15)
    metadata = read_json(root / "preflight.json")
    require(
        metadata["admin"] is True
        and metadata["native_arm"] is True
        and metadata["module_version"] == "1.0"
        and metadata["module_sha256"] == MODULE_SHA,
        "TOOL_TOKEN_VERSION_OR_SCHEMA_PREFLIGHT",
    )
    # Helper/setup output is private as well; no existing helper's exception or
    # incidental stdout may bypass the final positive public projection.
    with (root / "helper-private.log").open("x", encoding="utf-8") as private:
        with contextlib.redirect_stdout(private), contextlib.redirect_stderr(private):
            env, build, oracle = prepare(plan, root)
    controller.env = env
    details = controller.command(
        "profile-details",
        [
            controller.wpr,
            "-profiledetails",
            str(controller.profile) + "!OwnedEngineProcess.Light",
        ],
        5,
    )
    text = details.read_text()
    require(
        re.findall(r"Number of Buffers\s*:\s*(\d+)", text) == ["32", "32"]
        and re.findall(r"Buffer Size \(KB\)\s*:\s*(\d+)", text) == ["1024", "1024"]
        and PROFILE_NAME in text
        and "Microsoft-Antimalware-Engine" in text,
        "ACTUAL_PROFILE_UNSUPPORTED",
    )
    begin, end = controller.capture(lambda timeout: build(controller, timeout))
    with (root / "oracle-private.log").open("x", encoding="utf-8") as private:
        with contextlib.redirect_stdout(private), contextlib.redirect_stderr(private):
            oracle()
    durable(root / "artifact-oracle.json", {"full_pass": True})
    controller.command("decode", [*base, "-Phase", "Decode"], 60)
    report = read_json(root / "raw-report.json")
    schema_sha = descriptor(report)
    durable(root / "schema-descriptor.json", {"schema_sha256": schema_sha})
    # No complete-coverage decoder has been implemented. Runtime may validate
    # schema/envelope and preserve private evidence, but cannot claim total cost.
    project(report, root / "work", begin, end, complete_coverage=False)
    raise Stop("COMPLETE_CAPTURE_COVERAGE_UNPROVEN")


def job_workspace(authority, plan, env):
    raw = plan.get("job_workspace")
    require(
        type(raw) is str
        and raw == authority.get("job_workspace") == env.get("GITHUB_WORKSPACE"),
        "JOB_WORKSPACE_BINDING",
    )
    path = Path(raw)
    require(
        path.is_absolute()
        and not raw.startswith("\\\\")
        and ".." not in path.parts
        and str(path) == raw
        and str(path.resolve(strict=True)) == raw,
        "JOB_WORKSPACE_ALIAS",
    )
    for parent in (path, *path.parents):
        require(
            parent.is_dir()
            and not parent.is_symlink()
            and not parent.is_junction()
            and not getattr(parent.stat(follow_symlinks=False), "st_file_attributes", 0)
            & 0x400,
            "JOB_WORKSPACE_REPARSE",
        )
    return path


def private_root(workspace):
    root = workspace / (".p63-private-" + secrets.token_hex(16))
    require(not root.exists(), "FRESH_PRIVATE_ROOT_REQUIRED")
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "COMSPEC")}
    env.update(
        PATH=str(Path(env["SYSTEMROOT"]) / "System32"),
        NoDefaultCurrentDirectoryInExePath="1",
    )
    powershell = (
        Path(env["SYSTEMROOT"])
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )
    # This fixed ACL-only bootstrap cannot use the disk-logging guardian yet.
    # Both streams stay in memory; no unverified root receives raw diagnostics.
    try:
        completed = subprocess.run(
            [
                str(powershell),
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(HERE / "private_root.ps1"),
                "-Root",
                str(root),
            ],
            cwd=workspace,
            env=env,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except BaseException:
        raise Stop("PRIVATE_ROOT_BOOTSTRAP_FAILED") from None
    require(
        completed.returncode == 0
        and completed.stdout.strip() == b"P63_PRIVATE_ROOT_VERIFIED"
        and not completed.stderr
        and root.is_dir()
        and not root.is_symlink()
        and not root.is_junction(),
        "PRIVATE_ROOT_BOOTSTRAP_FAILED",
    )
    return root


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments:
        print(
            json.dumps(
                {
                    "mode": "SOURCE_ONLY",
                    "scope": "CONDITIONAL_CAPTURE_AND_SCHEMA_VALIDATION",
                    "collection_executed": False,
                    "diagnostic_ready": False,
                    "source_sha256": sha(Path(__file__)),
                }
            )
        )
        return 0
    result = {
        "status": "UNKNOWN",
        "diagnostic_ready": False,
        "source_sha256": sha(Path(__file__)),
    }
    root = None
    try:
        require(
            len(arguments) == 3 and arguments[0] == "--collect", "INVALID_ARGUMENTS"
        )
        require(sys.dont_write_bytecode, "CONTROLLER_REQUIRES_B_FLAG")
        authority = read_json(arguments[1], 100_000)
        plan = read_json(arguments[2], 100_000)
        require(sha(arguments[2]) == authority["plan_sha256"], "PARENT_PLAN_HASH")
        require(
            set(plan.get("source_sha256", {}))
            == {
                "collector.py",
                "private_report.ps1",
                "private_root.ps1",
                "ENGINE-PROCESS-MEMORY.wprp",
            }
            and all(
                sha(HERE / name) == digest
                for name, digest in plan["source_sha256"].items()
            ),
            "REVIEWED_COLLECTOR_SOURCE_HASH",
        )
        receipt = hosted_receipt(authority, os.environ)
        workspace = job_workspace(authority, plan, os.environ)
        marker = workspace / (
            ".p63-attempt-" + receipt["run_id"] + "-" + str(receipt["job_id"]) + ".json"
        )
        try:
            durable(marker, receipt)
        except FileExistsError:
            raise Stop("CAPTURE_ATTEMPT_ALREADY_USED") from None
        root = private_root(workspace)
        durable(root / "hosted-receipt.json", receipt)
        guardian = load_guardian(Path(plan["published_guardian"]))
        execute(authority, plan, root, guardian)
    except BaseException as error:
        raw = traceback.format_exc().encode()
        category = str(error) if type(error) is Stop else ""
        result["category"] = (
            category
            if re.fullmatch(r"[A-Z_]{1,80}", category)
            else "PRIVATE_UNEXPECTED_FAILURE"
        )
        result["private_error_sha256"] = hashlib.sha256(raw).hexdigest()
        if root is not None:
            try:
                (root / "private-error.txt").write_bytes(raw)
                for name, key in (
                    ("raw.etl", "raw_etl_sha256"),
                    ("raw-report.json", "raw_report_sha256"),
                ):
                    path = root / name
                    if path.is_file() and path.stat().st_size <= LIMIT:
                        result[key] = sha(path)
                schema = root / "schema-descriptor.json"
                if schema.is_file():
                    digest = read_json(schema)["schema_sha256"]
                    require(
                        type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest),
                        "PRIVATE_SCHEMA_HASH",
                    )
                    result["schema_sha256"] = digest
                durable(root / "public-result.json", result)
            except BaseException:
                result["failure_evidence_persistence"] = "FAILED"
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
