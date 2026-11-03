import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import screen

sys.path.insert(0, str(Path(screen.__file__).parent.parent / "hobl-complete-ci"))
from owned_process import Receipt


class ScreenTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / (".unit-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)

    def initial(self, cached):
        screen.save(self.root / "initial-cache.json", {"initially_cached": cached})

    def fake_guard(self, argv, **kwargs):
        self.calls.append(argv)
        self.assertTrue(kwargs["native_clock"])
        self.assertEqual(kwargs["env"]["UV_HTTP_RETRIES"], "0")
        self.assertEqual(kwargs["env"]["UV_HTTP_TIMEOUT"], "20")
        self.assertEqual(kwargs["timeout"], 60 if "install" in argv else 30)
        output = "uv 0.13.6 (native)" if "--version" in argv else "{}"
        Path(kwargs["stdout_path"]).write_text(output, encoding="utf-8")
        Path(kwargs["stderr_path"]).write_text("", encoding="utf-8")
        success = "install" not in argv
        return Receipt(0 if success else 1, False, 0.001, 0.001, True, False, True, (),
                       native_start_ns=100, native_end_ns=1000)

    def test_install_failure_retains_timing_before_discovery_or_candidate_identity(self):
        self.initial(False)
        self.calls = []
        with patch.dict(sys.modules, {"owned_process": SimpleNamespace(run_owned=self.fake_guard)}), \
                patch.object(screen, "native_pe"):
            with self.assertRaisesRegex(RuntimeError, "install failed"):
                screen.run(self.root, "uv.exe")
        receipt = json.loads((self.root / "install.json").read_text())
        self.assertEqual(receipt["receipt"]["returncode"], 1)
        self.assertGreater(receipt["invocation_wall_ns"], 0)
        self.assertEqual(receipt["receipt"]["native_end_ns"], 1000)
        self.assertFalse(any("find" in call for call in self.calls))
        install = self.calls[-1]
        self.assertTrue({"--no-bin", "--no-registry", "--no-config", "--no-progress"} <= set(install))

    def test_cached_stock_never_invokes_uv(self):
        self.initial(True)
        self.calls = []
        with patch.dict(sys.modules, {"owned_process": SimpleNamespace(run_owned=self.fake_guard)}):
            screen.run(self.root, "")
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(json.loads((self.root / "result.json").read_text())["candidate_skipped"])
        self.assertFalse((self.root / "python").exists())

    def test_finder_accepts_actual_file_but_rejects_escape_and_missing_path(self):
        install = self.root / "python"
        actual = install / "cpython-3.13.15-windows-aarch64-none" / "python.exe"
        actual.parent.mkdir(parents=True)
        actual.touch()
        self.assertEqual(screen.owned_candidate(str(actual), install), actual.resolve())
        outside = self.root / "outside.exe"
        outside.touch()
        with self.assertRaisesRegex(RuntimeError, "escaped"):
            screen.owned_candidate(str(outside), install)
        with self.assertRaises(FileNotFoundError):
            screen.owned_candidate(str(install / "missing.exe"), install)


if __name__ == "__main__":
    unittest.main()
