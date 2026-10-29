"""Independent API-boundary mocks; no processes or OS handles are created."""

import ctypes
from ctypes import wintypes as w
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "protocol"))
import owned_process as owned


def job_with(pids, after=None, state=0):
    job = object.__new__(owned._Job)
    job.handle, job.api = 1, Mock()
    job.members = Mock(side_effect=[set(pids), set(pids if after is None else after)])
    job.api.OpenProcess.side_effect = lambda access, inherit, pid: pid + 100
    job.api.WaitForSingleObject.return_value = state

    def belongs(handle, job_handle, result):
        ctypes.cast(result, ctypes.POINTER(w.BOOL)).contents.value = True
        return True

    job.api.IsProcessInJob.side_effect = belongs
    return job


class MembershipReview(unittest.TestCase):
    def test_complete_enumeration_retries_growth_and_partial_success(self):
        job = object.__new__(owned._Job)
        job.handle, job.api = 1, Mock()
        capacities = []

        def query(handle, kind, pointer, size, returned):
            value = pointer._obj
            capacities.append(len(value.ProcessIdList))
            count = 9 if len(capacities) == 1 else 17
            value.NumberOfAssignedProcesses = count
            value.NumberOfProcessIdsInList = min(count, len(value.ProcessIdList))
            for index in range(value.NumberOfProcessIdsInList):
                value.ProcessIdList[index] = index + 10
            return len(capacities) != 1

        job.api.QueryInformationJobObject.side_effect = query
        with patch.object(ctypes, "get_last_error", return_value=234):
            self.assertEqual(owned._Job.members(job), set(range(10, 27)))
        self.assertEqual(capacities, [8, 16, 32])

    def test_enumeration_unknown_and_growth_bound_reject(self):
        for error in (5, 234):
            with self.subTest(error=error):
                job = object.__new__(owned._Job)
                job.handle, job.api = 1, Mock()
                job.api.QueryInformationJobObject.return_value = 0
                with patch.object(ctypes, "get_last_error", return_value=error):
                    with self.assertRaises((OSError, RuntimeError)):
                        job.members()

    def test_only_waited_supervisor_excluded_and_handles_pinned(self):
        job = job_with({10, 20, 30})
        calls = 0

        def members():
            nonlocal calls
            calls += 1
            if calls == 2:
                job.api.CloseHandle.assert_not_called()
            return {10, 20, 30}

        job.members.side_effect = members
        evidence = []
        self.assertFalse(job.live_members(10, evidence))
        self.assertEqual(
            [call.args[2] for call in job.api.OpenProcess.call_args_list], [20, 30]
        )
        self.assertEqual(job.api.CloseHandle.call_count, 2)

    def test_live_and_unknown_members_never_become_empty(self):
        for mode in ("live", "reuse", "membership-error", "wait-error",
                     "access", "new", "second-query"):
            with self.subTest(mode=mode):
                job = job_with({20, 30})
                if mode == "live":
                    job.api.WaitForSingleObject.return_value = 258
                    self.assertTrue(job.live_members(10, []))
                    continue
                if mode == "reuse":
                    job.api.IsProcessInJob.side_effect = None
                    job.api.IsProcessInJob.return_value = 1
                elif mode == "membership-error":
                    job.api.IsProcessInJob.side_effect = OSError("identity query")
                elif mode == "wait-error":
                    job.api.WaitForSingleObject.return_value = 0xFFFFFFFF
                elif mode == "access":
                    job.api.OpenProcess.side_effect = PermissionError("open")
                elif mode == "new":
                    job.members.side_effect = [{20, 30}, {20, 30, 40}]
                else:
                    job.members.side_effect = [{20, 30}, OSError("second query")]
                with self.assertRaises((OSError, RuntimeError)):
                    job.live_members(10, [])
                opened = [
                    call.args[2] + 100 for call in job.api.OpenProcess.call_args_list
                ] if mode != "access" else []
                self.assertEqual(
                    [call.args[0] for call in job.api.CloseHandle.call_args_list], opened
                )

    def test_observation_close_errors_attempt_all_and_preserve_primary(self):
        for primary in (False, True):
            job = job_with({20, 30})
            if primary:
                job.members.side_effect = [{20, 30}, OSError("primary query")]
            job.api.CloseHandle.side_effect = OSError("close failed")
            evidence = []
            with self.assertRaisesRegex(
                (OSError, RuntimeError), "primary query" if primary else "cleanup"
            ):
                job.live_members(10, evidence)
            self.assertEqual(job.api.CloseHandle.call_count, 2)
            self.assertEqual(len(evidence[0]["close_errors"]), 2)

    def test_departed_requires_second_snapshot_absence(self):
        for after in (set(), {20}, {40}):
            job = job_with({20}, after)
            job.api.OpenProcess.side_effect = None
            job.api.OpenProcess.return_value = 0
            with patch.object(ctypes, "get_last_error", return_value=87):
                if after:
                    with self.assertRaises(RuntimeError):
                        job.live_members(10, [])
                else:
                    self.assertFalse(job.live_members(10, []))
            job.api.CloseHandle.assert_not_called()

    def test_api_false_returns_are_unknown_not_empty(self):
        for api in ("OpenProcess", "IsProcessInJob"):
            job = job_with({20})
            getattr(job.api, api).side_effect = None
            getattr(job.api, api).return_value = 0
            with patch.object(ctypes, "get_last_error", return_value=5):
                with self.assertRaises(OSError):
                    job.live_members(10, [])
            self.assertEqual(job.api.CloseHandle.call_count,
                             0 if api == "OpenProcess" else 1)

    def test_historical_kill_close_failure_skips_remaining_handle(self):
        job = job_with({20, 30})
        job.api.TerminateJobObject.side_effect = OSError("original termination error")
        job.api.CloseHandle.side_effect = OSError("secondary close error")
        with self.assertRaisesRegex(OSError, "secondary close error"):
            job.kill()
        self.assertEqual(job.api.OpenProcess.call_count, 2)
        self.assertEqual(job.api.CloseHandle.call_count, 1)

    def test_accounting_zero_bypasses_member_validation(self):
        process = Mock(pid=10, returncode=0)
        process.poll.return_value = 0
        process.communicate.return_value = (
            json.dumps(dict(owned=True, started=time.perf_counter(),
                            returncode=0, timed_out=False)), ""
        )
        job = Mock()
        job.alive.return_value = False
        job.live_members.side_effect = OSError("membership unavailable")
        with (
            patch.object(owned, "_WINDOWS", True),
            patch.object(owned, "_Job", return_value=job),
            patch.object(owned.subprocess, "Popen", return_value=process),
        ):
            result = owned.run_owned(
                ["mock"], cwd=Path(__file__).parent, env={},
                stdout_path=Path(__file__), stderr_path=Path(__file__), timeout=5,
            )
        self.assertTrue(result.succeeded, result)
        job.live_members.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
