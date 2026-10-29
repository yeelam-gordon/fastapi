"""Pending acceptance gates; execute only against the notified committed fix."""

import hashlib
import os
import shutil
import subprocess
import tarfile
import unittest
import zipfile
from pathlib import Path

import review_checks
from build import build


class FixedBehaviorChecks(unittest.TestCase):
    setUp = review_checks.ReviewChecks.setUp
    tearDown = review_checks.ReviewChecks.tearDown
    fixture = review_checks.ReviewChecks.fixture
    manifest = review_checks.ReviewChecks.manifest

    def assert_source_unchanged(self, source, before):
        for name, payload in before.items():
            self.assertEqual((source / name).read_bytes(), payload, name)
        actual = {
            p.relative_to(source).as_posix()
            for p in source.rglob("*")
            if p.is_file() and p.relative_to(source).parts[0].casefold() != ".pdm-build"
        }
        self.assertEqual(actual, set(before))

    def source_snapshot(self, source):
        return {
            p.relative_to(source).as_posix(): p.read_bytes()
            for p in source.rglob("*")
            if p.is_file()
        }

    def artifact_payloads(self, result):
        with tarfile.open(result["sdist"]) as archive:
            sdist = {
                m.name: (
                    archive.extractfile(m).read(),
                    m.mode,
                    m.uid,
                    m.gid,
                    m.uname,
                    m.gname,
                )
                for m in archive.getmembers()
            }
        with zipfile.ZipFile(result["wheel"]) as archive:
            wheel = {
                m.filename: (archive.read(m), m.external_attr >> 16)
                for m in archive.infolist()
            }
        return sdist, wheel

    def test_s1_then_s3_same_source_and_manifest(self):
        source = self.fixture()
        before = self.source_snapshot(source)
        manifest = self.manifest(source)
        original_manifest = manifest.read_bytes()
        first = build(source, manifest, self.root / "s1", 1)
        self.assert_source_unchanged(source, before)
        second = build(source, manifest, self.root / "s3", 3)
        self.assertEqual(self.artifact_payloads(first), self.artifact_payloads(second))
        self.assert_source_unchanged(source, before)
        self.assertEqual(manifest.read_bytes(), original_manifest)

    def test_fresh_payload_and_metadata_without_build_state_cleanup(self):
        source = self.fixture()
        manifest = self.manifest(source)
        original_manifest = manifest.read_bytes()
        build(source, manifest, self.root / "first", 1)
        (source / "demo/__init__.py").write_bytes(b"VALUE = 2\n")
        project = source / "pyproject.toml"
        project.write_text(project.read_text().replace('version="1"', 'version="2"'))
        second = build(source, manifest, self.root / "second", 3)
        with zipfile.ZipFile(second["wheel"]) as wheel:
            self.assertEqual(wheel.read("demo/__init__.py"), b"VALUE = 2\n")
            self.assertIn(b"Version: 2", wheel.read("demo-2.dist-info/METADATA"))
        with tarfile.open(second["sdist"]) as archive:
            self.assertEqual(
                archive.extractfile("demo-2/demo/__init__.py").read(), b"VALUE = 2\n"
            )
            self.assertIn(b"Version: 2", archive.extractfile("demo-2/PKG-INFO").read())
        self.assertEqual(manifest.read_bytes(), original_manifest)

    def test_unmanifested_source_not_mistaken_for_build_state(self):
        source = self.fixture()
        manifest = self.manifest(source)
        build(source, manifest, self.root / "first", 1)
        unexpected = source / ".unrelated" / "extra.txt"
        unexpected.parent.mkdir()
        unexpected.write_bytes(b"must remain and must cause rejection\n")
        with self.assertRaises(ValueError):
            build(source, manifest, self.root / "second", 3)
        self.assertFalse((self.root / "second").exists())
        self.assertEqual(
            unexpected.read_bytes(), b"must remain and must cause rejection\n"
        )

    def test_stock_isolated_b_then_sdk_same_source_and_manifest(self):
        source = self.fixture()
        before = self.source_snapshot(source)
        manifest = self.manifest(source)
        original_manifest = manifest.read_bytes()
        tools = Path(r"Q:\fastapi\Generated Files\arm-build")
        child_scratch = self.root / "child-scratch"
        child_scratch.mkdir()
        command = [
            str(tools / "tools" / "uv.exe"),
            "build",
            str(source),
            "--python",
            str(
                tools / "tools" / "official-tool-environment" / "Scripts" / "python.exe"
            ),
            "--offline",
            "--no-index",
            "--find-links",
            str(tools / "wheelhouse"),
            "--cache-dir",
            str(self.root / "uv-cache"),
            "--out-dir",
            str(self.root / "baseline"),
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env=os.environ
            | dict.fromkeys(("TEMP", "TMP", "TMPDIR"), str(child_scratch)),
        )
        print("FIXED GATE STOCK B:", command, result.returncode)
        print(result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0)
        self.assert_source_unchanged(source, before)
        sdk = build(source, manifest, self.root / "sdk", 3)
        with zipfile.ZipFile(sdk["wheel"]) as wheel:
            self.assertEqual(wheel.read("demo/__init__.py"), before["demo/__init__.py"])
            self.assertIn(b"Version: 1", wheel.read("demo-1.dist-info/METADATA"))
        self.assert_source_unchanged(source, before)
        self.assertEqual(manifest.read_bytes(), original_manifest)

    @unittest.skipUnless(
        Path("FIXED_CHECKS.PY").exists(), "requires case-insensitive filesystem"
    )
    def test_hook_case_aliases_rejected_before_execution(self):
        for name in ("pdm_build.py", "PDM_BUILD.PY", "Pdm_Build.py", "pdm_build.Py"):
            with self.subTest(name=name):
                source = self.fixture()
                marker = self.root / "hook-executed"
                (source / name).write_text(
                    "from pathlib import Path\n"
                    "def pdm_build_initialize(context):\n"
                    f"    Path({str(marker)!r}).write_text('executed')\n",
                    encoding="utf-8",
                )
                manifest = self.manifest(source)
                output = self.root / "output"
                try:
                    with self.assertRaises(ValueError):
                        build(source, manifest, output, 3)
                    self.assertFalse(marker.exists(), "unsupported hook executed")
                    self.assertFalse(output.exists(), "rejection happened after output")
                finally:
                    shutil.rmtree(source)

    def state_link_rejected(self, kind, nested, state_name=".pdm-build"):
        source = self.fixture()
        manifest = self.manifest(source)
        target = self.root / "outside-state"
        target.mkdir()
        (target / "sentinel").write_bytes(b"DO NOT CHANGE\n")
        before = hashlib.sha256((target / "sentinel").read_bytes()).hexdigest()
        state = source / state_name
        if nested:
            state.mkdir()
            link = state / "linked-directory"
        else:
            link = state
        if kind == "symlink":
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlink unavailable: {error}")
        else:
            shell = shutil.which("pwsh")
            if os.name != "nt" or shell is None:
                self.skipTest("Windows junction creation requires pwsh")
            quoted_link = str(link).replace("'", "''")
            quoted_target = str(target).replace("'", "''")
            command = (
                "$ErrorActionPreference='Stop'; "
                f"New-Item -ItemType Junction -Path '{quoted_link}' "
                f"-Target '{quoted_target}' | Out-Null"
            )
            result = subprocess.run(
                [shell, "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(link.is_junction())
        try:
            with self.assertRaises(ValueError):
                build(source, manifest, self.root / "output", 3)
            self.assertFalse((self.root / "output").exists())
            self.assertEqual(
                hashlib.sha256((target / "sentinel").read_bytes()).hexdigest(), before
            )
            self.assertEqual({p.name for p in target.iterdir()}, {"sentinel"})
            self.assertTrue(link.is_symlink() or link.is_junction())
        finally:
            if link.is_symlink():
                link.unlink()
            elif link.is_junction():
                link.rmdir()

    def test_root_build_state_symlink_rejected(self):
        self.state_link_rejected("symlink", nested=False)

    def test_nested_build_state_symlink_rejected(self):
        self.state_link_rejected("symlink", nested=True)

    def test_root_build_state_junction_rejected(self):
        self.state_link_rejected("junction", nested=False)

    def test_nested_build_state_junction_rejected(self):
        self.state_link_rejected("junction", nested=True)

    def test_case_alias_build_state_symlink_rejected(self):
        self.state_link_rejected("symlink", nested=False, state_name=".PDM-BUILD")

    def test_case_alias_build_state_junction_rejected(self):
        self.state_link_rejected("junction", nested=False, state_name=".PDM-BUILD")


if __name__ == "__main__":
    unittest.main(verbosity=2)
