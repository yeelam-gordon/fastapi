"""Focused stdlib tests; no builds, system recording, or temporary directories."""

import json
import os
import shutil
import struct
import subprocess
import sys
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import arm_diag_platform as platform


class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / (".platform-test-" + uuid.uuid4().hex)
        self.root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_isolated_stdlib_import_and_snapshot(self):
        module = str(Path(platform.__file__).resolve())
        code = (
            "import importlib.util,json,sys;"
            f"s=importlib.util.spec_from_file_location('adapter',{module!r});"
            "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
            "r=m.process_snapshot();assert 'psutil' not in sys.modules;"
            "assert r['scope']=='self_all_threads';"
            "assert r['cpu']['status']=='measured';print(json.dumps(r))"
        )
        result = subprocess.run(
            [sys.executable, "-I", "-S", "-c", code],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        snapshot = json.loads(result.stdout)
        self.assertGreaterEqual(snapshot["cost_ns"], 0)
        self.assertEqual(snapshot["cpu"]["unit"], "seconds")
        self.assertEqual(snapshot["cpu"]["aggregation"], "lifetime_cumulative")
        self.assertNotIn("children_user", json.dumps(snapshot))

    def test_darwin_units_and_distinct_block_io(self):
        usage = types.SimpleNamespace(ru_maxrss=123, ru_inblock=7, ru_oublock=9)
        resource = types.SimpleNamespace(RUSAGE_SELF=0, getrusage=lambda _: usage)
        with (
            patch.object(platform.sys, "platform", "darwin"),
            patch.dict(sys.modules, {"resource": resource}),
        ):
            result = platform.process_snapshot()
        self.assertIsNone(result["memory"]["peak_rss"]["value"])
        self.assertEqual(result["memory"]["peak_rss_raw"]["value"], 123)
        self.assertEqual(
            result["memory"]["peak_rss_raw"]["unit"], "unverified_native_unit"
        )
        self.assertEqual(result["io"]["ru_inblock"]["unit"], "block_io_operations")
        self.assertNotIn("ReadOperationCount", result["io"])

    def test_native_counter_error_is_unavailable_not_zero(self):
        with (
            patch.object(
                platform, "_windows_process", side_effect=OSError("private-token")
            ),
            patch.object(platform.sys, "platform", "win32"),
        ):
            snapshot = platform.process_snapshot()
        self.assertIsNone(snapshot["memory"]["rss"]["value"])
        self.assertIsNone(snapshot["io"]["value"])
        self.assertNotIn("private-token", json.dumps(snapshot))

    def test_cpu_failure_keeps_nulls(self):
        with patch.object(platform.os, "times", side_effect=OSError):
            snapshot = platform.process_snapshot()
        self.assertEqual(snapshot["cpu"]["status"], "unavailable")
        self.assertIsNone(snapshot["cpu"]["user_seconds"])
        self.assertIsNone(snapshot["cpu"]["kernel_seconds"])

    def test_windows_working_set_and_lifetime_peak(self):
        if sys.platform != "win32":
            self.skipTest("native Windows receipt test")
        snapshot = platform.process_snapshot()
        self.assertEqual(snapshot["memory"]["rss"]["status"], "measured")
        self.assertEqual(snapshot["memory"]["rss"]["unit"], "bytes")
        self.assertEqual(snapshot["memory"]["peak_rss"]["aggregation"], "lifetime_peak")
        self.assertEqual(snapshot["io"]["ReadTransferCount"]["unit"], "bytes")
        self.assertEqual(snapshot["io"]["ReadOperationCount"]["unit"], "operations")

    def test_pe_and_fat_macho_identities(self):
        pe = self.root / "python.exe"
        data = bytearray(256)
        data[:2] = b"MZ"
        struct.pack_into("<I", data, 60, 128)
        data[128:134] = b"PE\0\0" + struct.pack("<H", 0xAA64)
        pe.write_bytes(data)
        result = platform._binary(pe)
        self.assertEqual(result["architecture"]["value"][0]["name"], "arm64")
        self.assertEqual(len(result["sha256"]), 64)
        fat = self.root / "universal"
        fat.write_bytes(
            b"\xca\xfe\xba\xbe"
            + struct.pack(">I", 2)
            + struct.pack(">I", 0x100000C)
            + b"\0" * 16
            + struct.pack(">I", 0x1000007)
            + b"\0" * 16
        )
        names = {item["name"] for item in platform._architectures(fat)}
        self.assertEqual(names, {"arm64", "x86_64"})
        self.assertIsNone(platform._binary(fat)["selected_runtime_slice"]["value"])
        fat.write_bytes(b"\xca\xfe\xba\xbe" + struct.pack(">I", 1000))
        self.assertEqual(platform._binary(fat)["status"], "unavailable")

    def test_inventory_actual_action_contract_and_privacy(self):
        receipt = self.root / "action.json"
        action = Path(__file__).parent / "action" / "main.cjs"
        if not action.is_file():
            common = subprocess.run(
                ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                cwd=Path(__file__).parent,
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            ).stdout.strip()
            action = (
                Path(common).parent
                / "Generated Files"
                / "arm-build"
                / "diagnostics"
                / "action"
                / "main.cjs"
            )
        self.assertTrue(
            action.is_file(), "actual parent-owned action producer required"
        )
        node = shutil.which("node")
        self.assertIsNotNone(
            node, "existing Node runtime required for producer contract test"
        )
        subprocess.run(
            [node, str(action)],
            env={
                **os.environ,
                "DIAG_ROOT": str(self.root),
                "INPUT_OUTPUT": str(receipt),
                "UNDECLARED_SECRET": "DO_NOT_COPY_ENV",
            },
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        produced = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(produced["schema"], "arm-analysis-action-runtime-v1")
        self.assertNotIn("DO_NOT_COPY_ENV", json.dumps(produced))
        with (
            patch.dict(os.environ, {"ARM_DIAGNOSTIC_ACTION_JSON": str(receipt)}),
            patch.object(shutil, "which", return_value=None),
        ):
            actual = platform.inventory([], str(self.root / "actual-producer"))
        self.assertEqual(actual["actions_node"]["producer_schema"], produced["schema"])
        self.assertEqual(
            actual["actions_node"]["receipt"]["node"]["sha256"],
            produced["node"]["sha256"],
        )
        # Add disallowed fields without inventing or replacing any producer identity.
        produced["secret"] = "DO_NOT_COPY_ACTION_PAYLOAD"
        produced["node"]["secret"] = "DO_NOT_COPY_NODE_SECRET"
        produced["environment"]["PATH"] = "DO_NOT_COPY_ACTION_PATH"
        receipt.write_text(json.dumps(produced), encoding="utf-8")
        with (
            patch.dict(
                os.environ,
                {
                    "ARM_DIAGNOSTIC_ACTION_JSON": str(receipt),
                    "UNDECLARED_SECRET": "DO_NOT_COPY_ENV",
                    "GITHUB_WORKFLOW": "token=DO_NOT_COPY_SECRET",
                },
            ),
            patch.object(
                platform.shutil if hasattr(platform, "shutil") else shutil,
                "which",
                return_value=None,
            ),
        ):
            result = platform.inventory([str(self.root)], str(self.root / "out"))
        serialized = json.dumps(result)
        for secret in (
            "DO_NOT_COPY_ACTION_PAYLOAD",
            "DO_NOT_COPY_ACTION_PATH",
            "DO_NOT_COPY_NODE_SECRET",
            "DO_NOT_COPY_ENV",
            "DO_NOT_COPY_SECRET",
        ):
            self.assertNotIn(secret, serialized)
        self.assertNotIn("PATH", result["environment"])
        action_receipt = result["actions_node"]["receipt"]
        self.assertEqual(action_receipt["schema"], produced["schema"])
        for field in ("version", "architecture", "executable", "sha256"):
            self.assertEqual(
                action_receipt["node"][field], platform._safe(produced["node"][field])
            )
        self.assertEqual(
            action_receipt["host"]["platform"], produced["host"]["platform"]
        )
        for field in (
            "GITHUB_RUN_ID",
            "GITHUB_RUN_ATTEMPT",
            "GITHUB_JOB",
            "ImageVersion",
        ):
            value = produced["environment"][field]
            self.assertEqual(
                action_receipt["environment"][field],
                platform._safe(value) if value is not None else None,
            )
        self.assertNotIn("PATH", action_receipt["environment"])
        for field in ("version", "architecture", "executable", "sha256"):
            with self.subTest(missing_required_identity=field):
                malformed = json.loads(json.dumps(produced))
                del malformed["node"][field]
                receipt.write_text(json.dumps(malformed), encoding="utf-8")
                with patch.dict(
                    os.environ, {"ARM_DIAGNOSTIC_ACTION_JSON": str(receipt)}
                ):
                    unavailable = platform._action_inventory()
                self.assertEqual(unavailable["status"], "unavailable")
                self.assertIn(f"node.{field}", unavailable["reason"])
        for field, invalid in (
            ("node.sha256", "not-a-hash"),
            ("node.architecture", "unrecognized"),
            ("node.version", ""),
            ("node.executable", "relative"),
            ("host.platform", None),
        ):
            with self.subTest(invalid_identity=field):
                malformed = json.loads(json.dumps(produced))
                section, key = field.split(".")
                malformed[section][key] = invalid
                receipt.write_text(json.dumps(malformed), encoding="utf-8")
                with patch.dict(
                    os.environ, {"ARM_DIAGNOSTIC_ACTION_JSON": str(receipt)}
                ):
                    unavailable = platform._action_inventory()
                self.assertEqual(unavailable["status"], "unavailable")
                self.assertIn(field, unavailable["reason"])
        self.assertEqual(
            result["environment"]["GITHUB_WORKFLOW"]["value"], "<REDACTED>"
        )
        self.assertEqual(
            result["runner_image_origins"]["historical_windows_console"]["version"],
            "20261025.196.1",
        )
        self.assertEqual(
            result["runner_image_origins"]["historical_windows_bootstrap"]["version"],
            "20261026.197.1",
        )
        saved = self.root / "out" / "platform-inventory.json"
        self.assertEqual(json.loads(saved.read_text()), result)

    def test_invalid_or_missing_action_receipt(self):
        with patch.dict(
            os.environ, {"ARM_DIAGNOSTIC_ACTION_JSON": str(self.root / "absent")}
        ):
            self.assertEqual(platform._action_inventory()["status"], "unavailable")
        file = self.root / "invalid.json"
        file.write_text("[]", encoding="utf-8")
        with patch.dict(os.environ, {"ARM_DIAGNOSTIC_ACTION_JSON": str(file)}):
            self.assertEqual(platform._action_inventory()["status"], "unavailable")

    def test_native_capture_skips_callback_and_all_recording(self):
        calls = []
        with (
            patch.dict(os.environ, {"DIAG_NATIVE_TRACES_REQUESTED": "true"}),
            patch.object(shutil, "which", return_value="native-tool"),
            patch.object(platform, "_binary", return_value={"status": "measured"}),
            patch.object(
                platform,
                "_probe",
                side_effect=lambda argv: (
                    calls.append(argv)
                    or {"status": "measured", "stdout": "help", "returncode": 0}
                ),
            ),
        ):
            result = platform.native_capture(
                lambda: self.fail("unsupported capture must not invoke build"),
                str(self.root / "private_raw"),
            )
        self.assertFalse(result["build_invoked"])
        for collector in result["collectors"].values():
            self.assertTrue(collector["requested"])
            self.assertEqual(collector["status"], "unavailable")
            self.assertIsNone(collector["value"])
        self.assertTrue(all("-help" in argv or "help" in argv for argv in calls))
        self.assertEqual(result["upload_summaries"], [])
        self.assertFalse(list(self.root.rglob("*.etl")))

    def test_native_explicitly_disabled_never_probes_or_builds(self):
        with (
            patch.dict(os.environ, {"DIAG_NATIVE_TRACES_REQUESTED": "false"}),
            patch.object(shutil, "which", side_effect=AssertionError("must not probe")),
            patch.object(
                platform, "_probe", side_effect=AssertionError("must not run tools")
            ),
        ):
            result = platform.native_capture(
                lambda: self.fail("disabled native pass must not invoke build"),
                str(self.root),
            )
        self.assertEqual(result["status"], "not-requested")
        self.assertFalse(result["requested"])
        self.assertFalse(result["build_invoked"])
        self.assertEqual(result["capabilities"], {})
        self.assertIsNone(result["capture_window"])
        for collector in result["collectors"].values():
            self.assertFalse(collector["requested"])
            self.assertEqual(collector["status"], "not-requested")
            self.assertIsNone(collector["value"])
        self.assertEqual(
            json.loads((self.root / "native-capabilities.json").read_text()), result
        )

    def test_missing_native_tools_and_darwin_candidate_no_recording(self):
        with (
            patch.dict(os.environ, {"DIAG_NATIVE_TRACES_REQUESTED": "true"}),
            patch.object(shutil, "which", return_value=None),
            patch.object(platform.sys, "platform", "darwin"),
        ):
            result = platform.native_capture(
                lambda: self.fail("must skip"), str(self.root)
            )
        self.assertEqual(set(result["capabilities"]), {"sample", "xctrace", "fs_usage"})
        self.assertTrue(
            all(
                item["status"] == "unavailable"
                for item in result["capabilities"].values()
            )
        )

    def test_timeout_and_error_do_not_leak_command_or_exception(self):
        with patch.object(
            subprocess, "run", side_effect=subprocess.TimeoutExpired("secret", 5)
        ):
            result = platform._probe(["private-argv"])
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("secret", json.dumps(result))
        with patch.object(
            subprocess, "run", side_effect=PermissionError("private-path")
        ):
            result = platform._probe(["private-argv"])
        self.assertEqual(result["reason"], "PermissionError")
        self.assertNotIn("private-path", json.dumps(result))

    def test_filesystem_failure_retains_requested_actual_path(self):
        missing = self.root / "not-created" / "source"
        with patch.object(platform.sys, "platform", "unsupported"):
            result = platform._filesystem(str(missing))
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["exists"])
        self.assertEqual(result["probed_existing_ancestor"], str(self.root.resolve()))
        self.assertIn("not-created", result["requested_path"])


if __name__ == "__main__":
    unittest.main()
