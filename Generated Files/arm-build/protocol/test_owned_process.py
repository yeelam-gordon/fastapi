"""Tiny owned helpers only; no builds or process enumeration."""

import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import owned_process as owned  # noqa: E402

PYTHON = str(Path(sys.base_prefix) / "python.exe") if os.name == "nt" else sys.executable


def known_pid_alive(pid, *, terminate=False):
    from ctypes import wintypes as w

    api = owned._windows()
    api.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    api.OpenProcess.restype = w.HANDLE
    api.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    api.WaitForSingleObject.restype = w.DWORD
    api.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
    api.TerminateProcess.restype = w.BOOL
    handle = api.OpenProcess(0x100001, False, pid)  # SYNCHRONIZE | TERMINATE
    if not handle:
        if ctypes.get_last_error() == 87:  # ERROR_INVALID_PARAMETER: absent PID
            return False
        owned._checked(handle)
    try:
        if terminate and api.WaitForSingleObject(handle, 0) == 258:
            if not api.TerminateProcess(handle, 1):
                if api.WaitForSingleObject(handle, 5000) != 0:
                    owned._checked(False)
        state = api.WaitForSingleObject(handle, 5000 if terminate else 0)
        if state not in (0, 258):
            raise RuntimeError(f"Unexpected owned PID wait result: {state}")
        return state == 258
    finally:
        owned._checked(api.CloseHandle(handle))


class OwnedTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / (".owned-test-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)

    def run_helper(self, role, timeout=5):
        return owned.run_owned(
            [PYTHON, "-I", str(Path(__file__).resolve()),
             "--helper", role, str(self.root.resolve())],
            cwd=self.root, env=os.environ.copy(),
            stdout_path=self.root / "stdout", stderr_path=self.root / "stderr",
            timeout=timeout,
        )

    def test_normal_unfiltered_logs_and_separate_infrastructure(self):
        result = self.run_helper("normal")
        self.assertTrue(result.succeeded, result)
        self.assertGreater(result.command_wall, 0)
        self.assertGreater(result.infrastructure_wall, 0)
        self.assertEqual((self.root / "stdout").read_bytes(), b"out\r\n")
        self.assertEqual((self.root / "stderr").read_bytes(), b"err\r\n")

    def test_failure_retains_exit_code(self):
        result = self.run_helper("failure")
        self.assertEqual(result.returncode, 7)
        self.assertFalse(result.succeeded)
        self.assertTrue(result.cleanup_complete, result)

    @unittest.skipUnless(os.name == "nt", "Windows real job proof; POSIX mocked below")
    def test_timeout_and_fast_intermediate_parent(self):
        for role, limit in (("timeout", 1.5), ("orphan", 5)):
            with self.subTest(role=role):
                result = self.run_helper(role, limit)
                pids = [int(p.read_text()) for p in self.root.glob("pid-*")]
                try:
                    self.assertTrue(pids)
                    self.assertFalse(result.succeeded, result)
                    self.assertTrue(result.ownership_established, result)
                    self.assertTrue(result.cleanup_complete, result)
                    self.assertTrue(result.survivors, result)
                    self.assertTrue(result.liveness, result)
                    self.assertEqual(result.timed_out, role == "timeout", result)
                    if role == "orphan":
                        self.assertEqual(result.returncode, 0)
                    for pid in pids:
                        self.assertFalse(known_pid_alive(pid), (pid, result))
                finally:
                    for pid in pids:
                        self.assertFalse(known_pid_alive(pid, terminate=True))
                    for path in self.root.glob("pid-*"):
                        path.unlink()

    def test_setup_failure_never_launches_target(self):
        with patch.object(owned, "_Job", side_effect=OSError("cannot establish")):
            if os.name == "nt":
                result = self.run_helper("normal")
                self.assertFalse(result.succeeded)
                self.assertFalse(result.ownership_established)
                self.assertIsNone(result.command_wall)
                self.assertFalse((self.root / "stdout").exists())

    def test_setup_and_close_failures_preserve_both_diagnostics(self):
        api = Mock()
        api.CreateJobObjectW.return_value = 1
        api.SetInformationJobObject.side_effect = OSError("original setup failure")
        api.CloseHandle.side_effect = OSError("secondary close failure")
        with (
            patch.object(owned, "_WINDOWS", True),
            patch.object(owned, "_windows", return_value=api),
            patch.object(owned.subprocess, "Popen") as spawn,
        ):
            result = self.run_helper("normal")
        self.assertFalse(result.succeeded)
        self.assertFalse(result.cleanup_complete)
        self.assertTrue(any("original setup failure" in e for e in result.errors))
        self.assertTrue(any("secondary close failure" in e for e in result.errors))
        spawn.assert_not_called()
        api.CloseHandle.assert_called_once_with(1)

    def test_pipe_close_failures_preserve_status_and_attempt_every_close(self):
        process = Mock(pid=123, returncode=0)
        process.poll.return_value = 0
        process.communicate.return_value = (
            json.dumps({"owned": True, "started": time.perf_counter(),
                        "returncode": 7, "timed_out": False,
                        "error": "original invocation failure"}), ""
        )
        process.stdin.close.side_effect = OSError("stdin close failed")
        process.stdout.close.side_effect = OSError("stdout close failed")
        job = Mock()
        job.alive.return_value = False
        with (
            patch.object(owned, "_WINDOWS", True),
            patch.object(owned, "_Job", return_value=job),
            patch.object(owned.subprocess, "Popen", return_value=process),
        ):
            result = self.run_helper("failure")
        self.assertEqual(result.returncode, 7)
        self.assertFalse(result.succeeded)
        self.assertFalse(result.cleanup_complete)
        for message in (
            "original invocation failure", "stdin close failed", "stdout close failed"
        ):
            self.assertTrue(any(message in e for e in result.errors), result)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close.assert_called_once()
        job.close.assert_called_once()

    def test_posix_group_probe_is_owned_id_only(self):
        with patch.object(owned.os, "killpg", create=True) as kill:
            self.assertTrue(owned._group_alive(123))
            kill.assert_called_once_with(123, 0)
            kill.side_effect = ProcessLookupError
            self.assertFalse(owned._group_alive(123))
            kill.side_effect = PermissionError
            with self.assertRaises(PermissionError):
                owned._group_alive(123)

    def test_posix_group_cleanup_contract_mock(self):
        process = Mock(pid=123, returncode=0)
        process.poll.return_value = 0
        process.communicate.return_value = (
            json.dumps({"owned": True, "started": time.perf_counter(),
                        "returncode": 0, "timed_out": False}), ""
        )
        with (
            patch.object(owned, "_WINDOWS", False),
            patch.object(owned.subprocess, "Popen", return_value=process) as spawn,
            patch.object(owned, "_group_alive", side_effect=[True, False, False]),
            patch.object(owned.os, "killpg", create=True) as kill,
            patch.object(owned.signal, "SIGKILL", 9, create=True),
        ):
            result = self.run_helper("normal")
        self.assertTrue(spawn.call_args.kwargs["start_new_session"])
        kill.assert_called_once_with(123, 9)
        self.assertFalse(result.succeeded)
        self.assertTrue(result.survivors)
        self.assertTrue(result.cleanup_complete)

    def test_failed_drain_preserves_failure_and_closes_job(self):
        process = Mock(pid=123, returncode=0)
        process.poll.return_value = 0
        process.communicate.return_value = (
            json.dumps({"owned": True, "started": time.perf_counter(),
                        "returncode": 7, "timed_out": False}), ""
        )
        job = Mock()
        job.alive.return_value = True
        job.kill.side_effect = TimeoutError("owned process did not terminate")
        with (
            patch.object(owned, "_WINDOWS", True),
            patch.object(owned, "_Job", return_value=job),
            patch.object(owned.subprocess, "Popen", return_value=process),
        ):
            result = self.run_helper("failure")
        self.assertEqual(result.returncode, 7)
        self.assertFalse(result.succeeded)
        self.assertFalse(result.cleanup_complete)
        self.assertTrue(any("did not terminate" in e for e in result.errors))
        job.close.assert_called_once()

    def test_cleanup_query_failure_cannot_succeed(self):
        if os.name != "nt":
            self.skipTest("Windows job query injection")
        with patch.object(owned._Job, "alive", side_effect=OSError("query failed")):
            result = self.run_helper("normal")
        self.assertFalse(result.succeeded)
        self.assertFalse(result.cleanup_complete)
        self.assertTrue(any("query failed" in e for e in result.errors))

    def test_invalid_budget(self):
        for timeout in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                self.run_helper("normal", timeout)

    def test_accounting_positive_uses_owned_member_wait_states(self):
        from ctypes import wintypes as w

        for state, expected in ((0, False), (258, True)):
            with self.subTest(state=state):
                job = object.__new__(owned._Job)
                job.handle, job.api = 1, Mock()
                observations = []

                def members():
                    if observations:
                        job.api.CloseHandle.assert_not_called()
                    observations.append(True)
                    return {10, 20}

                job.members = Mock(side_effect=members)
                job.api.OpenProcess.return_value = 99
                job.api.WaitForSingleObject.return_value = state

                def belongs(process, handle, flag):
                    ctypes.cast(flag, ctypes.POINTER(w.BOOL)).contents.value = True
                    return True

                job.api.IsProcessInJob.side_effect = belongs
                evidence = []
                self.assertEqual(job.live_members(10, evidence), expected)
                self.assertEqual(evidence[0]["members"][0]["state"], "waited_supervisor")
                self.assertEqual(
                    evidence[0]["members"][1]["state"],
                    "terminated" if state == 0 else "live",
                )
                job.api.CloseHandle.assert_called_once_with(99)

    def test_departed_member_requires_absence_from_complete_second_snapshot(self):
        for after in (set(), {20}):
            job = object.__new__(owned._Job)
            job.handle, job.api = 1, Mock()
            job.members = Mock(side_effect=[{20}, after])
            job.api.OpenProcess.return_value = 0
            evidence = []
            with patch.object(ctypes, "get_last_error", return_value=87, create=True):
                if after:
                    with self.assertRaisesRegex(RuntimeError, "reappeared"):
                        job.live_members(10, evidence)
                else:
                    self.assertFalse(job.live_members(10, evidence))
                    self.assertEqual(evidence[0]["members"][0]["state"], "departed")

    def test_member_identity_wait_and_enumeration_unknowns_fail_closed(self):
        from ctypes import wintypes as w

        for kind in ("access", "identity", "wait", "enumeration", "new-member"):
            with self.subTest(kind=kind):
                job = object.__new__(owned._Job)
                job.handle, job.api = 1, Mock()
                job.members = Mock(side_effect=[{20}, {20, 30} if kind == "new-member" else {20}])
                job.api.OpenProcess.return_value = 99
                job.api.WaitForSingleObject.return_value = 0

                def belongs(process, handle, flag):
                    ctypes.cast(flag, ctypes.POINTER(w.BOOL)).contents.value = kind != "identity"
                    return True

                job.api.IsProcessInJob.side_effect = belongs
                if kind == "access":
                    job.api.OpenProcess.side_effect = PermissionError("access denied")
                elif kind == "wait":
                    job.api.WaitForSingleObject.return_value = 0xFFFFFFFF
                elif kind == "enumeration":
                    job.members.side_effect = OSError("incomplete membership")
                evidence = []
                with self.assertRaises((OSError, RuntimeError)):
                    job.live_members(10, evidence)
                self.assertIn("error", evidence[0])


def helper(role, root):
    (root / ("pid-" + str(os.getpid()))).write_text(str(os.getpid()))
    if role == "normal":
        os.write(1, b"out\r\n")
        os.write(2, b"err\r\n")
    elif role == "failure":
        raise SystemExit(7)
    elif role in ("orphan", "timeout"):
        command = [
            PYTHON, "-I", str(Path(__file__).resolve()),
            "--helper", "intermediate", str(root),
        ]
        child = subprocess.Popen(command)
        if role == "timeout":
            child.wait()
            time.sleep(30)
        else:
            child.wait(timeout=5)
    elif role == "intermediate":
        child = subprocess.Popen([
            PYTHON, "-I", str(Path(__file__).resolve()),
            "--helper", "sleep", str(root),
        ])
        (root / ("pid-" + str(child.pid))).write_text(str(child.pid))
    elif role == "sleep":
        time.sleep(30)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--helper"]:
        helper(sys.argv[2], Path(sys.argv[3]))
    else:
        unittest.main(verbosity=2)
