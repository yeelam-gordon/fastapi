"""Bounded review proof; only these helpers' explicitly recorded PIDs are touched."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
import uuid
from unittest.mock import Mock, patch

PROTOCOL = Path(__file__).resolve().parents[2] / "protocol"
sys.path.insert(0, str(PROTOCOL))
import owned_process as owned
from test_owned_process import known_pid_alive

PYTHON = str(Path(sys.base_prefix) / "python.exe")


class ReviewProof(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / (".proof-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)

    def test_real_parent_death_kills_supervisor_target_and_grandchild(self):
        controller = subprocess.Popen(
            [PYTHON, "-I", str(Path(__file__).resolve()), "--controller",
             str(self.root.resolve())],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        pids = []
        try:
            deadline = time.monotonic() + 8
            marker = self.root / "family.json"
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(marker.exists(), "family did not start")
            pids = json.loads(marker.read_text())
            self.assertEqual(len(pids), 3)
            self.assertTrue(all(known_pid_alive(pid) for pid in pids))
            controller.terminate()
            controller.wait(timeout=5)
            deadline = time.monotonic() + 5
            while any(known_pid_alive(pid) for pid in pids):
                self.assertLess(time.monotonic(), deadline, pids)
                time.sleep(0.02)
        finally:
            if controller.poll() is None:
                controller.terminate()
                controller.wait(timeout=5)
            if not pids and (self.root / "family.json").exists():
                pids = json.loads((self.root / "family.json").read_text())
            for pid in pids:
                self.assertFalse(known_pid_alive(pid, terminate=True))

    def test_real_missing_executable_preserves_error(self):
        result = owned.run_owned(
            [str(self.root / "absent.exe")], cwd=self.root,
            env=os.environ.copy(), stdout_path=self.root / "out",
            stderr_path=self.root / "err", timeout=5,
        )
        self.assertFalse(result.succeeded, result)
        self.assertTrue(result.ownership_established, result)
        self.assertTrue(result.cleanup_complete, result)
        self.assertTrue(any("FileNotFoundError" in e for e in result.errors), result)

    def test_both_platform_timer_boundaries_include_cleanup(self):
        for windows in (True, False):
            with self.subTest(windows=windows):
                process = Mock(pid=123, returncode=0)
                process.poll.return_value = 0
                process.communicate.return_value = (
                    json.dumps(dict(owned=True, started=103.0,
                                    returncode=0, timed_out=False)), ""
                )
                job = Mock()
                job.alive.return_value = False
                with (
                    patch.object(owned, "_WINDOWS", windows),
                    patch.object(owned, "_Job", return_value=job),
                    patch.object(owned.subprocess, "Popen", return_value=process),
                    patch.object(owned, "_group_alive", return_value=False),
                    patch.object(owned.time, "perf_counter",
                                 side_effect=[100.0, 110.0, 112.0]),
                ):
                    result = owned.run_owned(
                        ["fixed"], cwd=self.root, env={},
                        stdout_path=self.root / "out",
                        stderr_path=self.root / "err", timeout=20,
                    )
                self.assertTrue(result.succeeded, result)
                self.assertEqual(result.infrastructure_wall, 3.0)
                self.assertEqual(result.command_wall, 9.0)

    def test_job_setup_double_failure_loses_original_error(self):
        api = Mock()
        api.CreateJobObjectW.return_value = 1
        api.SetInformationJobObject.side_effect = OSError("original setup failure")
        api.CloseHandle.side_effect = OSError("secondary close failure")
        with patch.object(owned, "_windows", return_value=api):
            with self.assertRaisesRegex(OSError, "secondary close failure"):
                owned._Job("mock-only")

    def test_pipe_close_failure_escapes_instead_of_preserving_receipt(self):
        process = Mock(pid=123, returncode=0)
        process.poll.return_value = 0
        process.communicate.return_value = (
            json.dumps(dict(owned=True, started=time.perf_counter(),
                            returncode=7, timed_out=False)), ""
        )
        process.stdin.close.side_effect = OSError("pipe close failed")
        job = Mock()
        job.alive.return_value = False
        with (
            patch.object(owned, "_WINDOWS", True),
            patch.object(owned, "_Job", return_value=job),
            patch.object(owned.subprocess, "Popen", return_value=process),
        ):
            with self.assertRaisesRegex(OSError, "pipe close failed"):
                owned.run_owned(
                    ["fixed"], cwd=self.root, env={},
                    stdout_path=self.root / "out",
                    stderr_path=self.root / "err", timeout=5,
                )
        process.stdout.close.assert_not_called()
        process.stderr.close.assert_not_called()


def helper(role, root):
    if role == "--controller":
        owned.run_owned(
            [PYTHON, "-I", str(Path(__file__).resolve()), "--family", str(root)],
            cwd=root, env=os.environ.copy(), stdout_path=root / "out",
            stderr_path=root / "err", timeout=30,
        )
    elif role == "--family":
        child = subprocess.Popen([PYTHON, "-I", "-c", "import time; time.sleep(30)"])
        pending = root / "pending.json"
        pending.write_text(json.dumps([os.getppid(), os.getpid(), child.pid]))
        pending.rename(root / "family.json")
        time.sleep(30)


if __name__ == "__main__":
    if sys.argv[1:2] in (["--controller"], ["--family"]):
        helper(sys.argv[1], Path(sys.argv[2]))
    else:
        unittest.main(verbosity=2)
