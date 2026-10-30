"""Q-only guards for the separate supported-installer control."""

import base64
import csv
import hashlib
import io
import os
from pathlib import Path
from unittest.mock import patch

import driver
import installer
from guards import WHEEL, WHEEL_HASHES
from source import save
from test_reference import Fixture


class InstallerTests(Fixture):
    def run_object(self):
        run = driver.Run(self.root)
        run.uv = self.root / "uv"
        run.build_python = self.root / "native-python"
        run.source = self.root / "source"
        run.installer_wheels = {
            arm: self.root / "installer" / arm / "wheelhouse" / WHEEL for arm in "AB"
        }
        run.installer_constraints = {
            arm: self.root / "installer" / arm / "constraints.txt" for arm in "AB"
        }
        return run

    def test_pip_require_and_uv_verify_are_explicit_separate_controls(self):
        run = self.run_object()
        a = run.build_env("A", self.root / "A", "trials", installer_case=True)
        b = run.build_env("B", self.root / "B", "trials", installer_case=True)
        self.assertEqual(a["PIP_REQUIRE_HASHES"], "1")
        self.assertEqual(b["UV"], str(run.uv))
        self.assertNotIn("UV_REQUIRE_HASHES", b)
        self.assertEqual(b["UV_CONSTRAINT"], run.installer_constraints["B"].as_uri())
        self.assertEqual(b["UV_FIND_LINKS"], run.installer_wheels["B"].parent.as_uri())
        for key in ("UV_NO_CONFIG", "UV_OFFLINE", "UV_NO_MANAGED_PYTHON"):
            self.assertEqual(b[key], "1")
        self.assertEqual(b["UV_PYTHON_DOWNLOADS"], "never")
        self.assertNotEqual(a["UV_CACHE_DIR"], b["UV_CACHE_DIR"])
        self.assertNotIn("UV_NO_VERIFY_HASHES", b)

    def test_verification_bypass_forbidden_even_if_inherited(self):
        run = self.run_object()
        for value in ("1", "0"):
            with (
                self.subTest(value=value),
                patch.dict(os.environ, {"UV_NO_VERIFY_HASHES": value}),
            ):
                with self.assertRaises(RuntimeError):
                    run.build_env("B", self.root, "trials", installer_case=True)

    def test_positive_cold_and_warm_hash_gates_do_not_change_real_wheel(self):
        run = self.run_object()
        wheel = run.installer_wheels["B"]
        wheel.parent.mkdir(parents=True)
        wheel.write_bytes(b"fixture immutable stock body")
        caches = []

        def child(python, label, args, **kwargs):
            env = kwargs["env"]
            caches.append(env["UV_CACHE_DIR"])
            if label != "installer-hash-positive":
                wrong = self.root / label / "wrong-constraints.txt"
                text = wrong.read_text()
                self.assertIn("#sha256=" + installer.WRONG_SHA, text)
                self.assertIn("--hash=sha256:" + installer.WRONG_SHA, text)
            output = Path(args[args.index("--output") + 1])
            save(output, {"passed": True})
            return {}, b"", b""

        with patch.object(run, "py", side_effect=child) as invoke:
            run.installer_gates()
        self.assertEqual(invoke.call_count, 3)
        self.assertEqual(caches[0], caches[2])
        self.assertNotEqual(caches[0], caches[1])
        self.assertEqual(wheel.read_bytes(), b"fixture immutable stock body")

    def test_native_tool_requires_absolute_exact_official_body(self):
        with self.assertRaisesRegex(RuntimeError, "absolute"):
            installer.native_uv(Path("uv"))
        path = self.root / "uv.exe"
        path.write_bytes(b"wrong tool")
        with (
            patch.object(installer, "binary_guard"),
            patch.object(installer.platform, "system", return_value="Windows"),
        ):
            with self.assertRaisesRegex(RuntimeError, "official native"):
                installer.native_uv(path)

    def phase_text(self, uv, wheel):
        phase = (
            "* Creating isolated environment: venv+uv\n"
            "* Installing packages in isolated environment:\n - pdm-backend\n"
            "* Installed build dependency versions:\n - pdm-backend==2.5.0\n"
            f"* Using external uv from {uv}\n"
            "Using Python 3.12.10 environment at: fixture\n"
            f" + pdm-backend==2.5.0 (from {wheel.as_uri()}#sha256={WHEEL_HASHES['A']})\n"
        )
        return phase * 2 + "* Building sdist\n* Building wheel from sdist\n"

    def test_closed_input_and_exact_hashed_uri_selection(self):
        uv, wheel = self.root / "uv", self.root / "B" / WHEEL
        text = self.phase_text(uv, wheel)
        installer.phases(text, "", "B", uv, wheel, self.root / "A")
        for invalid in (
            text.replace("#sha256=" + WHEEL_HASHES["A"], ""),
            text.replace(" - pdm-backend\n", " - pdm-backend\n - unknown-dependency\n"),
            text.replace("3.12.10", "3.13.15"),
        ):
            with self.subTest(invalid=invalid), self.assertRaises(RuntimeError):
                installer.phases("", invalid, "B", uv, wheel, self.root / "A")

    def test_installed_record_validates_payload_and_path_boundary(self):
        isolated = self.root / "isolated"
        site = isolated / "site"
        record = site / "pdm_backend-2.5.0.dist-info" / "RECORD"
        record.parent.mkdir(parents=True)
        payload = site / "payload.py"
        payload.write_bytes(b"abc")
        digest = (
            base64.urlsafe_b64encode(hashlib.sha256(b"abc").digest())
            .rstrip(b"=")
            .decode()
        )
        rows = io.StringIO()
        csv.writer(rows).writerows(
            [
                ["payload.py", "sha256=" + digest, "3"],
                ["pdm_backend-2.5.0.dist-info/RECORD", "", ""],
            ]
        )
        record.write_text(rows.getvalue(), newline="")
        installer.installed_record(site, isolated)
        payload.write_bytes(b"bad")
        with self.assertRaisesRegex(RuntimeError, "mismatch"):
            installer.installed_record(site, isolated)
        record.write_text("../../escape,,\n")
        with self.assertRaisesRegex(RuntimeError, "escapes"):
            installer.installed_record(site, isolated)
