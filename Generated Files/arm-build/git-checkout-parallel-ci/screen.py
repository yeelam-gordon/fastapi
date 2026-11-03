"""Single ABBA checkout component screen. No retries, adoption, or HOBL payload."""
import ctypes
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import struct
import sys
from dataclasses import asdict

COMMIT = "864b569cf8453654fc3bc2c64108c0f644e2918c"
GUARD_SHA = "45d6db4f6452c4f7116ca23c6e2aa74cda90a15548bd5c9bb3b3574973ef458e"
HERE = Path(__file__).resolve().parent


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
        # Ignore inherited diagnostic destinations, but do not alter auth or TLS.
        for key in list(self.env):
            if key.startswith("GIT_TRACE"):
                del self.env[key]

    def call(self, args, cwd, env=None, timeout=30):
        self.count += 1
        prefix = self.private / f"{self.namespace}-{self.count}"
        receipt = self.guard.run_owned(
            list(map(str, args)), cwd=str(cwd), env=env or self.env,
            stdout_path=prefix.with_suffix(".stdout"),
            stderr_path=prefix.with_suffix(".stderr"),
            timeout=timeout, native_clock=True,
        )
        save(prefix.with_suffix(".json"), asdict(receipt))
        self.code = receipt.returncode if isinstance(receipt.returncode, int) else -1
        require(receipt.succeeded and receipt.survivors is False, "native-command")
        require(receipt.command_wall is not None and math.isfinite(receipt.command_wall),
                "native-command")
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


@named_gate("file-oracle")
def verify_files(repo, tree, unix):
    actual = set()
    for folder, dirs, names in os.walk(repo, followlinks=False):
        if Path(folder) == repo:
            dirs.remove(".git")
        require(all(not (Path(folder) / name).is_symlink() for name in dirs))
        for name in names:
            actual.add((Path(folder) / name).relative_to(repo).as_posix())
    require(actual == set(tree))
    for name, (mode, oid) in tree.items():
        path = repo / name
        require(stat.S_ISREG(path.lstat().st_mode))
        data = path.read_bytes()
        require(hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == oid)
        if unix:
            require(bool(path.stat().st_mode & 0o111) == (mode == "100755"))
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
    starts = [e for e in events if e.get("event") == "child_start"
              and any(re.fullmatch(r"(?:.*[/\\])?checkout--worker(?:\.exe)?", a)
                      for a in e.get("argv", []) if isinstance(a, str))]
    require(len(starts) == sum(e.get("event") == "child_start" for e in events))
    keys = [(s.get("sid"), s.get("child_id")) for s in starts]
    require(len(set(keys)) == len(keys))
    for sid, child in keys:
        exits = [e for e in events if e.get("event") == "child_exit"
                 and e.get("sid") == sid and e.get("child_id") == child]
        require(len(exits) == 1 and exits[0].get("code") == 0)
    require(len(starts) == (4 if workers == 4 else 0))
    exits = [e for e in events if e.get("event") == "exit" and "/" not in e.get("sid", "")]
    require(len(exits) == 1 and exits[0].get("code") == 0)
    clock = exits[0].get("t_abs")
    require(isinstance(clock, (int, float)) and math.isfinite(clock) and clock > 0)
    return dict(worker_launches=len(starts), worker_successful_exits=len(keys),
                trace2_exit_seconds=clock)


def comparisons(seconds):
    require(len(seconds) == 4 and all(isinstance(s, (int, float)) and math.isfinite(s)
                                    and s > 0 for s in seconds))
    result = []
    for pair, a, b in (("AB", 0, 1), ("BA", 3, 2)):
        delta = seconds[a] - seconds[b]
        result.append(dict(pair=pair, baseline_seconds=seconds[a], candidate_seconds=seconds[b],
                           saved_seconds=delta, improvement_percent=100 * delta / seconds[a],
                           passes=delta >= .2 and delta / seconds[a] >= .05))
    return result


@named_gate("binary")
def binary_identity(path):
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if os.name == "nt":
        require(data[:2] == b"MZ")
        offset = struct.unpack_from("<I", data, 60)[0]
        require(data[offset:offset + 4] == b"PE\0\0")
        machine = struct.unpack_from("<H", data, offset + 4)[0]
        require(machine in (0xAA64, 0x8664))
        return dict(format="PE", machine="arm64" if machine == 0xAA64 else "x64",
                    sha256=digest)
    magic = data[:4]
    cpus = []
    if magic in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe"):
        cpus = [struct.unpack_from("<I", data, 4)[0]]
    elif magic in (b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"):
        count = struct.unpack_from(">I", data, 4)[0]
        require(0 < count <= 8)
        stride = 32 if magic[-1] == 0xBF else 20
        cpus = [struct.unpack_from(">I", data, 8 + i * stride)[0] for i in range(count)]
    require(0x100000C in cpus and all(c in (0x100000C, 0x1000007) for c in cpus))
    return dict(format="Mach-O", slices=sorted("arm64" if c == 0x100000C else "x64"
                                             for c in cpus), sha256=digest)


@named_gate("binary")
def safe_version(raw):
    version = raw.decode("ascii").strip()
    require(re.fullmatch(r"git version [0-9]+\.[0-9]+\.[0-9]+[.a-zA-Z0-9-]{0,40}"
                         r"(?: \(Apple Git-[0-9]{1,5}\))?", version))
    return version


@named_gate("runtime")
def native_python():
    require(sys.version_info[:3] == (3, 13, 15) and struct.calcsize("P") == 8)
    require(sys._is_gil_enabled() and not hasattr(sys, "gettotalrefcount"))
    identity = binary_identity(Path(sys.executable).resolve())
    if os.name == "nt":
        process, native = ctypes.c_ushort(), ctypes.c_ushort()
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.GetCurrentProcess.restype = ctypes.c_void_p
        api.IsWow64Process2.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        require(api.IsWow64Process2(api.GetCurrentProcess(), ctypes.byref(process),
                                    ctypes.byref(native)))
        require(process.value == 0 and native.value == 0xAA64 and identity["machine"] == "arm64")
    else:
        require(sys.platform == "darwin" and platform.machine() == "arm64")
    return identity


def snapshot(source):
    gitdir = source / ".git"
    return {p.relative_to(gitdir).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in gitdir.rglob("*") if p.is_file()}


def screen(private, public, source):
    owned = Owned(private)
    stage = "identity"
    try:
        require(os.environ.get("GITHUB_ACTIONS") == "true"
                and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
                and os.environ.get("RUNNER_ARCH") == "ARM64", "host")
        stage = "runtime"
        runtime = native_python()
        host = dict(platform="windows" if os.name == "nt" else "macos",
                    architecture="arm64", github_hosted=True)
        if os.name == "nt":
            require(sys.getwindowsversion().build >= 22000, "host")
            host["windows_build"] = sys.getwindowsversion().build
        protocol_paths = [Path(__file__).resolve(),
                          HERE.parent / "hobl-complete-ci" / "owned_process.py"]
        protocol_before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in protocol_paths]
        stage = "binary"
        gitexe = Path(shutil.which("git")).resolve()
        launcher = binary_identity(gitexe)
        hooks = private / "empty-hooks"
        hooks.mkdir()

        def git(args, cwd=source, workers=1, env=None, timeout=30):
            return owned.call([gitexe, "-c", "core.autocrlf=false", "-c",
                               f"core.hooksPath={hooks}", "-c", f"checkout.workers={workers}",
                               "-c", "protocol.allow=never", "-c", "protocol.file.allow=always",
                               *args], cwd, env, timeout)

        raw, _ = git(["version"])
        version = safe_version(raw)
        raw, _ = git(["--exec-path"])
        execpath = Path(os.fsdecode(raw).strip())
        corepath = execpath / ("git.exe" if os.name == "nt" else "git")
        if os.name != "nt" and not corepath.is_file():
            corepath = execpath.parent.parent / "bin" / "git"
        core = binary_identity(corepath)
        stage = "source"
        head, _ = git(["rev-parse", "HEAD"])
        require(head.strip().decode() == COMMIT, "source-commit")
        raw, _ = git(["ls-tree", "-r", "-z", COMMIT])
        tree = parse_tree(raw)
        require(len(tree) == 2557, "tree")
        # Read every blob before measuring, allowing any source lazy fetch only here.
        inputs = private / "blob-input"
        inputs.write_bytes(b"".join(oid.encode() + b"\n" for _, oid in tree.values()))
        command = [gitexe, "-c", "core.autocrlf=false", "-c", f"core.hooksPath={hooks}",
                   "cat-file", "--batch"]
        blobs, _ = owned.call([sys.executable, "-I", "-B", __file__, "pipe", inputs, *command],
                              source, timeout=60)
        verify_batch(blobs, [oid for _, oid in tree.values()])
        del blobs
        owned.env["GIT_NO_LAZY_FETCH"] = "1"
        owned.env["GIT_TERMINAL_PROMPT"] = "0"
        # Inventory includes prepared objects and all metadata; no source writes permitted below.
        before = snapshot(source)
        source_digest = verify_files(source, tree, os.name != "nt")
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
        repos, settings = [], []
        for i in range(4):
            repo = private / f"arm-{i}"
            git(["clone", "--local", "--shared", "--no-checkout", "--no-hardlinks",
                 str(source), str(repo)], cwd=private)
            require(list(repo.iterdir()) == [repo / ".git"])
            config, _ = git(["config", "--null", "--list"], cwd=repo)
            values = {}
            for entry in config.split(b"\0"):
                if entry:
                    key, _, value = entry.partition(b"\n")
                    key = key.decode().lower()
                    if key in ("core.fscache", "core.fsmonitor", "core.filemode",
                               "core.symlinks", "core.ignorecase", "core.autocrlf",
                               "checkout.thresholdforparallelism", "core.sparsecheckout"):
                        values[key] = value.decode()
            require("checkout.thresholdforparallelism" not in values)
            require(values.get("core.sparsecheckout", "false") == "false")
            require(values.get("core.fsmonitor", "false") == "false")
            require(all(v in ("true", "false") for v in values.values()))
            settings.append(values)
            repos.append(repo)
            check_attributes(repo)
        require(all(v == settings[0] for v in settings))
        stage = "native-command"
        arms = []
        for i, (repo, workers) in enumerate(zip(repos, (1, 4, 4, 1)), 1):
            trace = private / f"trace-{i}.jsonl"
            env = dict(owned.env, GIT_TRACE2_EVENT=str(trace))
            _, receipt = git(["checkout", "--detach", "--force", COMMIT], cwd=repo,
                             workers=workers, env=env, timeout=45)
            stage = "trace-worker"
            summary = trace_summary([json.loads(s) for s in trace.read_text().splitlines()], workers)
            stage = "file-oracle"
            digest = verify_files(repo, tree, os.name != "nt")
            index, _ = git(["ls-files", "--stage", "-z"], cwd=repo)
            expected = b"".join(f"{mode} {oid} 0\t{name}".encode() + b"\0"
                                for name, (mode, oid) in sorted(tree.items()))
            require(index == expected)
            status, _ = git(["--no-optional-locks", "status", "--porcelain=v1",
                             "--untracked-files=all"], cwd=repo)
            head, _ = git(["rev-parse", "HEAD"], cwd=repo)
            require(not status and head.strip().decode() == COMMIT)
            require((repo / ".git" / "HEAD").read_text().strip() == COMMIT)
            arms.append(dict(order=i, workers=workers, command_wall_seconds=receipt.command_wall,
                             **summary, oracle=dict(files=2557, tree_sha256=digest,
                             raw_blobs=True, filenames=True, index_modes=True, clean=True,
                             detached_head=True, unix_exec_modes=os.name != "nt"), strict_drain=True))
            stage = "native-command"
        stage = "source-proof"
        require(before == snapshot(source))
        require(source_digest == verify_files(source, tree, os.name != "nt"))
        require(protocol_before == [hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in protocol_paths])
        pairs = comparisons([a["command_wall_seconds"] for a in arms])
        result = dict(schema=1, scope="checkout-component-only", commit=COMMIT,
                      status="positive-component-lead-only" if all(p["passes"] for p in pairs)
                      else "negative-close-no-retry", arms=arms, comparisons=pairs,
                      gate_passed=all(p["passes"] for p in pairs),
                      floors=dict(seconds=.2, percent=5), source_unchanged=True,
                      all_blobs_prepared=True, lazy_fetch_disabled=True, strict_drain=True,
                      protocol_unchanged=True,
                      strict_receipts=owned.count, guardian_sha256=GUARD_SHA,
                      configuration=dict(common=settings[0], workers=[1, 4, 4, 1],
                                         threshold=100, hooks="owned-empty",
                                         network_protocols="denied-after-prefetch",
                                         local_file_protocol="allowed-for-local-clones"),
                      identity=dict(host=host, git_version=version, launcher=launcher, core=core,
                                    python=runtime, native_runtime=True,
                                    git_native_arm64=(core.get("machine") == "arm64"
                                                     if os.name == "nt" else True)),
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
                        "native-command": "native-command"}.get(stage, category)
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
