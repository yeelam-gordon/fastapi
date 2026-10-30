"""Focused P50 policy fixtures: no source build, installer or resource allocation."""

import copy
import os
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import control
import hardware_control


class ControlTests(unittest.TestCase):
    def test_actual_family_and_guest_resource_requirements(self):
        cpu = {
            "system": "Linux",
            "machine": "aarch64",
            "local_correctness_only": False,
            "guest_logical": 4,
            "guest_cores": 4,
            "usable": 4,
            "identities": [{"implementer": 0x41, "part": 0xD49}] * 4,
            "models": ["Neoverse-N2"],
        }
        self.assertTrue(hardware_control.comparable(cpu)["comparable"])
        for key, value in (
            ("guest_logical", 3),
            ("guest_cores", 8),
            ("usable", 3),
            ("machine", "x86_64"),
            ("models", ["Arm"]),
            ("identities", [{"implementer": 0x41, "part": 0xD0C}] * 4),
            ("identities", []),
            ("local_correctness_only", True),
        ):
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                hardware_control.comparable({**cpu, key: value})
        win = {
            **copy.deepcopy(cpu),
            "system": "Windows",
            "models": ["Cobalt 100"],
            "identifier": "ARMv8 (64-bit) Family 8 Model D49 Revision 0",
            "processors": [{"Architecture": 12}],
        }
        self.assertTrue(hardware_control.comparable(win)["comparable"])
        local = {
            **win,
            "guest_logical": 16,
            "guest_cores": 16,
            "identities": win["identities"] * 4,
            "local_correctness_only": True,
        }
        self.assertFalse(hardware_control.comparable(local)["comparable"])
        with self.assertRaises(RuntimeError):
            hardware_control.comparable({**local, "local_correctness_only": False})

    def test_single_stock_seven_not_AB_or_extra_correctness_build(self):
        schedule = control.schedule(False)
        self.assertEqual(len(schedule), 7)
        self.assertFalse(schedule[0][1])
        self.assertEqual(sum(timed for _, timed in schedule), 6)
        self.assertEqual(control.schedule(True), [("warmup", False)])
        argv = control.argv_for("B", Path("python"), Path("uv"), Path("constraints"))
        self.assertEqual(argv[:3], ["uv", "build", "-v"])
        self.assertNotIn("--sdist", argv)
        self.assertNotIn("--wheel", argv)
        self.assertIn("--require-hashes", argv)

    def test_private_security_and_default_bytecode_environment(self):
        root = Path(__file__).parent / ".local" / ("p50-policy-" + uuid.uuid4().hex)
        self.addCleanup(shutil.rmtree, root)
        with patch.dict(
            os.environ,
            {
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": "foreign",
                "UV_NO_VERIFY_HASHES": "1",
                "GITHUB_TOKEN": "private",
            },
        ):
            env = control.stock_environment(root)
        self.assertEqual(env["HOME"], str(root / "home"))
        self.assertEqual(env["TEMP"], str(root / "scratch"))
        self.assertNotIn("PYTHONDONTWRITEBYTECODE", env)
        self.assertNotIn("PYTHONPATH", env)
        self.assertNotIn("UV_NO_VERIFY_HASHES", env)
        self.assertNotIn("GITHUB_TOKEN", env)
        if os.name == "nt":
            self.assertEqual(env["NoDefaultCurrentDirectoryInExePath"], "1")

    def test_exact_manual_fork_ref_and_attempt_only(self):
        env = {
            "GITHUB_REPOSITORY": "yeelam-gordon/fastapi",
            "GITHUB_REF": "refs/heads/perf/arm-cobalt-control",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_RUN_ATTEMPT": "1",
        }
        control.hosted_guard(env)
        for key in env:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                control.hosted_guard({**env, key: "wrong"})
        inputs = control.closure()
        self.assertIn(str(control.OWNERSHIP), inputs)
        self.assertIn(str(control.WORKFLOW), inputs)


if __name__ == "__main__":
    unittest.main()
