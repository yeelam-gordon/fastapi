import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("checkout_screen", HERE / "screen.py")
screen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screen)


class ScreenTests(unittest.TestCase):
    def test_ordered_floors_and_nonfinite(self):
        pairs = screen.comparisons([2.543, 1.536, 1.321, 2.655])
        self.assertTrue(all(p["passes"] for p in pairs))
        self.assertEqual([p["pair"] for p in pairs], ["AB", "BA"])
        self.assertFalse(screen.comparisons([1, .9, .9, 1])[0]["passes"])
        self.assertFalse(screen.comparisons([10, 9.7, 9.7, 10])[0]["passes"])
        self.assertFalse(screen.comparisons([2, 1, 3, 2])[1]["passes"])
        with self.assertRaises(ValueError):
            screen.comparisons([1, float("nan"), 1, 1])

    def test_trace_worker_role_and_root_clock(self):
        events = [dict(event="exit", sid="root", code=0, t_abs=.4)]
        for i in range(4):
            events += [dict(event="child_start", sid="root", child_id=i,
                            argv=["git", "checkout--worker"]),
                       dict(event="child_exit", sid="root", child_id=i, code=0)]
        # A child command exit must not replace the root's independent exit clock.
        events.append(dict(event="exit", sid="root/child", code=0, t_abs=.2))
        self.assertEqual(screen.trace_summary(events, 4), dict(
            worker_launches=4, worker_successful_exits=4, trace2_exit_seconds=.4))
        bad = events[:-2] + [dict(event="child_exit", sid="root", child_id=3, code=1)]
        with self.assertRaises(ValueError):
            screen.trace_summary(bad, 4)
        with self.assertRaises(ValueError):
            screen.trace_summary(events, 1)
        self.assertEqual(screen.trace_summary(events[:1], 1)["worker_launches"], 0)
        events[1]["argv"] = ["git", "not-checkout--worker"]
        with self.assertRaises(ValueError):
            screen.trace_summary(events, 4)

    def test_complete_raw_blob_oracle(self):
        # Explicit project-local scratch; never use the system temporary directory.
        root = HERE / ("test-owned-" + uuid.uuid4().hex)
        root.mkdir()
        try:
            (root / ".git").mkdir()
            raw = b"hello\n"
            oid = hashlib.sha1(b"blob 6\0" + raw).hexdigest()
            tree = screen.parse_tree(f"100644 blob {oid}\ta.txt\0".encode())
            (root / "a.txt").write_bytes(raw)
            self.assertRegex(screen.verify_files(root, tree, False), "^[0-9a-f]{64}$")
            (root / "a.txt").write_bytes(b"hello\r\n")
            with self.assertRaises(ValueError):
                screen.verify_files(root, tree, False)
            (root / "a.txt").write_bytes(raw)
            (root / "extra").write_bytes(b"")
            with self.assertRaises(ValueError):
                screen.verify_files(root, tree, False)
            for mode, kind, name in (("120000", "blob", "link"),
                                     ("160000", "commit", "module"),
                                     ("100644", "blob", "../escape")):
                with self.assertRaises(ValueError):
                    screen.parse_tree(f"{mode} {kind} {oid}\t{name}\0".encode())
        finally:
            shutil.rmtree(root)

    def test_batch_requires_every_complete_blob_not_missing_or_truncated(self):
        blob = b"hello\n"
        oid = hashlib.sha1(b"blob 6\0" + blob).hexdigest()
        raw = f"{oid} blob 6\n".encode() + blob + b"\n"
        screen.verify_batch(raw, [oid])
        for bad in (f"{oid} missing\n".encode(), raw[:-1], raw + b"extra",
                    raw.replace(b"hello", b"HELLO")):
            with self.assertRaises((ValueError, IndexError)):
                screen.verify_batch(bad, [oid])

    def test_failure_is_static_without_exception_or_raw_inputs(self):
        class FakeOwned:
            code = 123

            def __init__(self, _):
                pass
        root = HERE / ("test-owned-" + uuid.uuid4().hex)
        root.mkdir()
        try:
            with patch.dict(screen.os.environ, GITHUB_ACTIONS="true",
                            RUNNER_ENVIRONMENT="github-hosted", RUNNER_ARCH="ARM64"), \
                    patch.object(screen, "Owned", FakeOwned), patch.object(
                    screen, "native_python", side_effect=RuntimeError(
                        "TOKEN secret/config PID=123 https://private.invalid/path")):
                self.assertEqual(screen.screen(root, root, root), 1)
            value = json.loads((root / "stage.json").read_text())
            self.assertEqual(value, dict(schema=1, stage="runtime",
                                         category="runtime", native_code=123))
            self.assertFalse((root / "result.json").exists())
        finally:
            shutil.rmtree(root)

    def test_binary_identity_is_bounded_and_rejects_nonarm_mac(self):
        data = bytearray(128)
        data[:2] = b"MZ"
        screen.struct.pack_into("<I", data, 60, 64)
        data[64:68] = b"PE\0\0"
        screen.struct.pack_into("<H", data, 68, 0xAA64)
        class Binary:
            def read_bytes(self):
                return bytes(data)
        with patch.object(screen, "os", SimpleNamespace(name="nt")):
            self.assertEqual(screen.binary_identity(Binary())["machine"], "arm64")
            screen.struct.pack_into("<H", data, 68, 0x14C)
            with self.assertRaises(ValueError):
                screen.binary_identity(Binary())
        data = bytearray(b"\xcf\xfa\xed\xfe" + b"\0" * 28)
        screen.struct.pack_into("<I", data, 4, 0x100000C)
        with patch.object(screen, "os", SimpleNamespace(name="posix")):
            self.assertEqual(screen.binary_identity(Binary())["slices"], ["arm64"])
            screen.struct.pack_into("<I", data, 4, 0x1000007)
            with self.assertRaises(ValueError):
                screen.binary_identity(Binary())

    def test_version_whitelist_allows_platform_git_not_private_text(self):
        for value in (b"git version 2.51.0.windows.1\n",
                      b"git version 2.39.3 (Apple Git-146)\n", b"git version 2.56.0.vfs.1\n"):
            self.assertEqual(screen.safe_version(value), value.decode().strip())
        for value in (b"git version 2.51.0\nTOKEN=private",
                      b"git version 2.51.0 https://private.invalid/repo",
                      b"git version 2.51.0 (Apple Git-private/path)"):
            with self.assertRaises(ValueError):
                screen.safe_version(value)

    def test_original_guardian_hash(self):
        self.assertEqual(hashlib.sha256(
            (HERE.parent / "hobl-complete-ci" / "owned_process.py").read_bytes()
        ).hexdigest(), screen.GUARD_SHA)

    def test_named_gate_has_static_category_without_exception_text(self):
        with self.assertRaises(screen.GateFailure) as caught:
            screen.binary_identity(SimpleNamespace(
                read_bytes=lambda: (_ for _ in ()).throw(
                    OSError("private/path TOKEN=secret"))))
        self.assertEqual(caught.exception.category, "binary")
        self.assertEqual(str(caught.exception), "")


if __name__ == "__main__":
    unittest.main()
