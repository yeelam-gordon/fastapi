"""Supervisor integration with fake children/libproc on Windows; no launches."""

import ast
import ctypes
import importlib.util
import io
import json
import os
import subprocess
import sys
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import owned_process as owned

BASELINE = (
    Path(__file__).resolve().parents[3]
    / "worktrees"
    / "hosted-nvme-refs-20261110"
    / "Generated Files"
    / "arm-build"
    / "hosted-nvme-refs-screen"
    / "owned_process.py"
)


class GuardianTests(unittest.TestCase):
    def setUp(self):
        self.root = (
            Path(__file__).resolve().parent / "mock-evidence" / self._testMethodName
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self.progress = self.root / "stdout.actual-process.json"
        self.progress.unlink(missing_ok=True)
        self.expected = Path(sys.executable).resolve(strict=True)
        self.raw_image = str(self.expected.parent) + "\\\\.\\\\" + self.expected.name
        self.child = Mock(spec=subprocess.Popen)
        self.child.pid = 4321
        self.child.returncode = None
        self.child.poll.return_value = None
        self.child.wait.side_effect = self.wait_child
        self.events = []
        self.library = Mock()
        self.library.proc_pidinfo.side_effect = self.write_bsd
        self.library.proc_pidpath.side_effect = self.write_path
        self.adapter = None
        self.capture_error = None
        self.raced = False
        self.spec = {
            "argv": [str(self.expected), "-c", "never launched"],
            "stdout": str(self.root / "stdout.log"),
            "stderr": str(self.root / "stderr.log"),
            "timeout": 5,
            "native_clock": True,
            "job": "mock-job",
        }
        self.real_spec_loader = importlib.util.spec_from_file_location
        self.addCleanup(sys.modules.pop, "owned_darwin_identity", None)

    def wait_child(self, *, timeout):
        self.assertGreater(timeout, 0)
        self.assertLessEqual(timeout, 5)
        if self.spec["native_clock"]:
            self.assertTrue(self.progress.exists())
        self.events.append("wait")
        self.child.returncode = 0
        return 0

    def write_bsd(self, pid, flavor, argument, buffer, size):
        self.assertEqual((pid, flavor, argument, size), (4321, 3, 0, 136))
        self.events.append("bsd")
        information = self.adapter.ProcBsdInfo(
            pbi_pid=4321,
            pbi_ppid=os.getpid(),
            pbi_start_tvsec=1_699_999_999,
            pbi_start_tvusec=123456,
        )
        if self.raced and self.events.count("bsd") == 2:
            information.pbi_start_tvusec += 1
        ctypes.memmove(buffer, ctypes.byref(information), size)
        return size

    def write_path(self, pid, buffer, size):
        self.assertEqual((pid, size), (4321, 4096))
        self.events.append("path")
        encoded = self.raw_image.encode("utf-8")
        ctypes.memmove(buffer, encoded + b"\0", len(encoded) + 1)
        return len(encoded)

    def load_adapter(self, name, location):
        self.assertEqual(name, "owned_darwin_identity")
        self.assertEqual(
            location, Path(owned.__file__).resolve().with_name("darwin_identity.py")
        )
        self.assertTrue(location.is_absolute())
        module_spec = self.real_spec_loader(name, location)
        execute = module_spec.loader.exec_module

        def execute_with_fake_native(module):
            self.assertIs(sys.modules[name], module)
            execute(module)
            self.adapter = module
            module._load_libproc = Mock(return_value=self.library)
            if self.capture_error is not None:
                module._load_libproc.side_effect = self.capture_error
            module.capture_child_identity = Mock(wraps=module.capture_child_identity)

        module_spec.loader.exec_module = execute_with_fake_native
        return module_spec

    def supervise(self, *, windows=False):
        output = io.StringIO()
        spawn = Mock(return_value=self.child)
        with (
            patch.object(owned, "_WINDOWS", windows),
            patch.object(owned.sys, "platform", "win32" if windows else "darwin"),
            patch.object(owned.sys, "stdin", io.StringIO(json.dumps(self.spec))),
            patch.object(
                owned,
                "subprocess",
                SimpleNamespace(Popen=spawn, TimeoutExpired=subprocess.TimeoutExpired),
            ),
            patch.object(
                owned.importlib.util,
                "spec_from_file_location",
                side_effect=self.load_adapter,
            ) as load,
            patch.object(time, "time_ns", return_value=1_700_000_000_123_456_789),
            redirect_stdout(output),
        ):
            owned._supervise()
        spawn.assert_called_once()
        self.assertEqual(spawn.call_args.args, (self.spec["argv"],))
        self.load = load
        result = json.loads(output.getvalue())
        (self.root / "supervisor-result.json").write_text(
            output.getvalue(), encoding="utf-8"
        )
        return result

    def receipt(self, result, *, survivors):
        process = Mock(pid=9876, returncode=0)
        process.poll.return_value = 0
        process.communicate.return_value = (json.dumps(result), "")
        with (
            patch.object(owned, "_WINDOWS", False),
            patch.object(owned.subprocess, "Popen", return_value=process) as spawn,
            patch.object(owned, "_group_alive", side_effect=[survivors, False, False]),
            patch.object(owned.os, "killpg", create=True) as kill,
            patch.object(owned.signal, "SIGKILL", 9, create=True),
        ):
            receipt = owned.run_owned(
                self.spec["argv"],
                cwd=self.root,
                env={},
                stdout_path=self.spec["stdout"],
                stderr_path=self.spec["stderr"],
                timeout=5,
                native_clock=self.spec["native_clock"],
            )
        self.assertEqual(spawn.call_args.args[0][1:3], ["-I", "-B"])
        self.assertTrue(spawn.call_args.kwargs["start_new_session"])
        process.communicate.assert_called_once()
        self.assertEqual(process.communicate.call_args.kwargs["timeout"], 15)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close.assert_called_once()
        if survivors:
            kill.assert_called_once_with(9876, 9)
        else:
            kill.assert_not_called()
        self.assertTrue(receipt.cleanup_complete)
        return receipt

    def test_native_darwin_adapter_child_wait_stdout_sidecar_and_receipt(self):
        result = self.supervise()
        expected = {
            "pid": 4321,
            "parent_pid": os.getpid(),
            "executable": str(self.expected),
            "observed_executable": self.raw_image,
            "start_unix_interval_us": [1_699_999_999_123_456, 1_699_999_999_123_457],
        }
        self.assertEqual(result["actual_process"], expected)
        self.assertEqual(
            json.loads(self.progress.read_text(encoding="utf-8")), expected
        )
        self.assertNotEqual(expected["observed_executable"], expected["executable"])
        self.assertNotIn("birth_filetime", expected)
        self.assertFalse(self.progress.with_suffix(".new").exists())
        self.assertEqual(self.events, ["bsd", "path", "bsd", "wait"])
        self.adapter.capture_child_identity.assert_called_once_with(
            self.child, self.spec["argv"][0]
        )
        self.child.wait.assert_called_once()
        receipt = self.receipt(result, survivors=False)
        self.assertTrue(receipt.succeeded, receipt)
        self.assertEqual(receipt.actual_process, expected)
        self.assertEqual(receipt.native_start_ns, result["native_start_ns"])
        self.assertGreaterEqual(receipt.native_end_ns, receipt.native_start_ns)

    def test_capture_error_is_not_success_and_owned_family_is_cleaned(self):
        self.capture_error = OSError("fake libproc capture failure")
        result = self.supervise()
        self.assertEqual(result["error"], "OSError: fake libproc capture failure")
        self.assertIsNone(result["returncode"])
        self.assertNotIn("actual_process", result)
        self.assertFalse(self.progress.exists())
        self.child.wait.assert_not_called()
        receipt = self.receipt(result, survivors=True)
        self.assertFalse(receipt.succeeded)
        self.assertIsNone(receipt.actual_process)
        self.assertTrue(receipt.ownership_established)
        self.assertEqual(receipt.errors, ("OSError: fake libproc capture failure",))

    def test_raced_start_is_rejected_without_pid_fallback(self):
        self.raced = True
        result = self.supervise()
        self.assertEqual(
            result["error"], "IdentityError: BSD process start changed during capture"
        )
        self.assertNotIn("actual_process", result)
        self.assertFalse(self.progress.exists())
        self.child.wait.assert_not_called()
        self.assertFalse(self.receipt(result, survivors=True).succeeded)

    def test_missing_adapter_is_rejected_and_cleaned(self):
        with patch.object(
            self, "load_adapter", side_effect=FileNotFoundError("missing adapter")
        ):
            result = self.supervise()
        self.assertEqual(result["error"], "FileNotFoundError: missing adapter")
        self.assertNotIn("actual_process", result)
        self.assertFalse(self.progress.exists())
        self.child.wait.assert_not_called()
        self.assertFalse(self.receipt(result, survivors=True).succeeded)

    def test_nonnative_darwin_bootstrap_does_not_load_adapter(self):
        self.spec["native_clock"] = False
        result = self.supervise()
        self.load.assert_not_called()
        self.child.wait.assert_called_once()
        self.assertEqual(self.events, ["wait"])
        self.assertNotIn("actual_process", result)
        self.assertNotIn("native_start_ns", result)
        self.assertNotIn("error", result)
        self.assertFalse(self.progress.exists())
        receipt = self.receipt(result, survivors=False)
        self.assertTrue(receipt.succeeded, receipt)
        self.assertIsNone(receipt.native_start_ns)
        self.assertIsNone(receipt.native_end_ns)

    def test_sidecar_write_error_cannot_produce_success(self):
        with patch.object(owned.os, "replace", side_effect=OSError("sidecar failure")):
            result = self.supervise()
        self.assertEqual(result["error"], "OSError: sidecar failure")
        self.assertIn("actual_process", result)
        self.assertFalse(self.progress.exists())
        self.child.wait.assert_not_called()
        self.assertFalse(self.receipt(result, survivors=True).succeeded)
        staged = self.progress.with_suffix(".new")
        self.assertTrue(staged.exists())
        staged.unlink()

    def test_windows_provenance_remains_unconditional(self):
        self.spec["native_clock"] = False
        api = Mock()
        api.OpenJobObjectW.return_value = 123
        module = SimpleNamespace(
            popen_identity=Mock(
                return_value={"pid": 4321, "birth_filetime": 123456, "image": "mock"}
            )
        )
        module_spec = SimpleNamespace(loader=Mock())
        with (
            patch.object(owned, "_windows", return_value=api),
            patch.object(self, "load_adapter", return_value=module_spec) as load,
            patch.object(owned.importlib.util, "module_from_spec", return_value=module),
        ):
            result = self.supervise(windows=True)
        self.assertEqual(load.call_args.args[0], "owned_cli_identity")
        module.popen_identity.assert_called_once_with(self.child)
        api.AssignProcessToJobObject.assert_called_once_with(
            123, api.GetCurrentProcess.return_value
        )
        api.CloseHandle.assert_called_once_with(123)
        self.assertEqual(
            result["actual_process"], json.loads(self.progress.read_text("utf-8"))
        )
        self.assertNotIn("error", result)
        self.child.wait.assert_called_once()

    def test_only_source_delta_is_dataclass_conversion_and_darwin_branch(self):
        original = ast.parse(BASELINE.read_text(encoding="utf-8"))
        candidate = ast.parse(Path(owned.__file__).read_text(encoding="utf-8"))
        imports = [
            node
            for node in candidate.body
            if isinstance(node, ast.ImportFrom) and node.module == "dataclasses"
        ]
        imports[0].names = [name for name in imports[0].names if name.name != "asdict"]
        branches = [
            node
            for node in ast.walk(candidate)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Name)
            and node.test.id == "_WINDOWS"
            and len(node.orelse) == 1
            and isinstance(node.orelse[0], ast.If)
        ]
        self.assertEqual(len(branches), 1)
        self.assertEqual(
            ast.unparse(branches[0].orelse[0].test),
            "sys.platform == 'darwin' and spec.get('native_clock')",
        )
        branches[0].orelse = []
        self.assertEqual(ast.dump(candidate), ast.dump(original))


if __name__ == "__main__":
    unittest.main()
