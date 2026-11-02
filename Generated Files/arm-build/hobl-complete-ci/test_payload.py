import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import owned_process
import run_payload as payload


class PayloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.source = root / "source"
        self.output = root / "output"
        self.source.mkdir()
        self.output.mkdir()
        (self.source / "fastapi").mkdir()
        self.original = self.source / "fastapi" / "__init__.py"
        self.original.write_text("__version__ = '0.119.1'\n", encoding="utf-8")
        manifest = {
            "fastapi/__init__.py": hashlib.sha256(
                self.original.read_bytes()
            ).hexdigest()
        }
        self.manifest = root / "manifest.json"
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        dist = self.source / "dist"
        dist.mkdir()
        with zipfile.ZipFile(dist / "fastapi-0.119.1-py3-none-any.whl", "w") as archive:
            archive.writestr("fastapi/__init__.py", self.original.read_bytes())
        with tarfile.open(dist / "fastapi-0.119.1.tar.gz", "w:gz") as archive:
            member = tarfile.TarInfo("fastapi-0.119.1/fastapi/__init__.py")
            data = self.original.read_bytes()
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        self.args = types.SimpleNamespace(
            source=self.source,
            output=self.output,
            manifest=self.manifest,
            python=root / "venv" / "Scripts" / "python.exe",
            loops=1,
            index="https://pypi.org/simple",
            style="windows",
            prep_qualification="test",
        )
        self.identity = types.SimpleNamespace(
            returncode=0,
            stderr="",
            stdout=json.dumps(
                {
                    "machine": "ARM64",
                    "pointer_bits": 64,
                    "fastapi_origin": str(self.original),
                    "packages": {},
                }
            ),
        )

    @staticmethod
    def fake_phase(command, source, env, folder, name):
        (folder / f"{name}.stdout").write_text(
            "================ 2513 passed, 130 skipped in 90s ================\n"
            if name == "test"
            else "build complete\n",
            encoding="utf-8",
        )
        (folder / f"{name}.stderr").write_text("", encoding="utf-8")
        seconds = 2.5 if name == "build" else 90.0
        return {"exitcode": 0, "seconds": seconds, "hobl_rounded_seconds": seconds}

    def exercise(self, side_effect=None):
        with patch.object(payload.subprocess, "run", return_value=self.identity):
            with patch.object(
                payload, "phase", side_effect=side_effect or self.fake_phase
            ) as phases:
                payload.worker(self.args)
                return phases

    def test_windows_runs_complete_work_and_sums_both_phases(self):
        phases = self.exercise()
        self.assertEqual(
            phases.call_args_list[0].args[0], [str(self.args.python), "-m", "build"]
        )
        self.assertEqual(
            phases.call_args_list[1].args[0],
            [str(self.args.python), "-m", "coverage", "run", "-m", "pytest", "tests"],
        )
        result = json.loads((self.output / "result.json").read_bytes())
        self.assertEqual(result["median_scenario_runtime_seconds"], 92.5)
        self.assertFalse(result["under_10_seconds"])
        self.assertEqual(
            result["loops"][0]["outcomes"], {"passed": 2513, "skipped": 130}
        )

    def test_mac_uses_the_canonical_test_script(self):
        self.args.style = "macos"
        phases = self.exercise()
        self.assertEqual(phases.call_args_list[1].args[0], ["bash", "scripts/test.sh"])

    def test_analysis_worker_bypasses_all_build_and_performance_loops(self):
        self.args.phase_analysis = True
        canonical = {f"canonical-{number}": "hash" for number in range(2557)}
        self.manifest.write_text(json.dumps(canonical), encoding="utf-8")
        identity = json.loads(self.identity.stdout)
        identity.update(
            {
                "fastapi_version": "0.119.1",
                "packages": {"build": "1.6.1", "pip": "25.0.1"},
            }
        )
        self.identity.stdout = json.dumps(identity)
        with (
            patch.object(payload, "snapshot", return_value=canonical),
            patch("phase_analysis.run") as analysis,
        ):
            phases = self.exercise()
        phases.assert_not_called()
        self.assertEqual(analysis.call_count, 1)
        args, env, protected = analysis.call_args.args
        self.assertIs(args, self.args)
        self.assertEqual(env["PYTHONPATH"], "./docs_src")
        self.assertEqual(protected, canonical)
        self.assertFalse((self.output / "result.json").exists())

    def test_build_failure_never_runs_tests_or_publishes_success(self):
        with self.assertRaisesRegex(RuntimeError, "build failed"):
            self.exercise(lambda *args: {"exitcode": 1})
        self.assertFalse((self.output / "result.json").exists())

    def test_changed_source_is_rejected(self):
        def mutate(*args):
            result = self.fake_phase(*args)
            if args[-1] == "test":
                self.original.write_text("changed\n", encoding="utf-8")
            return result

        with self.assertRaisesRegex(RuntimeError, "canonical source changed"):
            self.exercise(mutate)
        self.assertFalse((self.output / "result.json").exists())

    def test_interpreter_path_does_not_follow_venv_symlink(self):
        wanted = self.args.python
        original_resolve = Path.resolve
        base_python = self.source / "base-python"

        def fake_resolve(path, *args, **kwargs):
            if path == wanted:
                return base_python
            return original_resolve(path, *args, **kwargs)

        self.args.worker = True
        with patch.object(Path, "resolve", fake_resolve):
            with patch.object(payload, "worker") as worker:
                payload.main(self.args)
        self.assertEqual(worker.call_args.args[0].python, wanted.absolute())

    def test_paired_schedule_has_two_warmups_and_five_alternating_pairs(self):
        schedule = payload.schedule(True, 5)
        self.assertEqual(schedule[:2], [("stock", False), ("uv", False)])
        self.assertEqual(
            schedule[2:],
            [
                (arm, True)
                for pair in (
                    ("stock", "uv"),
                    ("uv", "stock"),
                    ("stock", "uv"),
                    ("uv", "stock"),
                    ("stock", "uv"),
                )
                for arm in pair
            ],
        )

    def test_paired_uv_command_uses_same_python_and_pinned_build_constraints(self):
        self.args.paired_uv = self.source / "uv.exe"
        command = payload.build_command(self.args, "uv")
        self.assertEqual(command[:2], [str(self.args.paired_uv), "build"])
        self.assertEqual(command[command.index("--python") + 1], str(self.args.python))
        self.assertIn("--no-python-downloads", command)
        constraint = Path(command[command.index("--build-constraints") + 1])
        self.assertEqual(constraint.read_text().strip(), "pdm-backend==2.5.0")
        self.assertNotIn("--wheel", command)
        self.assertNotIn("--no-build-isolation", command)

    def test_paired_results_exclude_warmups_and_group_complete_score_medians(self):
        rows = [
            {
                "arm": "stock",
                "measured": False,
                "build_seconds": 1000,
                "test_seconds": 1000,
                "scenario_runtime_seconds": 2000,
            },
            {
                "arm": "uv",
                "measured": False,
                "build_seconds": 1000,
                "test_seconds": 1000,
                "scenario_runtime_seconds": 2000,
            },
        ]
        for value in (1, 2, 3, 4, 5):
            rows.extend(
                [
                    {
                        "arm": "stock",
                        "measured": True,
                        "build_seconds": value,
                        "test_seconds": 50,
                        "scenario_runtime_seconds": value + 50,
                    },
                    {
                        "arm": "uv",
                        "measured": True,
                        "build_seconds": value,
                        "test_seconds": 40,
                        "scenario_runtime_seconds": value + 40,
                    },
                ]
            )
        groups = payload.paired_summary(rows)
        self.assertEqual(groups["stock"]["median_scenario_runtime_seconds"], 53)
        self.assertEqual(groups["uv"]["median_scenario_runtime_seconds"], 43)
        self.assertEqual(groups["uv"]["measured_iterations"], 5)

    def exercise_paired(
        self, side_effect=None, archive_effect=None, snapshot_effect=None
    ):
        self.args.paired_uv = self.source / "uv.exe"
        self.args.loops = 5
        identity = json.loads(self.identity.stdout)
        identity.update(
            {
                "fastapi_version": "0.119.1",
                "packages": {"build": "1.6.1", "pip": "25.0.1"},
            }
        )
        self.identity.stdout = json.dumps(identity)
        canonical = {f"canonical-{number}": "hash" for number in range(2557)}
        self.manifest.write_text(json.dumps(canonical), encoding="utf-8")
        for path in (self.source / "dist").iterdir():
            path.unlink()
        (self.source / "dist").rmdir()

        def paired_phase(*args):
            if args[-1] == "build":
                (self.source / "dist").mkdir()
            return (side_effect or self.fake_phase)(*args)

        with (
            patch.object(payload.subprocess, "run", return_value=self.identity),
            patch.object(payload, "attest", return_value={"native_arm64": True}),
            patch.object(
                payload, "snapshot", side_effect=snapshot_effect, return_value=canonical
            ),
            patch.object(
                payload,
                "artifact_set",
                side_effect=archive_effect,
                return_value={"package": {"members": {"file": "hash"}}},
            ),
            patch.object(payload, "phase", side_effect=paired_phase) as phases,
        ):
            payload.worker(self.args)
        return phases

    def test_paired_worker_keeps_all_twelve_rows_and_untouched_test_commands(self):
        phases = self.exercise_paired()
        result = json.loads((self.output / "result.json").read_bytes())
        self.assertEqual(len(result["loops"]), 12)
        self.assertEqual(sum(row["measured"] for row in result["loops"]), 10)
        self.assertEqual(
            result["arms"]["stock"]["median_scenario_runtime_seconds"], 92.5
        )
        self.assertNotIn("median_scenario_runtime_seconds", result)
        self.assertTrue(all(row["status"] == "valid" for row in result["loops"]))
        self.assertEqual(phases.call_count, 24)
        for call in phases.call_args_list[1::2]:
            self.assertEqual(
                call.args[0],
                [
                    str(self.args.python),
                    "-m",
                    "coverage",
                    "run",
                    "-m",
                    "pytest",
                    "tests",
                ],
            )
            self.assertNotIn("PIP_CONSTRAINT", call.args[2])
        self.assertEqual(
            phases.call_args_list[0].args[0], [str(self.args.python), "-m", "build"]
        )
        environment = phases.call_args_list[0].args[2]
        self.assertEqual(
            environment["PIP_CONSTRAINT"],
            (self.output / "build-constraints.txt").resolve().as_uri(),
        )
        self.assertEqual(
            (self.output / "build-constraints.txt").read_bytes(),
            Path(payload.__file__).with_name("build-constraints.txt").read_bytes(),
        )
        self.assertNotEqual(environment["PIP_CACHE_DIR"], environment["UV_CACHE_DIR"])

    def test_paired_worker_contract_accepts_resolved_output_alias(self):
        self.output = self.output / ".." / self.output.name
        self.args.output = self.output
        self.assertNotEqual(self.output.as_uri(), self.output.resolve().as_uri())
        self.test_paired_worker_keeps_all_twelve_rows_and_untouched_test_commands()

    def test_paired_complete_median_is_not_sum_of_separate_phase_medians(self):
        rows = [
            {
                "arm": arm,
                "measured": True,
                "build_seconds": build,
                "test_seconds": test,
                "scenario_runtime_seconds": build + test,
            }
            for arm in ("stock", "uv")
            for build, test in ((1, 100), (2, 200), (3, 300), (4, 1), (5, 2))
        ]
        result = payload.paired_summary(rows)["stock"]
        self.assertEqual(result["median_scenario_runtime_seconds"], 101)
        self.assertNotEqual(
            result["median_scenario_runtime_seconds"],
            result["median_build_seconds"] + result["median_test_seconds"],
        )

    def test_paired_constraint_survives_actual_pip_parser_with_space_paths(self):
        self.output.rename(self.output.with_name("output with spaces"))
        self.output = self.output.with_name("output with spaces")
        self.args.output = self.output
        phases = self.exercise_paired()
        environment = phases.call_args_list[0].args[2]
        probe = (
            "import json;"
            "from pip._internal.commands import create_command;"
            "from pip._internal.req.req_file import parse_requirements;"
            "from pip._internal.network.session import PipSession;"
            "options,_=create_command('install').parse_args([]);"
            "print(json.dumps([r.requirement for path in options.constraints "
            "for r in parse_requirements(path,session=PipSession(),constraint=True)]))"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=self.source,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ["pdm-backend==2.5.0"])

    def test_paired_wrong_outcomes_retain_attempt_and_never_publish_success(self):
        def wrong_outcome(*args):
            result = self.fake_phase(*args)
            if args[-1] == "test":
                (args[-2] / "test.stdout").write_text(
                    "================ 2512 passed, 131 skipped in 90s ================\n",
                    encoding="utf-8",
                )
            return result

        with self.assertRaisesRegex(RuntimeError, "full covered tests failed"):
            self.exercise_paired(side_effect=wrong_outcome)
        rows = json.loads((self.output / "loops.json").read_bytes())
        self.assertEqual(rows[0]["outcomes"], {"passed": 2512, "skipped": 131})
        self.assertFalse((self.output / "result.json").exists())

    def test_paired_artifact_difference_retains_manifests_and_fails(self):
        with self.assertRaisesRegex(RuntimeError, "archive member content"):
            self.exercise_paired(
                archive_effect=[
                    {"package": {"members": {"file": "hash"}}},
                    {"package": {"members": {"file": "changed"}}},
                ]
            )
        self.assertTrue((self.output / "loop-2" / "artifacts.json").exists())
        self.assertFalse((self.output / "result.json").exists())

    def test_paired_source_change_between_iterations_fails(self):
        canonical = {f"canonical-{number}": "hash" for number in range(2557)}
        with self.assertRaisesRegex(RuntimeError, "canonical source changed"):
            self.exercise_paired(snapshot_effect=[canonical, canonical, canonical, {}])
        self.assertFalse((self.output / "result.json").exists())

    def test_paired_survivors_reject_success_and_guardian_timeout_is_bounded(self):
        self.args.worker = False
        self.args.output = self.output / "owned"
        self.args.paired_uv = self.source / "uv.exe"
        self.args.loops = 5
        self.args.guardian = Path(__file__).with_name("owned_process.py")
        failed = owned_process.Receipt(
            returncode=0,
            timed_out=False,
            command_wall=1,
            infrastructure_wall=0,
            ownership_established=True,
            survivors=True,
            cleanup_complete=True,
            errors=(),
        )
        fake_guard = types.SimpleNamespace()
        spec = types.SimpleNamespace(
            name="test_paired_guardian",
            loader=types.SimpleNamespace(exec_module=lambda _: None),
        )

        def finish_with_survivor(*args, **kwargs):
            payload.save(self.args.output / "result.json", {"status": "complete"})
            return failed

        with (
            patch.object(
                payload.importlib.util, "spec_from_file_location", return_value=spec
            ),
            patch.object(
                payload.importlib.util, "module_from_spec", return_value=fake_guard
            ),
            patch.object(
                fake_guard, "run_owned", create=True, side_effect=finish_with_survivor
            ) as run,
            self.assertRaisesRegex(RuntimeError, "complete workload failed"),
        ):
            payload.main(self.args)
        self.assertEqual(run.call_args.kwargs["timeout"], 1000)
        self.assertIn("--paired-uv", run.call_args.args[0])
        receipt = json.loads((self.args.output / "ownership-summary.json").read_bytes())
        self.assertFalse(receipt["succeeded"])
        self.assertEqual(
            json.loads((self.args.output / "result.json").read_bytes())["status"],
            "invalid-owned-lifecycle",
        )


if __name__ == "__main__":
    unittest.main()
