"""Source-only mocks; no uv, SDK, backend, process or package execution."""

import ast
import copy
import json
import shutil
import unittest
import uuid
from unittest.mock import patch

import bootstrap
import verify_raw


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.root = bootstrap.HERE / ("test-work-ci-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)

    def fixture(self, target):
        sdk = (
            self.root
            / "install"
            / (
                "cpython-3.13.15-windows-aarch64-none"
                if target == "win32"
                else "cpython-3.13.15-macos-aarch64-none"
            )
        )
        sdk.mkdir(parents=True)
        venv = self.root / "venv"
        venv.mkdir()
        executable = venv / (
            "Scripts\\python.exe" if target == "win32" else "bin/python"
        )
        base = sdk / ("python.exe" if target == "win32" else "bin/python3.13")
        observed = {
            "platform": target,
            "version_info": [3, 13, 15],
            "machine": "arm64",
            "platform_tag": "win-arm64" if target == "win32" else "macosx-11.0-arm64",
            "gil": True,
            "gil_disabled": 0,
            "jit_build": 0,
            "jit_enabled": False,
            "debug": 0,
            "optimization": 0,
            "isolated": 1,
            "dont_write_bytecode": True,
            "pycache_prefix": None,
            "bootstrap_environment": {},
            "prefix": str(venv),
            "base_prefix": str(sdk),
            "executable": str(executable),
            "base_executable": str(base),
            "cfg_utf8": "include-system-site-packages = false\nhome = "
            + str(sdk if target == "win32" else sdk / "bin")
            + "\n",
            "venv_links": {}
            if target == "win32"
            else {
                "python": str(sdk / "bin" / "python3"),
                "python3": "python",
                "python3.13": "python",
            },
        }
        return {"install": sdk.parent, "venv": venv}, observed, str(base)

    def test_setup_location_handoff_logs_names_not_values(self):
        env, record = bootstrap.handoff(
            {
                "PATH": "system",
                "pythonLocation": "private-location",
                "Python3_ROOT_DIR": "another-location",
                "UV_TOOL_DIR": "tool-location",
            }
        )
        self.assertEqual(env, {"PATH": "system"})
        self.assertEqual(
            record,
            {
                "removed_location_variable_names": [
                    "Python3_ROOT_DIR",
                    "UV_TOOL_DIR",
                    "pythonLocation",
                ],
                "values_retained": False,
            },
        )

    def test_unknown_overrides_are_fatal_not_stripped(self):
        for name in (
            "UV_CACHE_DIR",
            "UV_INSECURE_HOST",
            "PYTHONPATH",
            "PYTHONHOME",
            "PIP_CONFIG_FILE",
            "PIP_INDEX_URL",
            "COVERAGE_PROCESS_START",
            "COV_CORE_SOURCE",
            "SOURCE_DATE_EPOCH",
            "PYTEST_ADDOPTS",
            "pythonlocation",
        ):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Unknown"):
                bootstrap.handoff({name: "do-not-use"})

    def test_windows_receipt_uses_observed_base_not_requested_prefix(self):
        paths, observed, found = self.fixture("win32")
        associations = bootstrap.observe_runtime(observed, found, paths, "win32")
        self.assertEqual(associations["base_python"], observed["base_executable"])
        observed["base_prefix"] = str(self.root / "invented-request")
        (self.root / "invented-request").mkdir()
        with self.assertRaises(ValueError):
            bootstrap.observe_runtime(observed, found, paths, "win32")

    def test_darwin_base_is_actual_raw_venv_link_not_terminal_base_executable(self):
        paths, observed, found = self.fixture("darwin")
        with (
            patch.object(
                bootstrap.Path,
                "resolve",
                lambda path, **kwargs: (
                    path if path.name != "python3" else path.with_name("python3.13")
                ),
            ),
            patch.object(bootstrap.reference, "runtime_input_hashes") as scan,
        ):
            associations = bootstrap.observe_runtime(observed, found, paths, "darwin")
        self.assertEqual(associations["base_python"], observed["venv_links"]["python"])
        self.assertNotEqual(associations["base_python"], observed["base_executable"])
        self.assertEqual(scan.call_count, 1)

    def test_darwin_unexpected_link_is_not_resolved_into_acceptance(self):
        paths, observed, found = self.fixture("darwin")
        observed["venv_links"]["python"] = str(self.root / "elsewhere" / "python3.13")
        with self.assertRaisesRegex(ValueError, "finite link"):
            bootstrap.observe_runtime(observed, found, paths, "darwin")

    def test_darwin_probe_rejects_windows_arm64_abi_tag(self):
        paths, observed, found = self.fixture("darwin")
        observed["platform_tag"] = "win-arm64"
        with self.assertRaisesRegex(ValueError, "ABI"):
            bootstrap.observe_runtime(observed, found, paths, "darwin")

    def test_probe_positive_runtime_checks_reject_wrong_patch_isa_or_flags(self):
        paths, original, found = self.fixture("win32")
        for field, value in (
            ("version_info", [3, 13, 14]),
            ("machine", "AMD64"),
            ("gil", False),
            ("jit_enabled", True),
            ("optimization", 1),
            ("dont_write_bytecode", False),
            ("bootstrap_environment", {"PYTHONPATH": "override"}),
        ):
            observed = copy.deepcopy(original)
            observed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                bootstrap.observe_runtime(observed, found, paths, "win32")

    def test_alias_workspace_and_non_c_windows_paths_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "must be C"):
            bootstrap.fixed_paths(self.root, "win32")
        with patch.object(bootstrap.Path, "resolve", return_value=self.root / "other"):
            with self.assertRaisesRegex(ValueError, "canonical"):
                bootstrap.fixed_paths(self.root, "darwin")

    def test_failed_owned_command_retains_receipt_and_never_retries(self):
        preparation = bootstrap.Preparation(self.root, {"PATH": "system"})
        receipt = bootstrap.owned_process.Receipt(
            returncode=1,
            timed_out=False,
            command_wall=0.1,
            infrastructure_wall=0.01,
            ownership_established=True,
            survivors=False,
            cleanup_complete=True,
            errors=(),
        )
        with patch.object(
            bootstrap.owned_process, "run_owned", return_value=receipt
        ) as run:
            with self.assertRaisesRegex(ValueError, "first failed preparation"):
                preparation.command("find", ["uv", "python", "find"])
        self.assertEqual(run.call_count, 1)
        record = json.loads((self.root / "find.result.json").read_text())
        self.assertFalse(record["succeeded"])
        self.assertEqual(record["owned_receipt"]["returncode"], 1)
        self.assertFalse(record["owned_receipt"]["survivors"])

    def test_exhausted_clock_prevents_process_launch(self):
        preparation = bootstrap.Preparation(self.root, {})
        with (
            patch.object(
                bootstrap.time, "monotonic", return_value=preparation.deadline - 24
            ),
            patch.object(bootstrap.owned_process, "run_owned") as run,
            self.assertRaisesRegex(ValueError, "reserve"),
        ):
            preparation.command("late", ["uv"])
        run.assert_not_called()

    def test_nonfinite_or_boolean_preparation_budget_is_rejected(self):
        for seconds in (True, float("nan"), float("inf"), 0, 121):
            with (
                self.subTest(seconds=seconds),
                self.assertRaisesRegex(ValueError, "finite"),
            ):
                bootstrap.Preparation(self.root, {}, seconds)

    def test_actual_success_needs_process_identity_and_raw_streams(self):
        preparation = bootstrap.Preparation(self.root, {})
        receipt = bootstrap.owned_process.Receipt(
            returncode=0,
            timed_out=False,
            command_wall=0.1,
            infrastructure_wall=0.01,
            ownership_established=True,
            survivors=False,
            cleanup_complete=True,
            errors=(),
            actual_process={"pid": 42, "image": "uv", "birth_filetime": 123},
        )

        def finish(argv, **kwargs):
            kwargs["stdout_path"].write_bytes(b"observed-sdk\n")
            kwargs["stderr_path"].write_bytes(b"")
            return receipt

        with patch.object(
            bootstrap.owned_process, "run_owned", side_effect=finish
        ) as run:
            self.assertEqual(
                preparation.command("find", ["uv", "python", "find"]), "observed-sdk\n"
            )
        self.assertIs(run.call_args.kwargs["native_clock"], True)
        record = json.loads((self.root / "find.result.json").read_text())
        self.assertEqual(
            record["stdout_sha256"], bootstrap.sha(self.root / "find.stdout")
        )
        self.assertEqual(record["owned_receipt"]["actual_process"]["pid"], 42)

    def test_prepare_source_retains_patch_request_and_no_duplicate_managed_switch(self):
        source = (bootstrap.HERE / "bootstrap.py").read_text()
        module = ast.parse(source)
        prepare = next(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "prepare"
        )
        text = ast.get_source_segment(source, prepare)
        self.assertIn('UV_PYTHON_PREFERENCE="only-managed"', text)
        self.assertNotIn("--managed-python", text)
        patch_requests = [
            node
            for node in ast.walk(prepare)
            if isinstance(node, ast.List)
            and any(
                isinstance(item, ast.Constant) and item.value == "--python"
                for item in node.elts
            )
        ]
        self.assertEqual(len(patch_requests), 1)
        self.assertEqual(patch_requests[0].elts[4].value, "3.13.15")
        self.assertIn('"publisher_archive_freshly_verified": False', text)

    def test_receipt_binds_actual_find_probe_and_command_argument(self):
        paths, observed, found = self.fixture("win32")
        sdk = bootstrap.Path(observed["base_prefix"])
        shutil.rmtree(paths["install"])
        shutil.rmtree(paths["venv"])
        paths.update(
            {
                name: self.root / name
                for name in ("wheels", "source", "output", "cache", "evidence")
            }
        )
        wheel = paths["wheels"] / bootstrap.reference.shared.WHEEL
        real_sha = bootstrap.sha
        (self.root / "uv.exe").write_bytes(b"mock-qualified-uv")
        calls = []

        def fake_command(preparation, label, argv, **kwargs):
            calls.append((label, argv, kwargs))
            preparation.commands.append({"argv": argv})
            if label == "install":
                sdk.mkdir(parents=True)
                bootstrap.Path(found).write_bytes(b"mock-native-base")
            elif label == "venv":
                paths["venv"].mkdir()
            elif label == "backend":
                paths["wheels"].mkdir()
                wheel.write_bytes(b"x" * 199650)
            stdout = {
                "install": "",
                "find": found + "\n",
                "venv": "",
                "probe": json.dumps(observed),
                "backend": json.dumps(
                    {"bytes": 199650, "sha256": bootstrap.reference.shared.WHEEL_SHA}
                ),
            }[label]
            (paths["evidence"] / (label + ".stdout")).write_text(stdout)
            (paths["evidence"] / (label + ".stderr")).write_bytes(b"")
            return stdout

        with (
            patch.object(bootstrap, "fixed_paths", return_value=paths),
            patch.object(
                bootstrap.reference,
                "qualified_uv_identity",
                return_value={"qualified_version": "0.13.6"},
            ),
            patch.object(bootstrap.Preparation, "command", fake_command),
            patch.object(
                bootstrap,
                "sha",
                side_effect=lambda path: (
                    bootstrap.reference.shared.WHEEL_SHA
                    if path == wheel
                    else real_sha(path)
                ),
            ),
        ):
            receipt = bootstrap.prepare(self.root, self.root / "uv.exe", {})
        self.assertEqual(
            [call[0] for call in calls], ["install", "find", "venv", "probe", "backend"]
        )
        self.assertEqual(receipt["sdk_root"], observed["base_prefix"])
        self.assertEqual(receipt["base_python"], observed["base_executable"])
        self.assertEqual(receipt["find_actual_stdout"], found + "\n")
        self.assertEqual(receipt["python_request"], calls[2][1][4])
        self.assertEqual(calls[3][1][1:3], ["-I", "-B"])
        self.assertFalse(receipt["publisher_archive_freshly_verified"])
        self.assertFalse(receipt["native_coordinator_or_WA_WB_prior_success"])
        self.assertEqual(
            receipt["evidence_sha256"]["probe.stdout"],
            real_sha(paths["evidence"] / "probe.stdout"),
        )

    def test_original_verifier_is_frozen_not_ast_rewritten(self):
        template = bootstrap.HERE / "verify_readiness04.source"
        self.assertEqual(bootstrap.sha(template), verify_raw.ORIGINAL_SHA)
        self.assertNotIn("ast.", (bootstrap.HERE / "verify_raw.py").read_text())


if __name__ == "__main__":
    unittest.main()
