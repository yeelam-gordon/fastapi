import argparse
import base64
import csv
import dataclasses
import hashlib
import importlib.util
import io
import marshal
import shutil
import struct
import subprocess
import sys
import tarfile
import time
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

import screen
from owned_process import Receipt


class DriverTests(unittest.TestCase):
    def test_isolated_administrative_entrypoint_resolves_sealed_siblings(self):
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(screen.HERE / "screen.py"), "--help"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertIn("--candidate-cache", result.stdout)
        self.assertEqual(result.stderr, "")

    def setUp(self):
        self.root = Path(__file__).resolve().parent / ("test-work-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.args = argparse.Namespace(
            output=self.root,
            python=Path("C:\\runtime\\python.exe"),
            uv=Path("C:\\tools\\uv.exe"),
            wheels=Path("C:\\wheels"),
        )
        self.envs = {
            "C": {"UV_CACHE_DIR": "C:\\same\\cache"},
            "D": {"UV_CACHE_DIR": "D:\\same\\cache"},
        }
        self.argv = screen.command(
            self.args, Path("C:\\evidence\\build-constraints.txt")
        )
        self.receipt = Receipt(
            0,
            False,
            0.1,
            0.01,
            True,
            False,
            True,
            (),
            native_start_ns=1,
            native_end_ns=10,
            actual_process={
                "pid": 42,
                "image": str(self.args.uv),
                "birth_filetime": 100,
            },
        )
        self.canonical = {"source.py": "hash"}
        self.audit_impl = None
        self.source_after_impl = None

    def extract(self, archive, destination):
        destination.mkdir()
        (destination / "dist").mkdir()

    def owned(self, argv, **kwargs):
        folder = kwargs["stdout_path"].parent
        native = {
            "status": "COMPLETE",
            "returncode": 0,
            "argv": self.argv,
            "cwd": str(self.root / "canonical-source"),
            "environment": self.envs[folder.name[-1]],
            "pid": 42,
            "image": str(self.args.uv),
            "birth_filetime": 100,
            "start_ns": 1,
            "end_ns": 10,
        }
        return self.receipt, native

    def output_proof(self, source, canonical, inventory, folder):
        return {
            "tracked": canonical,
            "outputs": {
                "dist/" + path.name: screen.digest(path)
                for path in (source / "dist").iterdir()
            },
            "retained_generated": {},
            "pyc_associations": {},
        }

    def run_driver(self, *, failure=None, native=None, deadline=None):
        with (
            patch.object(screen, "extract", side_effect=self.extract),
            patch.object(screen, "manifest", return_value=self.canonical),
            patch.object(
                screen, "run_native", side_effect=native or self.owned
            ) as owned,
            patch.object(
                screen,
                "source_after",
                side_effect=self.source_after_impl or self.output_proof,
            ),
            patch.object(
                screen,
                "archive_audit",
                side_effect=failure or self.audit_impl,
                return_value=({"sdist": {}, "wheel": {}}, {}),
            ) as audit,
        ):
            try:
                result = screen.execute(
                    self.args,
                    self.canonical,
                    time.perf_counter() + 480 if deadline is None else deadline,
                    self.envs,
                    self.argv,
                )
                return result, owned.call_count, audit.call_count
            finally:
                self.owned_calls, self.audit_calls = owned.call_count, audit.call_count

    def test_failed_receipt_stops_before_audit_next_command_or_value(self):
        self.receipt = dataclasses.replace(self.receipt, returncode=1)
        with self.assertRaisesRegex(RuntimeError, "fatal receipt"):
            self.run_driver()
        self.assertEqual(self.owned_calls, 1)
        self.assertEqual(self.audit_calls, 0)
        self.assertTrue((self.root / "build-00-C" / "ownership.json").is_file())
        self.assertFalse((self.root / "rows.json").exists())
        self.assertFalse((self.root / "result.json").exists())

    def test_deadline_prevents_first_launch(self):
        with self.assertRaisesRegex(RuntimeError, "deadline prevents launch"):
            self.run_driver(deadline=time.perf_counter() + 99)
        self.assertEqual(self.owned_calls, 0)
        self.assertEqual(self.audit_calls, 0)

    def test_header_failure_stops_actual_driver(self):
        with self.assertRaisesRegex(ValueError, "Full frozen"):
            self.run_driver(failure=ValueError("Full frozen archive headers differ"))
        self.assertEqual(self.owned_calls, 1)
        self.assertFalse((self.root / "rows.json").exists())

    def test_record_failure_stops_actual_driver(self):
        with self.assertRaisesRegex(RuntimeError, "RECORD mismatch"):
            self.run_driver(failure=RuntimeError("RECORD mismatch"))
        self.assertEqual(self.owned_calls, 1)
        self.assertFalse((self.root / "rows.json").exists())

    def test_observed_argv_change_is_fatal(self):
        def changed(argv, **kwargs):
            receipt, data = self.owned(argv, **kwargs)
            data["argv"] = [*self.argv, "--no-build-isolation"]
            return receipt, data

        with self.assertRaisesRegex(RuntimeError, "actual CLI/environment differs"):
            self.run_driver(native=changed)
        self.assertEqual(self.owned_calls, 1)
        self.assertEqual(self.audit_calls, 0)

    def test_successful_driver_preserves_fixed_fourteen_build_schedule(self):
        rows, calls, audits = self.run_driver()
        self.assertEqual(calls, 14)
        self.assertEqual(audits, 14)
        self.assertEqual(
            [(row["arm"], row["measured"], row["pair"]) for row in rows],
            screen.schedule(),
        )

    def test_native_observation_keeps_uv_as_guardian_root(self):
        with patch.object(
            screen.owned_process, "run_owned", return_value=self.receipt
        ) as owned:
            receipt, native = screen.run_native(
                self.argv,
                cwd=self.root,
                env=self.envs["C"],
                native_clock=True,
            )
        owned.assert_called_once_with(
            self.argv,
            cwd=self.root,
            env=self.envs["C"],
            native_clock=True,
        )
        self.assertTrue(receipt.succeeded)
        self.assertEqual(native["status"], "COMPLETE")
        self.assertEqual(native["pid"], 42)
        self.assertEqual(
            {key: native[key] for key in self.receipt.actual_process},
            self.receipt.actual_process,
        )
        self.assertEqual((native["start_ns"], native["end_ns"]), (1, 10))

    def test_missing_qualified_actual_process_is_not_complete(self):
        receipt = dataclasses.replace(self.receipt, actual_process=None)
        with patch.object(screen.owned_process, "run_owned", return_value=receipt):
            _, native = screen.run_native(
                self.argv,
                cwd=self.root,
                env=self.envs["C"],
                native_clock=True,
            )
        self.assertEqual(native["status"], "FAILED")

    def packaging_fixture(
        self, destination, *, corrupt_record=False, changed_header=False
    ):
        destination.mkdir()
        dist = destination / "dist"
        dist.mkdir()
        (dist / ".gitignore").write_bytes(b"*")
        original = b'[project]\nname="fastapi"\ndynamic=["version"]\n'
        (destination / "pyproject.toml").write_bytes(original)
        generated = b'[project]\nname="fastapi"\ndynamic=[]\nversion="0.119.1"\n'
        with tarfile.open(dist / "fastapi-0.119.1.tar.gz", "w:gz") as archive:
            for index in range(1196):
                name = "pyproject.toml" if index == 0 else f"payload-{index}"
                data = generated if index == 0 else b"payload"
                member = tarfile.TarInfo("fastapi-0.119.1/" + name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        members = {f"fastapi/payload-{index}": b"payload" for index in range(56)}
        members["fastapi-0.119.1.dist-info/WHEEL"] = b"Generator: pdm-backend (2.5.0)\n"
        record_name = "fastapi-0.119.1.dist-info/RECORD"
        record = io.StringIO()
        writer = csv.writer(record)
        for name, data in members.items():
            value = (
                base64.urlsafe_b64encode(hashlib.sha256(data).digest())
                .rstrip(b"=")
                .decode()
            )
            writer.writerow(
                [name, "sha256=" + ("wrong" if corrupt_record else value), len(data)]
            )
        writer.writerow([record_name, "", ""])
        members[record_name] = record.getvalue().encode()
        with zipfile.ZipFile(dist / "fastapi-0.119.1-py3-none-any.whl", "w") as archive:
            for name, data in members.items():
                member = zipfile.ZipInfo(name)
                if changed_header:
                    member.comment = b"changed"
                archive.writestr(member, data)

    def use_real_audit(self):
        self.canonical = {
            "pyproject.toml": hashlib.sha256(
                b'[project]\nname="fastapi"\ndynamic=["version"]\n'
            ).hexdigest()
        }
        self.audit_impl = screen.archive_audit

    def test_real_record_validation_is_fatal_through_driver(self):
        self.use_real_audit()

        def extract(archive, destination):
            self.packaging_fixture(destination, corrupt_record=True)

        self.extract = extract
        with self.assertRaisesRegex(RuntimeError, "RECORD mismatch"):
            self.run_driver()
        self.assertEqual(self.owned_calls, 1)
        self.assertFalse((self.root / "rows.json").exists())
        first = self.root / "build-00-C"
        self.assertEqual(len(list((first / "artifacts").iterdir())), 2)
        self.assertEqual((first / "dist.gitignore").read_bytes(), b"*")

    def test_real_full_header_difference_is_fatal_through_driver(self):
        self.use_real_audit()
        builds = []

        def extract(archive, destination):
            self.packaging_fixture(destination, changed_header=bool(builds))
            builds.append(destination)

        self.extract = extract
        with self.assertRaisesRegex(ValueError, "Full frozen archive"):
            self.run_driver()
        self.assertEqual(self.owned_calls, 2)
        self.assertEqual(len(screen.load(self.root / "rows.json")), 1)
        self.assertTrue((self.root / "build-01-D" / "full-headers.json").is_file())

    def test_real_uv_ignore_and_raw_pyc_survive_all_driver_payload_replacements(self):
        self.use_real_audit()
        original_after, original_manifest = screen.source_after, screen.manifest
        sample = b"answer = 42\n"
        self.canonical["sample.py"] = hashlib.sha256(sample).hexdigest()

        def extract(archive, destination):
            self.packaging_fixture(destination)
            source = destination / "sample.py"
            source.write_bytes(sample)
            cache = destination / "__pycache__"
            cache.mkdir()
            header = importlib.util.MAGIC_NUMBER + struct.pack(
                "<III",
                0,
                int(source.stat().st_mtime) & 0xFFFFFFFF,
                len(sample),
            )
            (cache / "sample.cpython-313.pyc").write_bytes(
                header + marshal.dumps(compile(sample, str(source), "exec")),
            )

        def audit_source(source, canonical, inventory, folder):
            with patch.object(screen, "manifest", original_manifest):
                return original_after(source, canonical, inventory, folder)

        self.extract = extract
        self.source_after_impl = audit_source
        rows, calls, audits = self.run_driver()
        self.assertEqual((calls, audits), (14, 14))
        screen.seal_rows(self.root, rows)
        first = self.root / "build-00-C"
        self.assertEqual((first / "dist.gitignore").read_bytes(), b"*")
        self.assertEqual(len(list((first / "artifacts").iterdir())), 2)
        proof = screen.load(first / "source-after.json")
        association = proof["pyc_associations"]["__pycache__/sample.cpython-313.pyc"]
        retained = first / association["retained"]
        self.assertEqual(screen.digest(retained), association["pyc_sha256"])
        self.assertEqual(association["source_sha256"], self.canonical["sample.py"])
        with tarfile.open(first / "artifacts" / "fastapi-0.119.1.tar.gz") as archive:
            self.assertEqual(len(archive.getmembers()), 1196)

    def test_changed_uv_ignore_is_fatal_before_next_build(self):
        self.use_real_audit()

        def extract(archive, destination):
            self.packaging_fixture(destination)
            (destination / "dist" / ".gitignore").write_bytes(b"*\n")

        self.extract = extract
        with self.assertRaisesRegex(RuntimeError, "pinned UV dist ignore"):
            self.run_driver()
        self.assertEqual(self.owned_calls, 1)
        self.assertFalse((self.root / "rows.json").exists())


class ContractTests(unittest.TestCase):
    def test_environment_evidence_binds_without_disclosing_credentials(self):
        env = {
            "UV_CACHE_DIR": "D:\\same\\cache",
            "TEMP": "C:\\scratch",
            "ACTIONS_RUNTIME_TOKEN": "private-token",
        }
        evidence = screen.environment_evidence(env)
        self.assertNotIn("private-token", str(evidence))
        self.assertNotIn("ACTIONS_RUNTIME_TOKEN", str(evidence))
        self.assertNotIn(hashlib.sha256(b"private-token").hexdigest(), str(evidence))
        self.assertEqual(evidence["values"]["TEMP"], "C:\\scratch")
        self.assertEqual(env["ACTIONS_RUNTIME_TOKEN"], "private-token")

    def test_inherited_cache_override_preserves_every_other_value(self):
        inherited = {
            "UV_CACHE_DIR": "C:\\setup-uv",
            "TEMP": "C:\\scratch",
            "GITHUB_TOKEN": "private-token",
            "ACTIONS_RUNTIME_TOKEN": "other-token",
        }
        control = screen.environment(Path("C:\\same\\cache"), inherited)
        candidate = screen.environment(Path("D:\\same\\cache"), inherited)
        self.assertEqual(
            screen.environment_delta(control, candidate),
            {"changed_keys": ["UV_CACHE_DIR"], "all_non_cache_values_equal": True},
        )
        self.assertEqual(
            {key: value for key, value in control.items() if key != "UV_CACHE_DIR"},
            {key: value for key, value in inherited.items() if key != "UV_CACHE_DIR"},
        )
        self.assertEqual(inherited["UV_CACHE_DIR"], "C:\\setup-uv")

    def test_cache_is_only_environment_delta_and_cli_is_common(self):
        inherited = {"TEMP": "C:\\scratch", "TMP": "C:\\scratch", "PATH": "original"}
        control = screen.environment(Path("C:\\same\\cache"), inherited)
        candidate = screen.environment(Path("D:\\same\\cache"), inherited)
        self.assertEqual(
            inherited, {"TEMP": "C:\\scratch", "TMP": "C:\\scratch", "PATH": "original"}
        )
        self.assertEqual(
            {key for key in control if control[key] != candidate[key]}, {"UV_CACHE_DIR"}
        )
        args = argparse.Namespace(
            uv=Path("C:\\uv.exe"),
            python=Path("C:\\python.exe"),
            wheels=Path("C:\\wheels"),
        )
        self.assertEqual(
            screen.command(args, Path("C:\\constraints.txt")),
            [
                "C:\\uv.exe",
                "build",
                "--python",
                "C:\\python.exe",
                "--no-python-downloads",
                "--offline",
                "--build-constraints",
                "C:\\constraints.txt",
                "--find-links",
                "C:\\wheels",
            ],
        )

    def test_ambient_override_is_rejected_not_silently_removed(self):
        with self.assertRaisesRegex(RuntimeError, "ambient benchmark overrides"):
            screen.environment(Path("C:\\cache"), {"PYTHONPATH": "injected"})

    def test_statistics_require_complete_valid_frozen_schedule(self):
        rows = [
            {
                "arm": arm,
                "measured": measured,
                "pair": pair,
                "status": "VALID",
                "seconds": 10 if arm == "C" else 9,
            }
            for arm, measured, pair in screen.schedule()
        ]
        result = screen.summarize(rows)
        self.assertTrue(result["material"])
        self.assertEqual(result["wins"], 6)
        self.assertEqual(
            [pair["order"] for pair in result["pairs"]],
            ["AB", "BA", "AB", "BA", "AB", "BA"],
        )
        with self.assertRaisesRegex(RuntimeError, "complete frozen schedule"):
            screen.summarize(rows[:-1])
        rows[-1]["status"] = "FAILED"
        with self.assertRaisesRegex(RuntimeError, "invalid row"):
            screen.summarize(rows)

    def test_small_gain_never_passes_material_gate(self):
        rows = [
            {
                "arm": arm,
                "measured": measured,
                "pair": pair,
                "status": "VALID",
                "seconds": 10 if arm == "C" else 9.6,
            }
            for arm, measured, pair in screen.schedule()
        ]
        self.assertFalse(screen.summarize(rows)["material"])

    def test_support_copies_are_exactly_qualified(self):
        self.assertEqual(
            {name: screen.digest(screen.HERE / name) for name in screen.SUPPORT},
            screen.SUPPORT,
        )


if __name__ == "__main__":
    unittest.main()
