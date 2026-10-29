"""Focused stdlib tests; fixtures stay under this directory and are removed."""

import argparse
import base64
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import unittest
from unittest import mock
import uuid
import zipfile


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("benchmark", HERE / "benchmark.py")
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.root = HERE / f".test-benchmark-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)

    def wheel(self, name="one.whl", payload=b"hello", *, timestamp=2024, bad=None):
        path = self.root / name
        entries = {"pkg/__init__.py": payload, "pkg-1.dist-info/METADATA": b"Version: 1\n"}
        record = "pkg-1.dist-info/RECORD"
        rows = []
        for member, data in entries.items():
            hashed = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            rows.append([member, "sha256=" + hashed, str(len(data))])
        rows.append([record, "", ""])
        if bad == "hash":
            rows[0][1] = "sha256=incorrect"
        elif bad == "size":
            rows[0][2] = "1000"
        elif bad == "missing-row":
            rows.pop(0)
        elif bad == "duplicate":
            rows.append(rows[0])
        elif bad == "missing-file":
            entries.pop("pkg/__init__.py")
        elif bad == "weak-hash":
            rows[0][1] = "md5=invalid"
        elif bad == "self-hash":
            rows[-1][1] = "sha256=invalid"
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\r\n" if timestamp == 2025 else "\n")
        writer.writerows(rows)
        entries[record] = stream.getvalue().encode()
        with zipfile.ZipFile(path, "w") as archive:
            for member, data in entries.items():
                info = zipfile.ZipInfo(member, date_time=(timestamp, 1, 1, 0, 0, 0))
                archive.writestr(info, data)
        return path

    def sdist(self, directory, payload=b"hello", *, mtime=1, missing=False, mode=0o644):
        directory.mkdir(exist_ok=True)
        path = directory / "pkg-1.tar.gz"
        with tarfile.open(path, "w:gz") as archive:
            entries = {"pkg-1/pkg/__init__.py": payload, "pkg-1/PKG-INFO": b"Version: 1\n"}
            if missing:
                entries.pop("pkg-1/pkg/__init__.py")
            for name, data in entries.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mtime = mtime
                info.mode = mode
                archive.addfile(info, io.BytesIO(data))
        return path

    def test_wheel_timestamp_and_valid_record_serialization_are_equivalent(self):
        first = benchmark.wheel_members(self.wheel())
        second = benchmark.wheel_members(self.wheel("two.whl", timestamp=2025))
        self.assertEqual(first, second)

    def test_wheel_validly_recorded_content_mutation_is_not_equivalent(self):
        first = {"pkg.whl": benchmark.wheel_members(self.wheel())}
        second = {"pkg.whl": benchmark.wheel_members(self.wheel("two.whl", payload=b"changed"))}
        with self.assertRaisesRegex(benchmark.VerificationError, "changed content"):
            benchmark.compare_manifests(first, second)

    def test_record_errors_are_rejected(self):
        for error in (
            "hash", "size", "missing-row", "duplicate", "missing-file",
            "weak-hash", "self-hash",
        ):
            with self.subTest(error=error):
                with self.assertRaises(benchmark.VerificationError):
                    benchmark.wheel_members(self.wheel(bad=error))

    def test_sdist_timestamp_equivalence_and_semantic_differences(self):
        first = benchmark.sdist_members(self.sdist(self.root / "a"))
        second = benchmark.sdist_members(self.sdist(self.root / "b", mtime=99))
        self.assertEqual(first, second)
        for kwargs in ({"payload": b"changed"}, {"missing": True}):
            with self.subTest(kwargs=kwargs):
                actual = benchmark.sdist_members(self.sdist(self.root / "c", **kwargs))
                with self.assertRaises(benchmark.VerificationError):
                    benchmark.compare_manifests({"pkg.tar.gz": first}, {"pkg.tar.gz": actual})

    def test_unexpected_artifact_sets_rejected(self):
        with self.assertRaises(benchmark.VerificationError):
            benchmark.artifact_manifest(self.root)

        shutil.move(self.wheel(), self.root / "pkg-1.whl")
        self.sdist(self.root)
        benchmark.artifact_manifest(self.root)
        (self.root / "extra.txt").write_text("unexpected")
        with self.assertRaises(benchmark.VerificationError):
            benchmark.artifact_manifest(self.root)

    def test_sdist_executable_permission_change_is_not_equivalent(self):
        first = benchmark.sdist_members(self.sdist(self.root / "a", mode=0o755))
        second = benchmark.sdist_members(self.sdist(self.root / "b", mode=0o644))
        with self.assertRaisesRegex(benchmark.VerificationError, "changed content"):
            benchmark.compare_manifests({"pkg.tar.gz": first}, {"pkg.tar.gz": second})

    def test_unsafe_members_and_self_inclusion_rejected(self):
        for name in ("../escape", "/absolute", "a\\b", "a//b", "a/./b", "C:/bad",
                     "pkg/Generated Files/arm-build/result.json"):
            with self.subTest(name=name):
                with self.assertRaises(benchmark.VerificationError):
                    benchmark.member_name(name)

    def test_command_failure_preserves_raw_logs_and_report(self):
        recorder = benchmark.Recorder(self.root, {})
        with self.assertRaises(RuntimeError):
            recorder.run(
                [sys.executable, "-c",
                 "import sys; print('out'); print('err', file=sys.stderr); sys.exit(7)"],
                self.root, "failure", os.environ.copy(),
            )
        report = json.loads((self.root / "report.json").read_text())
        row = report["commands"][0]
        self.assertEqual(row["returncode"], 7)
        self.assertGreaterEqual(row["wall_seconds"], 0)
        self.assertEqual((self.root / row["stdout"]).read_text().strip(), "out")
        self.assertEqual((self.root / row["stderr"]).read_text().strip(), "err")

    def test_launch_failure_is_recorded(self):
        recorder = benchmark.Recorder(self.root, {})
        with self.assertRaises(RuntimeError):
            recorder.run([str(self.root / "no-such-executable")], self.root,
                         "missing", os.environ.copy())
        row = json.loads((self.root / "report.json").read_text())["commands"][0]
        self.assertIsNone(row["returncode"])
        self.assertIn("launch_error", row)

    def test_execute_failure_returns_nonzero_and_preserves_report(self):
        source = self.root / "repo"
        source.mkdir()
        output = self.root / "results"
        args = argparse.Namespace(source=str(source), output=str(output),
                                  repeats=5, uv="missing", importtime=False)
        with mock.patch.object(benchmark.shutil, "which", return_value=None):
            self.assertEqual(benchmark.execute(args), 1)
        report = json.loads((output / "report.json").read_text())
        self.assertEqual(report["status"], "failed")
        self.assertIn("uv executable not found", report["error"])
        self.assertEqual(benchmark.main([
            "--uv", "missing", "--source", str(source), "--output", str(output)
        ]), 1)

    def test_output_inside_source_and_too_few_repeats_rejected(self):
        for output, repeats in ((self.root / "inside", 5), (self.root.parent / "unused", 4)):
            args = argparse.Namespace(source=str(self.root), output=str(output),
                                      repeats=repeats, uv="missing", importtime=False)
            with self.subTest(repeats=repeats), self.assertRaises(ValueError):
                benchmark.execute(args)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
