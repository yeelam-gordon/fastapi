"""Single Windows ABBA worktree-add screen. No retries or HOBL payload."""
import ctypes
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import sys
from dataclasses import asdict
from decimal import Decimal

COMMIT = "864b569cf8453654fc3bc2c64108c0f644e2918c"
GUARD_SHA = "45d6db4f6452c4f7116ca23c6e2aa74cda90a15548bd5c9bb3b3574973ef458e"
HERE = Path(__file__).resolve().parent
WORKERS = (1, 4, 4, 1)


class GateFailure(ValueError):
    def __init__(self, category):
        self.category = category
        super().__init__()


def named_gate(category):
    def decorate(function):
        def checked(*args, **kwargs):
            try:
                return function(*args, **kwargs)
            except GateFailure as error:
                if error.category != "closed-scope-failure":
                    raise
                raise GateFailure(category) from None
            except Exception:
                raise GateFailure(category) from None
        return checked
    return decorate


def require(ok, category="closed-scope-failure"):
    if not ok:
        raise GateFailure(category)


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def guardian():
    path = HERE.parent / "hobl-complete-ci" / "owned_process.py"
    require(hashlib.sha256(path.read_bytes()).hexdigest() == GUARD_SHA)
    spec = importlib.util.spec_from_file_location("checkout_guardian", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Owned:
    def __init__(self, private, namespace="git"):
        self.private, self.count, self.code, self.namespace = private, 0, 0, namespace
        self.guard = guardian()
        self.env = dict(os.environ)
        # No inherited diagnostics, target paths, or injected -c settings.
        for key in list(self.env):
            if key.upper().startswith(("GIT_TRACE", "GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")) or key.upper() in {
                "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS", "GIT_DIR", "GIT_COMMON_DIR",
                "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_EXEC_PATH",
                "GIT_ATTR_SOURCE", "GIT_CONFIG", "GIT_TEMPLATE_DIR", "GIT_PREFIX",
            }:
                del self.env[key]
        self.env.update(GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0",
                        GIT_NO_REPLACE_OBJECTS="1", GIT_TRACE2="0", GIT_TRACE2_PERF="0",
                        GIT_TRACE2_EVENT="0")

    def call(self, args, cwd, env=None, timeout=30, native_clock=False):
        self.count += 1
        prefix = self.private / f"{self.namespace}-{self.count}"
        receipt = self.guard.run_owned(
            list(map(str, args)), cwd=str(cwd), env=env or self.env,
            stdout_path=prefix.with_suffix(".stdout"),
            stderr_path=prefix.with_suffix(".stderr"),
            timeout=timeout, native_clock=native_clock,
        )
        save(prefix.with_suffix(".json"), asdict(receipt))
        self.code = receipt.returncode if isinstance(receipt.returncode, int) else -1
        require(receipt.succeeded and receipt.survivors is False, "native-command")
        if native_clock:
            require(receipt.command_wall is not None and math.isfinite(receipt.command_wall)
                    and receipt.native_start_ns is not None and receipt.native_end_ns is not None
                    and receipt.native_end_ns > receipt.native_start_ns, "native-command")
        return prefix.with_suffix(".stdout").read_bytes(), receipt


@named_gate("tree")
def parse_tree(raw):
    tree = {}
    for row in raw.split(b"\0"):
        if not row:
            continue
        meta, name = row.split(b"\t", 1)
        mode, kind, oid = meta.decode("ascii").split()
        require(kind == "blob" and mode in ("100644", "100755"))
        name = name.decode("utf-8")
        require(not name.startswith("/") and "\\" not in name
                and all(part not in ("", ".", "..", ".git") for part in name.split("/")))
        require(name not in tree and re.fullmatch("[0-9a-f]{40}", oid))
        tree[name] = (mode, oid)
    require(len({name.casefold() for name in tree}) == len(tree))
    return tree


def ordinary(path, kind):
    info = path.lstat()
    return kind(info.st_mode) and not (
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


@named_gate("file-oracle")
def verify_files(repo, tree, *, linked=False):
    require(ordinary(repo, stat.S_ISDIR))
    require(ordinary(repo / ".git", stat.S_ISREG if linked else stat.S_ISDIR))
    actual = set()
    for folder, dirs, names in os.walk(repo, followlinks=False, onerror=walk_error):
        if Path(folder) == repo:
            (names if linked else dirs).remove(".git")
        require(all(ordinary(Path(folder) / name, stat.S_ISDIR) for name in dirs))
        for name in names:
            actual.add((Path(folder) / name).relative_to(repo).as_posix())
    require(actual == set(tree))
    for name, (mode, oid) in tree.items():
        path = repo / name
        require(ordinary(path, stat.S_ISREG))
        data = path.read_bytes()
        require(hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == oid)
    return hashlib.sha256(json.dumps(sorted(tree.items()), separators=(",", ":")).encode()).hexdigest()


@named_gate("tree")
def verify_batch(raw, oids):
    offset = 0
    for oid in oids:
        end = raw.index(b"\n", offset)
        actual, kind, size = raw[offset:end].split()
        require(actual.decode("ascii") == oid and kind == b"blob")
        size = int(size)
        require(size >= 0)
        offset = end + 1
        data = raw[offset:offset + size]
        require(len(data) == size and raw[offset + size:offset + size + 1] == b"\n")
        require(hashlib.sha1(b"blob " + str(size).encode() + b"\0" + data).hexdigest() == oid)
        offset += size + 1
    require(offset == len(raw))


@named_gate("trace-worker")
def trace_summary(events, workers):
    require(workers in (1, 4))

    def select(event, sid=None):
        return [(i, e) for i, e in enumerate(events)
                if e["event"] == event and (sid is None or e["sid"] == sid)]

    def one(rows):
        require(len(rows) == 1)
        return rows[0]

    def process(sid, name, hierarchy):
        begin, _ = one(select("start", sid))
        cmd, info = one(select("cmd_name", sid))
        end, exit_event = one(select("exit", sid))
        require(begin < cmd < end and info["name"] == name and info["hierarchy"] == hierarchy
                and exit_event["code"] == 0)
        return begin, end, exit_event

    def child(parent, launch, expected):
        start, event = launch
        argv = event["argv"]
        require(Path(argv[0]).name.lower() in ("git", "git.exe") and argv[1:] == expected)
        child_id = event["child_id"]
        require(type(child_id) is int and child_id >= 0)
        end, exit_event = one([
            (i, e) for i, e in select("child_exit", parent) if e["child_id"] == child_id])
        pid = exit_event["pid"]
        require(exit_event["code"] == 0 and type(pid) is int and pid > 0)
        _, info = one([(i, e) for i, e in select("start")
                       if e["sid"].rsplit("/", 1)[0] == parent
                       and re.fullmatch(r".*-P[0-9a-fA-F]+", e["sid"].rsplit("/", 1)[-1])
                       and int(e["sid"].rsplit("-P", 1)[-1], 16) == pid])
        return info["sid"], start, end

    root = one([e["sid"] for _, e in select("start") if "/" not in e["sid"]])
    root_start, root_end, root_exit = process(root, "worktree", "worktree")
    reset, start, end = child(root, one(select("child_start", root)),
                              ["reset", "--hard", "--no-recurse-submodules"])
    reset_start, reset_end, _ = process(reset, "reset", "worktree/reset")
    require(root_start < start < reset_start < reset_end < end < root_end)
    launches = select("child_start", reset)
    count = 4 if workers == 4 else 0
    require(len(launches) == count)
    seen = {root, reset}
    for launch in launches:
        sid, start, end = child(reset, launch, ["checkout--worker"])
        begin, finish, _ = process(sid, "checkout--worker", "worktree/reset/checkout--worker")
        require(sid not in seen and reset_start < start < begin < finish < end < reset_end)
        seen.add(sid)
    require(all(e["sid"] in seen for e in events))
    require(len(select("child_start")) == len(select("child_exit")) == count + 1)
    clock = root_exit["t_abs"]
    require(isinstance(clock, (int, float)) and math.isfinite(clock) and clock > 0)
    return dict(worker_launches=count, worker_successful_exits=count,
                trace2_exit_seconds=clock)


def comparisons(seconds):
    require(len(seconds) == 4 and all(isinstance(s, (int, float)) and math.isfinite(s)
                                    and s > 0 for s in seconds))
    result = []
    for pair, a, b in (("AB", 0, 1), ("BA", 3, 2)):
        baseline = Decimal(str(seconds[a]))
        delta = baseline - Decimal(str(seconds[b]))
        result.append(dict(pair=pair, baseline_seconds=seconds[a], candidate_seconds=seconds[b],
                           saved_seconds=float(delta), improvement_percent=float(100 * delta / baseline),
                           passes=delta >= Decimal(".20") and 100 * delta >= 5 * baseline))
    return result


@named_gate("binary")
def binary_identity(path):
    data = path.read_bytes()
    require(data[:2] == b"MZ")
    offset = struct.unpack_from("<I", data, 60)[0]
    require(data[offset:offset + 4] == b"PE\0\0")
    machine = struct.unpack_from("<H", data, offset + 4)[0]
    require(machine in (0xAA64, 0x8664))
    return dict(format="PE", machine="arm64" if machine == 0xAA64 else "x64",
                sha256=hashlib.sha256(data).hexdigest())


@named_gate("binary")
def safe_version(raw):
    version = raw.decode("ascii").strip()
    require(re.fullmatch(r"git version [0-9]+\.[0-9]+\.[0-9]+[.a-zA-Z0-9-]{0,40}", version))
    return version


@named_gate("runtime")
def native_python():
    require(sys.version_info[:3] == (3, 13, 15) and struct.calcsize("P") == 8)
    require(sys._is_gil_enabled() and not hasattr(sys, "gettotalrefcount"))
    identity = binary_identity(Path(sys.executable).resolve())
    process, native = ctypes.c_ushort(), ctypes.c_ushort()
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.GetCurrentProcess.restype = ctypes.c_void_p
    api.IsWow64Process2.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    require(api.IsWow64Process2(api.GetCurrentProcess(), ctypes.byref(process),
                                ctypes.byref(native)))
    require(process.value == 0 and native.value == 0xAA64 and identity["machine"] == "arm64")
    return identity


@named_gate("host")
def require_c_ntfs(private):
    resolve = ctypes.WinDLL("kernel32", use_last_error=True).GetVolumePathNameW
    resolve.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    root = ctypes.create_unicode_buffer(260)
    require(resolve(str(private), root, len(root)) and root.value.upper() == "C:\\")
    volume = ctypes.WinDLL("kernel32", use_last_error=True).GetVolumeInformationW
    volume.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_void_p,
                       ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32]
    fs = ctypes.create_unicode_buffer(32)
    require(volume(root.value, None, 0, None, None, None, fs, len(fs))
            and fs.value == "NTFS")


def walk_error(error):
    raise error


def snapshot(source, *, allow_registrations=False, metadata_only=False):
    gitdir = source / ".git"
    require(ordinary(gitdir, stat.S_ISDIR))
    result = {}
    for folder, dirs, names in os.walk(gitdir, onerror=walk_error):
        base = Path(folder)
        if allow_registrations and base == gitdir and "worktrees" in dirs:
            dirs.remove("worktrees")
        for n in dirs + names:
            p = base / n
            directory = n in dirs
            require(ordinary(p, stat.S_ISDIR if directory else stat.S_ISREG))
            rel = p.relative_to(gitdir)
            if directory:
                proof = None
            elif metadata_only and rel.parts[0] == "objects":
                st = p.stat()
                proof = (st.st_size, st.st_mtime_ns)
            else:
                proof = hashlib.sha256(p.read_bytes()).hexdigest()
            result[rel.as_posix()] = proof
    return result


def git_runner(owned, hooks, gitexe, source):
    def git(args, cwd=source, workers=1, env=None, timeout=30, native_clock=False):
        return owned.call([gitexe, "--no-pager", "-c", "core.autocrlf=false",
                           "-c", f"core.hooksPath={hooks}", "-c", f"checkout.workers={workers}",
                           "-c", "gc.auto=0", "-c", "maintenance.auto=false",
                           "-c", "worktree.useRelativePaths=false",
                           "-c", "protocol.allow=never", "-c", "protocol.file.allow=always",
                           *args], cwd, env, timeout, native_clock)
    return git


def prepare_donor(git, private, source):
    donor = private / "donor"
    # Copy the already checked-out source objects: no alternates or cross-volume data reads.
    git(["clone", "--local", "--no-checkout", "--no-hardlinks", "--no-tags",
         "--single-branch", str(source), str(donor)], cwd=private, timeout=45)
    require(list(donor.iterdir()) == [donor / ".git"])
    require(not any((donor / ".git" / p).exists() for p in
                    ("objects/info/alternates", "objects/info/http-alternates", "index", "worktrees")))
    require(not any((donor / ".git" / "objects" / "pack").glob("*.promisor")))
    head, _ = git(["rev-parse", "HEAD"], cwd=donor)
    require(head.strip() == COMMIT.encode())
    return donor


def run_trial(git, owned, private, donor, i, workers, *, native_clock):
    repo = private / f"arm-{i}"
    require(not os.path.lexists(repo))
    trace = private / f"trace-{i}.jsonl"
    env = dict(owned.env, GIT_TRACE2_EVENT=str(trace))
    _, receipt = git(["worktree", "add", "--detach", str(repo), COMMIT], cwd=donor,
                     workers=workers, env=env, timeout=25, native_clock=native_clock)
    summary = trace_summary([json.loads(s) for s in trace.read_bytes().splitlines()], workers)
    return repo, receipt, summary


@named_gate("file-oracle")
def verify_trial(git, donor, repo, tree):
    digest = verify_files(repo, tree, linked=True)
    registry = donor / ".git" / "worktrees"
    admin = registry / repo.name
    require(ordinary(registry, stat.S_ISDIR) and ordinary(admin, stat.S_ISDIR))
    link = (repo / ".git").read_text(encoding="utf-8").splitlines()
    require(len(link) == 1 and link[0].startswith("gitdir: "))
    require(Path(link[0][len("gitdir: "):]) == admin)
    for name in ("commondir", "gitdir", "HEAD", "index"):
        require(ordinary(admin / name, stat.S_ISREG))
    require((admin / "commondir").read_text(encoding="utf-8").splitlines() == ["../.."])
    require(Path((admin / "gitdir").read_text(encoding="utf-8").rstrip("\r\n")) == repo / ".git")
    require((admin / "HEAD").read_bytes() == COMMIT.encode() + b"\n")
    index, _ = git(["ls-files", "--stage", "-z"], cwd=repo)
    expected = b"".join(f"{mode} {oid} 0\t{name}".encode() + b"\0"
                        for name, (mode, oid) in sorted(tree.items()))
    require(index == expected)
    status, _ = git(["--no-optional-locks", "status", "--porcelain=v1",
                     "--untracked-files=all", "--ignored"], cwd=repo)
    head, _ = git(["rev-parse", "HEAD"], cwd=repo)
    require(not status and head.strip() == COMMIT.encode())
    return dict(files=len(tree), tree_sha256=digest, index_sha256=hashlib.sha256(index).hexdigest(),
                raw_blobs=True, filenames=True, index_modes=True, clean=True,
                detached_head=True, linked_worktree=True)


def screen(private, public, source):
    owned = Owned(private)
    stage = "identity"
    try:
        require(os.name == "nt" and os.environ.get("GITHUB_ACTIONS") == "true"
                and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
                and os.environ.get("RUNNER_ARCH") == "ARM64", "host")
        require(sys.getwindowsversion().build >= 22000, "host")
        require_c_ntfs(private)
        stage = "runtime"
        runtime = native_python()
        host = dict(platform="windows", architecture="arm64", github_hosted=True,
                    windows_build=sys.getwindowsversion().build, worktree_volume="C:", filesystem="NTFS")
        protocol_paths = [Path(__file__).resolve(),
                          HERE.parent / "hobl-complete-ci" / "owned_process.py"]
        protocol_before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in protocol_paths]
        stage = "binary"
        gitexe = Path(shutil.which("git")).resolve()
        launcher = binary_identity(gitexe)
        hooks = private / "empty-hooks"
        hooks.mkdir()

        git = git_runner(owned, hooks, gitexe, source)

        raw, _ = git(["version"])
        version = safe_version(raw)
        raw, _ = git(["--exec-path"])
        execpath = Path(os.fsdecode(raw).strip())
        core = binary_identity(execpath / "git.exe")
        require(core["machine"] == "arm64", "binary")
        stage = "source"
        head, _ = git(["rev-parse", "HEAD"])
        require(head.strip().decode() == COMMIT, "source-commit")
        raw, _ = git(["ls-tree", "-r", "-z", COMMIT])
        tree = parse_tree(raw)
        require(len(tree) == 2557, "tree")
        # This is the inherited blob-readiness check, on the full checked-out source only.
        inputs = private / "blob-input"
        inputs.write_bytes(b"".join(oid.encode() + b"\n" for _, oid in tree.values()))
        command = [gitexe, "--no-pager", "-c", "protocol.allow=never",
                   "-c", "core.autocrlf=false", "-c", f"core.hooksPath={hooks}",
                   "cat-file", "--batch"]
        blobs, _ = owned.call([sys.executable, "-I", "-B", __file__, "pipe", inputs, *command],
                              source, timeout=60)
        verify_batch(blobs, [oid for _, oid in tree.values()])
        del blobs
        # Inventory includes prepared objects and all metadata; no source writes permitted below.
        before = snapshot(source)
        source_digest = verify_files(source, tree)
        attributes = private / "attribute-input"
        attributes.write_bytes(b"\0".join(n.encode() for n in tree) + b"\0")
        command = [gitexe, "-c", "core.autocrlf=false", "-c", f"core.hooksPath={hooks}",
                   "-c", "protocol.allow=never", "-c", "protocol.file.allow=always",
                   "check-attr", f"--source={COMMIT}", "-z", "--all", "--stdin"]
        @named_gate("attributes")
        def check_attributes(repo):
            attrs, _ = owned.call([sys.executable, "-I", "-B", __file__, "pipe",
                                    attributes, *command], repo)
            fields = attrs.split(b"\0")
            require((len(fields) - 1) % 3 == 0 and fields[-1] == b"")
            for i in range(0, len(fields) - 1, 3):
                _, attr, value = fields[i:i + 3]
                require(not (attr in (b"filter", b"working-tree-encoding", b"ident")
                             and value not in (b"unset", b"unspecified")))
                require(not (attr == b"eol" and value == b"crlf"))
        check_attributes(source)
        stage = "config"
        donor = prepare_donor(git, private, source)
        config, _ = git(["config", "--null", "--list"], cwd=donor)
        values = {}
        for entry in config.split(b"\0"):
            if entry:
                key, _, value = entry.partition(b"\n")
                key = key.decode().lower()
                if key in ("core.fscache", "core.fsmonitor", "core.filemode",
                           "core.symlinks", "core.ignorecase", "core.autocrlf",
                           "checkout.thresholdforparallelism", "core.sparsecheckout",
                           "extensions.worktreeconfig", "extensions.partialclone"):
                    values[key] = value.decode()
        require(not {"checkout.thresholdforparallelism", "extensions.partialclone"} & values.keys())
        require(all(values.get(k, "false") == "false" for k in
                    ("core.sparsecheckout", "core.fsmonitor", "extensions.worktreeconfig",
                     "core.autocrlf")))
        require(all(v in ("true", "false") for v in values.values()))
        check_attributes(donor)
        # Do not read/warm the donor's copied object contents before the first timed add.
        donor_before = snapshot(donor, metadata_only=True)
        stage = "worktree-add"
        trials = [run_trial(git, owned, private, donor, i, workers, native_clock=True)
                  for i, workers in enumerate(WORKERS, 1)]
        stage = "file-oracle"
        arms = []
        for i, ((repo, receipt, summary), workers) in enumerate(zip(trials, WORKERS), 1):
            arms.append(dict(order=i, workers=workers, command_wall_seconds=receipt.command_wall,
                             **summary, oracle=verify_trial(git, donor, repo, tree), strict_drain=True))
        stage = "source-proof"
        require(before == snapshot(source))
        require(source_digest == verify_files(source, tree))
        require(list(donor.iterdir()) == [donor / ".git"])
        require(donor_before == snapshot(donor, allow_registrations=True, metadata_only=True))
        require({p.name for p in (donor / ".git" / "worktrees").iterdir()} ==
                {repo.name for repo, _, _ in trials})
        require(protocol_before == [hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in protocol_paths])
        pairs = comparisons([a["command_wall_seconds"] for a in arms])
        result = dict(schema=1, scope="worktree-add-detach-component-only", commit=COMMIT,
                      status="positive-component-lead-only" if all(p["passes"] for p in pairs)
                      else "negative-close-no-retry", arms=arms, comparisons=pairs,
                      gate_passed=all(p["passes"] for p in pairs),
                      floors=dict(seconds=.2, percent=5), source_unchanged=True,
                      donor_metadata_unchanged_except_registrations=True,
                      all_blobs_prepared=True, lazy_fetch_disabled=True, strict_drain=True,
                      protocol_unchanged=True,
                      strict_receipts=owned.count, guardian_sha256=GUARD_SHA,
                      configuration=dict(common=values, workers=list(WORKERS),
                                         threshold=100, hooks="owned-empty",
                                         network_protocols="denied",
                                         donor="local-object-copy-no-alternates"),
                      identity=dict(host=host, git_version=version, launcher=launcher, core=core,
                                    python=runtime, native_runtime=True,
                                    git_native_arm64=core["machine"] == "arm64"),
                      adoption=False, hobl_parity=False, physical_media_proven=False)
        save(public / "result.json", result)
        save(public / "stage.json", dict(schema=1, stage="complete", category="none", native_code=0))
        return 0
    except Exception as error:
        category = error.category if isinstance(error, GateFailure) else "closed-scope-failure"
        if category == "closed-scope-failure":
            category = {"identity": "host", "runtime": "runtime", "binary": "binary",
                        "source": "tree", "config": "config", "trace-worker": "trace-worker",
                        "file-oracle": "file-oracle", "source-proof": "source-proof",
                        "worktree-add": "worktree-add"}.get(stage, category)
        save(public / "stage.json", dict(schema=1, stage=stage, category=category,
                                         native_code=owned.code or -1))
        return 1


def bootstrap(private, public, source, uv):
    owned = Owned(private, "bootstrap")
    try:
        install = private / "python"
        install.mkdir()
        owned.env.update(UV_PYTHON_INSTALL_DIR=str(install), UV_CACHE_DIR=str(private / "uv-cache"),
                         UV_HTTP_RETRIES="0", UV_HTTP_TIMEOUT="20")
        version, _ = owned.call([uv, "--version"], private)
        require(version.strip() == b"uv 0.13.6" or version.startswith(b"uv 0.13.6 "))
        owned.call([uv, "python", "install", "3.13.15", "--no-bin", "--no-registry",
                    "--no-config", "--no-progress"], private, timeout=60)
        found, _ = owned.call([uv, "python", "find", "3.13.15", "--managed-python",
                              "--no-python-downloads", "--no-project", "--no-config",
                              "--no-progress"], private)
        python = Path(os.fsdecode(found).strip()).resolve(strict=True)
        require(python.is_file() and python.is_relative_to(install.resolve()))
        # The controller owns every Git invocation; this outer receipt also requires natural drain.
        owned.call([python, "-I", "-B", __file__, "screen", private, public, source],
                   private, timeout=230)
        result = json.loads((public / "result.json").read_text())
        result["strict_receipts"] += owned.count
        result["setup_strict_drain"] = True
        save(public / "result.json", result)
        return 0
    except Exception as error:
        stage_file = public / "stage.json"
        if not stage_file.exists() or json.loads(stage_file.read_text())["category"] == "none":
            save(public / "stage.json", dict(schema=1, stage="bootstrap",
                 category=error.category if isinstance(error, GateFailure)
                 else "closed-scope-failure", native_code=owned.code or -1))
        (public / "result.json").unlink(missing_ok=True)
        return 1


if __name__ == "__main__":
    if sys.argv[1] == "pipe":
        import subprocess
        with Path(sys.argv[2]).open("rb") as stream:
            sys.exit(subprocess.run(sys.argv[3:], stdin=stream).returncode)
    private, public, source = map(lambda p: Path(p).resolve(), sys.argv[2:5])
    sys.exit(bootstrap(private, public, source, sys.argv[5]) if sys.argv[1] == "bootstrap"
             else screen(private, public, source))
