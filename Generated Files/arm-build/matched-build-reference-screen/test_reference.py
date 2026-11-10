"""Source-only composition checks; all workload/process calls remain mocked."""

import copy
import io
import platform
import shutil
import struct
import subprocess
import sys
import unittest
import uuid
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import reference
import screen
import test_generated_metadata as legacy
from archive_headers import NATIVE_EXECUTABLE_SCRIPTS, expected_headers


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.root = screen.HERE / ("test-work-reference-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)

    def test_schedule_has_only_two_excluded_and_six_fixed_samples(self):
        self.assertEqual(
            screen.schedule(),
            [
                ("C", False, "WA"),
                ("D", False, "WB"),
                ("R", True, 1),
                ("R", True, 2),
                ("R", True, 3),
                ("R", True, 4),
                ("R", True, 5),
                ("R", True, 6),
            ],
        )
        self.assertEqual(reference.QUESTION["max_build_commands"], 8)

    def test_source_pins_are_checked_and_tampering_rejected(self):
        self.assertEqual(len(reference.source_preflight()), 64)
        original = screen.digest
        with (
            patch.object(
                screen,
                "digest",
                side_effect=lambda path: (
                    "0" * 64 if path.name == "runtime_links.py" else original(path)
                ),
            ),
            self.assertRaisesRegex(RuntimeError, "source pins differ"),
        ):
            reference.source_preflight()

    def test_pin_closure_rejects_an_unpinned_additional_helper(self):
        pins = screen.load(screen.HERE / "SOURCEPINS.json")
        del pins["files"]["metadata_time.py"]
        with (
            patch.object(screen, "load", return_value=pins),
            self.assertRaisesRegex(RuntimeError, "closure"),
        ):
            reference.source_preflight()

    def test_admission_finite_fresh_and_source_configuration_bound(self):
        config = {
            "seconds": 300,
            "platform": "win32",
            "profile": "HOSTED_WINDOWS_REFERENCE",
        }
        admission = {
            "authority": "separate-parent-native-readiness",
            "version": reference.VERSION,
            "profile": config["profile"],
            "sourcepins_sha256": "source",
            "issued_unix": 1000,
            "expires_unix": 1500,
            "question_sha256": reference.canonical_hash(reference.QUESTION),
            "configuration_sha256": reference.canonical_hash(config),
            "max_build_commands": 8,
            "bootstrap_receipt_qualified": True,
            "target_isa_runtime_prerequisites_qualified": True,
            "fixed_paths_and_cache_qualified": True,
        }
        reference.admission_check(admission, config, "source", 1100)
        for field, value in (
            ("sourcepins_sha256", "different"),
            ("question_sha256", "different"),
            ("configuration_sha256", "different"),
            ("max_build_commands", 9),
            ("version", 1),
            ("profile", "LOCAL_WINDOWS_READINESS"),
            ("expires_unix", float("inf")),
            ("issued_unix", 1200),
            ("bootstrap_receipt_qualified", False),
            ("target_isa_runtime_prerequisites_qualified", False),
            ("native_platform_qualified", True),
            ("expires_unix", 1100),
            ("issued_unix", 0),
        ):
            with (
                self.subTest(field=field, value=value),
                self.assertRaises(RuntimeError),
            ):
                reference.admission_check(
                    {**admission, field: value}, config, "source", 1100
                )
        with self.assertRaises(RuntimeError):
            reference.admission_check(
                admission, {**config, "seconds": 601}, "source", 1100
            )

    def test_default_refusal_never_calls_native_or_bootstrap(self):
        with (
            patch.object(sys, "argv", ["reference.py"]),
            patch.object(screen, "run_native") as native,
        ):
            with self.assertRaisesRegex(RuntimeError, "NOTADMITTED"):
                reference.main()
            native.assert_not_called()

    def test_preflight_has_no_runtime_or_native_calls(self):
        with (
            patch.object(sys, "argv", ["reference.py", "--source-preflight"]),
            patch.object(screen, "runtime_identity") as runtime,
            patch.object(reference, "qualified_uv_identity") as identity,
            patch("builtins.print"),
        ):
            reference.main()
            runtime.assert_not_called()
            identity.assert_not_called()

    def test_exact_qualified_uv_bytes_and_static_isa_need_no_spawn(self):
        windows = self.root / "uv.exe"
        image = bytearray(96)
        image[:2] = b"MZ"
        struct.pack_into("<I", image, 60, 64)
        image[64:68] = b"PE\0\0"
        struct.pack_into("<H", image, 68, 0xAA64)
        windows.write_bytes(image)
        mac = self.root / "uv"
        mac.write_bytes(struct.pack("<8I", 0xFEEDFACF, 0x0100000C, 0, 2, 0, 0, 0, 0))
        original_digest = screen.digest
        image_digests = {
            windows: reference.QUALIFIED_UV["win32"]["sha256"],
            mac: reference.QUALIFIED_UV["darwin"]["sha256"],
        }
        with (
            patch.object(
                screen,
                "digest",
                side_effect=lambda path: (
                    image_digests.get(path) or original_digest(path)
                ),
            ),
            patch.object(
                subprocess, "run", side_effect=AssertionError("no metadata subprocess")
            ) as run,
            patch.object(
                subprocess,
                "Popen",
                side_effect=AssertionError("no metadata subprocess"),
            ) as popen,
            patch.object(screen.owned_process, "run_owned") as owned,
        ):
            for native_platform, path in (("win32", windows), ("darwin", mac)):
                with self.subTest(platform=native_platform):
                    result = reference.qualified_uv_identity(
                        path, platform=native_platform
                    )
                    self.assertEqual(result["sha256"], image_digests[path])
                    self.assertEqual(
                        result["qualified_source_revision"], reference.UV_REVISION
                    )
                    self.assertEqual(result["qualified_version"], "0.13.6")
                    self.assertIs(result["version_observed"], False)
                    self.assertNotIn("version", result)
            run.assert_not_called()
            popen.assert_not_called()
            owned.assert_not_called()

    def test_same_version_other_revision_binary_fails_before_static_acceptance(self):
        image = self.root / "uv"
        image.write_bytes(b"uv 0.13.6 (other-revision same-version)")
        with (
            patch.object(subprocess, "run") as run,
            patch.object(subprocess, "Popen") as popen,
            patch.object(screen, "pe_arm64") as pe,
            patch.object(screen, "macho_arm64") as macho,
        ):
            for native_platform in ("win32", "darwin"):
                with (
                    self.subTest(platform=native_platform),
                    self.assertRaisesRegex(
                        RuntimeError, "qualified UV binary/source identity"
                    ),
                ):
                    reference.qualified_uv_identity(image, platform=native_platform)
            run.assert_not_called()
            popen.assert_not_called()
            pe.assert_not_called()
            macho.assert_not_called()

    def test_expected_digest_does_not_replace_actual_architecture_check(self):
        image = self.root / "uv"
        image.write_bytes(b"not an executable")
        for native_platform in ("win32", "darwin"):
            with (
                self.subTest(platform=native_platform),
                patch.object(
                    screen,
                    "digest",
                    return_value=reference.QUALIFIED_UV[native_platform]["sha256"],
                ),
                self.assertRaises(RuntimeError),
            ):
                reference.qualified_uv_identity(image, platform=native_platform)

    def test_initial_and_later_input_seals_reject_drift_from_qualified_UV(self):
        args = SimpleNamespace(uv=self.root / "uv")
        for native_platform in ("win32", "darwin"):
            with (
                self.subTest(platform=native_platform),
                patch.object(screen, "digest", return_value="0" * 64),
                self.assertRaisesRegex(RuntimeError, "UV qualified input seal differs"),
            ):
                reference.nonruntime_inputs(args, (), {"platform": native_platform})

    def test_entrypoint_metadata_path_uses_static_identity_without_spawning(self):
        output = self.root / "synthetic-output"
        args = SimpleNamespace(
            output=output, uv=self.root / "uv", source=self.root / "audit-only"
        )
        config = {
            "seconds": 600,
            "platform": "win32",
            "profile": "HOSTED_WINDOWS_REFERENCE",
        }
        failed_reset = output / "build-07-R" / "source-reset.json"

        def stop_before_acquisition(*args):
            failed_reset.parent.mkdir()
            screen.save(failed_reset, {"completed": False, "fixture": "synthetic"})
            raise RuntimeError("source-only stop before acquisition")

        with (
            patch.object(reference, "admission_check"),
            patch.object(reference, "configuration_paths", return_value=args),
            patch.object(reference, "claim_attempt") as marker,
            patch.object(reference, "creation_policy", return_value=None),
            patch.object(screen, "runtime_identity", return_value={}),
            patch.object(
                reference, "qualified_uv_identity", return_value={}
            ) as identity,
            patch.object(
                screen,
                "git",
                side_effect=stop_before_acquisition,
            ),
            patch.object(subprocess, "run") as run,
            patch.object(subprocess, "Popen") as popen,
            self.assertRaisesRegex(RuntimeError, "source-only stop"),
        ):
            reference.run(
                config,
                {"attempt_marker": str(self.root / "not-created")},
                "mock-source",
            )
        identity.assert_called_once_with(args.uv, platform="win32")
        marker.assert_called_once()
        run.assert_not_called()
        popen.assert_not_called()
        self.assertFalse((self.root / "not-created").exists())
        failure = screen.load(output / "failure.json")
        self.assertEqual(failure["sourcepins"], "mock-source")
        self.assertEqual(
            failure["source_reset_logs"][str(failed_reset.relative_to(output))],
            screen.digest(failed_reset),
        )

    def test_platform_ignore_bytes_are_positive_not_normalized(self):
        self.assertEqual(screen.pdm_ignore_bytes("win32"), b"*\r\n")
        self.assertEqual(screen.pdm_ignore_bytes("darwin"), b"*\n")
        with self.assertRaises(RuntimeError):
            screen.pdm_ignore_bytes("linux")
        source = self.root / "source"
        (source / ".pdm-build").mkdir(parents=True)
        (source / ".pdm-build" / ".gitignore").write_bytes(b"*\r\n")
        with (
            patch.object(screen.sys, "platform", "darwin"),
            self.assertRaisesRegex(RuntimeError, "stock PDM"),
        ):
            screen.source_after(source, {}, {}, self.root)
        (source / ".pdm-build" / ".gitignore").write_bytes(b"*\n")
        with patch.object(screen.sys, "platform", "darwin"):
            result = screen.source_after(source, {}, {}, self.root)
        self.assertEqual(set(result["outputs"]), {".pdm-build/.gitignore"})

    def test_runtime_manifest_seam_never_relaxes_generic_manifest(self):
        with (
            patch.object(Path, "is_symlink", return_value=True),
            self.assertRaisesRegex(RuntimeError, "payload reparse"),
        ):
            screen.manifest_entry(self.root, self.root)
        policy = object()
        with (
            patch.object(reference, "runtime_input_hashes", return_value={}) as inputs,
            patch.object(reference, "RuntimeGuard") as guard,
        ):
            before, observed_guard = reference.initial_runtime_guard(
                SimpleNamespace(python="python", output=self.root),
                {"runtime_roots": ["sdk", "venv"]},
                policy,
                lambda: {"nonruntime": "sealed"},
            )
            self.assertEqual(before, {"nonruntime": "sealed", "runtime": {}})
            self.assertIs(observed_guard, guard.return_value)
            self.assertIs(
                inputs.call_args.args[1], guard.call_args.kwargs["link_policy"]
            )
            inputs.assert_called_once_with(["sdk", "venv"], policy)
            observed_guard.final()
            inputs.assert_called_once()

    def test_one_attempt_uses_exclusive_creation_and_never_retries(self):
        with patch.object(Path, "open") as opening:
            opening.return_value.__enter__.return_value = io.StringIO()
            reference.claim_attempt(self.root / "attempt", "source", {})
            opening.assert_called_once_with("x", encoding="utf-8")
        with (
            patch.object(Path, "open", side_effect=FileExistsError) as opening,
            self.assertRaises(FileExistsError),
        ):
            reference.claim_attempt(self.root / "attempt", "source", {})
        opening.assert_called_once()

    def test_expired_controller_budget_prevents_first_workload(self):
        args = SimpleNamespace(output=self.root)
        with patch.object(screen, "run_native") as native:
            with self.assertRaisesRegex(RuntimeError, "deadline prevents launch"):
                screen.execute(args, {}, 0, {}, [], Mock())
            native.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_actual_fixed_execute_routes_all_eight_builds_to_same_environment(self):
        args = SimpleNamespace(output=self.root, uv=Path(sys.executable))
        argv = [sys.executable, "build", "--offline"]
        env = {"UV_CACHE_DIR": str(self.root / "fixed-cache")}
        process = {
            "pid": 42,
            "image": sys.executable,
            "birth_filetime": screen.FILETIME_EPOCH + 10_000_000,
        }
        receipt = screen.owned_process.Receipt(
            0,
            False,
            0.1,
            0.01,
            True,
            False,
            True,
            (),
            native_start_ns=1,
            native_end_ns=2,
            actual_process=process,
        )

        def native_call(actual_argv, **kwargs):
            self.assertEqual(actual_argv, argv)
            self.assertIs(kwargs["env"], env)
            self.assertEqual(kwargs["cwd"], self.root / "canonical-source")
            reset = screen.load(kwargs["stdout_path"].parent / "source-reset.json")
            self.assertTrue(reset["completed"])
            self.assertLessEqual(reset["ended_ns"], screen.time.perf_counter_ns())
            return receipt, {
                **process,
                "argv": argv,
                "cwd": str(kwargs["cwd"]),
                "environment": env,
                "start_ns": 1,
                "end_ns": 2,
                "returncode": 0,
                "status": "COMPLETE",
            }

        def audit(source, canonical, reference_inventory, folder, reference_folder):
            screen.save(folder / "generated-metadata-proof.json", {})
            screen.save(folder / "full-headers.json", {})
            return {}, {}

        guard = Mock()
        with (
            patch.object(screen, "room"),
            patch.object(
                screen, "extract", side_effect=lambda archive, live: live.mkdir()
            ),
            patch.object(screen, "run_native", side_effect=native_call) as native,
            patch.object(screen, "archive_audit", side_effect=audit),
            patch.object(screen, "source_after", return_value={"outputs": {}}),
        ):
            rows = screen.execute(
                args, {}, 600, dict.fromkeys(("C", "D", "R"), env), argv, guard
            )
        self.assertEqual(native.call_count, 8)
        self.assertEqual(guard.before_row.call_count, 8)
        self.assertEqual(guard.after_row.call_count, 8)
        self.assertEqual(
            [(r["arm"], r["measured"], r["pair"]) for r in rows], screen.schedule()
        )
        self.assertEqual(len(screen.load(self.root / "rows.json")), 8)
        self.assertEqual(len(list(self.root.glob("build-*"))), 8)
        for row in rows:
            folder = self.root / row["folder"]
            self.assertEqual(
                row["source_reset_sha256"], screen.digest(folder / "source-reset.json")
            )
            reset = screen.load(folder / "source-reset.json")
            self.assertTrue(reset["completed"])
            self.assertEqual(reset["events"], [])
            self.assertEqual(reset["extra_attempts"], 0)

    def test_creation_policy_binds_receipt_request_roots_digest_and_raw_base_alias(
        self,
    ):
        args = SimpleNamespace(sdk_root=self.root / "sdk", venv_root=self.root / "venv")
        config = {
            "creation_receipt": str(self.root / "future-observed-receipt"),
            "creation_receipt_sha256": "receipt-hash",
            "publisher_sha256": reference.ARCHIVE_SHA256,
            "base_python": str(args.sdk_root / "bin" / "python3"),
        }
        receipt = {
            "kind": "observed-uv-venv-creation",
            "uv_version": "0.13.6",
            "python_request": "3.13.15",
            "variant": "normal",
            "sdk_root": str(args.sdk_root),
            "venv_root": str(args.venv_root),
            "base_python": config["base_python"],
            "publisher_sha256": reference.ARCHIVE_SHA256,
        }
        with (
            patch.object(reference.sys, "platform", "darwin"),
            patch.object(screen, "digest", return_value="receipt-hash"),
            patch.object(screen, "load", return_value=receipt),
            patch.object(reference, "DarwinRuntimeLinks") as policy,
        ):
            self.assertIs(reference.creation_policy(config, args), policy.return_value)
            policy.assert_called_once_with(
                args.sdk_root,
                args.venv_root,
                config["base_python"],
                reference.ARCHIVE_SHA256,
            )
            for key in (
                "python_request",
                "uv_version",
                "base_python",
                "publisher_sha256",
                "sdk_root",
                "venv_root",
                "kind",
            ):
                with (
                    self.subTest(key=key),
                    patch.object(
                        screen, "load", return_value={**receipt, key: "wrong"}
                    ),
                    self.assertRaisesRegex(RuntimeError, "creation provenance"),
                ):
                    reference.creation_policy(config, args)

    def test_macho_rejects_x86_pe_and_non_executable(self):
        image = self.root / "image"
        image.write_bytes(struct.pack("<8I", 0xFEEDFACF, 0x0100000C, 0, 2, 0, 0, 0, 0))
        screen.macho_arm64(image)
        for data in (
            b"MZ" + bytes(64),
            struct.pack("<8I", 0xFEEDFACF, 0x01000007, 0, 2, 0, 0, 0, 0),
            struct.pack("<8I", 0xFEEDFACF, 0x0100000C, 0, 6, 0, 0, 0, 0),
        ):
            image.write_bytes(data)
            with self.assertRaisesRegex(RuntimeError, "Mach-O"):
                screen.macho_arm64(image)

    def test_native_mac_runtime_uses_lexical_venv_image_without_windows_apis(self):
        with (
            patch.object(screen.sys, "platform", "darwin"),
            patch.object(screen.sys, "dont_write_bytecode", False),
            patch.object(screen.sys, "pycache_prefix", None),
            patch.object(
                screen.sysconfig, "get_platform", return_value="macosx-14.0-arm64"
            ),
            patch.object(screen.sysconfig, "get_config_var", return_value=None),
            patch.object(platform, "machine", return_value="arm64"),
            patch.object(screen, "macho_arm64") as macho,
            patch.object(screen, "pe_arm64", side_effect=AssertionError("not PE")),
            patch.object(
                screen.ctypes, "WinDLL", side_effect=AssertionError("not Windows")
            ),
        ):
            result = screen.runtime_identity()
        macho.assert_called_once_with(Path(sys.executable))
        self.assertEqual(result["executable"], sys.executable)
        self.assertNotIn("affinity_mask", result)
        args = SimpleNamespace(
            uv=self.root / "uv",
            python=self.root / "venv" / "bin" / "python",
            wheels=self.root / "wheels",
        )
        command = screen.command(args, self.root / "constraints")
        self.assertEqual(command[command.index("--python") + 1], str(args.python))

    def test_environment_never_strips_epoch_or_exposes_secrets(self):
        env = {"TEMP": "t", "TMPDIR": "d", "SECRET": "not-retained"}
        evidence = screen.environment_evidence(env)
        self.assertEqual(evidence["values"], {"TEMP": "t", "TMPDIR": "d"})
        with self.assertRaises(RuntimeError):
            screen.environment(self.root, {**env, "SOURCE_DATE_EPOCH": "1"})

    def test_header_policy_changes_only_declared_fields(self):
        fixture = legacy.GeneratedMetadataTests()
        inventory = fixture.inventory(1700000000.25)
        member = next(iter(inventory["sdist"].values()))
        for name in NATIVE_EXECUTABLE_SCRIPTS:
            inventory["sdist"][name] = {**copy.deepcopy(member), "mode": 0o644}
        expected = expected_headers(inventory, "darwin")
        self.assertEqual(expected["wheel"]["fastapi/__init__.py"]["create_system"], 3)
        for name in NATIVE_EXECUTABLE_SCRIPTS:
            self.assertEqual(expected["sdist"][name]["mode"], 0o755)
            expected["sdist"][name]["mode"] = 0o644
        expected["wheel"]["fastapi/__init__.py"]["create_system"] = 0
        self.assertEqual(expected, inventory)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "platform": "win32",
            "profile": "HOSTED_WINDOWS_REFERENCE",
            "source": r"C:\audit-checkout",
            "cache": r"D:\private-cache",
            "python": r"C:\venv\Scripts\python.exe",
            "uv": r"C:\tools\uv.exe",
            "wheels": r"C:\wheels",
            "output": r"C:\native-output",
            "sdk_root": r"C:\sdk",
            "venv_root": r"C:\venv",
        }
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(reference.sys, "platform", "win32"))
        self.stack.enter_context(
            patch.object(reference.sys, "executable", self.config["python"])
        )
        self.stack.enter_context(
            patch.object(reference.sys, "prefix", self.config["venv_root"])
        )
        self.stack.enter_context(
            patch.object(reference.sys, "base_prefix", self.config["sdk_root"])
        )
        self.stack.enter_context(patch.object(Path, "is_symlink", return_value=False))
        self.stack.enter_context(patch.object(Path, "is_junction", return_value=False))
        self.stack.enter_context(patch.object(Path, "exists", return_value=False))
        self.stack.enter_context(
            patch.object(
                Path,
                "resolve",
                autospec=True,
                side_effect=lambda path, strict=False: path,
            )
        )
        self.volumes = self.stack.enter_context(
            patch.object(
                screen,
                "volume_identity",
                return_value={"filesystem": "ReFS", "serial": 20},
            )
        )

    def test_explicit_hosted_profile_preserves_C_checkout_D_cache(self):
        args = reference.configuration_paths(self.config)
        self.assertEqual(args.source.drive, "C:")
        self.assertEqual(args.cache.drive, "D:")
        self.assertEqual((args.output / "canonical-source").drive, "C:")
        self.volumes.assert_called_once_with(args.cache)

    def test_explicit_local_Q_audit_and_cache_keep_native_source_and_inputs_C(self):
        config = {
            **self.config,
            "profile": "LOCAL_WINDOWS_READINESS",
            "source": r"Q:\audit-checkout",
            "cache": r"Q:\private-cache",
        }
        args = reference.configuration_paths(config)
        self.assertEqual(args.source.drive, "Q:")
        self.assertEqual(args.cache.drive, "Q:")
        for path in (
            args.output / "canonical-source",
            args.python,
            args.uv,
            args.wheels,
            args.sdk_root,
            args.venv_root,
        ):
            self.assertEqual(path.drive, "C:")
        self.assertEqual(
            reference.selected_profile(config)["classification"],
            "LOCAL_READINESS_NONCOMPARATIVE",
        )
        self.volumes.assert_called_once_with(args.cache)

    def test_no_missing_unknown_or_cross_platform_profile_fallback(self):
        missing = dict(self.config)
        del missing["profile"]
        for config in (
            missing,
            {**self.config, "profile": "unknown"},
            {**self.config, "profile": "DARWIN_REFERENCE"},
            {**self.config, "platform": "darwin", "profile": "LOCAL_WINDOWS_READINESS"},
            {
                **self.config,
                "platform": "darwin",
                "profile": "HOSTED_WINDOWS_REFERENCE",
            },
        ):
            with (
                self.subTest(config=config),
                self.assertRaisesRegex(RuntimeError, "platform-bound profile"),
            ):
                reference.configuration_paths(config)
        self.volumes.assert_not_called()

    def test_hosted_cannot_relabel_Q_checkout_or_Q_cache(self):
        for config in (
            {**self.config, "source": r"Q:\audit-checkout"},
            {**self.config, "cache": r"Q:\private-cache"},
        ):
            with (
                self.subTest(config=config),
                self.assertRaisesRegex(RuntimeError, "profile Windows"),
            ):
                reference.configuration_paths(config)

    def test_missing_hosted_D_does_not_probe_or_fall_back_to_Q(self):
        self.volumes.side_effect = OSError("D unavailable")
        with self.assertRaisesRegex(OSError, "D unavailable"):
            reference.configuration_paths(self.config)
        self.volumes.assert_called_once_with(Path(r"D:\private-cache"))

    def test_local_requires_Q_checkout_and_Q_cache_not_hosted_drives(self):
        local = {
            **self.config,
            "profile": "LOCAL_WINDOWS_READINESS",
            "source": r"Q:\audit-checkout",
            "cache": r"Q:\private-cache",
        }
        for config in (
            {**local, "source": r"C:\audit-checkout"},
            {**local, "cache": r"D:\private-cache"},
        ):
            with (
                self.subTest(config=config),
                self.assertRaisesRegex(RuntimeError, "profile Windows"),
            ):
                reference.configuration_paths(config)

    def test_local_never_moves_runtime_UV_wheels_or_native_output_to_Q(self):
        local = {
            **self.config,
            "profile": "LOCAL_WINDOWS_READINESS",
            "source": r"Q:\audit-checkout",
            "cache": r"Q:\private-cache",
        }
        for field in ("python", "uv", "wheels", "output", "sdk_root", "venv_root"):
            config = {**local, field: rf"Q:\misplaced\{field}"}
            with (
                self.subTest(field=field),
                patch.object(reference.sys, "executable", config["python"]),
                patch.object(reference.sys, "prefix", config["venv_root"]),
                patch.object(reference.sys, "base_prefix", config["sdk_root"]),
                self.assertRaisesRegex(RuntimeError, "Windows C native"),
            ):
                reference.configuration_paths(config)

    def test_local_keeps_wheelhouse_disjoint_from_audit_checkout(self):
        config = {
            **self.config,
            "profile": "LOCAL_WINDOWS_READINESS",
            "source": r"Q:\audit-checkout",
            "cache": r"Q:\private-cache",
            "wheels": r"Q:\audit-checkout\wheels",
        }
        with self.assertRaisesRegex(RuntimeError, "disjoint fixed roots"):
            reference.configuration_paths(config)

    def test_local_cache_still_requires_ReFS_and_fresh_cache_and_output(self):
        config = {
            **self.config,
            "profile": "LOCAL_WINDOWS_READINESS",
            "source": r"Q:\audit-checkout",
            "cache": r"Q:\private-cache",
        }
        self.volumes.return_value = {"filesystem": "NTFS"}
        with self.assertRaisesRegex(RuntimeError, "profile ReFS"):
            reference.configuration_paths(config)
        self.volumes.return_value = {"filesystem": "ReFS"}
        for field in ("cache", "output"):
            with (
                self.subTest(field=field),
                patch.object(
                    Path,
                    "exists",
                    new=lambda path, field=field: path == Path(config[field]),
                ),
                self.assertRaisesRegex(RuntimeError, "fresh output/cache"),
            ):
                reference.configuration_paths(config)

    def test_local_junction_or_noncanonical_checkout_is_not_repaired(self):
        config = {
            **self.config,
            "profile": "LOCAL_WINDOWS_READINESS",
            "source": r"Q:\audit-checkout",
            "cache": r"Q:\private-cache",
        }
        with (
            patch.object(Path, "is_junction", return_value=True),
            self.assertRaisesRegex(RuntimeError, "fixed paths cannot use aliases"),
        ):
            reference.configuration_paths(config)
        with (
            patch.object(
                Path,
                "resolve",
                new=lambda path, strict=False: Path(r"Q:\other-checkout"),
            ),
            self.assertRaisesRegex(RuntimeError, "canonical declared audit checkout"),
        ):
            reference.configuration_paths(config)

    def test_local_admission_names_profile_and_only_target_runtime_prerequisites(self):
        config = {
            "seconds": 300,
            "platform": "win32",
            "profile": "LOCAL_WINDOWS_READINESS",
        }
        admission = {
            "authority": "separate-parent-native-readiness",
            "version": reference.VERSION,
            "profile": config["profile"],
            "sourcepins_sha256": "source",
            "issued_unix": 1000,
            "expires_unix": 1500,
            "question_sha256": reference.canonical_hash(reference.QUESTION),
            "configuration_sha256": reference.canonical_hash(config),
            "max_build_commands": 8,
            "bootstrap_receipt_qualified": True,
            "target_isa_runtime_prerequisites_qualified": True,
            "fixed_paths_and_cache_qualified": True,
        }
        reference.admission_check(admission, config, "source", 1100)
        with self.assertRaisesRegex(RuntimeError, "source-bound admission"):
            reference.admission_check(
                {**admission, "profile": "HOSTED_WINDOWS_REFERENCE"},
                config,
                "source",
                1100,
            )


class DarwinMetadataTests(legacy.GeneratedMetadataTests):
    def setUp(self):
        super().setUp()
        for folder in (self.reference_folder, self.folder):
            receipt = screen.load(folder / "ownership.json")
            windows = receipt["actual_process"]
            birth = (windows["birth_filetime"] - screen.FILETIME_EPOCH) // 10
            process = {
                "pid": 42,
                "parent_pid": 900,
                "observed_executable": sys.executable,
                "executable": str(Path(sys.executable).resolve(strict=True)),
                "start_unix_interval_us": [birth, birth + 1],
            }
            receipt["actual_process"] = process
            command = screen.load(folder / "command.json")
            command["argv"][0] = sys.executable
            native = screen.load(folder / "native.json")
            for key in windows:
                del native[key]
            native.update(process)
            native["argv"] = command["argv"]
            for name, value in (
                ("ownership.json", receipt),
                ("command.json", command),
                ("native.json", native),
                ("stdout.actual-process.json", process),
            ):
                screen.save(folder / name, value)
        self.platform = patch.object(screen.sys, "platform", "darwin")
        self.platform.start()
        self.addCleanup(self.platform.stop)
        screen.require_generated_headers(
            self.reference, None, self.reference_folder, None
        )

    def test_default_time_change_has_independent_utc_bounds_and_no_map_rewrite(self):
        self.compare()
        proof = screen.load(self.folder / "generated-metadata-proof.json")
        self.assertEqual(proof["platform"], "darwin")
        self.assertEqual(
            proof["UTC_window_ns"], [1700000010_000000000, 1700000012_000000999]
        )
        self.assertNotIn("birth_filetime", proof["actual_process"])
        self.assertNotIn("native_QPC_ns", proof)
        self.assertEqual(
            proof["native_monotonic_ns"], [9_000_000_000_000_000, 9_000_002_000_000_000]
        )

    def test_each_native_association_mismatch_is_rejected(self):
        original = screen.load(self.folder / "native.json")
        for field, value in (
            ("parent_pid", 901),
            ("observed_executable", "relative"),
            ("executable", "wrong"),
            ("start_unix_interval_us", [1, 2]),
            ("argv", ["wrong", "build"]),
            ("cwd", "wrong"),
            ("environment", {}),
            ("returncode", 1),
            ("status", "FAILED"),
        ):
            with self.subTest(field=field):
                screen.save(self.folder / "native.json", {**original, field: value})
                with self.assertRaises((RuntimeError, ValueError)):
                    self.compare()
        screen.save(self.folder / "native.json", original)

    def test_sidecar_and_failed_drain_rejected(self):
        screen.save(self.folder / "stdout.actual-process.json", {})
        with self.assertRaisesRegex(RuntimeError, "association"):
            self.compare()
        receipt = screen.load(self.folder / "ownership.json")
        screen.save(
            self.folder / "stdout.actual-process.json", receipt["actual_process"]
        )
        receipt["survivors"] = True
        screen.save(self.folder / "ownership.json", receipt)
        with self.assertRaisesRegex(RuntimeError, "successful native lifetime"):
            self.compare()

    def test_platform_is_not_inferred_from_receipt(self):
        with self.assertRaises((RuntimeError, ValueError)):
            screen.generated_metadata_proof(self.actual, self.folder, platform="win32")


if __name__ == "__main__":
    unittest.main()
