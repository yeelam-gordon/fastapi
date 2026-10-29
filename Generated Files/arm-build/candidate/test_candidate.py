import io
import shutil
import tarfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from build import build
from ops import BufferedSdistBuilder, extract_selected, payloads
from selector import configuration, safe_path, select


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("scratch/unit")
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root)

    def assert_joined(self):
        self.assertFalse(
            any(t.name.startswith("sdist-read") for t in threading.enumerate())
        )

    def test_reads_fresh_bytes_in_order_and_closes(self):
        path = self.root / "file"
        for workers in (1, 3):
            path.write_bytes(b"first")
            self.assertEqual(list(payloads([("file", path)], workers))[0][2], b"first")
            path.write_bytes(b"changed")
            reader = payloads([("file", path)] * 8, workers)
            self.assertEqual(next(reader)[2], b"changed")
            reader.close()
            self.assert_joined()

    def test_read_failure_joins(self):
        with self.assertRaises(FileNotFoundError):
            list(payloads([("missing", self.root / "missing")] * 8, 3))
        self.assert_joined()

    def test_pdm_pin_fails_before_output(self):
        output = self.root / "output"
        with patch("build.importlib.metadata.version", return_value="2.6.0"):
            with self.assertRaisesRegex(ValueError, "2.5.0"):
                build(self.root, self.root / "unused.json", output, 3)
        self.assertFalse(output.exists())

    def builder(self):
        builder = object.__new__(BufferedSdistBuilder)
        builder.workers = 3
        builder.modes = {"file": {"mode": 0o755}}
        builder._show_add_file = lambda *args: None
        builder._package_metadata = SimpleNamespace(
            as_rfc822=lambda: "Name: demo\nVersion: 1\n"
        )
        context = SimpleNamespace(
            dist_dir=self.root,
            config=SimpleNamespace(metadata={"name": "demo", "version": "1"}),
        )
        path = self.root / "file"
        path.write_bytes(b"payload")
        return builder, context, [("file", path)] * 8

    def test_target_write_failure_joins(self):
        builder, context, files = self.builder()
        with patch.object(
            tarfile.TarFile, "addfile", side_effect=OSError("target failed")
        ):
            with self.assertRaisesRegex(OSError, "target failed"):
                builder.build_artifact(context, files)
        self.assert_joined()

    def test_canonical_mode_and_metadata(self):
        builder, context, files = self.builder()
        with tarfile.open(builder.build_artifact(context, files[:1])) as archive:
            info = archive.getmember("demo-1/file")
            self.assertEqual(
                (info.mode, info.uid, info.gid, info.uname, info.gname),
                (0o755, 0, 0, "", ""),
            )
            self.assertEqual(archive.extractfile(info).read(), b"payload")
            self.assertEqual(
                archive.extractfile("demo-1/PKG-INFO").read(),
                b"Name: demo\nVersion: 1\n",
            )

    def test_unsafe_configs_and_paths(self):
        for name in ("../escape", "/absolute", "C:/drive", "a\\b", "a/../b", "a//b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_path(name)
        for build_config in (
            {"includes": ["x"]},
            {"source-includes": ["tests/*"]},
            {"source-includes": ["../outside"]},
        ):
            with self.assertRaises(ValueError):
                configuration(
                    {
                        "build-system": {"build-backend": "pdm.backend"},
                        "tool": {"pdm": {"build": build_config}},
                    },
                    [],
                )
        with self.assertRaisesRegex(ValueError, "hooks"):
            configuration(
                {"build-system": {"build-backend": "pdm.backend"}}, ["pdm_build.py"]
            )

    def test_archive_selector_and_extraction_filters(self):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            archive.addfile(tarfile.TarInfo("../escape"))
        stream.seek(0)
        with tarfile.open(fileobj=stream) as archive:
            with self.assertRaises(ValueError):
                select(archive)
            with self.assertRaises(tarfile.OutsideDestinationError):
                extract_selected(archive, self.root, ["../escape"])

    def test_archive_links_and_duplicates_rejected(self):
        for duplicate in (False, True):
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode="w") as archive:
                info = tarfile.TarInfo("pkg/file")
                if not duplicate:
                    info.type, info.linkname = tarfile.SYMTYPE, "../../escape"
                archive.addfile(info)
                if duplicate:
                    archive.addfile(info)
            stream.seek(0)
            with tarfile.open(fileobj=stream) as archive:
                with self.assertRaises(ValueError):
                    select(archive)


if __name__ == "__main__":
    unittest.main(verbosity=2)
