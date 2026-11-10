"""Positively audited warmup bytecode outputs followed by a complete runtime seal."""

import hashlib
import importlib.util
import io
import json
import marshal
import stat
import struct
import sys
import types
from concurrent.futures import ThreadPoolExecutor
from itertools import repeat
from pathlib import Path


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def code_key(value):
    if isinstance(value, types.CodeType):
        fields = (
            "co_argcount co_posonlyargcount co_kwonlyargcount co_nlocals co_stacksize "
            "co_flags co_code co_names co_varnames co_filename co_name co_qualname "
            "co_firstlineno co_linetable co_exceptiontable co_freevars co_cellvars"
        ).split()
        return tuple(getattr(value, name) for name in fields), code_key(value.co_consts)
    if isinstance(value, (tuple, frozenset)):
        items = (code_key(item) for item in value)
        return type(value).__name__, tuple(items) if isinstance(
            value, tuple
        ) else frozenset(items)
    if isinstance(value, str):
        return "str", value
    return type(value).__name__, marshal.dumps(value)


def header_matches(data, source):
    return (
        len(data) >= 16
        and data[:4] == importlib.util.MAGIC_NUMBER
        and struct.unpack_from("<III", data, 4)
        == (0, source["timestamp"], source["size"] & 0xFFFFFFFF)
    )


def runtime_entry(path, root):
    require(
        not path.is_symlink() and not path.is_junction(),
        "runtime symlink/junction",
    )
    name = path.relative_to(root).as_posix()
    if path.is_dir():
        return name, None, None
    before = path.stat()
    require(stat.S_ISREG(before.st_mode), "nonregular runtime output")
    data = path.read_bytes()
    after = path.stat()
    fields = ("st_size", "st_mtime_ns", "st_ctime_ns", "st_mode", "st_ino")
    require(
        all(getattr(before, field) == getattr(after, field) for field in fields),
        "runtime changed during snapshot",
    )
    record = {
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": before.st_size,
        "mtime_ns": before.st_mtime_ns,
        "ctime_ns": before.st_ctime_ns,
        "mode": before.st_mode,
        "inode": before.st_ino,
        "timestamp": int(before.st_mtime) & 0xFFFFFFFF,
    }
    return name, record, data if path.suffix.lower() == ".pyc" else None


class RuntimeGuard:
    def __init__(
        self,
        python,
        identity,
        output,
        initial_inputs,
        nonruntime_snapshot,
        link_policy=None,
    ):
        require(
            Path(python).resolve() == Path(sys.executable).resolve()
            and identity["version"] == sys.version
            and sys.version_info[:3] == (3, 13, 15)
            and sys.flags.optimize == 0
            and sys.implementation.cache_tag == "cpython-313",
            "runtime compiler must be the exact target Python 3.13.15, optimize=0",
        )
        self.roots = {
            name: Path(name).resolve(strict=True) for name in identity["runtime_roots"]
        }
        require(
            set(self.roots.values())
            == {Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()},
            "runtime compiler prefix association",
        )
        self.link_policy = link_policy
        if link_policy is not None:
            link_policy.bind_compiler(self.roots)
        self.output, self.inputs = Path(output), nonruntime_snapshot
        self.expected_inputs = {
            key: value for key, value in initial_inputs.items() if key != "runtime"
        }
        self.phase, self.sealed, self.evidence = 0, None, {}
        self.current, self.raw = self.scan()
        if link_policy is not None:
            link_policy.check_initial(self.current)
        require(
            {
                root: {name: value["sha256"] for name, value in files.items()}
                for root, files in self.current["files"].items()
            }
            == initial_inputs["runtime"],
            "runtime changed before initial metadata seal",
        )
        require(
            self.current["inputs"] == self.expected_inputs, "nonruntime input changed"
        )
        associations = []
        for index, (root, entries) in enumerate(self.raw.items()):
            for name in entries:
                try:
                    source = Path(
                        importlib.util.source_from_cache(str(Path(root) / name))
                    )
                    source_name = source.relative_to(root).as_posix()
                except ValueError:
                    source_name = None
                associations.append(
                    {
                        "root": root,
                        "cache": name,
                        "source": source_name,
                        "source_seal": self.current["files"][root].get(source_name),
                        "raw": str(
                            self.output
                            / "runtime-initial"
                            / "after"
                            / str(index)
                            / name
                        ),
                    }
                )
        self.record(
            self.output / "runtime-initial.json",
            {
                "state": self.current,
                "cache_associations": associations,
                "root_bindings": {name: str(path) for name, path in self.roots.items()},
                "compiler": {
                    "executable": sys.executable,
                    "version": sys.version,
                    "cache_tag": sys.implementation.cache_tag,
                    "optimize": sys.flags.optimize,
                    "dont_inherit": True,
                },
            },
        )
        self.retain(self.output / "runtime-initial", {}, self.raw)

    def record(self, path, value):
        save(path, value)
        self.evidence[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()

    def scan(self):
        if getattr(self, "link_policy", None) is not None:
            return self.link_policy.scan(self.roots, self.inputs, runtime_entry)
        files, directories, raw = {}, {}, {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            for declared, root in self.roots.items():
                require(
                    Path(declared).resolve(strict=True) == root,
                    "runtime root binding changed",
                )
                files[declared], raw[declared], directories[declared] = {}, {}, []
                entries = pool.map(runtime_entry, sorted(root.rglob("*")), repeat(root))
                for name, record, data in entries:
                    if record is None:
                        directories[declared].append(name)
                    else:
                        files[declared][name] = record
                        if data is not None:
                            raw[declared][name] = data
        return {
            "files": files,
            "directories": directories,
            "inputs": self.inputs(),
        }, raw

    def retain(self, folder, before, after):
        for label, roots in (("before", before), ("after", after)):
            for index, entries in enumerate(roots.values()):
                for name, data in entries.items():
                    target = folder / label / str(index) / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    self.evidence[str(target)] = hashlib.sha256(data).hexdigest()

    def before_row(self, arm, measured, pair, folder):
        require(
            measured
            if self.phase >= 2
            else (arm, measured, pair)
            == (("C", False, "WA") if self.phase == 0 else ("D", False, "WB")),
            "runtime warmup phase boundary",
        )
        observed, _ = self.scan()
        self.record(folder / "runtime-before.json", observed)
        require(observed == self.current, "runtime/input changed between commands")

    def after_row(self, arm, measured, pair, folder):
        observed, raw = self.scan()
        audit = {"state": observed, "associations": []}
        target = folder / "runtime-after.json"
        self.record(target, audit)
        changed = {
            root: {
                name: data
                for name, data in entries.items()
                if observed["files"][root][name]
                != self.current["files"][root].get(name)
            }
            for root, entries in raw.items()
        }
        old = {
            root: {
                name: self.raw[root][name] for name in entries if name in self.raw[root]
            }
            for root, entries in changed.items()
        }
        retained = folder / "runtime-cache-outputs"
        self.retain(retained, old, changed)
        require(observed["inputs"] == self.expected_inputs, "nonruntime input changed")
        if measured:
            require(
                self.sealed is not None and observed == self.sealed,
                "measured runtime/input changed after WB seal",
            )
            return
        self.before_phase(arm, pair)
        if self.link_policy is not None:
            require(
                observed["links"] == self.current["links"],
                "runtime link/target changed during warmup",
            )
            require(
                all(
                    observed["ancestors"].get(name) == value
                    for name, value in self.current["ancestors"].items()
                ),
                "runtime ancestor changed during warmup",
            )
        for index, (root, files) in enumerate(observed["files"].items()):
            previous = self.current["files"][root]
            require(previous.keys() <= files.keys(), "runtime file deletion")
            allowed_directories = set()
            for name, metadata in files.items():
                if metadata == previous.get(name):
                    continue
                cache = Path(root) / name
                require(
                    cache.parent.name == "__pycache__",
                    "unexplained non-cache runtime write",
                )
                source = cache.parent.parent / (
                    cache.name.removesuffix(".cpython-313.pyc") + ".py"
                )
                require(
                    cache.name
                    == Path(
                        importlib.util.cache_from_source(str(source), optimization="")
                    ).name,
                    "noncanonical runtime cache",
                )
                source_name = source.relative_to(Path(root)).as_posix()
                sealed_source = previous.get(source_name)
                require(
                    sealed_source is not None
                    and files.get(source_name) == sealed_source,
                    "runtime bytecode source changed or outside sealed root",
                )
                data = raw[root][name]
                require(
                    header_matches(data, sealed_source),
                    f"runtime bytecode magic/flags/timestamp/size: {cache}",
                )
                prior = self.raw[root].get(name)
                if prior is not None:
                    stale = prior[:4] != importlib.util.MAGIC_NUMBER or (
                        len(prior) >= 16
                        and struct.unpack_from("<I", prior, 4)[0] == 0
                        and not header_matches(prior, sealed_source)
                    )
                    require(
                        stale,
                        f"replacement of a preserved valid runtime cache: {cache}",
                    )
                stream = io.BytesIO(data[16:])
                code = marshal.load(stream)
                require(
                    isinstance(code, types.CodeType) and not stream.read(),
                    "runtime bytecode payload",
                )
                source_bytes = source.read_bytes()
                require(
                    source.resolve().is_relative_to(self.roots[root])
                    and hashlib.sha256(source_bytes).hexdigest()
                    == sealed_source["sha256"],
                    "runtime compile source hash differs",
                )
                expected = compile(
                    source_bytes, str(source), "exec", dont_inherit=True, optimize=0
                )
                require(
                    code_key(code) == code_key(expected),
                    f"runtime bytecode filename/deep code differs: {cache}",
                )
                allowed_directories.add(cache.parent.relative_to(Path(root)).as_posix())
                audit["associations"].append(
                    {
                        "root": root,
                        "cache": name,
                        "source": source_name,
                        "source_seal": sealed_source,
                        "before": previous.get(name),
                        "after": metadata,
                        "filename": str(source),
                        "raw_before": str(retained / "before" / str(index) / name)
                        if prior is not None
                        else None,
                        "raw_after": str(retained / "after" / str(index) / name),
                    }
                )
            prior_dirs, next_dirs = (
                set(self.current["directories"][root]),
                set(observed["directories"][root]),
            )
            require(
                prior_dirs <= next_dirs
                and next_dirs - prior_dirs <= allowed_directories,
                "unexplained runtime directory change",
            )
        self.record(target, audit)
        self.current, self.raw = observed, raw
        self.phase += 1
        if self.phase == 2:
            self.sealed = observed
            self.record(self.output / "runtime-seal-after-WB.json", self.sealed)

    def before_phase(self, arm, pair):
        require(
            self.phase < 2
            and (arm, pair) == (("C", "WA") if self.phase == 0 else ("D", "WB")),
            "runtime warmup phase boundary",
        )

    def final(self):
        observed, _ = self.scan()
        self.record(self.output / "runtime-final.json", observed)
        require(
            self.sealed is not None and observed == self.sealed,
            "final runtime/input seal differs",
        )
        require(
            all(
                hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
                for path, digest in self.evidence.items()
            ),
            "runtime audit evidence changed",
        )
        save(
            self.output / "runtime-evidence-seal.json",
            {
                Path(path).relative_to(self.output).as_posix(): digest
                for path, digest in self.evidence.items()
            },
        )
