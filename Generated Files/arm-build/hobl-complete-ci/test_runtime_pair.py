import contextlib
import copy
import hashlib
import io
import json
import sys
import tempfile
import types
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

import owned_process
import run_payload as payload
import runtime_pair
import test_payload as fixtures


class RuntimePairTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PayloadTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.args.candidate_python = (
            self.fixture.source / "candidate" / "python.exe"
        )
        self.current = {
            "files": {f"file-{n}.py": {"1": ["context"]} for n in range(863)},
            "contexts": [f"context-{n}" for n in range(1409)],
            "excluded": {},
        }

    def exercise(self, **kwargs):
        def probe(python, action, source, argument, env, folder):
            if action == "identity":
                return {"packages": {"coverage": "7.17.0"}, "executable": str(python)}
            return self.current

        with (
            patch.object(runtime_pair, "probe", side_effect=probe),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            return self.fixture.exercise_paired(**kwargs)

    def test_both_runtimes_use_common_uv_and_private_coverage_and_keep_dist_through_tests(
        self,
    ):
        def phase(*args):
            if args[-1] == "test":
                self.assertTrue((self.fixture.source / "dist").is_dir())
            return self.fixture.fake_phase(*args)

        calls = self.exercise(side_effect=phase).call_args_list
        rows = json.loads((self.fixture.output / "loops.json").read_bytes())
        self.assertEqual(len(rows), 12)
        self.assertEqual(
            [r["arm"] for r in rows[:6]],
            ["stock", "candidate", "stock", "candidate", "candidate", "stock"],
        )
        self.assertEqual(sum(r["measured"] for r in rows), 10)
        for row, build, test in zip(rows, calls[::2], calls[1::2], strict=True):
            python = (
                self.fixture.args.python
                if row["arm"] == "stock"
                else self.fixture.args.candidate_python
            )
            command = build.args[0]
            self.assertEqual(command[1], "build")
            self.assertEqual(command[command.index("--python") + 1], str(python))
            self.assertEqual(
                test.args[0],
                [str(python), "-m", "coverage", "run", "-m", "pytest", "tests"],
            )
            self.assertIn(f"loop-{row['loop']}", test.args[2]["COVERAGE_FILE"])
            self.assertIn(row["arm"], test.args[2]["HOME"])
            self.assertNotIn("PIP_CONSTRAINT", build.args[2])
        result = json.loads((self.fixture.output / "result.json").read_bytes())
        self.assertEqual(result["status"], "pending-owned-lifecycle")
        self.assertEqual(set(result["arms"]), {"stock", "candidate"})

    def test_mac_keeps_canonical_script_and_docs_path(self):
        self.fixture.args.style = "macos"
        calls = self.exercise().call_args_list
        for call in calls[1::2]:
            self.assertEqual(call.args[0], ["bash", "scripts/test.sh"])
            self.assertEqual(call.args[2]["PYTHONPATH"], "./docs_src")

    def test_runtime_outcome_failure_keeps_dist_and_rejects_score(self):
        def phase(*args):
            value = self.fixture.fake_phase(*args)
            if args[-1] == "test":
                (args[-2] / "test.stdout").write_text(
                    "=== 2510 passed, 133 skipped ===\n"
                )
            return value

        with self.assertRaisesRegex(RuntimeError, "full covered tests"):
            self.exercise(side_effect=phase)
        self.assertTrue((self.fixture.source / "dist").exists())
        self.assertFalse((self.fixture.output / "result.json").exists())

    def test_runtime_lifecycle_gates_final_success_and_uses_1100_second_bound(self):
        args = self.fixture.args
        args.worker = False
        args.output = self.fixture.output / "owned"
        args.paired_uv = self.fixture.source / "uv.exe"
        args.guardian = Path(__file__).with_name("owned_process.py")
        args.loops = 5
        receipt = owned_process.Receipt(
            returncode=0,
            timed_out=False,
            command_wall=1,
            infrastructure_wall=0,
            ownership_established=True,
            survivors=False,
            cleanup_complete=True,
            errors=(),
        )
        fake_guard = types.SimpleNamespace()
        spec = types.SimpleNamespace(
            name="runtime_test_guard",
            loader=types.SimpleNamespace(exec_module=lambda _: None),
        )

        def finish(*_args, **_kwargs):
            payload.save(
                args.output / "result.json", {"status": "pending-owned-lifecycle"}
            )
            return receipt

        with (
            patch.object(
                payload.importlib.util, "spec_from_file_location", return_value=spec
            ),
            patch.object(
                payload.importlib.util, "module_from_spec", return_value=fake_guard
            ),
            patch.object(
                fake_guard, "run_owned", create=True, side_effect=finish
            ) as run,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            payload.main(args)
        self.assertEqual(run.call_args.kwargs["timeout"], 1100)
        self.assertIn("--candidate-python", run.call_args.args[0])
        self.assertEqual(
            json.loads((args.output / "result.json").read_bytes())["status"], "complete"
        )

    def test_pin_comparison_normalizes_names_but_not_versions_or_omissions(self):
        runtime_pair.compare_pins(
            {"Pydantic_Core": "2.50.1"}, {"pydantic-core": "2.50.1"}
        )
        for value in ({}, {"pydantic-core": "2.50.0"}):
            with self.assertRaisesRegex(RuntimeError, "pins differ"):
                runtime_pair.compare_pins({"pydantic_core": "2.50.1"}, value)

    def test_guard_rejects_unknown_source_and_transports_exact_patch(self):
        with self.assertRaisesRegex(RuntimeError, "original guard hash"):
            runtime_pair.corrected(b"unknown")
        patch_bytes = (
            Path(runtime_pair.__file__).with_name("common-guard.patch").read_bytes()
        )
        self.assertEqual(
            hashlib.sha256(patch_bytes).hexdigest(), runtime_pair.PATCH_SHA
        )

    def test_excluded_differences_remain_raw_but_reportable_losses_rejected(self):
        old = {
            "files": {"a.py": {"1": ["a"], "2": ["b"]}},
            "contexts": ["a", "b"],
            "excluded": {"a.py": [1]},
        }
        new = copy.deepcopy(old)
        del new["files"]["a.py"]["1"]
        differences = runtime_pair.compare(old, new)
        self.assertTrue(differences[0]["excluded"])
        del new["files"]["a.py"]["2"]
        self.assertFalse(all(d["excluded"] for d in runtime_pair.compare(old, new)))
        new["contexts"] = ["a"]
        with self.assertRaisesRegex(RuntimeError, "context set differs"):
            runtime_pair.compare(old, new)

    def test_oracle_missing_shard_fails_before_coverage_import(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "private").mkdir()
            with patch.dict(sys.modules, {"coverage": None}):
                with self.assertRaisesRegex(RuntimeError, "exactly main and CLI"):
                    runtime_pair.oracle(root, root)

    def test_oracle_warning_is_retained_and_fails_closed(self):
        source = self.fixture.source.resolve()
        folder = self.fixture.output
        (folder / "private").mkdir()
        for name in (".coverage.main", ".coverage.cli"):
            (folder / "private" / name).write_bytes(b"untouched shard")
        filename = str(self.fixture.original.resolve())
        data = types.SimpleNamespace(
            read=lambda: None,
            update=lambda part: None,
            has_arcs=lambda: False,
            measured_files=lambda: [filename],
            contexts_by_lineno=lambda _: {1: ["test"]},
        )
        options = {
            "branch": False,
            "parallel": True,
            "dynamic_context": "test_function",
            "source": ["docs_src", "tests", "fastapi"],
            "omit": [
                "docs_src/response_model/tutorial003_04.py",
                "docs_src/response_model/tutorial003_04_py310.py",
            ],
        }

        def analysis(_):
            warnings.warn("oracle warning", stacklevel=1)
            return filename, [1], [], [], ""

        config = types.SimpleNamespace(
            get_option=lambda key: options[key.removeprefix("run:")],
            analysis2=analysis,
        )
        coverage = types.SimpleNamespace(
            Coverage=lambda **_: config,
            CoverageData=lambda **_: data,
        )
        with patch.dict(sys.modules, {"coverage": coverage}):
            with self.assertRaisesRegex(RuntimeError, "coverage warning"):
                runtime_pair.oracle(folder, source)
        self.assertEqual(
            json.loads((folder / "private" / "coverage-warnings.json").read_bytes()),
            ["oracle warning"],
        )

    def test_invalid_runtime_context_fails_before_coverage_import(self):
        with patch.dict(sys.modules, {"coverage": None}):
            with self.assertRaisesRegex(RuntimeError, "runtime version"):
                runtime_pair.identity(self.fixture.source, "0.0.0")

    def test_workflow_runtime_labels_and_provisioning_are_optional(self):
        workflow = (
            Path(__file__).parents[3]
            / ".github"
            / "workflows"
            / "arm-build-diagnostics.yml"
        )
        if not workflow.exists():
            return  # The workflow tools checkout intentionally contains helpers only.
        text = workflow.read_text()
        self.assertIn('"runner":"macos-14"', text)
        self.assertIn('"runner":"macos-15"', text)
        self.assertIn("timeout-minutes: 20", text)
        self.assertIn("--candidate-python", text)
        self.assertEqual(
            text.count(
                "uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
            ),
            2,
        )


if __name__ == "__main__":
    unittest.main()
