"""Portable adapter negative vectors, with no native or workload execution."""

import copy
import json
import shutil
import stat
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import bootstrap
import case_contract as contract
import deploy
from archive_headers import TAR_FIELDS, WHEEL_FIELDS


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.root = bootstrap.HERE / ("test-work-contract-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.image = self.root / "python3.13"
        self.image.write_bytes(b"mock-native-image")
        self.darwin = {
            "pid": 42,
            "parent_pid": 41,
            "executable": str(self.image),
            "observed_executable": str(self.image),
            "start_unix_interval_us": [1000000, 1000001],
        }

    def test_darwin_birth_is_unix_microsecond_interval_not_filetime(self):
        key, window = contract.process_identity(self.darwin, str(self.image), "darwin")
        self.assertEqual(key, (42, 1000000))
        self.assertEqual(window, (1000000000, 1000000999))
        for field, value in (
            ("birth_filetime", 116444736000000001),
            ("pid", True),
            ("parent_pid", 42),
            ("start_unix_interval_us", [1000000, 1000002]),
            ("start_unix_interval_us", [True, 2]),
            ("observed_executable", str(self.root / "wrong-image")),
        ):
            process = copy.deepcopy(self.darwin)
            process[field] = value
            with (
                self.subTest(field=field),
                self.assertRaises((ValueError, RuntimeError, OSError)),
            ):
                contract.process_identity(process, str(self.image), "darwin")

    def test_windows_birth_does_not_accept_darwin_schema_or_boolean_filetime(self):
        process = {
            "pid": 42,
            "image": str(self.image),
            "birth_filetime": 116444736000000010,
        }
        self.assertEqual(
            contract.process_identity(process, str(self.image), "win32")[1],
            (1000, 1000),
        )
        process["birth_filetime"] = True
        with self.assertRaises(ValueError):
            contract.process_identity(process, str(self.image), "win32")
        with self.assertRaises(RuntimeError):
            contract.process_identity(self.darwin, str(self.image), "win32")

    def test_natural_drain_cannot_be_replaced_by_status_or_exit_zero(self):
        receipt = {
            "returncode": 0,
            "timed_out": False,
            "ownership_established": True,
            "survivors": False,
            "cleanup_complete": True,
            "errors": [],
            "liveness": [],
        }
        contract.drained(receipt)
        for field, value in (
            ("survivors", True),
            ("ownership_established", False),
            ("cleanup_complete", False),
            ("liveness", [{"pid": 42}]),
            ("errors", ["lost identity"]),
        ):
            broken = dict(receipt, **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                contract.drained(broken)

    def test_descriptor_origin_and_role_schema_are_fail_closed(self):
        case = {
            "schema": 1,
            "profile": "DARWIN_REFERENCE",
            "platform": "darwin",
            "preparation_origin": "installed-copy",
        }
        read = Mock(return_value=json.dumps(case).encode())
        with self.assertRaisesRegex(ValueError, "origin"):
            contract.validate_case(self.root / "case.json", read)
        self.assertEqual(read.call_count, 1)
        case["schema"] = 2
        read.return_value = json.dumps(case).encode()
        with self.assertRaisesRegex(ValueError, "schema"):
            contract.validate_case(self.root / "case.json", read)
        case["schema"] = True
        read.return_value = json.dumps(case).encode()
        with self.assertRaisesRegex(ValueError, "schema"):
            contract.validate_case(self.root / "case.json", read)

    def test_windows_manifest_members_are_native_portable_without_prefix_escape(self):
        member = contract.release_member(
            r"Generated Files\arm-build\matched-build-reference-ci\deploy.py"
        )
        self.assertEqual(
            member.parts,
            ("Generated Files", "arm-build", "matched-build-reference-ci", "deploy.py"),
        )
        for value in (
            r"C:relative.py",
            r"\absolute.py",
            r"..\outside.py",
            "/absolute.py",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                contract.release_member(value)

    def test_descriptor_checks_real_release_records_and_rejects_tampered_content(self):
        root = self.root / "matched-case"
        root.mkdir()
        record = root / "observed.json"
        record.write_text('{"observed":true}')
        descriptor = root / "case.json"
        bindings = {name: contract.binding(record) for name in contract.ROLES}
        bindings["release"] = contract.binding(bootstrap.HERE / "RELEASE.json")
        case = {
            "schema": 1,
            "profile": "DARWIN_REFERENCE",
            "platform": "darwin",
            "preparation_origin": "uv-managed-install",
            "descriptor_path": str(descriptor),
            "case_root": str(root),
            "core_root": str(bootstrap.CORE),
            "preparation_root": str(self.root / "matched-evidence"),
            "output": str(self.root / "matched-output"),
            "verification_output": str(self.root / "matched-verification"),
            "release_root": str(bootstrap.HERE.parents[2]),
            "core_sourcepins_sha256": bootstrap.PIN,
            "bindings": bindings,
            "records": [],
            "run_number": 12,
        }
        descriptor.write_text(json.dumps(case))
        self.assertEqual(
            contract.validate_case(descriptor, Path.read_bytes)["profile"],
            "DARWIN_REFERENCE",
        )
        record.write_text('{"observed":false}')
        with self.assertRaisesRegex(ValueError, "record changed"):
            contract.validate_case(descriptor, Path.read_bytes)

    def header_fixture(self):
        wheel = dict.fromkeys(WHEEL_FIELDS, 0)
        wheel.update(
            create_system=3,
            external_attr=(stat.S_IFREG | 0o644) << 16,
            date_time=[2016, 1, 1, 0, 0, 0],
            extract_version=20,
            create_version=20,
            compress_type=8,
            comment="",
            extra="",
            sha256="a" * 64,
        )
        tar = dict.fromkeys(TAR_FIELDS, 0)
        tar.update(
            uid=0,
            gid=0,
            uname="",
            gname="",
            linkname="",
            devmajor=0,
            devminor=0,
            type="0",
            mode=0o644,
            mtime=0,
            pax_headers={},
            sha256="b" * 64,
        )
        return {
            "wheel": {"module.py": wheel},
            "sdist": {"fastapi-0.119.1/PKG-INFO": tar},
        }

    def test_darwin_full_header_policy_rejects_creator_mode_and_pax_rewrites(self):
        inventory = self.header_fixture()
        contract.headers(inventory, "darwin", {}, self.root)
        for kind, field, value in (
            ("wheel", "create_system", 0),
            ("wheel", "external_attr", 0),
            ("wheel", "date_time", [2026, 1, 1, 0, 0, 0]),
            ("sdist", "uid", 1),
            ("sdist", "pax_headers", {"mtime": "0"}),
        ):
            actual = copy.deepcopy(inventory)
            next(iter(actual[kind].values()))[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                contract.headers(actual, "darwin", {}, self.root)

    def test_darwin_full_state_comparison_never_filters_links_or_target_metadata(self):
        config = {
            "sdk_root": str(self.root / "sdk"),
            "venv_root": str(self.root / "venv"),
            "base_python": str(self.image),
            "publisher_sha256": bootstrap.PUBLISHER["darwin"],
        }
        final = {
            "files": {},
            "directories": {},
            "links": {
                "sdk": {
                    "bin/python": {
                        "raw_target": "python3.13",
                        "target": {"sha256": "a" * 64},
                    }
                }
            },
            "ancestors": {"sdk": {"inode": 7}},
            "inputs": {},
        }
        for field in ("links", "ancestors", "files"):
            observed = copy.deepcopy(final)
            observed[field] = {}
            if field == "files":
                observed[field] = {"unexpected": {}}
            policy = Mock()
            policy.scan.return_value = (observed, {})
            with patch.object(
                bootstrap.reference, "DarwinRuntimeLinks", return_value=policy
            ):
                with (
                    self.subTest(field=field),
                    self.assertRaisesRegex(ValueError, "full Darwin"),
                ):
                    contract.runtime_links(config, final, Mock())
            policy.bind_compiler.assert_called_once()
            policy.scan.assert_called_once()

    def test_long_stock_source_name_requires_exact_pax_path_not_normalization(self):
        inventory = self.header_fixture()
        relative = "tests/" + "a" * 100 + ".py"
        name = "fastapi-0.119.1/" + relative
        member = copy.deepcopy(next(iter(inventory["sdist"].values())))
        member.update(mtime=123.0, pax_headers={"mtime": "123.0", "path": name})
        inventory["sdist"][name] = member
        with patch.object(Path, "stat", return_value=SimpleNamespace(st_mtime=123.0)):
            contract.headers(inventory, "darwin", {relative: {}}, self.root)
            member["pax_headers"]["path"] = relative
            with self.assertRaisesRegex(ValueError, "PAX"):
                contract.headers(inventory, "darwin", {relative: {}}, self.root)

    def test_expired_or_replayed_parent_allocation_cannot_launch(self):
        review = {
            "approved": True,
            "maximum_jobs": 2,
            "delegated_native_admission": True,
            "expected_run_number": 12,
            "issued_unix": 10,
            "expires_unix": 20,
        }
        env = {
            "GITHUB_REPOSITORY": "yeelam-gordon/fastapi",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "RUNNER_ENVIRONMENT": "github-hosted",
            "RUNNER_ARCH": "ARM64",
            "GITHUB_RUN_NUMBER": "12",
        }
        with (
            patch.object(Path, "read_bytes", return_value=json.dumps(review).encode()),
            patch.object(deploy.time, "time", return_value=30),
        ):
            with self.assertRaisesRegex(ValueError, "fresh one-run"):
                deploy.authorize(env)
        env["GITHUB_RUN_ATTEMPT"] = "2"
        with patch.object(Path, "read_bytes", return_value=json.dumps(review).encode()):
            with self.assertRaisesRegex(ValueError, "exact manual"):
                deploy.authorize(env)

    def test_outer_source_requests_default_I_but_metadata_clocks_are_not_build_samples(
        self,
    ):
        source = (bootstrap.HERE / "deploy.py").read_text()
        self.assertIn('"argv": [config["python"], "-I",', source)
        self.assertIn('"OUTER_METADATA_NOT_BUILD_SAMPLES"', source)
        self.assertIn(
            'config["python"], "-I", "-B", str(HERE / "verify_raw.py")', source
        )
        self.assertNotIn('"native_platform_qualified"', source)

    def test_mocked_owned_outer_emits_descriptor_consumable_by_portable_contract(self):
        paths = {
            name: self.root / name
            for name in (
                "install",
                "venv",
                "wheels",
                "source",
                "output",
                "cache",
                "evidence",
            )
        }
        paths["output"] = self.root / "matched-output"
        paths["evidence"] = self.root / "matched-evidence"
        for name in ("install", "venv", "wheels", "source", "evidence"):
            paths[name].mkdir()
        sdk = paths["install"] / "cpython-3.13.15-macos-aarch64-none"
        sdk.mkdir()
        python = paths["venv"] / "bin" / "python"
        python.parent.mkdir()
        python.write_bytes(b"mock-created-runtime")
        uv = self.root / "uv"
        uv.write_bytes(b"mock-qualified-uv")
        associations = {
            "sdk_root": str(sdk),
            "venv_root": str(paths["venv"]),
            "base_python": str(sdk / "bin" / "python3"),
        }
        receipt = {
            "elapsed_seconds": 0.01,
            "publisher_sha256": bootstrap.PUBLISHER["darwin"],
            "evidence_sha256": {},
            **associations,
        }
        bootstrap.save(paths["evidence"] / "creation-receipt.json", receipt)
        bootstrap.save(
            paths["evidence"] / "runtime-observed.json", {"executable": str(python)}
        )
        bootstrap.save(
            paths["evidence"] / "uv-static-identity.json", {"executable": str(uv)}
        )
        (paths["evidence"] / "find.stdout").write_text(
            associations["base_python"] + "\n"
        )
        (self.root / "matched-job-evidence").mkdir()
        calls = []

        def finish(argv, **kwargs):
            calls.append(argv)
            kwargs["stdout_path"].write_bytes(b"")
            kwargs["stderr_path"].write_bytes(b"")
            birth = time.time_ns() // 1000
            process = dict(
                self.darwin,
                executable=argv[0],
                observed_executable=argv[0],
                start_unix_interval_us=[birth, birth + 1],
            )
            bootstrap.save(
                kwargs["stdout_path"].with_suffix(".actual-process.json"), process
            )
            if len(calls) == 1:
                root = self.root / "matched-case"
                config = json.loads((root / "configuration.json").read_bytes())
                admission = json.loads((root / "admission.json").read_bytes())
                bootstrap.save(
                    Path(admission["attempt_marker"]),
                    {
                        "sourcepins": bootstrap.PIN,
                        "configuration": contract.canonical(config),
                    },
                )
            return bootstrap.owned_process.Receipt(
                returncode=0,
                timed_out=False,
                command_wall=0.000001,
                infrastructure_wall=0.000001,
                ownership_established=True,
                survivors=False,
                cleanup_complete=True,
                errors=(),
                native_start_ns=100,
                native_end_ns=200,
                actual_process=process,
            )

        now = time.time()
        with (
            patch.object(deploy, "authorize", return_value={"expires_unix": now + 900}),
            patch.object(bootstrap, "fixed_paths", return_value=paths),
            patch.object(bootstrap, "observe_runtime", return_value=associations),
            patch.object(bootstrap.reference, "qualified_uv_identity"),
            patch.object(
                bootstrap.reference.shared,
                "git",
                side_effect=[bootstrap.reference.shared.REVISION.encode(), b""],
            ),
            patch.object(bootstrap.owned_process, "run_owned", side_effect=finish),
            patch.object(deploy.sys, "platform", "darwin"),
            patch.dict(
                deploy.os.environ,
                {
                    "MATCHED_JOB_START_MS": str(int((now - 10) * 1000)),
                    "GITHUB_RUN_NUMBER": "12",
                },
                clear=True,
            ),
        ):
            deploy.run(self.root)
        root = self.root / "matched-case"
        descriptor = root / "case.json"
        case = contract.validate_case(descriptor, Path.read_bytes)
        config = json.loads((root / "configuration.json").read_bytes())
        admission = json.loads((root / "admission.json").read_bytes())
        self.assertEqual(set(case["bindings"]), contract.ROLES)
        self.assertEqual(case["missing_bindings"], [])
        self.assertEqual(case["preparation_origin"], "uv-managed-install")
        self.assertEqual(calls[0][:2], [str(python), "-I"])
        self.assertNotIn("-B", calls[0])
        self.assertEqual(calls[1][:3], [str(python), "-I", "-B"])
        self.assertTrue(all(call[0] == str(python) for call in calls))
        self.assertTrue(admission["target_isa_runtime_prerequisites_qualified"])
        self.assertNotIn("native_platform_qualified", admission)
        self.assertLessEqual(admission["expires_unix"] - admission["issued_unix"], 600)
        contract.outer(case, config, {"controller_seconds": 0.0000001}, Path.read_bytes)


if __name__ == "__main__":
    unittest.main()
