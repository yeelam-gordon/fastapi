import argparse
import json
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import isolated_build as wrapper


class WrapperTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / (".wrapper-test-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        for name in ("uv", "python", "manifest"):
            (self.root / name).write_text("{}")
        for name in ("source", "wheels"):
            (self.root / name).mkdir()
        self.args = argparse.Namespace(
            uv=self.root / "uv",
            python=self.root / "python",
            source=self.root / "source",
            source_manifest=self.root / "manifest",
            out_dir=self.root / "out",
            workers=1,
            cache_dir=self.root / "cache",
            wheelhouse=self.root / "wheels",
            report=self.root / "report.json",
        )

    def fake_process(self, argv, *, cwd, env, log):
        self.assertNotIn("PYTHONPATH", env)
        self.assertNotIn("PYTHONHOME", env)
        self.assertEqual(env["PYTHONNOUSERSITE"], "1")
        log.write_bytes(b"raw stdout\r\nraw stderr\r\n")
        if log.stem == "create":
            (cwd.parent / "venv").mkdir()
        elif log.stem == "identity":
            self.assertEqual(argv[1:4], ["-B", "-I", "-c"])
            self.assertIn("dont_write_bytecode=sys.dont_write_bytecode", argv[4])
            log.write_text(
                json.dumps(
                    {"prefix": str(cwd.parent / "venv"), "dont_write_bytecode": True}
                )
            )
        elif log.stem == "sdk":
            self.assertEqual(argv[1:4], ["-B", "-E", "-s"])
            self.assertEqual(
                argv[argv.index("--source") + 1], str(self.args.source.resolve())
            )
            artifacts = self.args.out_dir / "artifacts"
            artifacts.mkdir(parents=True)
            (artifacts / "x.tar.gz").write_bytes(b"sdist")
            (artifacts / "x.whl").write_bytes(b"wheel")
        return 0

    def receipt(self):
        return json.loads(self.args.report.read_text())

    def test_freshness_offline_hashes_cleanup_and_no_report_reuse(self):
        roots = []
        with patch.object(wrapper, "run_process", side_effect=self.fake_process):
            for n in range(2):
                self.args.out_dir = self.root / f"out{n}"
                self.args.report = self.root / f"report{n}.json"
                self.assertEqual(wrapper.execute(self.args), 0)
                report = self.receipt()
                self.assertTrue(
                    report["environment"]["identity"]["dont_write_bytecode"]
                )
                roots.append(report["environment"]["root"])
                self.assertFalse(report["environment"]["existed_before"])
                self.assertFalse(report["environment"]["exists_after_cleanup"])
                self.assertFalse(Path(roots[-1]).exists())
                install = report["phases"][1]["argv"]
                for flag in (
                    "--offline",
                    "--require-hashes",
                    "--no-index",
                    "--only-binary",
                    "--no-config",
                ):
                    self.assertIn(flag, install)
            self.assertNotEqual(*roots)
            previous = self.args.report.read_bytes()
            self.assertEqual(wrapper.execute(self.args), 1)
            self.assertEqual(previous, self.args.report.read_bytes())

    def test_failed_process_retains_raw_log_and_original_error(self):
        def fail(argv, **kwargs):
            self.fake_process(argv, **kwargs)
            return 23 if kwargs["log"].stem == "install" else 0

        with patch.object(wrapper, "run_process", side_effect=fail):
            self.assertEqual(wrapper.execute(self.args), 1)
        report = self.receipt()
        self.assertEqual(report["phases"][1]["returncode"], 23)
        self.assertIn("23", report["errors"][0]["message"])
        self.assertEqual(
            Path(report["phases"][1]["log"]).read_bytes(),
            b"raw stdout\r\nraw stderr\r\n",
        )
        self.assertFalse(report["environment"]["exists_after_cleanup"])

    def test_cleanup_failure_does_not_hide_original_failure(self):
        real_rmtree = shutil.rmtree
        with (
            patch.object(wrapper, "run_process", return_value=19),
            patch.object(
                wrapper.shutil, "rmtree", side_effect=OSError("cleanup blocked")
            ),
        ):
            self.assertEqual(wrapper.execute(self.args), 1)
        report = self.receipt()
        self.assertEqual(
            [e["phase"] for e in report["errors"]], ["invocation", "cleanup"]
        )
        self.assertTrue(report["environment"]["exists_after_cleanup"])
        real_rmtree(report["environment"]["root"])

    def test_unsupported_workers_and_existing_output_fail_before_process(self):
        with patch.object(wrapper, "run_process") as process:
            self.args.workers = 2
            self.assertEqual(wrapper.execute(self.args), 1)
            self.assertIn("workers", self.receipt()["errors"][0]["message"])
            self.args.report = self.root / "existing-output.json"
            self.args.workers = 3
            self.args.out_dir.mkdir()
            self.assertEqual(wrapper.execute(self.args), 1)
            self.assertIn("absent", self.receipt()["errors"][0]["message"])
            process.assert_not_called()

    def test_posix_phase_inherits_controller_group_and_returns_exit(self):
        with (
            patch.object(wrapper, "os") as operating_system,
            patch.object(wrapper.subprocess, "Popen") as popen,
        ):
            operating_system.name = "posix"
            child = popen.return_value
            child.wait.return_value = 17
            self.assertEqual(
                wrapper.run_process(
                    ["fixture"], cwd=self.root, env={}, log=self.root / "phase.log"
                ),
                17,
            )
            options = popen.call_args.kwargs
            self.assertFalse(options.get("start_new_session", False))
            self.assertIn(options.get("process_group"), (None, -1))
            self.assertEqual(options["creationflags"], 0)
            operating_system.killpg.assert_not_called()
            child.kill.assert_not_called()
            child.wait.assert_called_once_with()

    def test_posix_interruption_never_signals_shared_controller_group(self):
        interrupted = KeyboardInterrupt("fixture interruption")
        with (
            patch.object(wrapper, "os") as operating_system,
            patch.object(wrapper.subprocess, "Popen") as popen,
        ):
            operating_system.name = "posix"
            child = popen.return_value
            child.wait.side_effect = [interrupted, -9]
            with self.assertRaises(KeyboardInterrupt) as caught:
                wrapper.run_process(
                    ["fixture"], cwd=self.root, env={}, log=self.root / "interrupt.log"
                )
            self.assertIs(caught.exception, interrupted)
            self.assertFalse(popen.call_args.kwargs.get("start_new_session", False))
            operating_system.killpg.assert_not_called()
            child.kill.assert_called_once_with()
            self.assertEqual(child.wait.call_count, 2)


if __name__ == "__main__":
    unittest.main()
