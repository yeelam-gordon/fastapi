"""Q-only frontend fixtures: never invoke a build or native executable."""

import io
import json
import shutil
import struct
import subprocess
import sys
import unittest
import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import frontend
from guards import architecture_ok, slices

HERE = Path(__file__).resolve().parent


def native_log(wheel, *, sdist_only=False):
    phases = ["sdist"] if sdist_only else ["sdist", "wheel"]
    lines = ["Building source distribution..."]
    for kind in phases:
        if kind == "wheel":
            lines.append("Building wheel from source distribution...")
        lines += [
            "DEBUG Installing build requirement: pdm-backend==2.5.0 "
            f"(from {wheel.as_uri()}#sha256={frontend.STOCK})",
            "DEBUG Creating PEP 517 build environment",
            f"DEBUG Calling `pdm.backend.get_requires_for_build_{kind}()`",
        ]
    return "\n".join(lines)


def abi_fixture(system, base):
    abi = {
        "cache_tag": "cpython-312",
        "version": "3.12.10",
        "system": system,
        "bits": 64,
        "machine": "ARM64" if system == "Windows" else "arm64",
        "soabi": None if system == "Windows" else "cpython-312-darwin",
        "sysconfig_platform": (
            "win-arm64" if system == "Windows" else "macosx-11.0-universal2"
        ),
        "ext_suffix": (
            ".cp312-win_arm64.pyd" if system == "Windows" else ".cpython-312-darwin.so"
        ),
        "base": str(base),
    }
    if system == "Windows":
        abi["extension_suffixes"] = [".cp312-win_arm64.pyd", ".pyd"]
    return abi


class Fixture(unittest.TestCase):
    def setUp(self):
        self.root = HERE / ".local" / ("frontend path spaces " + uuid.uuid4().hex)
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_raw_clock_endpoints_elapsed_and_chronology_outside_boundary(self):
        run = frontend.FrontendRun(self.root)
        events = []
        perf = iter((1_000_000_000, 1_250_000_001))
        utc = iter((1_700_000_000_000_000_000, 1_700_000_000_300_000_000))

        def clock(kind, values):
            events.append(kind)
            return next(values)

        def spawn(argv, **kwargs):
            events.append("subprocess")
            return subprocess.CompletedProcess(argv, 0)

        with (
            patch("frontend.time.time_ns", side_effect=lambda: clock("UTC", utc)),
            patch(
                "frontend.time.perf_counter_ns", side_effect=lambda: clock("perf", perf)
            ),
            patch("frontend.subprocess.run", side_effect=spawn) as child,
        ):
            row, _, _ = run.spawn_frontend(
                "clock", ["fixture-only"], self.root, {}, timed=True, expected=0
            )
        self.assertEqual(events, ["UTC", "perf", "subprocess", "perf", "UTC"])
        child.assert_called_once()
        self.assertEqual(row["perf_counter_ns_start"], 1_000_000_000)
        self.assertEqual(row["perf_counter_ns_stop"], 1_250_000_001)
        self.assertEqual(row["elapsed_ns"], 250_000_001)
        self.assertEqual(row["wall_seconds"], 0.250000001)
        self.assertGreater(row["wall_utc_ns_after"], row["wall_utc_ns_before"])
        self.assertEqual(
            json.loads((run.upload / "clock-process" / "command.json").read_bytes()),
            row,
        )
        with (
            patch("frontend.time.perf_counter_ns", side_effect=[2, 2]),
            patch(
                "frontend.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "clock interval"):
                run.spawn_frontend(
                    "zero-clock",
                    ["fixture-only"],
                    self.root,
                    {},
                    timed=True,
                    expected=0,
                )
        invalid = json.loads(
            (run.upload / "zero-clock-process" / "command.json").read_bytes()
        )
        self.assertFalse(invalid["valid"])

    def test_complete_helper_import_manifest_rejects_hidden_legacy_chain(self):
        run = frontend.FrontendRun(self.root)
        imports = frontend.helper_imports(run.frozen_inputs)
        expected = {
            "frontend",
            "driver",
            "cpu_audit",
            "installer",
            "compare",
            "frozen",
            "guards",
            "source",
        }
        self.assertTrue(expected <= imports.keys())
        self.assertTrue(all(row["sha256"] for row in imports.values()))
        for path in (
            HERE.parent / "legacy" / "fixture_receipts.py",
            self.root / "unmanifested.py",
        ):
            with patch.dict(
                sys.modules, {"fixture_receipts": SimpleNamespace(__file__=str(path))}
            ):
                with self.assertRaises(RuntimeError):
                    frontend.helper_imports(run.frozen_inputs)

    def test_setup_only_minimal_or_reused_outer_and_verify_only_setup_constraint(self):
        wheel = self.root / frontend.WHEEL
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("fixture", b"fixture")
        versions = frontend.constraints(HERE / "build-constraints.txt")

        def fake_extract(archive, target, proof):
            target.mkdir()
            (target / "pyproject.toml").write_text(
                '[build-system]\nrequires=["pdm-backend"]\nbuild-backend="pdm.backend"\n'
            )
            return {}

        def fake_command(label, argv, **kwargs):
            out = b"uv 0.13.6" if label == "uv-version" else json.dumps(abi).encode()
            return {}, out, b""

        for preflight, valid_abi in ((True, True), (False, True), (True, False)):
            abi = abi_fixture(frontend.platform.system(), sys._base_executable)
            if not valid_abi:
                abi["cache_tag"] = "cpython-313"
            run = frontend.FrontendRun(self.root / f"{preflight}-{valid_abi}")
            identity = {
                "prefix": str(run.root / "outer"),
                "distributions": versions,
            }
            metadata = {
                "urls": [
                    {
                        "filename": frontend.WHEEL,
                        "digests": {"sha256": frontend.STOCK},
                        "url": "https://files.pythonhosted.org/fixture.whl",
                    }
                ]
            }
            with (
                patch("frontend.native_guard", return_value={"fixture": True}),
                patch("frontend.installer.native_uv"),
                patch("frontend.binary_guard"),
                patch("driver.binary_guard"),
                patch("frontend.sha", return_value=frontend.STOCK),
                patch("frontend.outer_snapshot", return_value={}),
                patch("frontend.helper_imports", return_value={}),
                patch("frontend.verify_record"),
                patch(
                    "frontend.fetch",
                    return_value=(
                        self.root / "source.tar",
                        {"files": {str(i): {} for i in range(2557)}},
                    ),
                ),
                patch("frontend.extract", side_effect=fake_extract),
                patch.object(run, "command", side_effect=fake_command),
                patch.object(run, "identity", return_value=identity),
                patch.object(
                    run, "make_venv", return_value=self.root / "python"
                ) as make,
                patch(
                    "urllib.request.urlopen",
                    return_value=io.StringIO(json.dumps(metadata)),
                ),
                patch(
                    "urllib.request.urlretrieve",
                    side_effect=lambda url, target: shutil.copyfile(wheel, target),
                ),
            ):
                if valid_abi:
                    run.setup_frontend(
                        self.root / "uv",
                        preflight=preflight,
                        stock_wheel=wheel if preflight else None,
                    )
                else:
                    with self.assertRaisesRegex(RuntimeError, "Actual child ABI"):
                        run.setup_frontend(
                            self.root / "uv", preflight=True, stock_wheel=wheel
                        )
                    self.assertEqual(
                        json.loads((run.upload / "outer-before.json").read_bytes()), {}
                    )
                    self.assertFalse((run.upload / "actual-python-abi.json").exists())
            if preflight:
                make.assert_not_called()
            else:
                make.assert_called_once_with("minimal", "build-constraints.txt")
            self.assertNotIn("--hash=", run.setup_constraint.read_text())
            self.assertIn("#sha256=", run.setup_constraint.read_text())
            self.assertEqual(len(run.wheels), 2)
            self.assertEqual(run.wheels["A"].read_bytes(), run.wheels["B"].read_bytes())

    def test_actual_abi_and_readonly_bytecode_negatives(self):
        valid = abi_fixture("Darwin", sys._base_executable)
        with (
            patch("frontend.binary_guard"),
            patch("frontend.platform.system", return_value="Darwin"),
        ):
            frontend.verify_python_abi(valid)
            for key, bad in (
                ("cache_tag", "cpython-313"),
                ("version", "3.12.9"),
                ("bits", 32),
                ("machine", "x86_64"),
                ("soabi", None),
                ("soabi", "cpython-313-darwin"),
                ("system", "Windows"),
                ("sysconfig_platform", "macosx-10.9-x86_64"),
                ("sysconfig_platform", None),
                ("ext_suffix", ".cpython-313-darwin.so"),
                ("base", str(self.root / "other-python")),
            ):
                with self.assertRaises(RuntimeError):
                    frontend.verify_python_abi({**valid, key: bad})
        bytecode = self.root / "__pycache__" / "example.pyc"
        bytecode.parent.mkdir()
        bytecode.write_bytes(b"old")
        before = frontend.outer_snapshot(self.root)
        bytecode.write_bytes(b"new")
        self.assertNotEqual(before, frontend.outer_snapshot(self.root))

    def test_actual_windows_null_soabi_receipt_requires_strict_arm64_abi_and_pe(self):
        base = self.root / "python-official" / "python.exe"
        base.parent.mkdir()
        data = bytearray(128)
        data[:2] = b"MZ"
        struct.pack_into("<I", data, 60, 80)
        data[80:84] = b"PE\0\0"
        struct.pack_into("<H", data, 84, 0xAA64)
        base.write_bytes(data)
        # Observed c62/sysconfig-followup values; base is relocated to owned Q.
        valid = abi_fixture("Windows", base)
        with (
            patch("frontend.platform.system", return_value="Windows"),
            patch("frontend.sys._base_executable", str(base)),
        ):
            frontend.verify_python_abi(valid)
            for key, bad in (
                ("cache_tag", "cpython-313"),
                ("version", "3.13.0"),
                ("bits", 32),
                ("machine", "AMD64"),
                ("soabi", "cpython-312-darwin"),
                ("system", "Darwin"),
                ("sysconfig_platform", "win-amd64"),
                ("sysconfig_platform", None),
                ("ext_suffix", ".pyd"),
                ("ext_suffix", ".cp313-win_arm64.pyd"),
                ("ext_suffix", ".cp312-win_amd64.pyd"),
                ("ext_suffix", None),
                ("base", str(self.root / "other-python.exe")),
            ):
                with self.subTest(key=key, bad=bad), self.assertRaises(RuntimeError):
                    frontend.verify_python_abi({**valid, key: bad})
            struct.pack_into("<H", data, 84, 0x8664)
            base.write_bytes(data)
            with self.assertRaisesRegex(RuntimeError, "native ARM64"):
                frontend.verify_python_abi(valid)

    def test_exact_default_sdist_to_wheel_and_constraint_paths(self):
        uv, python, constraint = (
            self.root / name for name in ("uv", "python", "c.txt")
        )
        a = frontend.argv_for("A", python, uv, constraint)
        b = frontend.argv_for("B", python, uv, constraint)
        self.assertEqual(a, [str(python), "-m", "build", "-v", "--installer", "uv"])
        self.assertEqual(b[b.index("--python") + 1], str(python))
        self.assertEqual(b[b.index("--build-constraints") + 1], str(constraint))
        self.assertNotIn("--sdist", b)
        self.assertNotIn("--wheel", b)
        self.assertNotIn("--require-build-hashes", b)
        for flag in (
            "--require-hashes",
            "--offline",
            "--no-index",
            "--no-config",
            "--no-managed-python",
            "--no-python-downloads",
            "--no-create-gitignore",
        ):
            self.assertIn(flag, b)

    def test_closed_logs_and_unknown_input_stop_on_both_hosts(self):
        for host in ("Windows", "Darwin"):
            with self.subTest(host=host):
                wheel = self.root / host / frontend.WHEEL
                uv = self.root / "uv"
                uv.write_bytes(b"fixture")
                text = native_log(wheel)
                self.assertEqual(len(frontend.verify_log(text, wheel, uv)["hooks"]), 2)
                for bad in (
                    text + "\nDEBUG Installing build requirement: extra==1",
                    text.replace("pdm-backend==2.5.0", "pdm-backend==2.4.0"),
                    text.replace("Building wheel from source distribution...", ""),
                    text + "\nInstalling extra requirements for build backend",
                    text.replace(frontend.STOCK, "0" * 64),
                ):
                    with self.assertRaises(RuntimeError):
                        frontend.verify_log(bad, wheel, uv)
                frontend.verify_log(
                    native_log(wheel, sdist_only=True), wheel, uv, sdist_only=True
                )

    def test_mac_transients_native_and_unknown_hook_negatives(self):
        base = self.root / "cache" / "builds-v0" / "one"
        site = base / "lib" / "python3.12" / "site-packages"
        site.mkdir(parents=True)
        (base / "pyvenv.cfg").write_text("include-system-site-packages = false\n")
        for kind in ("sdist", "wheel"):
            (base / f"get_requires_for_build_{kind}.txt").write_text("[]")
        exe, sites = frontend.transient_paths(base, "Darwin")
        self.assertEqual(exe, base / "bin" / "python")
        self.assertEqual(sites, [site])
        observer = frontend.Observation(self.root / "cache", self.root / "stock.whl")
        with patch("frontend.platform.system", return_value="Darwin"):
            with patch.object(
                observer.stop, "wait", side_effect=lambda _: observer.stop.set()
            ):
                observer.run()
        self.assertEqual(observer.verify(("sdist", "wheel"))["hooks"]["wheel"], [])
        (base / "get_requires_for_build_wheel.txt").write_text('["surprise"]')
        observer = frontend.Observation(self.root / "cache", self.root / "stock.whl")
        with patch("frontend.platform.system", return_value="Darwin"):
            with patch.object(
                observer.stop, "wait", side_effect=lambda _: observer.stop.set()
            ):
                observer.run()
        with self.assertRaises(RuntimeError):
            observer.verify(("sdist", "wheel"))
        native = slices(b"\xcf\xfa\xed\xfe" + struct.pack("<I", 0x100000C))
        architecture_ok("Darwin", "arm64", 64, native)
        for machine, translated in (("x86_64", 0), ("arm64", 1)):
            with self.assertRaises(RuntimeError):
                architecture_ok("Darwin", machine, 64, native, translated)

    def test_missing_json_never_inferred_from_logs_or_metadata(self):
        observer = frontend.Observation(self.root, self.root / "stock.whl")
        observer.rows["one"] = {"stock_payloads": 70, "sdist": []}
        with self.assertRaises(RuntimeError):
            observer.verify(("sdist", "wheel"))

    def test_environment_hash_policies_and_private_caches(self):
        run = frontend.FrontendRun(self.root)
        run.uv = self.root / "uv"
        run.wheels = {a: self.root / a / frontend.WHEEL for a in "AB"}
        run.backend_constraints = {a: self.root / a / "constraints.txt" for a in "AB"}
        for arm in "AB":
            env = run.env_for(arm, self.root, self.root / arm / "cache")
            self.assertNotIn("UV_NO_VERIFY_HASHES", env)
            self.assertNotIn("UV_REQUIRE_HASHES", env)
            self.assertNotIn("UV_NO_BUILD_ISOLATION", env)
            self.assertEqual(env["UV_OFFLINE"], "1")
            self.assertEqual(env["SOURCE_DATE_EPOCH"], "1700000000")
            if arm == "A":
                self.assertIn("UV_CONSTRAINT", env)
                self.assertNotIn("UV_BUILD_CONSTRAINT", env)
            else:
                self.assertNotIn("UV_CONSTRAINT", env)
                self.assertIn("UV_BUILD_CONSTRAINT", env)
        wheel = self.root / frontend.WHEEL
        self.assertEqual(frontend.constraint_text(wheel).count(frontend.STOCK), 2)
        self.assertIn("%20", frontend.constraint_text(wheel))

    def test_preflight_schedule_and_no_observer_in_fourteen(self):
        for preflight in (True, False):
            run = frontend.FrontendRun(self.root / str(preflight))
            seen = []

            def execute(label, arm, _seen=seen, **kwargs):
                _seen.append((label, arm, kwargs))
                return {"label": label, "arm": arm, **kwargs}

            with (
                patch.object(run, "execute_frontend", side_effect=execute),
                patch.object(run, "integrity_frontend"),
                patch("frontend.summary", return_value={}),
            ):
                run.run_frontend(preflight=preflight)
            self.assertEqual(
                [r[2].get("probe") for r in seen[:3]],
                ["positive", "negative-cold", "negative-warm"],
            )
            self.assertEqual(
                [r[0] for r in seen[3:5]], ["correctness-A", "correctness-B"]
            )
            self.assertEqual(len(seen), 5 if preflight else 19)
            result = json.loads((run.upload / "frontend-result.json").read_bytes())
            self.assertEqual(result["archives"], 4 if preflight else 32)
        # Exercise the actual timed branch, with every external operation mocked.
        run = frontend.FrontendRun(self.root / "timer")
        run.build_python, run.uv = self.root / "python", self.root / "uv"
        run.backend_constraints = {"B": self.root / "constraints"}
        run.wheels = {"B": self.root / frontend.WHEEL}
        work, src = self.root / "work", self.root / "src"
        with (
            patch.object(run, "fresh_source", return_value=(work, src, {})),
            patch.object(run, "env_for", return_value={}),
            patch.object(run, "spawn_frontend", side_effect=RuntimeError("stop")),
            patch(
                "frontend.Observation", side_effect=AssertionError("observer in timer")
            ),
            patch("frontend.unchanged"),
            patch("frontend.tree", return_value={}),
        ):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                run.execute_frontend("pair-1-B", "B", pair=1, timed=True)
            with self.assertRaisesRegex(RuntimeError, "stop"):
                run.execute_frontend("warmup-B", "B")

    def test_failure_logs_raw_bytes_and_no_retry(self):
        run = frontend.FrontendRun(self.root)
        calls = []

        def fake(argv, **kwargs):
            calls.append(argv)
            kwargs["stdout"].write(b"raw\r\n\xff")
            kwargs["stderr"].write(b"failure\r\n")
            return subprocess.CompletedProcess(argv, 7)

        with patch("frontend.subprocess.run", side_effect=fake):
            with self.assertRaises(RuntimeError):
                run.spawn_frontend(
                    "failed", ["not-executed"], self.root, {}, timed=True, expected=0
                )
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            (run.upload / "failed-process" / "stdout").read_bytes(), b"raw\r\n\xff"
        )
        row = json.loads((run.upload / "failed-process" / "command.json").read_bytes())
        self.assertEqual(row["exit"], 7)
        self.assertFalse(row["valid"])

    def test_hosted_ref_attempt_and_preflight_root_guards(self):
        valid = {
            "GITHUB_REPOSITORY": "yeelam-gordon/fastapi",
            "GITHUB_REF": "refs/heads/perf/hobl-arm-frontend",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
        }
        frontend.hosted_guard(valid)
        for key in valid:
            with self.assertRaises(RuntimeError):
                frontend.hosted_guard({**valid, key: "wrong"})
        with self.assertRaisesRegex(RuntimeError, "fresh owned root"):
            frontend.main(
                [
                    "--root",
                    str(self.root),
                    "--uv",
                    str(self.root / "uv"),
                    "--preflight-only",
                ]
            )

    def test_workflow_default_and_old_reference_compatibility(self):
        workflow = (
            HERE.parents[2] / ".github" / "workflows" / "arm-build-diagnostics.yml"
        )
        text = workflow.read_text()
        self.assertIn("default: both", text)
        self.assertIn("refs/heads/perf/hobl-arm-reference", text)
        self.assertIn("refs/heads/perf/hobl-arm-frontend", text)
        self.assertIn("github.run_attempt == '1'", text)
        self.assertEqual(text.count("\n  diagnostics:"), 1)
        self.assertEqual(text.count("\n  matched-reference:"), 1)
        self.assertIn("if: inputs.platform != 'matched-frontend'", text)
        self.assertIn("if: inputs.platform == 'matched-frontend'", text)
        self.assertIn(
            "inputs.platform != 'matched-macos' && inputs.platform != 'matched-frontend'",
            text,
        )
        self.assertNotIn("pytest", text.split("- name: One frontend-only cohort")[1])


if __name__ == "__main__":
    unittest.main()
