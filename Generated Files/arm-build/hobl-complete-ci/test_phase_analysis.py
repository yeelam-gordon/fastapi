import copy
import json
import os
import shutil
import subprocess
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import phase_analysis as analysis
import run_payload as payload


class AnalysisTests(unittest.TestCase):
    @staticmethod
    def complete_raw():
        events = []
        reports = []

        def span(kind, parent, start, end, nodeid=None, **extra):
            event = {
                "id": len(events),
                "parent": parent,
                "kind": kind,
                "nodeid": nodeid,
                "thread_id": 7,
                "start_ns": start,
                "end_ns": end,
                "elapsed_ns": end - start,
                "cpu_start_ns": start,
                "cpu_end_ns": end,
                "cpu_elapsed_ns": end - start,
                **extra,
            }
            events.append(event)
            return event["id"]

        root = span("pytest_command", None, 0, 1000)
        span("session_start", root, 1, 3)
        span("collection", root, 4, 6)
        loop = span("test_loop", root, 10, 990)
        for number, node in enumerate(("test::first", "test::second", "test::skip")):
            start = 10 + number * 300
            protocol = span("protocol", loop, start, start + 250, node)
            phases = (
                ("setup", "teardown")
                if node.endswith("skip")
                else ("setup", "call", "teardown")
            )
            for index, when in enumerate(phases):
                position = start + 1 + index * 60
                phase = span(when, protocol, position, position + 20, node)
                if when == "setup":
                    fixture = span(
                        "fixture_setup",
                        phase,
                        position + 1,
                        position + 15,
                        fixture="outer",
                        fixture_scope="function",
                        file=__file__,
                        line=1,
                    )
                    span(
                        "fixture_setup",
                        fixture,
                        position + 2,
                        position + 10,
                        fixture="inner",
                        fixture_scope="function",
                        file=__file__,
                        line=2,
                    )
                span(
                    "make_report",
                    protocol,
                    position + 21,
                    position + 30,
                    node,
                    report_when=when,
                )
                span(
                    "log_report",
                    protocol,
                    position + 31,
                    position + 40,
                    node,
                    report_when=when,
                )
                reports.append(
                    {
                        "nodeid": node,
                        "when": when,
                        "outcome": "skipped"
                        if node.endswith("skip") and when == "setup"
                        else "passed",
                        "wasxfail": None,
                    }
                )
        span("session_finish", root, 991, 999)
        return {
            "events": events,
            "reports": reports,
            "collected_nodeids": ["test::first", "test::second", "test::skip"],
            "caller_thread_id": 7,
        }

    @staticmethod
    def lifecycle_raw():
        kinds = (
            "pytest_command",
            "session_start",
            "collection",
            "test_loop",
            "session_finish",
        )
        return {
            "caller_thread_id": 7,
            "collected_nodeids": [],
            "reports": [],
            "events": [
                {
                    "id": index,
                    "parent": None if index == 0 else 0,
                    "kind": kind,
                    "nodeid": None,
                    "thread_id": 7,
                    "start_ns": 0 if index == 0 else index * 2,
                    "end_ns": 100 if index == 0 else index * 2 + 1,
                    "elapsed_ns": 100 if index == 0 else 1,
                    "cpu_start_ns": 0 if index == 0 else index * 2,
                    "cpu_end_ns": 100 if index == 0 else index * 2 + 1,
                    "cpu_elapsed_ns": 100 if index == 0 else 1,
                }
                for index, kind in enumerate(kinds)
            ],
        }

    @classmethod
    def lifecycle_mutations(cls):
        controls = {}
        for index, kind in enumerate(
            ("session_start", "collection", "test_loop", "session_finish"), 1
        ):
            removed = cls.lifecycle_raw()
            removed["events"].pop(index)
            for new_id, row in enumerate(removed["events"]):
                row["id"] = new_id
            controls["missing_" + kind] = removed
            replaced = cls.lifecycle_raw()
            replaced["events"][index]["kind"] = (
                "session_start" if kind == "collection" else "collection"
            )
            controls["count_preserving_missing_" + kind] = replaced
        duplicate = cls.lifecycle_raw()
        duplicate["events"].append(
            {
                **duplicate["events"][2],
                "id": 5,
                "start_ns": 10,
                "end_ns": 11,
                "cpu_start_ns": 10,
                "cpu_end_ns": 11,
            }
        )
        controls["duplicate_collection"] = duplicate
        return controls

    def test_lifecycle_missing_and_duplicate_controls_preserve_integer_accounting(self):
        helper = Path(__file__).parent
        analysis.summarize(self.lifecycle_raw(), helper, helper / "python", 0, 0)
        for name, raw in self.lifecycle_mutations().items():
            with self.subTest(control=name):
                rows = analysis.account(raw)
                self.assertEqual(sum(row["exclusive_ns"] for row in rows), 100)
                self.assertEqual(sum(row["exclusive_cpu_ns"] for row in rows), 100)
                with self.assertRaisesRegex(RuntimeError, "exactly one lifecycle span"):
                    analysis.summarize(raw, helper, helper / "python", 0, 0)

    def test_lifecycle_order_rejected_without_changing_cardinality(self):
        helper = Path(__file__).parent
        raw = self.lifecycle_raw()
        raw["events"][1]["kind"], raw["events"][2]["kind"] = (
            "collection",
            "session_start",
        )
        analysis.account(raw)
        with self.assertRaisesRegex(RuntimeError, "lifecycle order"):
            analysis.summarize(raw, helper, helper / "python", 0, 0)

    def test_exact_node_attribution_rejects_count_preserving_mutations(self):
        helper = Path(__file__).parent
        original = self.complete_raw()
        analysis.summarize(original, helper, helper / "venv" / "bin" / "python", 2, 1)

        def duplicate_protocol(raw):
            for row in raw["events"]:
                if row["nodeid"] == "test::second":
                    row["nodeid"] = "test::first"

        def call_on_skipped_node(raw):
            row = next(r for r in raw["events"] if r["kind"] == "call")
            row["nodeid"] = "test::skip"

        def duplicate_phase(raw):
            row = next(
                r
                for r in raw["events"]
                if r["kind"] == "setup" and r["nodeid"] == "test::second"
            )
            row["nodeid"] = "test::first"

        def duplicate_report_when(raw):
            row = next(
                r
                for r in raw["events"]
                if r["kind"] == "make_report" and r["report_when"] == "call"
            )
            row["report_when"] = "setup"

        def duplicate_log_node(raw):
            row = next(
                r
                for r in raw["events"]
                if r["kind"] == "log_report" and r["nodeid"] == "test::second"
            )
            row["nodeid"] = "test::first"

        for mutate in (
            duplicate_protocol,
            duplicate_phase,
            call_on_skipped_node,
            duplicate_report_when,
            duplicate_log_node,
        ):
            with self.subTest(mutation=mutate.__name__):
                raw = copy.deepcopy(original)
                mutate(raw)
                self.assertEqual(len(raw["events"]), len(original["events"]))
                self.assertEqual(raw["reports"], original["reports"])
                with self.assertRaisesRegex(RuntimeError, "attribution"):
                    analysis.summarize(
                        raw, helper, helper / "venv" / "bin" / "python", 2, 1
                    )

    def test_zero_exit_valid_json_postprocess_warning_is_retained_and_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manifest = root / "manifest.json"
            manifest.write_text("{}", encoding="utf-8")
            args = types.SimpleNamespace(
                output=root / "output",
                source=root,
                python=Path(__file__),
                manifest=manifest,
                style="windows",
            )
            raw = self.complete_raw()
            diagnostic = "CoverageWarning: saved-data diagnostic\n"

            def execute(command, **kwargs):
                if kwargs.get("capture_output"):
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        json.dumps({"shards": [{}, {}], "contexts": 2}),
                        diagnostic,
                    )
                (
                    args.output / "analysis" / "private" / "raw-boundaries.json"
                ).write_text(json.dumps(raw), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0)

            with (
                patch.object(analysis.subprocess, "run", side_effect=execute),
                patch.object(analysis, "summarize", return_value={}),
                patch.object(payload, "snapshot", return_value={}),
                self.assertRaisesRegex(RuntimeError, "postprocess diagnostics"),
            ):
                analysis.run(args, {"PYTHONPATH": "./docs_src"}, {})
            self.assertEqual(
                (args.output / "analysis" / "postprocess.stderr").read_text(),
                diagnostic,
            )
            self.assertFalse((args.output / "result.json").exists())
            self.assertFalse((args.output / "analysis" / "summary.json").exists())

    def test_account_rejects_bad_thread_overlap_and_duration(self):
        root = {
            "id": 0,
            "parent": None,
            "kind": "pytest_command",
            "thread_id": 7,
            "start_ns": 0,
            "end_ns": 20,
            "elapsed_ns": 20,
        }
        child = {
            "id": 1,
            "parent": 0,
            "kind": "setup",
            "thread_id": 7,
            "start_ns": 2,
            "end_ns": 8,
            "elapsed_ns": 6,
        }
        raw = {"caller_thread_id": 7, "events": [root, child]}
        for row in raw["events"]:
            row.update(
                cpu_start_ns=row["start_ns"],
                cpu_end_ns=row["end_ns"],
                cpu_elapsed_ns=row["elapsed_ns"],
            )
        self.assertEqual(sum(r["exclusive_ns"] for r in analysis.account(raw)), 20)
        for field, value in (
            ("thread_id", 9),
            ("end_ns", 30),
            ("elapsed_ns", -1),
            ("start_ns", 2.0),
        ):
            bad = copy.deepcopy(raw)
            bad["events"][1][field] = value
            with self.assertRaises(RuntimeError):
                analysis.account(bad)
        bad = copy.deepcopy(raw)
        bad["events"].append({**child, "id": 2})
        with self.assertRaisesRegex(RuntimeError, "overlapping"):
            analysis.account(bad)

    def test_analysis_rejects_impossible_hook_nesting(self):
        helper = Path(__file__).parent
        raw = {
            "caller_thread_id": 7,
            "events": [
                {
                    "id": 0,
                    "parent": None,
                    "kind": "pytest_command",
                    "thread_id": 7,
                    "start_ns": 0,
                    "end_ns": 20,
                    "elapsed_ns": 20,
                    "nodeid": None,
                },
                {
                    "id": 1,
                    "parent": 0,
                    "kind": "collection",
                    "thread_id": 7,
                    "start_ns": 2,
                    "end_ns": 8,
                    "elapsed_ns": 6,
                    "nodeid": None,
                },
            ],
            "collected_nodeids": [],
            "reports": [],
        }
        for row in raw["events"]:
            row.update(
                cpu_start_ns=row["start_ns"],
                cpu_end_ns=row["end_ns"],
                cpu_elapsed_ns=row["elapsed_ns"],
            )
        for kind, start in (
            ("session_start", 0),
            ("test_loop", 9),
            ("session_finish", 11),
        ):
            raw["events"].append(
                {
                    **raw["events"][1],
                    "id": len(raw["events"]),
                    "kind": kind,
                    "start_ns": start,
                    "end_ns": start + 1,
                    "elapsed_ns": 1,
                    "cpu_start_ns": start,
                    "cpu_end_ns": start + 1,
                    "cpu_elapsed_ns": 1,
                }
            )
        analysis.summarize(raw, helper, helper / "venv" / "bin" / "python", 0, 0)
        raw["events"].append(
            {
                **raw["events"][1],
                "id": 5,
                "parent": 1,
                "kind": "terminal_summary",
                "start_ns": 3,
                "end_ns": 4,
                "elapsed_ns": 1,
                "cpu_start_ns": 3,
                "cpu_end_ns": 4,
                "cpu_elapsed_ns": 1,
            }
        )
        with self.assertRaisesRegex(RuntimeError, "hook nesting"):
            analysis.summarize(raw, helper, helper / "venv" / "bin" / "python", 0, 0)

    def test_full_outcome_parser_rejects_failures_duplicates_and_missing_teardown(self):
        reports = [
            {
                "nodeid": "test::pass",
                "when": when,
                "outcome": "passed",
                "wasxfail": None,
            }
            for when in ("setup", "call", "teardown")
        ] + [
            {"nodeid": "test::skip", "when": when, "outcome": outcome, "wasxfail": None}
            for when, outcome in (("setup", "skipped"), ("teardown", "passed"))
        ]
        raw = {"collected_nodeids": ["test::pass", "test::skip"], "reports": reports}
        self.assertEqual(analysis.outcomes(raw, 1, 1), {"passed": 1, "skipped": 1})
        for mutate in (
            lambda r: r["reports"].pop(),
            lambda r: r["reports"].append(r["reports"][0]),
            lambda r: r["reports"][1].update(outcome="failed"),
        ):
            bad = copy.deepcopy(raw)
            mutate(bad)
            with self.assertRaises(RuntimeError):
                analysis.outcomes(bad, 1, 1)

    def test_observer_hash_and_default_schedule_unchanged(self):
        self.assertEqual(
            payload.digest(Path(analysis.__file__).with_name("hobl_phase_observer.py")),
            analysis.OBSERVER_SHA256,
        )
        self.assertEqual(payload.schedule(False, 5), [("stock", True)] * 5)

    def test_env_preserves_normal_plugins_and_original_context(self):
        helper = Path(analysis.__file__).parent
        folder = helper
        env = {
            "PYTHONPATH": "./docs_src",
            "PYTEST_PLUGINS": "normal_plugin",
            "CONTEXT": "",
        }
        observed = analysis.diagnostic_env(env, folder, helper, "windows")
        self.assertEqual(env["PYTHONPATH"], "./docs_src")
        self.assertEqual(
            observed["PYTEST_PLUGINS"], "normal_plugin,hobl_phase_observer"
        )
        self.assertEqual(observed["CONTEXT"], "")
        self.assertNotIn("PYTEST_DISABLE_PLUGIN_AUTOLOAD", observed)
        with patch.object(Path, "write_text") as write:
            mac = analysis.diagnostic_env(env, folder, helper, "macos")
        self.assertIn('command coverage "$@"', write.call_args.args[0])
        self.assertIn("BASH_ENV", mac)

    def test_public_paths_resolve_aliases_without_exposing_home(self):
        root = Path(__file__).parent.resolve()
        alias = root / "not-created" / ".." / "test_phase_analysis.py"
        self.assertEqual(
            analysis.public_file(str(alias), root, root / "venv" / "bin" / "python"),
            "source/test_phase_analysis.py",
        )
        self.assertEqual(
            analysis.public_file(
                str(Path.home() / "unknown.py"), root, root / "venv" / "bin" / "python"
            ),
            "external/unknown.py",
        )

    def test_mac_shell_preserves_plugin_import_when_script_resets_pythonpath(self):
        bash = (
            Path(r"C:\Program Files\Git\bin\bash.exe")
            if os.name == "nt"
            else Path(shutil.which("bash") or "/missing-bash")
        )
        if not bash.exists():
            self.skipTest("local bash unavailable")
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "private").mkdir()
            env = analysis.diagnostic_env(
                {"PYTHONPATH": "./docs_src"}, root, root, "macos"
            )
            (root / "coverage").write_text(
                '#!/bin/bash\nprintf "%s\\n" "$PYTHONPATH" "$@"\n', encoding="utf-8"
            )
            (root / "coverage").chmod(0o755)
            env = {**os.environ, **env}
            env["BASH_ENV"] = (root / "private" / "observer-env.bash").as_posix()
            binary_dir = (
                "/" + root.drive[0].lower() + root.as_posix()[2:]
                if os.name == "nt"
                else root.as_posix()
            )
            probe = subprocess.run(
                [
                    str(bash),
                    "--noprofile",
                    "--norc",
                    "-c",
                    'export PATH="$HOBL_TEST_BIN:$PATH"; export PYTHONPATH=./docs_src; coverage run -m pytest tests',
                ],
                env={**env, "HOBL_TEST_BIN": binary_dir},
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(probe.returncode, 0, probe.stderr)
            self.assertEqual(
                probe.stdout.splitlines(),
                [str(root) + ":./docs_src", "run", "-m", "pytest", "tests"],
            )

    def test_guardian_propagates_analysis_flag_and_bound(self):
        import types

        args = types.SimpleNamespace(
            source=Path.cwd(),
            python=Path(__file__),
            output=Path.cwd() / "unused-analysis-output",
            manifest=Path(__file__),
            guardian=Path(payload.__file__).with_name("owned_process.py"),
            worker=False,
            loops=5,
            index="https://pypi.org/simple",
            style="windows",
            prep_qualification="test",
            phase_analysis=True,
        )
        receipt = types.SimpleNamespace(succeeded=True)
        with (
            patch.object(Path, "exists", return_value=False),
            patch.object(Path, "mkdir"),
            patch.object(payload, "save"),
            patch.object(payload.dataclasses, "asdict", return_value={}),
            patch.object(Path, "read_text", return_value=json.dumps({})),
            patch.object(
                Path,
                "read_bytes",
                return_value=b'{"status":"awaiting-owned-natural-drain"}',
            ),
            patch.object(payload.importlib.util, "spec_from_file_location") as spec,
            patch.object(payload.importlib.util, "module_from_spec") as module,
        ):
            for key, value in {
                "returncode": 0,
                "timed_out": False,
                "ownership_established": True,
                "survivors": [],
                "cleanup_complete": True,
                "errors": [],
            }.items():
                setattr(receipt, key, value)
            module.return_value.run_owned.return_value = receipt
            with patch.object(
                payload,
                "digest",
                return_value="45d6db4f6452c4f7116ca23c6e2aa74cda90a15548bd5c9bb3b3574973ef458e",
            ):
                payload.main(args)
        command = module.return_value.run_owned.call_args.args[0]
        self.assertIn("--phase-analysis", command)
        self.assertEqual(module.return_value.run_owned.call_args.kwargs["timeout"], 600)
        spec.assert_called_once()

    def test_cpu_scalar_negative_and_nested_conservation(self):
        raw = self.complete_raw()
        rows = analysis.account(raw)
        self.assertEqual(
            sum(r["exclusive_cpu_ns"] for r in rows), rows[0]["cpu_elapsed_ns"]
        )
        self.assertTrue(
            all(
                type(r["exclusive_cpu_ns"]) is int and r["exclusive_cpu_ns"] >= 0
                for r in rows
            )
        )
        for value in (-1, 0.5, True):
            bad = copy.deepcopy(raw)
            bad["events"][1]["cpu_elapsed_ns"] = value
            with self.assertRaises(RuntimeError):
                analysis.account(bad)
        bad = copy.deepcopy(raw)
        bad["events"][1]["cpu_end_ns"] = 1001
        bad["events"][1]["cpu_elapsed_ns"] = 1000
        with self.assertRaisesRegex(RuntimeError, "CPU children"):
            analysis.account(bad)

    def test_analysis_workflow_uses_current_candidate_without_stock_bootstrap(self):
        helper = Path(__file__).parent
        workflow = (
            helper.parents[2] / ".github" / "workflows" / "arm-build-diagnostics.yml"
        )
        if not workflow.exists():
            return
        text = workflow.read_text()
        self.assertIn(
            "matrix.platform == 'macos' && inputs.platform != 'hobl-python313-gap-analysis'",
            text,
        )
        self.assertIn("$paired = @('--phase-analysis')", text)
        self.assertIn("evidence/analysis/**", text)
        bootstrap = (helper / "bootstrap.ps1").read_text()
        self.assertIn("$python = $env:HOBL_CANDIDATE_BASE", bootstrap)
        self.assertIn(
            "$env:RUNNER_OS -eq 'Windows' -and $env:HOBL_MODE -ne 'hobl-python313-gap-analysis'",
            bootstrap,
        )

    def test_quantized_cpu_wall_difference_is_signed_not_clamped(self):
        raw = self.complete_raw()
        raw["events"][0]["cpu_end_ns"] += 1
        raw["events"][0]["cpu_elapsed_ns"] += 1
        result = analysis.account(raw)
        self.assertEqual(result[0]["wall_minus_caller_cpu_ns"], -1)
        raw["events"][0]["cpu_end_ns"] += analysis.CPU_WALL_TOLERANCE_NS
        raw["events"][0]["cpu_elapsed_ns"] += analysis.CPU_WALL_TOLERANCE_NS
        with self.assertRaisesRegex(RuntimeError, "quantization tolerance"):
            analysis.account(raw)

    def test_canonical_comparison_retains_excluded_and_reportable_differences(self):
        left = {
            "files": {"a.py": {"1": ["one"], "2": ["two"]}},
            "contexts": ["one", "two"],
            "excluded": {"a.py": [1]},
        }
        right = copy.deepcopy(left)
        del right["files"]["a.py"]["1"]
        result = analysis.compare_coverage(left, right)
        self.assertTrue(result["reportable_associations_equal"])
        self.assertTrue(result["raw_differences"][0]["excluded"])
        del right["files"]["a.py"]["2"]
        self.assertFalse(
            analysis.compare_coverage(left, right)["reportable_associations_equal"]
        )
        del right["files"]["a.py"]
        with self.assertRaisesRegex(RuntimeError, "file set differs"):
            analysis.compare_coverage(left, right)


if __name__ == "__main__":
    unittest.main()
