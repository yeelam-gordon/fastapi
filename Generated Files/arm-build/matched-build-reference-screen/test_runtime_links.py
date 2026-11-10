import hashlib
import json
import stat
import sys
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import test_runtime_bytecode
from runtime_bytecode import RuntimeGuard
from runtime_links import (
    ARCHIVE_SHA256,
    SDK_LINKS,
    DarwinRuntimeLinks,
    runtime_input_hashes,
)


class RuntimeLinksTests(unittest.TestCase):
    write_cache = test_runtime_bytecode.RuntimeBytecodeTests.write_cache
    begin = test_runtime_bytecode.RuntimeBytecodeTests.begin
    warm = test_runtime_bytecode.RuntimeBytecodeTests.warm

    def setUp(self):
        test_runtime_bytecode.RuntimeBytecodeTests.setUp(self)
        self.sdk = self.root / "sdk"
        self.sdk.mkdir()
        self.enterContext(patch.object(sys, "base_prefix", str(self.sdk)))
        self.enterContext(
            patch.object(sys, "executable", str(self.runtime / "bin" / "python"))
        )
        self.enterContext(
            patch.object(sys, "_base_executable", str(self.sdk / "bin" / "python3.13"))
        )
        self.links = {}
        self.overrides = {}
        for name, target in SDK_LINKS:
            path = self.sdk / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"mock link")
            (path.parent / target).write_bytes(
                b"sealed installed target: " + target.encode()
            )
            self.links[path] = target
        for name, target in (
            ("bin/python", str(self.sdk / "bin" / "python3.13")),
            ("bin/python3", "python"),
            ("bin/python3.13", "python"),
        ):
            path = self.runtime / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"mock link")
            self.links[path] = target
        original_lstat, original_resolve, original_stat = (
            Path.lstat,
            Path.resolve,
            Path.stat,
        )
        self.original_lstat = original_lstat

        def lstat(path):
            value = original_lstat(path)
            fields = {
                name: getattr(value, name)
                for name in (
                    "st_mode",
                    "st_ino",
                    "st_dev",
                    "st_nlink",
                    "st_size",
                    "st_mtime",
                    "st_ctime",
                    "st_mtime_ns",
                    "st_ctime_ns",
                )
            }
            if path in self.links:
                fields.update(
                    st_mode=stat.S_IFLNK | 0o777, st_size=len(self.links[path])
                )
            fields.update(self.overrides.get(path, {}))
            return types.SimpleNamespace(**fields)

        def resolve(path, **kwargs):
            visited = set()
            while path in self.links:
                if path in visited:
                    raise OSError("mock cycle")
                visited.add(path)
                target = Path(self.links[path])
                path = target if target.is_absolute() else path.parent / target
            return original_resolve(path, **kwargs)

        def mock_stat(path, *, follow_symlinks=True):
            if follow_symlinks and path in self.links:
                path = resolve(path, strict=True)
            value = original_stat(path, follow_symlinks=follow_symlinks)
            if path not in self.overrides:
                return value
            fields = {
                name: getattr(value, name)
                for name in (
                    "st_mode",
                    "st_ino",
                    "st_dev",
                    "st_nlink",
                    "st_size",
                    "st_mtime",
                    "st_ctime",
                    "st_mtime_ns",
                    "st_ctime_ns",
                )
            }
            fields.update(self.overrides[path])
            return types.SimpleNamespace(**fields)

        self.enterContext(patch.object(Path, "lstat", lstat))
        self.enterContext(patch.object(Path, "stat", mock_stat))
        self.enterContext(
            patch.object(Path, "is_symlink", lambda path: path in self.links)
        )
        self.enterContext(patch.object(Path, "resolve", resolve))
        self.enterContext(
            patch("runtime_links.os.readlink", lambda path: self.links[Path(path)])
        )
        self.policy = DarwinRuntimeLinks(
            self.sdk, self.runtime, self.sdk / "bin" / "python3.13", ARCHIVE_SHA256
        )
        self.roots = [str(self.runtime), str(self.sdk)]

    def start(self):
        return RuntimeGuard(
            sys.executable,
            {"version": sys.version, "runtime_roots": self.roots},
            self.output,
            {"runtime": runtime_input_hashes(self.roots, self.policy), **self.external},
            lambda: dict(self.external),
            link_policy=self.policy,
        )

    def test_exact_publisher_and_source_venv_graph_preserves_raw_metadata_and_content(
        self,
    ):
        guard = self.start()
        links = guard.current["links"]
        self.assertEqual(len(links[str(self.sdk)]), 9)
        self.assertEqual(
            set(links[str(self.runtime)]),
            {"bin/python", "bin/python3", "bin/python3.13"},
        )
        for root, entries in links.items():
            for name, record in entries.items():
                path = Path(root) / name
                self.assertEqual(record["path"], str(path))
                self.assertEqual(record["raw_target"], self.links[path])
                self.assertEqual(record["lstat"]["mode"], stat.S_IFLNK | 0o777)
                self.assertEqual(
                    record["lstat"]["inode"], self.original_lstat(path).st_ino
                )
                target = Path(record["target_root"]) / record["target_name"]
                self.assertEqual(
                    record["target"]["sha256"],
                    hashlib.sha256(target.read_bytes()).hexdigest(),
                )
                self.assertIn(
                    record["target_name"], guard.current["files"][record["target_root"]]
                )
                self.assertNotIn(name, guard.current["files"][root])
        self.warm(guard)
        folder = self.begin(guard, "C", True, 1)
        guard.after_row("C", True, 1, folder)
        guard.final()
        initial = json.loads((self.output / "runtime-initial.json").read_text())
        self.assertEqual(initial["state"]["links"], links)

    def test_publisher_base_alias_is_an_exact_absolute_association_not_canonicalized_raw(
        self,
    ):
        base = self.sdk / "bin" / "python3"
        self.links[self.runtime / "bin" / "python"] = str(base)
        self.policy = DarwinRuntimeLinks(self.sdk, self.runtime, base, ARCHIVE_SHA256)
        guard = self.start()
        self.assertEqual(
            guard.current["links"][str(self.runtime)]["bin/python"]["raw_target"],
            str(base),
        )
        self.warm(guard)
        guard.final()

    def test_missing_expected_link_even_if_replaced_with_regular_file_is_fatal(self):
        del self.links[self.sdk / "bin" / "idle3"]
        with self.assertRaisesRegex(RuntimeError, "missing runtime links"):
            self.start()

    def test_extra_initial_link_is_not_an_allowlist(self):
        extra = self.runtime / "extra"
        extra.write_bytes(b"mock link")
        self.links[extra] = "module.py"
        with self.assertRaisesRegex(RuntimeError, "unexpected runtime link"):
            self.start()

    def test_absolute_sdk_link_is_rejected_even_to_the_expected_regular_target(self):
        self.links[self.sdk / "bin" / "python"] = str(self.sdk / "bin" / "python3.13")
        with self.assertRaisesRegex(RuntimeError, "raw link target"):
            self.start()

    def test_lexically_different_same_target_is_rejected(self):
        self.links[self.sdk / "bin" / "idle3"] = "./idle3.13"
        with self.assertRaisesRegex(RuntimeError, "raw link target"):
            self.start()

    def test_escape_from_declared_sdk_is_not_a_venv_exemption(self):
        self.links[self.runtime / "bin" / "python"] = str(
            Path(sys._base_executable).parent.parent.parent / "other"
        )
        with self.assertRaisesRegex(RuntimeError, "raw link target"):
            runtime_input_hashes(self.roots, self.policy)

    def test_cycle_is_rejected_without_following_it(self):
        self.links[self.sdk / "bin" / "idle3"] = "idle3"
        with self.assertRaisesRegex(RuntimeError, "raw link target"):
            runtime_input_hashes(self.roots, self.policy)

    def test_dangling_regular_target_is_fatal(self):
        (self.sdk / "bin" / "idle3.13").unlink()
        with self.assertRaisesRegex(RuntimeError, "not sealed regular"):
            self.start()

    def test_directory_link_target_is_rejected_without_traversal(self):
        target = self.sdk / "bin" / "idle3.13"
        target.unlink()
        target.mkdir()
        with self.assertRaisesRegex(RuntimeError, "not sealed regular"):
            self.start()

    def test_unexpected_directory_link_is_not_traversed(self):
        alias = self.runtime / "directory-alias"
        alias.write_bytes(b"mock link")
        self.links[alias] = str(self.sdk)
        original = Path.iterdir

        def iterdir(path):
            self.assertNotEqual(path, alias, "directory link was traversed")
            return original(path)

        with patch.object(Path, "iterdir", iterdir):
            with self.assertRaisesRegex(RuntimeError, "unexpected runtime link"):
                self.start()

    def test_junction_is_never_an_allowed_link(self):
        junction = self.sdk / "bin" / "python"
        with patch.object(Path, "is_junction", lambda path: path == junction):
            with self.assertRaisesRegex(RuntimeError, "runtime junction"):
                self.start()

    def test_hardlinked_regular_input_is_rejected(self):
        self.overrides[self.source] = {"st_nlink": 2}
        with self.assertRaisesRegex(RuntimeError, "type/hardlink"):
            self.start()

    def test_hardlinked_symbolic_link_is_rejected(self):
        self.overrides[self.sdk / "bin" / "idle3"] = {"st_nlink": 2}
        with self.assertRaisesRegex(RuntimeError, "runtime link hardlink"):
            self.start()

    def test_link_change_between_hash_api_and_constructor_is_rejected(self):
        hashes = runtime_input_hashes(self.roots, self.policy)
        self.overrides[self.sdk / "bin" / "idle3"] = {"st_ino": 123}
        with self.assertRaisesRegex(RuntimeError, "between input hashes"):
            RuntimeGuard(
                sys.executable,
                {"version": sys.version, "runtime_roots": self.roots},
                self.output,
                {"runtime": hashes, **self.external},
                lambda: dict(self.external),
                link_policy=self.policy,
            )

    def test_same_bytes_target_replacement_during_warmup_is_rejected(self):
        guard = self.start()
        folder = self.begin(guard)
        target = self.sdk / "bin" / "python3.13"
        self.overrides[target] = {"st_ino": 123}
        with self.assertRaisesRegex(RuntimeError, "link/target changed"):
            guard.after_row("C", False, "WA", folder)

    def test_link_metadata_change_is_fatal_in_wa(self):
        guard = self.start()
        folder = self.begin(guard)
        self.overrides[self.sdk / "bin" / "idle3"] = {"st_mode": stat.S_IFLNK | 0o775}
        with self.assertRaisesRegex(RuntimeError, "link/target changed"):
            guard.after_row("C", False, "WA", folder)

    def test_link_metadata_change_is_fatal_in_wb(self):
        guard = self.start()
        folder = self.begin(guard)
        guard.after_row("C", False, "WA", folder)
        folder = self.begin(guard, "D", False, "WB")
        self.overrides[self.sdk / "bin" / "idle3"] = {"st_mode": stat.S_IFLNK | 0o775}
        with self.assertRaisesRegex(RuntimeError, "link/target changed"):
            guard.after_row("D", False, "WB", folder)

    def test_ancestor_identity_change_during_warmup_is_fatal(self):
        guard = self.start()
        folder = self.begin(guard)
        self.overrides[self.sdk / "bin"] = {"st_ino": 123}
        with self.assertRaisesRegex(RuntimeError, "ancestor changed"):
            guard.after_row("C", False, "WA", folder)

    def test_ancestor_changed_to_link_cannot_hide_a_subtree(self):
        guard = self.start()
        self.links[self.sdk / "bin"] = str(self.root / "outside")
        with self.assertRaisesRegex(RuntimeError, "unexpected runtime link"):
            self.begin(guard)

    def test_link_metadata_change_after_wb_is_fatal_to_measured_and_final_seals(self):
        guard = self.start()
        self.warm(guard)
        folder = self.begin(guard, "C", True, 1)
        self.overrides[self.sdk / "bin" / "idle3"] = {"st_mtime_ns": 10}
        with self.assertRaisesRegex(RuntimeError, "measured runtime/input changed"):
            guard.after_row("C", True, 1, folder)
        with self.assertRaisesRegex(RuntimeError, "final runtime/input seal differs"):
            guard.final()

    def test_policy_does_not_weaken_nested_filename_or_source_proof(self):
        guard = self.start()
        folder = self.begin(guard)
        code = compile(
            self.source.read_bytes(),
            str(self.source),
            "exec",
            dont_inherit=True,
            optimize=0,
        )
        changed = code.replace(
            co_consts=tuple(
                value.replace(co_filename="other.py")
                if isinstance(value, types.CodeType)
                else value
                for value in code.co_consts
            )
        )
        self.write_cache(code=changed)
        with self.assertRaisesRegex(RuntimeError, "filename/deep code"):
            guard.after_row("C", False, "WA", folder)

    def test_policy_preserves_stale_cache_bytes_and_final_evidence_seal(self):
        self.write_cache(stale=True)
        stale = self.cache.read_bytes()
        guard = self.start()
        self.warm(guard)
        initial = (
            self.output
            / "runtime-initial"
            / "after"
            / "0"
            / self.cache.relative_to(self.runtime)
        )
        self.assertEqual(initial.read_bytes(), stale)
        initial.write_bytes(b"tampered")
        with self.assertRaisesRegex(RuntimeError, "audit evidence changed"):
            guard.final()

    def test_policy_never_executes_source_and_rejects_late_source_mutation(self):
        self.source.write_bytes(b'raise AssertionError("must not execute")\n')
        guard = self.start()
        self.warm(guard)
        self.source.write_bytes(b"late change")
        with self.assertRaisesRegex(RuntimeError, "final runtime/input seal differs"):
            guard.final()

    def test_new_hash_api_with_default_none_rejects_links(self):
        with self.assertRaisesRegex(RuntimeError, "symlink/junction"):
            runtime_input_hashes(self.roots)

    def test_wrong_compiler_base_cannot_borrow_the_sdk_exemption(self):
        with patch.object(sys, "_base_executable", str(self.source)):
            with self.assertRaisesRegex(
                RuntimeError, "compiler/base executable association"
            ):
                self.start()

    def test_outside_base_alias_cannot_borrow_the_sdk_exemption(self):
        outside = self.root / "outside-python"
        outside.write_bytes(b"mock link")
        self.links[outside] = str(self.sdk / "bin" / "python3.13")
        with patch.object(sys, "_base_executable", str(outside)):
            with self.assertRaisesRegex(
                RuntimeError, "compiler/base executable association"
            ):
                self.start()

    def test_free_threaded_compiler_is_not_the_normal_archive_profile(self):
        with patch.object(sys, "abiflags", "t", create=True):
            with self.assertRaisesRegex(
                RuntimeError, "compiler/base executable association"
            ):
                self.start()

    def test_wrong_archive_or_arbitrary_base_executable_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "unsupported publisher archive"):
            DarwinRuntimeLinks(
                self.sdk, self.runtime, self.sdk / "bin" / "python3.13", "wrong"
            )
        with self.assertRaisesRegex(RuntimeError, "unsupported exact uv base"):
            DarwinRuntimeLinks(self.sdk, self.runtime, self.source, ARCHIVE_SHA256)

    def test_regular_target_changed_after_worker_read_is_rejected(self):
        original = Path.read_bytes
        target = self.sdk / "bin" / "idle3.13"

        def read(path):
            data = original(path)
            if path == target:
                self.overrides[target] = {"st_ino": 123}
            return data

        with patch.object(Path, "read_bytes", read):
            with self.assertRaisesRegex(RuntimeError, "changed during snapshot"):
                self.start()

    def test_policy_scans_overlap_four_regular_reads_and_join_workers_on_failure(self):
        original = Path.read_bytes
        barrier = threading.Barrier(4)
        lock = threading.Lock()
        workers = set()
        calls = 0

        def read(path):
            nonlocal calls
            with lock:
                calls += 1
                first_batch = calls <= 4
                workers.add(threading.current_thread())
            if first_batch:
                barrier.wait(timeout=5)
            return original(path)

        with patch.object(Path, "read_bytes", read):
            hashes = runtime_input_hashes(self.roots, self.policy)
        self.assertEqual(len(workers), 4)
        self.assertTrue(all(not worker.is_alive() for worker in workers))
        self.assertEqual(
            hashes[str(self.runtime)]["module.py"],
            hashlib.sha256(self.source.read_bytes()).hexdigest(),
        )
        workers.clear()

        def fail(path):
            with lock:
                workers.add(threading.current_thread())
            raise OSError("test read failure")

        with patch.object(Path, "read_bytes", fail):
            with self.assertRaisesRegex(OSError, "test read failure"):
                runtime_input_hashes(self.roots, self.policy)
        self.assertTrue(all(not worker.is_alive() for worker in workers))

    def test_post_wb_raw_target_change_is_rejected_even_to_same_file(self):
        guard = self.start()
        self.warm(guard)
        self.links[self.sdk / "bin" / "idle3"] = "./idle3.13"
        with self.assertRaisesRegex(RuntimeError, "raw link target"):
            guard.final()

    def test_link_disappearing_during_command_is_fatal(self):
        guard = self.start()
        folder = self.begin(guard)
        del self.links[self.sdk / "bin" / "idle3"]
        with self.assertRaisesRegex(RuntimeError, "missing runtime links"):
            guard.after_row("C", False, "WA", folder)


class RuntimeInputHashesTests(unittest.TestCase):
    write_cache = test_runtime_bytecode.RuntimeBytecodeTests.write_cache
    begin = test_runtime_bytecode.RuntimeBytecodeTests.begin
    warm = test_runtime_bytecode.RuntimeBytecodeTests.warm
    setUp = test_runtime_bytecode.RuntimeBytecodeTests.setUp

    def test_link_free_hash_api_and_explicit_none_keep_original_state_and_warmups(self):
        self.write_cache(stale=True)
        hashes = runtime_input_hashes([str(self.runtime)])
        self.assertEqual(
            hashes[str(self.runtime)],
            {
                path.relative_to(self.runtime).as_posix(): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in self.runtime.rglob("*")
                if path.is_file()
            },
        )
        guard = RuntimeGuard(
            sys.executable,
            {"version": sys.version, "runtime_roots": [str(self.runtime)]},
            self.output,
            {"runtime": hashes, **self.external},
            lambda: dict(self.external),
            link_policy=None,
        )
        self.assertEqual(set(guard.current), {"files", "directories", "inputs"})
        self.warm(guard)
        guard.final()


if __name__ == "__main__":
    unittest.main()
