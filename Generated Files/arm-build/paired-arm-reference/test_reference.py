"""Q-only fixture/mocked regressions; no bootstrap, restoration or benchmark."""

import ast
import base64
import csv
import gzip
import hashlib
import io
import json
import os
import shutil
import sqlite3
import struct
import subprocess
import tarfile
import unittest
import uuid
import xml.etree.ElementTree as ET
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import compare
import driver
import frozen
import guards
import source

HERE = Path(__file__).resolve().parent


class Fixture(unittest.TestCase):
    def setUp(self):
        self.root = HERE / ".local" / "fixtures" / uuid.uuid4().hex
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root)


class NativeTests(unittest.TestCase):
    def test_native_universal2_not_tag_rejected(self):
        data = bytearray(48)
        data[:4] = b"\xca\xfe\xba\xbe"
        struct.pack_into(">I", data, 4, 2)
        struct.pack_into(">I", data, 8, 0x1000007)
        struct.pack_into(">I", data, 28, 0x100000C)
        architectures = guards.slices(data)
        guards.architecture_ok("Darwin", "arm64", 64, architectures)
        with self.assertRaises(RuntimeError):
            guards.architecture_ok("Darwin", "arm64", 64, architectures, translated=1)

    def test_reject_x86_process_even_with_arm_slice(self):
        for system in ("Windows", "Darwin"):
            with self.subTest(system=system), self.assertRaises(RuntimeError):
                guards.architecture_ok(system, "x86_64", 64, {0xAA64, 0x100000C})

    def test_reject_x64_windows_pe(self):
        data = bytearray(128)
        data[:2] = b"MZ"
        struct.pack_into("<I", data, 60, 80)
        data[80:84] = b"PE\0\0"
        struct.pack_into("<H", data, 84, 0x8664)
        with self.assertRaises(RuntimeError):
            guards.architecture_ok("Windows", "ARM64", 64, guards.slices(data))
        struct.pack_into("<H", data, 84, 0xAA64)
        guards.architecture_ok("Windows", "ARM64", 64, guards.slices(data))

    def test_thin_macho(self):
        guards.architecture_ok(
            "Darwin",
            "arm64",
            64,
            guards.slices(b"\xcf\xfa\xed\xfe" + struct.pack("<I", 0x100000C)),
        )

    def test_no_platform_global_mutation_or_eager_sysconfig(self):
        tree = ast.parse((HERE / "guards.py").read_text())
        self.assertFalse(
            any(
                isinstance(n, ast.Import)
                and any(name.name == "sysconfig" for name in n.names)
                for n in tree.body
            )
        )
        self.assertNotIn("sys.platform =", (HERE / "guards.py").read_text())


class EnvironmentTests(Fixture):
    def test_synthetic_home_no_credentials_hooks_or_corporate_feed(self):
        env = guards.environment(
            self.root,
            {
                "HOME": "private-home",
                "USERPROFILE": "private-home",
                "PIP_INDEX_URL": "https://private-feed/",
                "PIP_TRUSTED_HOST": "private",
                "PYTHONPATH": "private-hook",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPYCACHEPREFIX": "private-pyc",
                "UV": "private-tool",
                "FASTAPI_CLOUD_TOKEN": "private",
                "SENTRY_DSN": "private",
                "GITHUB_TOKEN": "private",
                "COVERAGE_CORE": "sysmon",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "CONTEXT": "private",
                "PATH": "normal-tools",
            },
        )
        self.assertNotIn("private", json.dumps(env))
        self.assertEqual(env["HOME"], str(self.root / "home"))
        self.assertEqual(env["PATH"], "normal-tools")
        self.assertEqual(env["PIP_INDEX_URL"], "https://pypi.org/simple")
        self.assertNotIn("PYTHONDONTWRITEBYTECODE", env)
        self.assertNotIn("COVERAGE_CORE", env)

    def test_expected_cli_one_and_raw_bytes(self):
        message = b"Path does not exist non_existent_file.py\r\n"
        guards.cli_valid(1, message, b"")
        for code, out, err in (
            (0, message, b""),
            (2, message, b""),
            (1, b"", b""),
            (1, message, b"error"),
        ):
            with (
                self.subTest(code=code, out=out, err=err),
                self.assertRaises(RuntimeError),
            ):
                guards.cli_valid(code, out, err)
        with self.assertRaises(RuntimeError):
            guards.raw_equal((message, b""), (message.replace(b"\r\n", b"\n"), b""))

    def test_command_no_profile_or_bytecode_flags(self):
        python = self.root / "python.exe"
        self.assertEqual(
            guards.cli_command(python),
            [
                str(python),
                "-m",
                "coverage",
                "run",
                "-m",
                "fastapi",
                "dev",
                "non_existent_file.py",
            ],
        )

    def test_build_constraints_and_clock_environment(self):
        run = driver.Run(self.root)
        run.wheels = {a: self.root / a / guards.WHEEL for a in "AB"}
        run.backend_constraints = {a: self.root / a / "constraints.txt" for a in "AB"}
        env = run.build_env("B", self.root / "evidence", "trials")
        self.assertEqual(env["PIP_NO_INDEX"], "1")
        self.assertEqual(env["PIP_REQUIRE_HASHES"], "1")
        self.assertEqual(env["SOURCE_DATE_EPOCH"], "1700000000")
        self.assertEqual(env["PIP_CONSTRAINT"], run.backend_constraints["B"].as_uri())
        self.assertNotIn(" ", env["PIP_CONSTRAINT"])
        self.assertNotIn(" ", env["PIP_FIND_LINKS"])
        self.assertNotIn("PYTHONDONTWRITEBYTECODE", env)
        with self.assertRaises(RuntimeError):
            driver.Run(self.root)

    def test_exit_immediate_capture_no_ignore_errors(self):
        run = driver.Run(self.root)
        with patch.object(
            driver.subprocess,
            "run",
            return_value=subprocess.CompletedProcess(["mock"], 2),
        ):
            with self.assertRaises(RuntimeError):
                run.command("failure", ["mock"], expected=1)
        row = json.loads((run.upload / "failure" / "command.json").read_text())
        self.assertEqual(row["exit"], 2)
        self.assertFalse(row["valid"])
        self.assertFalse(row["performance_eligible"])

    def test_timeout_preserves_partial_stdio_hashes(self):
        run = driver.Run(self.root)
        with patch.object(
            driver.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired("mock", 1800),
        ):
            with self.assertRaises(subprocess.TimeoutExpired):
                run.command("timeout", ["mock"])
        row = json.loads((run.upload / "timeout" / "command.json").read_text())
        self.assertEqual(row["error"], "TimeoutExpired")
        self.assertIn("stdout_sha256", row)
        self.assertFalse(row["valid"])


class PreflightInputTests(Fixture):
    def test_local_inputs_refused_for_ci(self):
        run = driver.Run(self.root)
        with self.assertRaisesRegex(RuntimeError, "preflight-only"):
            run.preflight_inputs(False, stock_wheel=self.root / "stock.whl")
        with patch.dict(
            os.environ, {"PIP_INDEX_URL": "https://approved.example/simple"}
        ):
            run.preflight_inputs(False)
        self.assertEqual(run.owner_dev_index, "https://pypi.org/simple")

    def test_bad_local_bodies_stop_before_setup(self):
        run = driver.Run(self.root)
        bad = self.root / "respx-0.23.1-py3-none-any.whl"
        bad.write_bytes(b"not the frozen wheel")
        for keyword in ("stock_wheel", "respx_wheel"):
            with self.subTest(keyword=keyword), patch.object(run, "setup") as setup:
                with self.assertRaisesRegex(RuntimeError, "frozen official SHA256"):
                    run.execute(preflight=True, **{keyword: bad})
                setup.assert_not_called()

    def test_approved_process_index_is_preflight_owner_only(self):
        run = driver.Run(self.root)
        run.test_python = self.root / "reference-python"
        with patch.dict(
            os.environ, {"PIP_INDEX_URL": "https://approved.example/simple"}
        ):
            run.preflight_inputs(True)
            self.assertEqual(
                os.environ["PIP_INDEX_URL"], "https://approved.example/simple"
            )
        with patch.object(run, "py") as invoke:
            run.owner_dev_install()
        args = invoke.call_args.args[2]
        env = invoke.call_args.kwargs["env"]
        self.assertEqual(env["PIP_INDEX_URL"], "https://approved.example/simple")
        self.assertNotIn("PIP_NO_INDEX", env)
        self.assertIn("--require-hashes", args)
        self.assertIn("--no-deps", args)
        self.assertIn("--only-binary=:all:", args)
        self.assertEqual(
            args[args.index("--target") + 1], str(self.root / "owner-dev-only")
        )
        self.assertEqual(run.env["PIP_INDEX_URL"], "https://pypi.org/simple")

    def test_verified_local_respx_has_no_index_lookup(self):
        run = driver.Run(self.root)
        run.test_python = self.root / "reference-python"
        wheel = self.root / "respx-0.23.1-py3-none-any.whl"
        wheel.write_bytes(b"fixture")
        expected = "b18004b029935384bccfa6d7d9d74b4ec9af73a081cc28600fffc0447f4b8c1a"
        with patch.object(driver, "sha", return_value=expected):
            run.preflight_inputs(True, respx_wheel=wheel)
        with patch.object(run, "py") as invoke:
            run.owner_dev_install()
        env = invoke.call_args.kwargs["env"]
        self.assertEqual(env["PIP_NO_INDEX"], "1")
        self.assertEqual(env["PIP_FIND_LINKS"], self.root.as_uri())
        self.assertIn("--require-hashes", invoke.call_args.args[2])

    def test_preflight_index_does_not_weaken_tls_or_log_url_credentials(self):
        run = driver.Run(self.root)
        for index in (
            "http://unverified.example/simple",
            "https://user:password@example.test/simple",
            "https://example.test/simple?token=private",
        ):
            with (
                self.subTest(index=index),
                patch.dict(os.environ, {"PIP_INDEX_URL": index}),
            ):
                with self.assertRaisesRegex(RuntimeError, "verified HTTPS"):
                    run.preflight_inputs(True)


class SourceTests(Fixture):
    def test_pinned_fetch_uses_ordinary_git_without_security_overrides(self):
        calls = []
        with (
            patch.object(source, "git", return_value=(guards.REV + "\n").encode()),
            patch.object(source, "prove", return_value={"files": {}}),
        ):
            source.fetch(
                self.root,
                "pinned",
                "https://github.com/fastapi/fastapi.git",
                guards.REV,
                lambda label, args: calls.append(args),
            )
        self.assertEqual(calls[0], ["git", "init", str(self.root / "pinned-objects")])
        self.assertIn("--depth=1", calls[1])
        self.assertEqual(calls[1][-1], guards.REV)
        self.assertEqual(len(calls), 3)
        self.assertNotIn("checkout", repr(calls))
        self.assertNotIn("safe.bareRepository", repr(calls))

    def archive(self, data=b"line one\nline two\n", mode=0o664):
        path = self.root / "source.tar"
        info = tarfile.TarInfo("package.py")
        info.mode, info.size, info.mtime = mode, len(data), 1700000000
        with tarfile.open(path, "w", pax_headers={"comment": guards.REV}) as archive:
            archive.addfile(info, io.BytesIO(data))
        oid = hashlib.sha1(
            b"blob " + str(len(data)).encode() + b"\0" + data
        ).hexdigest()
        return path, oid

    def test_raw_lf_git_blob_and_actual_modes(self):
        path, oid = self.archive()
        listing = f"100644 blob {oid}\tpackage.py\0".encode()
        with patch.object(source, "git", return_value=listing):
            proof = source.prove(self.root, guards.REV, path)
        dest = self.root / "out"
        before = source.extract(path, dest, proof)
        self.assertEqual((dest / "package.py").read_bytes(), b"line one\nline two\n")
        receipt = source.mode_receipt(before, proof)
        row = receipt["members"]["package.py"]
        self.assertEqual(row["archive"], 0o664)
        self.assertEqual(row["data_filter"], 0o644)
        self.assertEqual(
            row["observed_stat"], (dest / "package.py").stat().st_mode & 0o777
        )
        self.assertIn("UNRESOLVED", receipt["status"])
        source.unchanged(dest, before)
        (dest / "package.py").write_bytes(b"line one\r\nline two\r\n")
        with self.assertRaises(RuntimeError):
            source.unchanged(dest, before)

    def test_raw_crlf_rejected_against_lf_blob(self):
        _, oid = self.archive()
        path, _ = self.archive(b"line one\r\nline two\r\n")
        with patch.object(
            source, "git", return_value=f"100644 blob {oid}\tpackage.py\0".encode()
        ):
            with self.assertRaises(RuntimeError):
                source.prove(self.root, guards.REV, path)

    def test_executable_flag_not_waived(self):
        path, oid = self.archive(mode=0o775)
        with patch.object(
            source, "git", return_value=f"100755 blob {oid}\tpackage.py\0".encode()
        ):
            proof = source.prove(self.root, guards.REV, path)
        before = source.extract(path, self.root / "out", proof)
        self.assertEqual(
            source.mode_receipt(before, proof)["members"]["package.py"]["data_filter"],
            0o755,
        )
        with patch.object(
            source, "git", return_value=f"100644 blob {oid}\tpackage.py\0".encode()
        ):
            with self.assertRaises(RuntimeError):
                source.prove(self.root, guards.REV, path)

    def test_member_set_mismatch_rejected(self):
        path, oid = self.archive()
        listing = (
            f"100644 blob {oid}\tpackage.py\0" * 1 + f"100644 blob {oid}\textra.py\0"
        )
        with patch.object(source, "git", return_value=listing.encode()):
            with self.assertRaises(RuntimeError):
                source.prove(self.root, guards.REV, path)

    def test_changed_archive_rejected_before_extract(self):
        path, oid = self.archive()
        with patch.object(
            source, "git", return_value=f"100644 blob {oid}\tpackage.py\0".encode()
        ):
            proof = source.prove(self.root, guards.REV, path)
        with path.open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaises(RuntimeError):
            source.extract(path, self.root / "out", proof)


class CoverageTests(Fixture):
    def run_object(self):
        run = driver.Run(self.root)
        run.test_python = self.root / "python.exe"
        run.source = self.root
        run.full_env = {}
        (self.root / "full-coverage").mkdir()
        receipts = run.upload / "full-worker-cpu"
        receipts.mkdir()
        run.cpu_environment = lambda stage: ({}, receipts)
        return run

    def test_failed_full_suite_preserves_raw_coverage(self):
        run = self.run_object()

        def child(*args, **kwargs):
            (self.root / "full-coverage" / ".coverage.partial").write_bytes(b"partial")
            raise RuntimeError("original test failure")

        with patch.object(run, "py", side_effect=child) as invoke:
            with self.assertRaisesRegex(RuntimeError, "original test failure"):
                run.full_correctness()
        self.assertEqual(invoke.call_count, 1)
        self.assertEqual(
            (run.upload / "raw-full-coverage" / ".coverage.partial").read_bytes(),
            b"partial",
        )

    def test_stale_coverage_refused_before_full_invocation(self):
        run = self.run_object()
        (self.root / "full-coverage" / ".coverage.stale").write_bytes(b"old")
        with patch.object(run, "py") as invoke:
            with self.assertRaises(RuntimeError):
                run.full_correctness()
        invoke.assert_not_called()

    def test_successful_coverage_order_and_raw_shards(self):
        run = self.run_object()
        calls = []
        files = ["docs_src/a.py", "tests/b.py"] + [
            f"fastapi/f{i}.py" for i in range(861)
        ]
        contexts = [""] + [f"test{i}" for i in range(1408)]

        def child(python, label, args, **kwargs):
            calls.append(label)
            shards = self.root / "full-coverage"
            if label == "full-correctness":
                for name in ("worker", "cli"):
                    (shards / (".coverage." + name)).write_bytes(name.encode())
            elif label == "coverage-combine":
                self.assertEqual(
                    (run.upload / "raw-full-coverage" / ".coverage.cli").read_bytes(),
                    b"cli",
                )
                with closing(sqlite3.connect(shards / ".coverage")) as db, db:
                    db.execute("CREATE TABLE file (path TEXT)")
                    db.execute("CREATE TABLE context (context TEXT)")
                    db.executemany("INSERT INTO file VALUES (?)", [(p,) for p in files])
                    db.executemany(
                        "INSERT INTO context VALUES (?)", [(c,) for c in contexts]
                    )
            elif label == "coverage-json":
                source.save(
                    run.upload / "coverage.json",
                    {
                        "files": {
                            p: {"contexts": {"1": contexts if i == 0 else [""]}}
                            for i, p in enumerate(files)
                        }
                    },
                )
            return {"wall_seconds": 1}, b"2513 passed, 130 skipped", b""

        with (
            patch.object(run, "py", side_effect=child),
            patch.object(run, "integrity"),
            patch.object(driver, "junit_oracle", return_value={}),
            patch.object(
                driver.cpu_audit,
                "audit",
                return_value={"covered_worker_receipts_complete": True},
            ),
        ):
            run.full_correctness()
        self.assertEqual(
            calls, ["full-correctness", "coverage-combine", "coverage-json"]
        )
        self.assertTrue((run.upload / "coverage-shape.json").exists())

    def test_same_counts_different_node_identities_not_accepted(self):
        suite = ET.Element("testsuite")
        for i in range(2643):
            case = ET.SubElement(suite, "testcase", classname="wrong", name=f"test{i}")
            if i < 130:
                ET.SubElement(case, "skipped", message="requires Pydantic v1")
        path = self.root / "junit.xml"
        ET.ElementTree(suite).write(path)
        with self.assertRaisesRegex(RuntimeError, "node identities"):
            driver.junit_oracle(path)


class OrchestrationTests(Fixture):
    def execute(self, preflight):
        run = driver.Run(self.root)

        def build(label, arm, pair=0, timed=False, installer_case=False):
            return {
                "label": label,
                "arm": arm,
                "pair": pair,
                "valid": True,
                "timed": pair > 0,
                "wall_seconds": 1 if arm == "B" else 2,
            }, self.root

        def cli(label, arm, pair=0, timed=False):
            return build(label, arm, pair, timed)[0], (b"equal", b"")

        with (
            patch.object(run, "setup"),
            patch.object(run, "prepare_installer"),
            patch.object(run, "installer_gates") as hashes,
            patch.object(run, "cpu_hook_smoke") as smoke,
            patch.object(run, "build", side_effect=build) as builds,
            patch.object(run, "semantic_gates") as semantics,
            patch.object(run, "full_correctness") as full,
            patch.object(run, "integrity"),
            patch.object(run, "cli", side_effect=cli) as clis,
            patch.object(driver, "compare_outputs", return_value={"full_pass": True}),
        ):
            run.execute(preflight=preflight)
            self.assertEqual(smoke.call_count, int(preflight))
            hashes.assert_called_once()
        return builds, clis, full, semantics

    def test_bounded_cohort_counts(self):
        builds, clis, full, semantics = self.execute(False)
        self.assertEqual(builds.call_count, 32)
        self.assertEqual(
            sum(
                call.kwargs.get("installer_case", False)
                for call in builds.call_args_list
            ),
            16,
        )
        self.assertEqual(clis.call_count, 16)
        full.assert_called_once()
        semantics.assert_called_once()

    def test_preflight_has_no_timings_or_full_suite(self):
        builds, clis, full, semantics = self.execute(True)
        self.assertEqual(builds.call_count, 4)
        self.assertEqual(clis.call_count, 2)
        full.assert_not_called()
        semantics.assert_called_once()


class BackendTests(Fixture):
    def test_default_outer_pip_selection_without_ensurepip(self):
        run = driver.Run(self.root)
        run.build_python = self.root / "python.exe"
        good = {
            "valid_outer_pip": True,
            "virtualenv_available": False,
            "create_with_virtualenv": False,
            "display_name": "venv+pip",
        }
        with patch.object(run, "py", return_value=({}, json.dumps(good).encode(), b"")):
            run.isolation_probe()
        bad = {**good, "valid_outer_pip": False}
        with patch.object(run, "py", return_value=({}, json.dumps(bad).encode(), b"")):
            with self.assertRaises(RuntimeError):
                run.isolation_probe()

    def test_candidate_exact_hash_and_record(self):
        candidate = guards.candidate_bytes(HERE / (guards.WHEEL + ".gz"))
        self.assertEqual(
            hashlib.sha256(candidate).hexdigest(), guards.WHEEL_HASHES["B"]
        )
        with zipfile.ZipFile(io.BytesIO(candidate)) as archive:
            frozen.verify_record(archive)
            self.assertEqual(
                hashlib.sha256(archive.read("pdm/backend/sdist.py")).hexdigest(),
                guards.MODULE_HASHES["B"],
            )
        changed = self.root / "changed.gz"
        changed.write_bytes((HERE / (guards.WHEEL + ".gz")).read_bytes() + b"changed")
        with self.assertRaises(RuntimeError):
            guards.candidate_bytes(changed)

    def test_backend_requires_exact_both_identities(self):
        candidate = self.root / guards.WHEEL
        candidate.write_bytes(guards.candidate_bytes(HERE / (guards.WHEEL + ".gz")))
        with self.assertRaises(RuntimeError):
            driver.verify_backend(candidate, candidate)

    def test_record_corruption_rejected(self):
        wheel = self.root / "corrupt.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("payload.py", b"bad")
            archive.writestr(
                "x.dist-info/RECORD", "payload.py,sha256=bad,3\nx.dist-info/RECORD,,\n"
            )
        with zipfile.ZipFile(wheel) as archive, self.assertRaises(RuntimeError):
            frozen.verify_record(archive)

    def test_both_raw_phase_streams_required(self):
        out = "Building wheel from sdist\n"
        err = ("Creating isolated environment: venv+pip\n  - pdm-backend==2.5.0\n") * 2
        driver.verify_phases(out, err)
        for bad in (
            err.replace("venv+pip", "uv"),
            err.replace("2.5.0", "2.6.0"),
            err + err,
        ):
            with self.assertRaises(RuntimeError):
                driver.verify_phases(out, bad)

    def test_pip_exact_selection(self):
        log = self.root / "pip.log"
        a = self.root / "A" / guards.WHEEL
        b = self.root / "B" / guards.WHEEL
        log.write_text(
            f"Processing {a}\n" * 2 + "Successfully installed pdm-backend-2.5.0\n"
        )
        driver.verify_selection(log, a, b)
        log.write_text(log.read_text() + f"Processing {b}\n")
        with self.assertRaises(RuntimeError):
            driver.verify_selection(log, a, b)

    def distributions(self, folder, mode=0o644, wrapper_time=1):
        folder.mkdir()
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as tar:
            info = tarfile.TarInfo("x/payload.py")
            info.mode, info.size = mode, 3
            tar.addfile(info, io.BytesIO(b"abc"))
        (folder / "x.tar.gz").write_bytes(
            gzip.compress(stream.getvalue(), mtime=wrapper_time)
        )
        record = io.StringIO()
        digest = (
            base64.urlsafe_b64encode(hashlib.sha256(b"abc").digest())
            .rstrip(b"=")
            .decode()
        )
        csv.writer(record, lineterminator="\n").writerows(
            [
                ["payload.py", "sha256=" + digest, "3"],
                ["x.dist-info/RECORD", "", ""],
            ]
        )
        with zipfile.ZipFile(folder / "x.whl", "w") as wheel:
            wheel.writestr("payload.py", b"abc")
            wheel.writestr("x.dist-info/RECORD", record.getvalue())

    def test_comparator_only_gzip_mtime_allowed(self):
        a, b = self.root / "A", self.root / "B"
        self.distributions(a)
        self.distributions(b, wrapper_time=2)
        compare.compare_outputs(a, b)
        shutil.rmtree(b)
        self.distributions(b, mode=0o666)
        with self.assertRaises(RuntimeError):
            compare.compare_outputs(a, b)


class ScheduleTests(unittest.TestCase):
    def test_exact_schedule_and_summary_excludes_warmups(self):
        commands = guards.sequence()
        self.assertEqual(len(commands), 14)
        self.assertEqual([arm for _, arm, _ in commands], list("ABABBAABBAABBA"))
        rows = [
            {
                "label": label,
                "arm": arm,
                "pair": pair,
                "valid": True,
                "timed": pair > 0,
                "wall_seconds": 1 if arm == "B" else 2,
            }
            for label, arm, pair in commands
        ]
        result = frozen.summary(rows)
        self.assertEqual(result["B_wins"], 6)
        self.assertEqual(result["arms"]["A"]["n"], 6)
        self.assertEqual(result["order_groups"]["AB"]["B_wins"], 3)
        with self.assertRaises(RuntimeError):
            frozen.summary(rows[:-1])

    def test_only_two_jobs_and_unchanged_default_analysis(self):
        text = (
            HERE.parents[2] / ".github" / "workflows" / "arm-build-diagnostics.yml"
        ).read_text()
        old, matched = text.split("\n  matched-reference:", 1)
        self.assertIn("default: both", old)
        self.assertNotIn("      case:", old)
        self.assertIn("if: inputs.platform != 'matched-reference'", old)
        self.assertIn("Preserve native Python setup receipts", old)
        self.assertEqual(matched.count("- runner:"), 2)
        self.assertIn("runner: windows-11-arm", matched)
        self.assertIn("runner: macos-15", matched)
        self.assertNotIn("ubuntu", matched)
        self.assertIn("github.run_attempt == '1'", matched)
        self.assertIn("refs/heads/perf/hobl-arm-reference", matched)
        self.assertNotIn("retry", matched.split("steps:", 1)[0].replace("no retry", ""))


if __name__ == "__main__":
    unittest.main()
