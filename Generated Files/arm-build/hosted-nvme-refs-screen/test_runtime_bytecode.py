import hashlib
import importlib.util
import json
import marshal
import os
import shutil
import struct
import sys
import threading
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from runtime_bytecode import RuntimeGuard


class RuntimeBytecodeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent / (
            "test-work-runtime-" + uuid.uuid4().hex
        )
        self.runtime, self.output = self.root / "runtime", self.root / "evidence"
        self.runtime.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root)
        self.source = self.runtime / "module.py"
        self.source.write_bytes(
            b"def outer():\n    def inner():\n        return (-0.0, 'value')\n    return inner\n"
        )
        self.cache = Path(
            importlib.util.cache_from_source(str(self.source), optimization="")
        )
        self.external = {"tool": "sealed"}
        self.enterContext(patch.object(sys, "prefix", str(self.runtime)))
        self.enterContext(patch.object(sys, "base_prefix", str(self.runtime)))

    def write_cache(self, *, stale=False, filename=None, code=None, source=None):
        source = source or self.source
        cache = Path(importlib.util.cache_from_source(str(source), optimization=""))
        metadata = source.stat()
        header = importlib.util.MAGIC_NUMBER + struct.pack(
            "<III",
            0,
            (int(metadata.st_mtime) - int(stale)) & 0xFFFFFFFF,
            metadata.st_size,
        )
        code = code or compile(
            source.read_bytes(),
            filename or str(source),
            "exec",
            dont_inherit=True,
            optimize=0,
        )
        cache.parent.mkdir(exist_ok=True)
        cache.write_bytes(header + marshal.dumps(code))

    def test_scan_overlaps_four_reads_and_preserves_every_record(self):
        payloads = {self.source: self.source.read_bytes()}
        for index in range(3):
            path = self.runtime / f"payload-{index}.txt"
            payloads[path] = str(index).encode()
            path.write_bytes(payloads[path])
        barrier = threading.Barrier(4)
        original = Path.read_bytes

        def read(path):
            barrier.wait(timeout=5)
            return original(path)

        guard = object.__new__(RuntimeGuard)
        guard.roots = {str(self.runtime): self.runtime.resolve()}
        guard.inputs = lambda: dict(self.external)
        with patch.object(Path, "read_bytes", read):
            state, raw = guard.scan()
        self.assertEqual(
            {
                name: value["sha256"]
                for name, value in state["files"][str(self.runtime)].items()
            },
            {
                path.name: hashlib.sha256(data).hexdigest()
                for path, data in payloads.items()
            },
        )
        self.assertEqual(state["directories"], {str(self.runtime): []})
        self.assertEqual(state["inputs"], self.external)
        self.assertEqual(raw, {str(self.runtime): {}})

    def test_scan_propagates_worker_read_failure(self):
        guard = object.__new__(RuntimeGuard)
        guard.roots = {str(self.runtime): self.runtime.resolve()}
        guard.inputs = lambda: self.fail(
            "Inputs must not be accepted after a read failure"
        )
        with patch.object(Path, "read_bytes", side_effect=OSError("test read failure")):
            with self.assertRaisesRegex(OSError, "test read failure"):
                guard.scan()

    def start(self):
        inputs = {
            "runtime": {
                str(self.runtime): {
                    path.relative_to(self.runtime).as_posix(): hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest()
                    for path in self.runtime.rglob("*")
                    if path.is_file()
                }
            },
            **self.external,
        }
        return RuntimeGuard(
            Path(sys.executable),
            {"version": sys.version, "runtime_roots": [str(self.runtime)]},
            self.output,
            inputs,
            lambda: dict(self.external),
        )

    def begin(self, guard, arm="C", measured=False, pair="WA"):
        folder = self.output / str(pair) / arm
        guard.before_row(arm, measured, pair, folder)
        return folder

    def warm(self, guard):
        first = self.begin(guard)
        self.write_cache()
        guard.after_row("C", False, "WA", first)
        second = self.begin(guard, "D", False, "WB")
        guard.after_row("D", False, "WB", second)

    def test_stale_cache_is_proved_retained_and_sealed_at_wb(self):
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
        proof = json.loads(
            (self.output / "WA" / "C" / "runtime-after.json").read_text()
        )
        association = proof["associations"][0]
        self.assertEqual(Path(association["raw_before"]).read_bytes(), stale)
        self.assertEqual(
            Path(association["raw_after"]).read_bytes(), self.cache.read_bytes()
        )
        self.assertEqual(association["filename"], str(self.source))
        self.assertTrue((self.output / "runtime-seal-after-WB.json").exists())
        folder = self.begin(guard, "C", True, 1)
        guard.after_row("C", True, 1, folder)
        guard.final()

    def test_measured_cannot_start_before_both_warmups(self):
        guard = self.start()
        with self.assertRaisesRegex(RuntimeError, "phase boundary"):
            self.begin(guard, "C", True, 1)
        with self.assertRaisesRegex(RuntimeError, "final runtime"):
            guard.final()

    def test_wb_may_add_another_proven_cache_before_complete_seal(self):
        later = self.runtime / "later.py"
        later.write_bytes(b"value = 7\n")
        guard = self.start()
        folder = self.begin(guard)
        self.write_cache()
        guard.after_row("C", False, "WA", folder)
        folder = self.begin(guard, "D", False, "WB")
        self.write_cache(source=later)
        guard.after_row("D", False, "WB", folder)
        proof = json.loads((folder / "runtime-after.json").read_text())
        self.assertEqual(proof["associations"][0]["source"], "later.py")
        guard.final()

    def test_code_proof_never_executes_the_sealed_module(self):
        self.source.write_bytes(b'raise AssertionError("module must not execute")\n')
        guard = self.start()
        self.warm(guard)
        guard.final()

    def test_valid_cache_replacement_is_never_an_exception(self):
        self.write_cache()
        guard = self.start()
        folder = self.begin(guard)
        self.write_cache()
        metadata = self.cache.stat()
        os.utime(
            self.cache, ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000_000)
        )
        with self.assertRaisesRegex(RuntimeError, "preserved valid"):
            guard.after_row("C", False, "WA", folder)

    def assert_bad_header(self, offset, replacement):
        guard = self.start()
        folder = self.begin(guard)
        self.write_cache()
        data = bytearray(self.cache.read_bytes())
        data[offset : offset + len(replacement)] = replacement
        self.cache.write_bytes(data)
        with self.assertRaisesRegex(RuntimeError, "magic/flags/timestamp/size"):
            guard.after_row("C", False, "WA", folder)
        self.assertTrue(
            (
                folder
                / "runtime-cache-outputs"
                / "after"
                / "0"
                / self.cache.relative_to(self.runtime)
            ).exists()
        )

    def test_wrong_magic_is_fatal(self):
        self.assert_bad_header(0, b"bad!")

    def test_hash_based_flags_are_not_default_outputs(self):
        self.assert_bad_header(4, struct.pack("<I", 3))

    def test_wrong_timestamp_is_fatal(self):
        self.assert_bad_header(8, b"\0\0\0\0")

    def test_wrong_source_size_is_fatal(self):
        self.assert_bad_header(12, b"\0\0\0\0")

    def test_changed_source_hash_is_fatal(self):
        guard = self.start()
        folder = self.begin(guard)
        self.source.write_bytes(b"changed = True\n")
        self.write_cache()
        with self.assertRaisesRegex(RuntimeError, "source changed"):
            guard.after_row("C", False, "WA", folder)

    def test_same_source_bytes_with_changed_metadata_are_fatal(self):
        guard = self.start()
        folder = self.begin(guard)
        metadata = self.source.stat()
        os.utime(
            self.source, ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000_000)
        )
        self.write_cache()
        with self.assertRaisesRegex(RuntimeError, "source changed"):
            guard.after_row("C", False, "WA", folder)

    def test_wrong_code_filename_is_fatal(self):
        guard = self.start()
        folder = self.begin(guard)
        self.write_cache(filename="other.py")
        with self.assertRaisesRegex(RuntimeError, "filename/deep code"):
            guard.after_row("C", False, "WA", folder)

    def test_nested_code_filename_cannot_hide_behind_top_level_equality(self):
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

    def test_changed_code_with_correct_filename_is_fatal(self):
        guard = self.start()
        folder = self.begin(guard)
        code = compile(
            b"answer = 99\n", str(self.source), "exec", dont_inherit=True, optimize=0
        )
        self.write_cache(code=code)
        with self.assertRaisesRegex(RuntimeError, "filename/deep code"):
            guard.after_row("C", False, "WA", folder)

    def test_trailing_bytes_are_not_a_stock_compiler_output(self):
        guard = self.start()
        folder = self.begin(guard)
        self.write_cache()
        self.cache.write_bytes(self.cache.read_bytes() + b"unexplained")
        with self.assertRaisesRegex(RuntimeError, "bytecode payload"):
            guard.after_row("C", False, "WA", folder)

    def test_cache_deletion_is_fatal(self):
        self.write_cache(stale=True)
        guard = self.start()
        folder = self.begin(guard)
        self.cache.unlink()
        with self.assertRaisesRegex(RuntimeError, "file deletion"):
            guard.after_row("C", False, "WA", folder)

    def test_non_cache_write_is_fatal(self):
        guard = self.start()
        folder = self.begin(guard)
        (self.runtime / "unexpected.txt").write_bytes(b"write")
        with self.assertRaisesRegex(RuntimeError, "non-cache runtime write"):
            guard.after_row("C", False, "WA", folder)

    def test_noncanonical_optimization_path_is_fatal(self):
        guard = self.start()
        folder = self.begin(guard)
        self.write_cache()
        self.cache.rename(self.cache.with_name("module.cpython-313.opt-1.pyc"))
        with self.assertRaisesRegex(RuntimeError, "noncanonical runtime cache"):
            guard.after_row("C", False, "WA", folder)

    def test_unsealed_source_cannot_authorize_cache(self):
        guard = self.start()
        folder = self.begin(guard)
        self.write_cache()
        self.cache.rename(self.cache.with_name("unknown.cpython-313.pyc"))
        with self.assertRaisesRegex(RuntimeError, "outside sealed root"):
            guard.after_row("C", False, "WA", folder)

    def test_runtime_symlink_is_fatal(self):
        guard = self.start()
        with patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "symlink/junction"):
                self.begin(guard)

    def test_runtime_root_rebinding_cannot_escape_sealed_root(self):
        guard = self.start()
        original_resolve = Path.resolve

        def rebind(path, **kwargs):
            return (
                self.root if path == self.runtime else original_resolve(path, **kwargs)
            )

        with patch.object(Path, "resolve", rebind):
            with self.assertRaisesRegex(RuntimeError, "root binding changed"):
                self.begin(guard)

    def test_nonruntime_input_mutation_is_fatal(self):
        guard = self.start()
        folder = self.begin(guard)
        self.external["tool"] = "changed"
        with self.assertRaisesRegex(RuntimeError, "nonruntime input"):
            guard.after_row("C", False, "WA", folder)

    def test_even_canonical_default_cache_write_is_fatal_after_wb(self):
        guard = self.start()
        self.warm(guard)
        folder = self.begin(guard, "C", True, 1)
        metadata = self.cache.stat()
        os.utime(
            self.cache, ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000_000)
        )
        with self.assertRaisesRegex(RuntimeError, "measured runtime/input changed"):
            guard.after_row("C", True, 1, folder)

    def test_final_audit_rejects_runtime_mutation_after_last_row(self):
        guard = self.start()
        self.warm(guard)
        self.source.write_bytes(b"changed_after_last_row = True\n")
        with self.assertRaisesRegex(RuntimeError, "final runtime/input seal differs"):
            guard.final()

    def test_initial_raw_cache_evidence_cannot_be_modified(self):
        self.write_cache(stale=True)
        guard = self.start()
        self.warm(guard)
        initial = (
            self.output
            / "runtime-initial"
            / "after"
            / "0"
            / self.cache.relative_to(self.runtime)
        )
        initial.write_bytes(b"tampered")
        with self.assertRaisesRegex(RuntimeError, "audit evidence changed"):
            guard.final()

    def test_different_compile_interpreter_identity_is_fatal(self):
        with self.assertRaisesRegex(RuntimeError, "exact target Python"):
            RuntimeGuard(
                Path(sys.executable),
                {"version": "different", "runtime_roots": [str(self.runtime)]},
                self.output,
                {},
                lambda: {},
            )


if __name__ == "__main__":
    unittest.main()
