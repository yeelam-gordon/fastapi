"""Owned known-PID parent-death gate; no system process census."""

import json
import os
import shutil
import subprocess
import sys
import time
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import owned_process as owned
from test_owned_process import known_pid_alive

PYTHON = str(Path(sys.base_prefix) / "python.exe")


class ParentDeath(unittest.TestCase):
    def test_parent_death(self):
        root = Path(__file__).parent / (".death-" + uuid.uuid4().hex)
        root.mkdir()
        controller = subprocess.Popen(
            [PYTHON, "-I", str(Path(__file__).resolve()), "--controller", str(root.resolve())],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        pids = []
        try:
            marker = root / "family.json"
            deadline = time.monotonic() + 8
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(marker.exists())
            pids = json.loads(marker.read_text())
            self.assertTrue(all(known_pid_alive(pid) for pid in pids))
            controller.terminate()
            controller.wait(timeout=5)
            deadline = time.monotonic() + 5
            while any(known_pid_alive(pid) for pid in pids):
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.02)
        finally:
            if controller.poll() is None:
                controller.terminate()
                controller.wait(timeout=5)
            marker = root / "family.json"
            if not pids and marker.exists():
                pids = json.loads(marker.read_text())
            for pid in pids:
                self.assertFalse(known_pid_alive(pid, terminate=True))
            shutil.rmtree(root)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--controller"]:
        root = Path(sys.argv[2])
        owned.run_owned(
            [PYTHON, "-I", str(Path(__file__).resolve()), "--family", str(root)],
            cwd=root, env=os.environ.copy(), stdout_path=root / "out",
            stderr_path=root / "err", timeout=30,
        )
    elif sys.argv[1:2] == ["--family"]:
        root = Path(sys.argv[2])
        child = subprocess.Popen([PYTHON, "-I", "-c", "import time;time.sleep(30)"])
        pending = root / "pending.json"
        pending.write_text(json.dumps([os.getppid(), os.getpid(), child.pid]))
        pending.rename(root / "family.json")
        time.sleep(30)
    else:
        unittest.main(verbosity=2)
