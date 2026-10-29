"""Independent bounded failure-path checks; run from this directory."""

import json
import os
import shutil
import subprocess
import tarfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from build import build
from ops import extract_selected, payloads
from selector import configuration


class ReviewChecks(unittest.TestCase):
    def setUp(self):
        self.root = Path("scratch/review-unit").resolve()
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root)

    def fixture(self):
        source = self.root / "source"
        source.mkdir()
        (source / "demo").mkdir()
        (source / "demo/__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
        (source / "pyproject.toml").write_text(
            '[build-system]\nrequires=["pdm-backend==2.5.0"]\n'
            'build-backend="pdm.backend"\n[project]\nname="demo"\nversion="1"\n',
            encoding="utf-8",
        )
        return source

    def manifest(self, source):
        manifest = self.root / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    p.relative_to(source).as_posix(): {"mode": 0o644}
                    for p in source.rglob("*")
                    if p.is_file()
                }
            ),
            encoding="utf-8",
        )
        return manifest

    def test_manifest_extra_missing_and_invalid_modes(self):
        source = self.fixture()
        manifest = self.manifest(source)
        original = json.loads(manifest.read_text())
        for content in (
            {},
            original | {"missing": {"mode": 0o644}},
            original | {"pyproject.toml": {"mode": 0o600}},
            original | {"../outside": {"mode": 0o644}},
        ):
            manifest.write_text(json.dumps(content))
            with self.assertRaises(ValueError):
                build(source, manifest, self.root / "output", 3)
            self.assertFalse((self.root / "output").exists())

    def test_plugins_and_configuration_rejected(self):
        config = {
            "build-system": {"build-backend": "pdm.backend"},
            "project": {"name": "demo", "version": "1"},
        }
        with patch("selector.importlib.metadata.entry_points", return_value=[object()]):
            with self.assertRaisesRegex(ValueError, "hooks"):
                configuration(config, [])
        for options in (
            {"build": {"custom-hook": "anything.py"}},
            {"version": {"source": "call", "getter": "demo:get"}},
            {"version": {"source": "scm"}},
            {"build": {"package-dir": "lib"}},
        ):
            with self.assertRaises(ValueError):
                configuration(config | {"tool": {"pdm": options}}, [])

    def test_actual_payload_and_metadata_refresh(self):
        source = self.fixture()
        manifest = self.manifest(source)
        first = build(source, manifest, self.root / "first", 1)
        shutil.rmtree(source / ".pdm-build")
        (source / "demo/__init__.py").write_bytes(b"VALUE = 2\n")
        project = source / "pyproject.toml"
        project.write_text(project.read_text().replace('version="1"', 'version="2"'))
        second = build(source, manifest, self.root / "second", 3)
        self.assertIn("demo-1.tar.gz", first["sdist"])
        self.assertIn("demo-2.tar.gz", second["sdist"])
        with tarfile.open(second["sdist"]) as archive:
            self.assertEqual(
                archive.extractfile("demo-2/demo/__init__.py").read(), b"VALUE = 2\n"
            )
            self.assertIn(b"Version: 2", archive.extractfile("demo-2/PKG-INFO").read())

    def test_reproduce_sdk_one_then_three_same_source(self):
        source = self.fixture()
        manifest = self.manifest(source)
        original_manifest = manifest.read_bytes()
        build(source, manifest, self.root / "first", 1)
        self.assertTrue((source / ".pdm-build/pyproject.toml").exists())
        with self.assertRaisesRegex(ValueError, "exactly match"):
            build(source, manifest, self.root / "second", 3)
        self.assertEqual(manifest.read_bytes(), original_manifest)
        self.assertFalse((self.root / "second").exists())

    def test_wheel_only_reads_new_sdist(self):
        source = self.fixture()
        original = (source / "demo/__init__.py").read_bytes()
        manifest = self.manifest(source)

        def extracted_then_changed(archive, destination, selected):
            extract_selected(archive, destination, selected)
            (source / "demo/__init__.py").write_bytes(b"CHANGED_AFTER_SDIST = True\n")
            project = source / "pyproject.toml"
            project.write_text(
                project.read_text().replace('version="1"', 'version="9"')
            )

        with patch("ops.extract_selected", side_effect=extracted_then_changed):
            result = build(source, manifest, self.root / "output", 3)
        with zipfile.ZipFile(result["wheel"]) as wheel:
            self.assertEqual(wheel.read("demo/__init__.py"), original)
            self.assertIn(b"Version: 1", wheel.read("demo-1.dist-info/METADATA"))

    def test_existing_and_nested_output_rejected(self):
        source = self.fixture()
        manifest = self.manifest(source)
        with self.assertRaisesRegex(ValueError, "outside source"):
            build(source, manifest, source / "output", 3)
        output = self.root / "output"
        output.mkdir()
        with self.assertRaises(FileExistsError):
            build(source, manifest, output, 3)
        self.assertFalse((source / ".pdm-build").exists())

    def test_reproduce_stock_uv_then_sdk_same_source(self):
        source = self.fixture()
        manifest = self.manifest(source)
        tools = Path(r"Q:\fastapi\Generated Files\arm-build")
        command = [
            str(tools / "tools/uv.exe"),
            "build",
            str(source),
            "--python",
            str(tools / "tools/official-tool-environment/Scripts/python.exe"),
            "--offline",
            "--no-index",
            "--find-links",
            str(tools / "wheelhouse"),
            "--out-dir",
            str(self.root / "baseline"),
            "--cache-dir",
            str(self.root / "uv-cache"),
        ]
        # Keep all child scratch/cache writes on the owned Q: fixture.
        child_scratch = self.root / "child-scratch"
        child_scratch.mkdir()
        environment = os.environ | {
            "TEMP": str(child_scratch),
            "TMP": str(child_scratch),
            "TMPDIR": str(child_scratch),
        }
        result = subprocess.run(
            command, capture_output=True, text=True, env=environment
        )
        print("STOCK UV COMMAND:", command)
        print("STOCK UV EXIT:", result.returncode)
        print(result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0)
        self.assertTrue((source / ".pdm-build/pyproject.toml").exists())
        with self.assertRaisesRegex(ValueError, "exactly match"):
            build(source, manifest, self.root / "sdk", 3)

    def test_three_initial_reads_then_close_joins(self):
        calls = []

        class File:
            def read_bytes(self):
                calls.append(threading.current_thread().name)
                return b"x"

        iterator = payloads([(str(i), File()) for i in range(20)], 3)
        self.assertEqual(next(iterator)[0], "0")
        iterator.close()
        self.assertGreaterEqual(len(calls), 1)
        self.assertLessEqual(len(calls), 3)
        self.assertFalse(
            any(t.name.startswith("sdist-read") for t in threading.enumerate())
        )

    @unittest.skipUnless(
        Path("REVIEW_CHECKS.PY").exists(), "case-insensitive filesystem"
    )
    def test_reproduce_case_variant_hook_execution(self):
        source = self.fixture()
        (source / "PDM_BUILD.PY").write_text(
            "def pdm_build_initialize(context):\n"
            "    (context.dist_dir / 'hook-ran.txt').write_text('executed')\n",
            encoding="utf-8",
        )
        manifest = self.manifest(source)
        configuration(
            {
                "build-system": {"build-backend": "pdm.backend"},
                "project": {"name": "demo", "version": "1"},
            },
            ["pyproject.toml", "demo/__init__.py", "PDM_BUILD.PY"],
        )
        with self.assertRaisesRegex(ValueError, "Missing canonical mode"):
            build(source, manifest, self.root / "output", 3)
        self.assertEqual(
            (self.root / "output/artifacts/hook-ran.txt").read_text(), "executed"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
