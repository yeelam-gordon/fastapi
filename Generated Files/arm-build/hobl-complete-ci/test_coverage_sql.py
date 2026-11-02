import copy
import json
import os
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import coverage_sql as sql
import owned_process
import run_payload as payload
import test_payload


class CoverageSQLTests(unittest.TestCase):
    def test_patch_preserves_native_newline_convention(self):
        patch_bytes = Path(sql.__file__).with_name("candidate-v2.patch").read_bytes()
        import hashlib

        for newline in (b"\n", b"\r\n"):
            raw = (sql.OLD + "\n").encode().replace(b"\n", newline)
            expected_hash = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
            candidate_hash = hashlib.sha256((sql.NEW + "\n").encode()).hexdigest()
            with (
                patch.object(sql, "OWNER_SHA", expected_hash),
                patch.object(sql, "CANDIDATE_SHA", candidate_hash),
            ):
                result = sql.transform(raw, patch_bytes)
            self.assertEqual(result, (sql.NEW + "\n").encode().replace(b"\n", newline))

    def test_patch_rejects_bad_owner_and_bad_patch(self):
        patch_bytes = Path(sql.__file__).with_name("candidate-v2.patch").read_bytes()
        with self.assertRaisesRegex(RuntimeError, "owner source"):
            sql.transform(b"unexpected", patch_bytes)
        with self.assertRaisesRegex(RuntimeError, "incorrect V2 patch"):
            sql.transform(b"unexpected", b"unexpected")

    def test_oracle_requires_exact_associations_not_equal_counts(self):
        baseline = {
            "files": {"tests/a.py": {"14": ["a"], "79": ["b"]}},
            "contexts": ["a", "b"],
            "excluded": {"tests/a.py": [14]},
        }
        current = copy.deepcopy(baseline)
        current["files"]["tests/a.py"]["79"] = ["a"]
        differences = sql.compare(baseline, current)
        self.assertEqual(len(differences), 1)
        self.assertFalse(differences[0]["excluded"])
        current["contexts"] = ["a"]
        with self.assertRaisesRegex(RuntimeError, "context set"):
            sql.compare(baseline, current)

    def test_missing_cli_shard_fails_closed(self):
        fixture = test_payload.PayloadTests()
        fixture.setUp()
        try:
            with self.assertRaisesRegex(RuntimeError, "two|exactly main"):
                sql.oracle(fixture.output, fixture.source)
        finally:
            fixture.doCleanups()

    def test_environment_both_arms_preserves_overlay_at_mac_boundary(self):
        fixture = test_payload.PayloadTests()
        fixture.setUp()
        try:
            treatment = object.__new__(sql.Treatment)
            treatment.root = fixture.output / "overlays"
            treatment.args = types.SimpleNamespace(style="macos", source=fixture.source)
            for arm in ("stock", "candidate"):
                folder = fixture.output / arm
                folder.mkdir()
                with patch.object(treatment, "run", return_value={"arm": arm}):
                    env = treatment.environment({}, folder, arm)
                self.assertEqual(
                    env["PYTHONPATH"].split(os.pathsep),
                    [str(treatment.root / arm), "./docs_src"],
                )
                self.assertIn(
                    'command coverage "$@"', Path(env["BASH_ENV"]).read_text()
                )
                self.assertNotIn("observer", Path(env["BASH_ENV"]).read_text())
        finally:
            fixture.doCleanups()

    def test_optional_worker_uses_common_build_candidate_labels_and_post_test_gate(
        self,
    ):
        fixture = test_payload.PayloadTests()
        fixture.setUp()
        fixture.args.coverage_sql = True
        treatment = unittest.mock.Mock()
        treatment.environment.side_effect = lambda env, folder, arm: {
            **env,
            "TREATMENT": arm,
        }
        try:
            with patch.object(sql, "Treatment", return_value=treatment):
                phases = fixture.exercise_paired()
            rows = json.loads((fixture.output / "loops.json").read_bytes())
            self.assertEqual([row["arm"] for row in rows[:2]], ["stock", "candidate"])
            self.assertEqual(sum(row["measured"] for row in rows), 10)
            for call in phases.call_args_list[::2]:
                self.assertEqual(
                    call.args[0][:2], [str(fixture.args.paired_uv), "build"]
                )
            self.assertEqual(treatment.finish.call_count, 12)
            result = json.loads((fixture.output / "result.json").read_bytes())
            self.assertEqual(set(result["arms"]), {"stock", "candidate"})
            self.assertEqual(result["status"], "awaiting-owned-lifecycle")
        finally:
            fixture.doCleanups()

    def test_false_outcome_does_not_postprocess_or_move_archives(self):
        fixture = test_payload.PayloadTests()
        fixture.setUp()
        fixture.args.coverage_sql = True
        treatment = unittest.mock.Mock()
        treatment.environment.side_effect = lambda env, *args: env

        def incorrect(*args):
            result = fixture.fake_phase(*args)
            if args[-1] == "test":
                (args[-2] / "test.stdout").write_text(
                    "=== 2512 passed, 130 skipped ===\n"
                )
            return result

        try:
            with patch.object(sql, "Treatment", return_value=treatment):
                with self.assertRaisesRegex(RuntimeError, "not a valid score"):
                    fixture.exercise_paired(side_effect=incorrect)
            treatment.finish.assert_not_called()
            self.assertTrue((fixture.source / "dist").exists())
            self.assertFalse((fixture.output / "result.json").exists())
        finally:
            fixture.doCleanups()

    def test_postprocessing_error_cannot_publish_success(self):
        fixture = test_payload.PayloadTests()
        fixture.setUp()
        fixture.args.coverage_sql = True
        treatment = unittest.mock.Mock()
        treatment.environment.side_effect = lambda env, *args: env
        treatment.finish.side_effect = RuntimeError("new private warning")
        try:
            with patch.object(sql, "Treatment", return_value=treatment):
                with self.assertRaisesRegex(RuntimeError, "new private warning"):
                    fixture.exercise_paired()
            self.assertFalse((fixture.output / "result.json").exists())
            self.assertTrue((fixture.source / "dist").exists())
        finally:
            fixture.doCleanups()

    def test_private_postprocessing_stderr_fails_closed(self):
        fixture = test_payload.PayloadTests()
        fixture.setUp()
        try:
            (fixture.output / "private").mkdir()
            treatment = object.__new__(sql.Treatment)
            treatment.args = fixture.args
            result = types.SimpleNamespace(
                returncode=0, stdout="{}", stderr="warning with private path\n"
            )
            with patch.object(sql.subprocess, "run", return_value=result):
                with self.assertRaisesRegex(RuntimeError, "failed; private stderr"):
                    treatment.run("oracle", [], {}, fixture.output)
            self.assertTrue(
                (fixture.output / "private" / "coverage-oracle.stderr").exists()
            )
            self.assertFalse((fixture.output / "coverage-oracle.stderr").exists())
        finally:
            fixture.doCleanups()

    def test_optional_lifecycle_bound_and_promotion_require_clean_drain(self):
        for survivors in (False, True):
            fixture = test_payload.PayloadTests()
            fixture.setUp()
            args = fixture.args
            args.coverage_sql = True
            args.worker = False
            args.paired_uv = fixture.source / "uv.exe"
            args.loops = 5
            args.output = fixture.output / "owned"
            args.guardian = Path(payload.__file__).with_name("owned_process.py")
            receipt = owned_process.Receipt(0, False, 1, 0, True, survivors, True, ())
            fake_guard = types.SimpleNamespace()
            spec = types.SimpleNamespace(
                name="coverage_sql_guard",
                loader=types.SimpleNamespace(exec_module=lambda _: None),
            )

            def finish(*unused, args=args, receipt=receipt, **kwargs):
                payload.save(
                    args.output / "result.json", {"status": "awaiting-owned-lifecycle"}
                )
                return receipt

            try:
                with (
                    patch.object(
                        payload.importlib.util,
                        "spec_from_file_location",
                        return_value=spec,
                    ),
                    patch.object(
                        payload.importlib.util,
                        "module_from_spec",
                        return_value=fake_guard,
                    ),
                    patch.object(
                        fake_guard, "run_owned", create=True, side_effect=finish
                    ) as run,
                ):
                    if survivors:
                        with self.assertRaisesRegex(
                            RuntimeError, "complete workload failed"
                        ):
                            payload.main(args)
                    else:
                        payload.main(args)
                self.assertEqual(run.call_args.kwargs["timeout"], 1100)
                self.assertIn("--coverage-sql", run.call_args.args[0])
                self.assertEqual(
                    json.loads((args.output / "result.json").read_bytes())["status"],
                    "invalid-owned-lifecycle" if survivors else "complete",
                )
            finally:
                fixture.doCleanups()


if __name__ == "__main__":
    unittest.main()
