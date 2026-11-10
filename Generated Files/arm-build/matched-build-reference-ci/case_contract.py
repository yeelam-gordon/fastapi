"""Fixed local Windows, hosted Windows and Darwin evidence associations."""

import hashlib
import json
import os
import stat
import subprocess
import sys
import sysconfig
from pathlib import Path, PureWindowsPath

import bootstrap

PROFILES = {
    "LOCAL_WINDOWS_READINESS": ("win32", "installed-copy"),
    "HOSTED_WINDOWS_REFERENCE": ("win32", "uv-managed-install"),
    "DARWIN_REFERENCE": ("darwin", "uv-managed-install"),
}
ROLES = {"release", "configuration", "admission", "core_marker", "launch_marker",
         "outer_command", "outer_receipt", "outer_result", "creation_receipt"}
require = bootstrap.require


def decode(path, read):
    return json.loads(read(Path(path)))


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def binding(path):
    return {"path": str(path), "sha256": bootstrap.sha(path)}

def release_member(name):
    relative = PureWindowsPath(name)
    require(not relative.drive and not relative.root and ".." not in relative.parts,
            "relative release member")
    return Path(*relative.parts)


def validate_case(path, read):
    case = decode(path, read)
    require(type(case["schema"]) is int and case["schema"] == 1
            and case["profile"] in PROFILES, "case schema/profile")
    require((case["platform"], case["preparation_origin"]) == PROFILES[case["profile"]],
            "explicit preparation origin/platform")
    require(case["descriptor_path"] == str(path) and not case.get("missing_bindings")
            and set(case["bindings"]) == ROLES,
            "descriptor lexical/role closure")
    require(case["core_sourcepins_sha256"] == bootstrap.PIN, "qualified core identity")
    for name in ("descriptor_path", "case_root", "core_root", "preparation_root", "output"):
        value = Path(case[name])
        require(value.is_absolute() and ".." not in value.parts, "absolute case prefixes")
    if case["profile"] != "LOCAL_WINDOWS_READINESS":
        workspace = Path(case["case_root"]).parent
        require(Path(case["case_root"]) == workspace / "matched-case"
                and Path(path) == workspace / "matched-case" / "case.json"
                and Path(case["output"]) == workspace / "matched-output"
                and Path(case["preparation_root"]) == workspace / "matched-evidence"
                and Path(case["verification_output"]) == workspace / "matched-verification",
                "fixed hosted evidence prefixes")
    for record in list(case["bindings"].values()) + case["records"]:
        require(set(record) == {"path", "sha256"}, "record schema")
        require(hashlib.sha256(read(Path(record["path"]))).hexdigest() == record["sha256"],
                f"case record changed: {record['path']}")
    release = decode(case["bindings"]["release"]["path"], read)
    require(type(release["schema"]) is int and release["schema"] == 1
            and release["hosted_raw_verifier_ready"] is True
            and release["core_sourcepins_sha256"] == bootstrap.PIN, "combined release/core schema")
    root = Path(case["release_root"])
    require(root.is_absolute() and len(release["files"]) < 128, "finite release root")
    expected = {(Path("Generated Files") / "arm-build" / bootstrap.HERE.name / p.name).as_posix()
                for p in bootstrap.HERE.iterdir() if p.is_file() and p.name != "RELEASE.json"}
    expected.update({".github/workflows/arm-build-diagnostics.yml",
                     ".github/workflows/matched-native-build-reference.yml",
                     "Generated Files/arm-build/matched-build-reference-screen/SOURCEPINS.json"})
    require({release_member(name).as_posix() for name in release["files"]} == expected,
            "complete combined source closure")
    for name, expected in release["files"].items():
        relative = release_member(name)
        require(hashlib.sha256(read(root / relative)).hexdigest() == expected, "release source bytes")
    core = Path(case["core_root"])
    pins = decode(core / "SOURCEPINS.json", read)
    require(hashlib.sha256(read(core / "SOURCEPINS.json")).hexdigest() == bootstrap.PIN,
            "core manifest bytes")
    closure = {p.name for p in core.iterdir() if p.suffix in (".py", ".source")
               or p.name in ("ORIGINS.json", "build-constraints.txt")}
    require(closure == set(pins["files"]), "core preflight source closure")
    for name, expected in pins["files"].items():
        require(hashlib.sha256(read(core / name)).hexdigest() == expected, "core source bytes")
    return case


def process_identity(process, executable, target):
    shared = bootstrap.reference.shared
    require(shared.associated_process(process, process, executable, target), "process image association")
    if target == "win32":
        birth = process["birth_filetime"]
        require(type(birth) is int and 116444736000000000 < birth < 2**64, "real FILETIME")
        lower = (birth - 116444736000000000) * 100
        return (process["pid"], birth), (lower, lower)
    require(target == "darwin", "explicit identity platform")
    interval = process["start_unix_interval_us"]
    require(isinstance(interval, (tuple, list)) and len(interval) == 2
            and all(type(value) is int for value in interval)
            and interval[0] > 0 and interval[1] == interval[0] + 1, "Darwin Unix birth interval")
    return (process["pid"], interval[0]), (interval[0] * 1000, interval[1] * 1000 - 1)


def drained(receipt):
    require(receipt["returncode"] == 0 and receipt["timed_out"] is False
            and receipt["ownership_established"] is True and receipt["survivors"] is False
            and receipt["cleanup_complete"] is True and receipt["errors"] == []
            and receipt["liveness"] == [], "owned natural drain")


def authority(case, config, protocol, identity, initial, read):
    require(sys.platform == case["platform"] and sys.executable == config["python"] and sys.flags.isolated == 1
            and sys.dont_write_bytecode and sys.flags.optimize == 0
            and sys.pycache_prefix is None and sys.version_info[:3] == (3, 13, 15),
            "exact SDK compiler -I -B optimize=0")
    require(sys.version == identity["version"] == initial["compiler"]["version"],
            "complete compiler version")
    require(initial["compiler"]["executable"] == config["python"]
            and initial["compiler"]["cache_tag"] == "cpython-313"
            and initial["compiler"]["optimize"] == 0
            and initial["compiler"]["dont_inherit"] is True
            and protocol["version"] == 3, "actual compiler/profile schema")
    require(sys.prefix == config["venv_root"] and sys.base_prefix == config["sdk_root"],
            "observed compiler prefixes")
    expected_base = str(Path(config["sdk_root"]) / "bin" / "python3.13") if case["platform"] == "darwin" else config["base_python"]
    require(sys._base_executable == expected_base, "terminal compiler base association")
    require(sys._is_gil_enabled() and not any(sysconfig.get_config_var(key)
            for key in ("Py_GIL_DISABLED", "PYTHON_JIT", "Py_DEBUG")), "normal runtime")
    require(identity["gil"] and not identity["jit"] and identity["bytecode"] == "default",
            "actual default-writing core, not verifier flags")
    require(sysconfig.get_platform() == identity["platform"]
            and (identity["platform"] == "win-arm64" if case["platform"] == "win32"
                 else identity["platform"].startswith("macosx-") and identity["platform"].endswith("-arm64")), "native compiler ABI")
    admission = decode(case["bindings"]["admission"]["path"], read)
    require(admission == decode(Path(config["output"]) / "admission-used.json", read),
            "exact used admission")
    bootstrap.reference.admission_check(admission, config, bootstrap.PIN, admission["issued_unix"])
    require(protocol["sourcepins"] == bootstrap.PIN and config["seconds"] <= 540, "core cap/pin")
    marker = decode(case["bindings"]["core_marker"]["path"], read)
    require(admission["attempt_marker"] == case["bindings"]["core_marker"]["path"]
            and marker == {"sourcepins": bootstrap.PIN, "configuration": canonical(config)},
            "exclusive core marker")
    review = decode(Path(case["release_root"]) / "Generated Files" / "arm-build" /
                    "matched-build-reference-ci" / "PARENT-REVIEW.json", read)
    launch = decode(case["bindings"]["launch_marker"]["path"], read)
    require(review["approved"] is True and review["maximum_jobs"] == 2
            and review["delegated_native_admission"] is True
            and review["expected_run_number"] == case["run_number"]
            and 0 < review["expires_unix"] - review["issued_unix"] <= 1800
            and review["issued_unix"] <= launch["created_unix"] < review["expires_unix"],
            "finite separate parent delegation")
    require(launch["configuration"] == canonical(config)
            and launch["release"] == case["bindings"]["release"]["sha256"]
            and launch["never_remove"] is True, "outer one-attempt source binding")


def outer(case, config, result, read):
    records = {name: decode(case["bindings"][name]["path"], read)
               for name in ("outer_command", "outer_receipt", "outer_result", "admission")}
    command, receipt, launch = (records[name] for name in ("outer_command", "outer_receipt", "outer_result"))
    drained(receipt)
    require(command["argv"] == [config["python"], "-I", str(Path(case["core_root"]) / "reference.py"),
            "--configuration", case["bindings"]["configuration"]["path"],
            "--admission", case["bindings"]["admission"]["path"]], "default-I core exact argv")
    require(command["cwd"] == case["case_root"] and command["timeout_seconds"] == config["seconds"] + 25
            and command["cleanup_reserve_seconds"] == 25
            and command["scoped_git_override"] == {"core.autocrlf": "false"}
            and command["clock_scope"] == "OUTER_METADATA_NOT_BUILD_SAMPLES", "outer scopes/bounds")
    require(receipt["actual_process"] == decode(Path(case["case_root"]) / "controller.actual-process.json", read),
            "outer raw sidecar")
    _, birth = process_identity(receipt["actual_process"], config["python"], case["platform"])
    admission = records["admission"]
    require(admission["issued_unix"] * 1e9 <= birth[0] <= birth[1] < admission["expires_unix"] * 1e9,
            "fresh admission at actual outer birth")
    require(result["controller_seconds"] <= config["seconds"]
            and result["controller_seconds"] < receipt["command_wall"] <= command["timeout_seconds"]
            and receipt["command_wall"] < launch["outer_elapsed_seconds"]
            and launch["outer_succeeded"] is True, "separate actual outer clocks")
    require(read(Path(case["case_root"]) / "controller.stdout") == b""
            and read(Path(case["case_root"]) / "controller.stderr") == b"", "successful outer raw streams")
    prep = decode(Path(case["case_root"]) / "preparation-total.json", read)
    require(admission["issued_unix"] <= prep["observed_unix"] <= birth[0] / 1e9
            and prep["pre_outer_job_seconds"] >= prep["private_preparation_seconds"] > 0,
            "all prerequisite/preparation clocks outside native samples")

def path_profile(case, config, read):
    profile = bootstrap.reference.PROFILES[case["profile"]]
    root = Path(config["output"])
    declared = decode(root / "path-profile.json", read)
    require(declared["profile"] == case["profile"]
            and declared["classification"] == profile["classification"]
            and declared["audit_checkout"] == config["source"]
            and declared["native_source_cwd"] == str(root / "canonical-source"), "actual path profile")
    roots = [Path(config[name]) for name in ("source", "wheels", "output", "cache", "sdk_root", "venv_root")]
    for index, path in enumerate(roots):
        require(path.resolve(strict=True) == path, "canonical fixed roots")
        for ancestor in (path, *path.parents):
            require(not ancestor.is_symlink() and not ancestor.is_junction(), "no root aliases")
        require(all(not path.is_relative_to(other) and not other.is_relative_to(path)
                    for other in roots[index + 1:]), "disjoint fixed roots")
    cache = decode(root / "cache-filesystem.json", read)
    if case["platform"] == "win32":
        require(Path(config["source"]).drive == profile["checkout_drive"]
                and Path(config["cache"]).drive == profile["cache_drive"]
                and all(Path(config[name]).drive == "C:" for name in
                        ("python", "uv", "wheels", "output", "sdk_root", "venv_root")), "fixed Windows drives")
        volumes = {name: bootstrap.reference.shared.volume_identity(Path(config[key]))
                   for name, key in (("audit_checkout", "source"), ("native_source_output", "output"), ("cache", "cache"))}
        require(declared["volumes"] == volumes and cache == volumes["cache"]
                and cache["filesystem"].upper() == "REFS", "actual unchanged volume identities")
    else:
        path = Path(config["cache"])
        require(declared["volumes"] is None and cache == {
            "device": path.stat().st_dev, "mode": path.stat().st_mode,
            "existing_parent_device": path.parent.stat().st_dev}
            and stat.S_IMODE(path.stat().st_mode) == 0o700, "actual existing private Mac cache filesystem")

def runtime_links(config, final, read):
    policy = bootstrap.reference.DarwinRuntimeLinks(
        config["sdk_root"], config["venv_root"], config["base_python"], config["publisher_sha256"])
    roots = {name: Path(name) for name in (config["sdk_root"], config["venv_root"])}
    policy.bind_compiler(roots)

    # Use the core's exact scan while retaining every regular read independently.
    from runtime_bytecode import runtime_entry
    def entry(path, root):
        read(path)
        return runtime_entry(path, root)
    observed, _ = policy.scan(roots, lambda: final["inputs"], entry)
    require(observed == final, "full Darwin links/ancestors/regular targets/content")

def runtime_link_metadata(config, final):
    from runtime_links import directory_identity, metadata
    require(set(final["links"]) == {config["sdk_root"], config["venv_root"]}, "final link roots")
    for root, links in final["links"].items():
        for name, record in links.items():
            path = Path(root) / name
            require(path.is_symlink() and not path.is_junction()
                    and os.readlink(path) == record["raw_target"]
                    and metadata(path.lstat()) == record["lstat"], "final raw runtime link metadata")
    for name, expected in final["ancestors"].items():
        require(directory_identity(Path(name)) == expected, "final runtime ancestor identity")


def headers(inventory, target, tree, source):
    from archive_headers import NATIVE_EXECUTABLE_SCRIPTS, require_reference
    require_reference(inventory, inventory)
    for name, member in inventory["wheel"].items():
        expected = 0o600 << 16 if name.endswith(".dist-info/RECORD") else (stat.S_IFREG | 0o644) << 16
        require(member["create_system"] == (0 if target == "win32" else 3)
                and member["external_attr"] == expected
                and member["date_time"] == [2016, 1, 1, 0, 0, 0]
                and all(member[key] == value for key, value in {
                    "extract_version": 20, "create_version": 20, "volume": 0,
                    "compress_type": 8, "internal_attr": 0, "flag_bits": 0,
                    "comment": "", "extra": ""}.items()), "stock complete ZIP header policy")
    for name, member in inventory["sdist"].items():
        require(all(member[key] == value for key, value in {
            "uid": 0, "gid": 0, "uname": "", "gname": "", "linkname": "",
            "devmajor": 0, "devminor": 0, "type": "0",
            "mode": 0o755 if target == "darwin" and name in NATIVE_EXECUTABLE_SCRIPTS else 0o644,
        }.items()), "stock platform tar header policy")
        relative = name.split("/", 1)[1]
        if relative in tree and relative != "pyproject.toml":
            require(member["mtime"] == (source / relative).stat().st_mtime, "raw source tar mtime")
            pax = {"mtime": str(float(member["mtime"]))}
            if not name.isascii() or len(name.encode("ascii")) > 100:
                pax["path"] = name
            require(member["pax_headers"] == pax, "source PAX header")
        elif relative == "PKG-INFO":
            require(member["mtime"] == 0 and member["pax_headers"] == {}, "stock PKG-INFO timestamp")


def setup_location_handoff(handoff, target):
    removed = handoff["removed_location_variable_names"]
    require(removed == sorted(set(removed))
            and all(bootstrap.is_location_handoff(name, target) for name in removed)
            and handoff["values_retained"] is False, "known locations only names handoff")


def creation(case, config, inputs, read):
    root = Path(case["preparation_root"])
    receipt = decode(case["bindings"]["creation_receipt"]["path"], read)
    require(receipt["kind"] == "observed-uv-venv-creation"
            and receipt["python_request"] == receipt["venv_requested_python_argument"] == "3.13.15"
            and receipt["variant"] == "normal" and receipt["uv_version"] == "0.13.6",
            "actual patch-request creation contract")
    require(receipt["publisher_digest_basis"] == "CATALOG_EXPECTATION_ONLY"
            and receipt["publisher_archive_freshly_verified"] is False
            and receipt["publisher_sha256"] == bootstrap.PUBLISHER[case["platform"]] == config["publisher_sha256"],
            "honest SDK catalog expectation")
    for name, expected in receipt["evidence_sha256"].items():
        relative = Path(name)
        require(not relative.is_absolute() and len(relative.parts) == 1, "creation evidence path")
        require(hashlib.sha256(read(root / relative)).hexdigest() == expected, "creation raw seal")
    commands = decode(root / "commands.json", read)
    require(len(commands) == 5 and 0 < receipt["elapsed_seconds"] <= 120, "bounded five preparation operations")
    prior_end = 0
    caps = {"install": 50, "find": 10, "venv": 20, "probe": 10, "backend": 40}
    for label, command in zip(("install", "find", "venv", "probe", "backend"), commands, strict=True):
        drained(command["owned_receipt"])
        require(command == decode(root / f"{label}.result.json", read), "actual preparation result")
        spec = decode(root / f"{label}.command.json", read)
        require(all(command[key] == value for key, value in spec.items())
                and 0 < command["timeout_seconds"] <= caps[label] and command["cwd"] == str(root)
                and command["clock_scope"] == "PREPARATION_METADATA_ONLY_NOT_BUILD_SAMPLES",
                "preparation raw command/bounds")
        process = command["owned_receipt"]["actual_process"]
        process_identity(process, command["argv"][0], case["platform"])
        owned = command["owned_receipt"]
        start, end = owned["native_start_ns"], owned["native_end_ns"]
        require(type(start) is int and type(end) is int and prior_end < start < end
                and 0 < owned["command_wall"] <= command["timeout_seconds"]
                and (end - start) / 1e9 <= command["timeout_seconds"], "actual bounded preparation clocks")
        prior_end = end
        require(process == decode(root / f"{label}.actual-process.json", read), "preparation sidecar")
        for stream in ("stdout", "stderr"):
            require(hashlib.sha256(read(Path(command[stream + "_path"]))).hexdigest()
                    == command[stream + "_sha256"], "raw preparation stream")
    require(sum(c["owned_receipt"]["command_wall"] + c["owned_receipt"]["infrastructure_wall"]
                for c in commands) <= receipt["elapsed_seconds"], "all preparation wall scopes")
    expected_argv = [
        [config["uv"], "python", "install", "3.13.15", "--no-bin", "--no-config", "--no-progress"]
        + (["--no-registry"] if case["platform"] == "win32" else []),
        [config["uv"], "python", "find", "3.13.15", "--no-python-downloads", "--no-project", "--no-config", "--no-progress"],
        [config["uv"], "venv", config["venv_root"], "--python", "3.13.15", "--no-python-downloads", "--no-config", "--no-progress"],
    ]
    temps = commands[3]["environment_values"]
    require(set(temps) <= {"TEMP", "TMP", "TMPDIR"}, "clean metadata launch whitelist")
    expected_env = dict(temps, UV_PYTHON_INSTALL_DIR=str(Path(config["sdk_root"]).parent),
                        UV_PYTHON_PREFERENCE="only-managed", UV_HTTP_RETRIES="0", UV_HTTP_TIMEOUT="20")
    for command, argv in zip(commands[:3], expected_argv, strict=True):
        require(command["argv"] == argv and command["environment_values"] == expected_env,
                "exact actual managed request/environment")
    require(commands[4]["environment_values"] == temps, "backend clean launch environment")
    require(commands[3]["argv"] == [config["python"], "-I", "-B", "-c", bootstrap.PROBE]
            and commands[4]["argv"] == [config["python"], "-I", "-B",
                str(bootstrap.HERE / "prepare_backend.py"), "--output", config["wheels"]],
            "exact metadata-only probe/backend argv")
    handoff = decode(root / "setup-location-handoff.json", read)
    setup_location_handoff(handoff, case["platform"])
    observed = decode(root / "runtime-observed.json", read)
    require(observed == json.loads(read(Path(commands[3]["stdout_path"])))
            and observed["version"] == sys.version, "actual compiler probe bytes")
    found = read(root / "find.stdout").decode()
    require(found == receipt["find_actual_stdout"], "observed find raw stdout")
    paths = {"install": Path(config["sdk_root"]).parent, "venv": Path(config["venv_root"])}
    associations = bootstrap.observe_runtime(observed, found.strip(), paths, case["platform"])
    require(all(config[key] == receipt[key] == value for key, value in associations.items()),
            "created associations not requested paths")
    cfg = read(Path(config["venv_root"]) / "pyvenv.cfg")
    require(cfg == read(root / "new-pyvenv.cfg") == observed["cfg_utf8"].encode()
            and hashlib.sha256(cfg).hexdigest() == observed["cfg_sha256"], "actual created configuration")
    uv = decode(Path(config["output"]) / "uv-identity.json", read)
    require(uv["sha256"] == inputs["uv"] == bootstrap.reference.QUALIFIED_UV[case["platform"]]["sha256"]
            and not uv["version_observed"], "static qualified UV bytes only")
    require(hashlib.sha256(read(root / "qualified-uv.bin")).hexdigest() == inputs["uv"],
            "retained actual qualified UV bytes")
    wheel = Path(config["wheels"]) / bootstrap.reference.shared.WHEEL
    require(wheel.stat().st_size == 199650
            and inputs["wheels"] == {wheel.name: bootstrap.reference.shared.WHEEL_SHA}, "actual sole backend")
    for executable in (config["uv"], config["python"], sys._base_executable):
        read(Path(executable).resolve(strict=True))
        (bootstrap.reference.shared.pe_arm64 if case["platform"] == "win32"
         else bootstrap.reference.shared.macho_arm64)(Path(executable))
    if case["platform"] == "win32":
        job = Path(case["case_root"]).parent / "matched-job-evidence"
        before, storage = job / "storage-before.json", decode(job / "storage.json", read)
        read(before)
        command = ["pwsh", "-NoProfile", "-NonInteractive", "-File",
                   str(bootstrap.HERE / "Verify-Storage.ps1"), "-Before", str(before)]
        actual = subprocess.run(command, capture_output=True, check=True, timeout=15)
        qualified = json.loads(actual.stdout.decode("utf-8-sig"))
        require(storage["Status"] == "Prepared" and storage["Reason"] == "OrdinaryReFS"
                and storage["BenchmarkEligible"] is True
                and qualified["Number"] == storage["DiskNumber"]
                and qualified["UniqueId"] == storage["DiskUniqueId"], "retained RAW NVMe qualification")
        volume = decode(Path(config["output"]) / "cache-filesystem.json", read)
        require(volume["filesystem"].upper() == "REFS" and Path(config["cache"]).drive == "D:",
                "actual fixed D ReFS cache")
