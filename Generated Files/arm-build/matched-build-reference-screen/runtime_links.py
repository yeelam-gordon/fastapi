"""Private, source-only fixed uv 0.13.6 Darwin CPython 3.13.15 link contract."""

import json
import os
import stat
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from runtime_bytecode import RuntimeGuard

ARCHIVE_SHA256 = "d66c67f16148c7454b1509c32747175f7669c8b8e105b97b92a0000d66af6e6e"
SDK_LINKS = (
    ("bin/idle3", "idle3.13"),
    ("bin/pydoc3", "pydoc3.13"),
    ("bin/python", "python3.13"),
    ("bin/python3", "python3.13"),
    ("bin/python3-config", "python3.13-config"),
    ("lib/pkgconfig/python3-embed.pc", "python-3.13-embed.pc"),
    ("lib/pkgconfig/python3.pc", "python-3.13.pc"),
    ("share/man/man1/python.1", "python3.13.1"),
    ("share/man/man1/python3.1", "python3.13.1"),
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def metadata(value):
    return {
        name: getattr(value, "st_" + field)
        for name, field in (
            ("inode", "ino"),
            ("device", "dev"),
            ("mode", "mode"),
            ("size", "size"),
            ("mtime_ns", "mtime_ns"),
            ("ctime_ns", "ctime_ns"),
            ("nlink", "nlink"),
        )
    }


def directory_identity(path):
    value = path.lstat()
    require(
        stat.S_ISDIR(value.st_mode)
        and not path.is_symlink()
        and not path.is_junction(),
        f"runtime ancestor is not a real directory: {path}",
    )
    return {key: metadata(value)[key] for key in ("device", "inode", "mode")}


class DarwinRuntimeLinks:
    """Fixed patch request, normal GIL, separate canonical SDK and uv venv only.

    The base executable is the exact absolute `base_python` from the creation
    receipt, not a path inferred from the initial tree. SDK executable aliases
    can be retained by uv's landmark-based find_base_python; only the publisher's
    two aliases and its regular versioned executable are supported here.
    """

    def __init__(self, sdk_root, venv_root, base_executable, archive_sha256):
        require(archive_sha256 == ARCHIVE_SHA256, "unsupported publisher archive")
        self.sdk, self.venv = Path(sdk_root), Path(venv_root)
        for root in (self.sdk, self.venv):
            require(
                root.is_absolute()
                and str(root) == str(root.resolve(strict=True))
                and ".." not in root.parts,
                "runtime policy needs canonical absolute roots",
            )
        require(
            not self.sdk.is_relative_to(self.venv)
            and not self.venv.is_relative_to(self.sdk),
            "runtime policy needs separate disjoint SDK and venv",
        )
        self.base = Path(base_executable)
        require(
            str(base_executable) == str(self.base)
            and self.base
            in {
                self.sdk / "bin" / name for name in ("python", "python3", "python3.13")
            },
            "unsupported exact uv base executable",
        )
        self.rules = {
            str(self.sdk): {
                name: (target, str(self.sdk), (Path(name).parent / target).as_posix())
                for name, target in SDK_LINKS
            },
            str(self.venv): {
                "bin/python": (str(self.base), str(self.sdk), "bin/python3.13"),
                "bin/python3": ("python", str(self.sdk), "bin/python3.13"),
                "bin/python3.13": ("python", str(self.sdk), "bin/python3.13"),
            },
        }
        self.initial_state = None

    def bind_compiler(self, roots):
        require(
            set(roots) == set(self.rules)
            and Path(sys.prefix) == self.venv
            and Path(sys.base_prefix) == self.sdk
            and Path(sys.executable) == self.venv / "bin" / "python"
            and sys._base_executable == str(self.sdk / "bin" / "python3.13")
            and not getattr(sys, "abiflags", ""),
            "Darwin runtime compiler/base executable association",
        )

    def check_initial(self, state):
        if self.initial_state is not None:
            require(
                {key: value for key, value in state.items() if key != "inputs"}
                == self.initial_state,
                "runtime changed between input hashes and initial seal",
            )

    def scan(self, roots, inputs, regular_entry):
        require(
            set(roots) == set(self.rules)
            and all(str(root) == declared for declared, root in roots.items()),
            "runtime policy root association",
        )
        files, directories, raw, links, ancestors = {}, {}, {}, {}, {}
        paths = []
        for declared, root in roots.items():
            require(root.resolve(strict=True) == root, "runtime root binding changed")
            for ancestor in reversed((root, *root.parents)):
                ancestors[str(ancestor)] = directory_identity(ancestor)
            files[declared], directories[declared], raw[declared], links[declared] = (
                {},
                [],
                {},
                {},
            )
            pending = [root]
            while pending:
                parent = pending.pop()
                for path in sorted(parent.iterdir()):
                    name = path.relative_to(root).as_posix()
                    require(not path.is_junction(), "runtime junction")
                    value = path.lstat()
                    if stat.S_ISLNK(value.st_mode):
                        require(name in self.rules[declared], "unexpected runtime link")
                        require(value.st_nlink == 1, "runtime link hardlink")
                        target, target_root, target_name = self.rules[declared][name]
                        observed_target = os.readlink(path)
                        require(observed_target == target, "runtime raw link target")
                        # No directory traversal or general-purpose link resolution.
                        # The complete allowed graph closes to this one regular member.
                        links[declared][name] = {
                            "path": str(path),
                            "raw_target": observed_target,
                            "lstat": metadata(value),
                            "target_root": target_root,
                            "target_name": target_name,
                        }
                    elif stat.S_ISDIR(value.st_mode):
                        directories[declared].append(name)
                        ancestors[str(path)] = directory_identity(path)
                        pending.append(path)
                    else:
                        require(stat.S_ISREG(value.st_mode), "nonregular runtime input")
                        paths.append((declared, root, path))
            directories[declared].sort()
            require(
                set(links[declared]) == set(self.rules[declared]),
                "missing runtime links",
            )

        def read(item):
            declared, root, path = item
            before = path.lstat()
            require(
                stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
                "runtime regular target type/hardlink",
            )
            name, record, data = regular_entry(path, root)
            after = path.lstat()
            require(
                metadata(before) == metadata(after) and not path.is_junction(),
                "runtime target replaced during snapshot",
            )
            record.update(device=before.st_dev, nlink=before.st_nlink)
            return declared, name, record, data

        with ThreadPoolExecutor(max_workers=4) as pool:
            for declared, name, record, data in pool.map(read, paths):
                files[declared][name] = record
                if data is not None:
                    raw[declared][name] = data
        for declared, entries in links.items():
            for name, record in entries.items():
                target = files[record["target_root"]].get(record["target_name"])
                require(target is not None, "runtime link target is not sealed regular")
                record["target"] = dict(target)
                path = Path(declared) / name
                require(
                    metadata(path.lstat()) == record["lstat"]
                    and os.readlink(path) == record["raw_target"]
                    and not path.is_junction(),
                    "runtime link changed during snapshot",
                )
                target_path = Path(record["target_root"]) / record["target_name"]
                require(
                    all(
                        target[key] == value
                        for key, value in metadata(target_path.lstat()).items()
                    )
                    and not target_path.is_junction(),
                    "runtime link target replaced during snapshot",
                )
        for name, identity in ancestors.items():
            require(
                directory_identity(Path(name)) == identity,
                "runtime ancestor changed during snapshot",
            )
        return {
            "files": files,
            "directories": directories,
            "links": links,
            "ancestors": ancestors,
            "inputs": inputs(),
        }, raw

    def remember_inputs(self, state):
        self.check_initial(state)
        self.initial_state = json.loads(
            json.dumps({key: value for key, value in state.items() if key != "inputs"})
        )


def runtime_input_hashes(roots, link_policy=None):
    """Runtime-only regular-file manifest; never use for source/wheel inputs."""
    guard = object.__new__(RuntimeGuard)
    guard.roots = {str(root): Path(root).resolve(strict=True) for root in roots}
    guard.inputs = dict
    guard.link_policy = link_policy
    state, _ = guard.scan()
    if link_policy is not None:
        link_policy.remember_inputs(state)
    return {
        root: {name: record["sha256"] for name, record in entries.items()}
        for root, entries in state["files"].items()
    }
