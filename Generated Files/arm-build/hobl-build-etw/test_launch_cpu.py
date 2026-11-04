import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import launch


@unittest.skipUnless(sys.platform == "win32", "Windows owned-process counters")
class ProcessCpu(unittest.TestCase):
    def test_command_anchor_preserves_failure_exit_and_cpu(self):
        with tempfile.TemporaryDirectory(
            prefix="test-private-cpu-cli-", dir=Path(__file__).parent
        ) as directory:
            destination = Path(directory) / "anchor.json"
            completed = subprocess.run(
                [
                    sys._base_executable,
                    "-I",
                    "-B",
                    str(Path(launch.__file__)),
                    str(destination),
                    sys._base_executable,
                    "-I",
                    "-B",
                    "-c",
                    "raise SystemExit(3)",
                ],
                check=False,
                timeout=10,
            )
            self.assertEqual(completed.returncode, 3)
            anchor = json.loads(destination.read_text(encoding="utf-8"))
            self.assertGreaterEqual(anchor["qpc_end"], anchor["qpc_after"])
            for key in ("process_kernel_100ns", "process_user_100ns"):
                self.assertIs(type(anchor[key]), int)
                self.assertGreaterEqual(anchor[key], 0)

    def test_completed_owned_process_cpu_and_birth(self):
        with tempfile.TemporaryDirectory(
            prefix="test-private-cpu-", dir=Path(__file__).parent
        ) as directory:
            gate = Path(directory) / "release"
            process, anchor = launch.spawn(
                [
                    sys._base_executable,
                    "-I",
                    "-B",
                    "-c",
                    "import sys,time; from pathlib import Path\n"
                    "gate=Path(sys.argv[1]); deadline=time.perf_counter()+5\n"
                    "while not gate.exists():\n"
                    " if time.perf_counter()>deadline: raise TimeoutError('release')\n"
                    " time.sleep(0.005)\n"
                    "end=time.perf_counter()+0.12\n"
                    "while time.perf_counter()<end: sum(i*i for i in range(1000))",
                    str(gate),
                ]
            )
            try:
                with self.assertRaisesRegex(ValueError, "process_still_running"):
                    launch.completed_cpu(process, anchor)
                gate.touch()
                self.assertEqual(process.wait(timeout=10), 0)
                values = launch.completed_cpu(process, anchor)
                self.assertEqual(
                    set(values), {"process_kernel_100ns", "process_user_100ns"}
                )
                self.assertTrue(
                    all(type(value) is int and value >= 0 for value in values.values())
                )
                self.assertGreater(values["process_user_100ns"], 0)
                with self.assertRaisesRegex(ValueError, "native_creation_mismatch"):
                    launch.completed_cpu(
                        process,
                        dict(anchor, creation_filetime=anchor["creation_filetime"] + 1),
                    )
            finally:
                gate.touch(exist_ok=True)
                process.wait(timeout=10)

    def test_native_counter_error_is_not_a_zero_measurement(self):
        with patch.object(
            launch.ctypes.windll.kernel32, "GetProcessTimes", return_value=0
        ):
            with self.assertRaises(OSError):
                launch.process_times(SimpleNamespace(_handle=123))


if __name__ == "__main__":
    unittest.main()
