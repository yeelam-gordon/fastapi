"""Fixture-only tests: no SDK invocation, environment installation or benchmark."""

import copy
import csv
import hashlib
import io
import struct
import sys
import tarfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

import compare_pairs as compare
import measure_pairs as measure


def report(system):
    check = dict.fromkeys(
        (
            "source",
            "membership",
            "payloads",
            "modes",
            "ownership",
            "metadata",
            "record",
            "smoke",
        ),
        True,
    )
    check.update(differences=[], canonical_record_sha256="record")
    return {
        "schema": measure.SCHEMA,
        "status": "complete",
        "system": system,
        "source": {"revision": measure.SOURCE, "archive_sha256": "source"},
        "harness_revision": "tools",
        "tool_hashes": {"wrapper.py": "raw"},
        "runtime": {
            "version": "3.13.15",
            "native_arm64": True,
            "executable_sha256": "exe",
            "shared_library_sha256": "lib",
        },
        "uv": {"version": "0.13.6"},
        "scopes": {
            "B": "standard_uv_isolated_wall",
            "S1": "sdk_caller_isolated_wall",
            "S3": "sdk_caller_isolated_wall",
        },
        "samples": [
            {
                "block": block,
                "variant": variant,
                "timed": block >= 0,
                "wall": {"B": 6, "S1": 4, "S3": 3}[variant],
                "returncode": 0,
                "timed_out": False,
                "cleanup_errors": [],
                "correctness": copy.deepcopy(check),
            }
            for block, order in [(-1, ("B", "S1", "S3")), *enumerate(measure.ORDERS)]
            for variant in order
        ],
    }


class ComparisonTests(unittest.TestCase):
    def test_best_mac_is_not_frozen(self):
        windows, mac = report("Windows"), report("Darwin")
        for sample in mac["samples"]:
            if sample["variant"] == "S1":
                sample["wall"] = 2
        result = compare.compare(windows, mac)
        self.assertEqual(result["best_correct_sdk"], {"Windows": "S3", "Darwin": "S1"})
        self.assertFalse(result["sdk_caller_isolated_sample_parity"])
        self.assertEqual(result["best_sdk_ratio_windows_over_mac"], 1.5)
        self.assertEqual(
            set(result["variant_ratios_windows_over_mac"]), {"B", "S1", "S3"}
        )
        self.assertFalse(result["baseline_eligible"]["Darwin"])
        self.assertEqual(result["within_block_S1_minus_S3"]["Windows"], [1] * 5)
        self.assertIsNone(result["cpu_seconds"])

    def test_invalid_evidence_rejected(self):
        def mutate_source(r):
            r["source"]["revision"] = "wrong"

        def mutate_runtime(r):
            r["runtime"]["native_arm64"] = False

        def mutate_correctness(r):
            r["samples"][2]["correctness"]["modes"] = False

        def mutate_missing(r):
            r["samples"].pop()

        def mutate_timeout(r):
            r["samples"][4]["timed_out"] = True

        def mutate_nan(r):
            r["samples"][4]["wall"] = float("nan")

        def mutate_code(r):
            r["tool_hashes"]["wrapper.py"] = "different raw bytes"

        for mutate in (
            mutate_source,
            mutate_runtime,
            mutate_correctness,
            mutate_missing,
            mutate_timeout,
            mutate_nan,
            mutate_code,
        ):
            with self.subTest(mutation=mutate.__name__):
                windows = report("Windows")
                mutate(windows)
                with self.assertRaises(ValueError):
                    compare.compare(windows, report("Darwin"))

    def test_known_baseline_is_failed_not_waived(self):
        windows = report("Windows")
        for sample in windows["samples"]:
            if sample["variant"] == "B":
                check = sample["correctness"]
                check["modes"] = False
                check["differences"] = [
                    {
                        "archive": "sdist",
                        "name": name,
                        "field": "mode",
                        "expected": 0o755,
                        "actual": 0o644,
                    }
                    for name in sorted(measure.KNOWN_MODES)
                ]
        result = compare.compare(windows, report("Darwin"))
        self.assertFalse(result["summaries"]["Windows"]["B"]["correct"])
        self.assertEqual(result["summaries"]["Windows"]["B"]["median"], 6)
        windows["samples"][0]["correctness"]["differences"][0]["actual"] = 0o600
        with self.assertRaises(ValueError):
            compare.compare(windows, report("Darwin"))

    def test_native_universal2_and_rosetta(self):
        self.assertTrue(
            measure.native_runtime("Darwin", "arm64", "macosx-11.0-universal2")
        )
        self.assertFalse(
            measure.native_runtime("Darwin", "x86_64", "macosx-11.0-universal2")
        )
        self.assertFalse(
            measure.native_runtime("Darwin", "arm64", "macosx-11.0-universal2", True)
        )


class ArchiveTests(unittest.TestCase):
    def test_independent_archive_record_and_modes(self):
        # Entirely in memory: these fixtures cannot run or modify the candidate.
        tarstream, zipstream = io.BytesIO(), io.BytesIO()
        name = "fastapi-0.162.0/PKG-INFO"
        data = b"Name: fastapi\nVersion: 0.162.0\n"
        with tarfile.open(fileobj=tarstream, mode="w:gz") as archive:
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o644
            archive.addfile(info, io.BytesIO(data))
        payloads = {
            "fastapi-0.162.0.dist-info/METADATA": data,
            "fastapi-0.162.0.dist-info/WHEEL": b"Wheel-Version: 1.0\n",
        }
        record_name = "fastapi-0.162.0.dist-info/RECORD"
        rows = [
            [
                key,
                "sha256="
                + measure.base64.urlsafe_b64encode(hashlib.sha256(value).digest())
                .decode()
                .rstrip("="),
                str(len(value)),
            ]
            for key, value in payloads.items()
        ] + [[record_name, "", ""]]
        text = io.StringIO()
        csv.writer(text).writerows(rows)
        payloads[record_name] = text.getvalue().encode()
        oracle = {
            "sdist": {
                name: {
                    "sha256": measure.digest(data),
                    "mode": 0o644,
                    "uid": 0,
                    "gid": 0,
                    "uname": "",
                    "gname": "",
                    "size": len(data),
                }
            },
            "wheel": {
                key: {"sha256": measure.digest(value), "full_mode": 0o100644}
                for key, value in payloads.items()
            },
        }
        with zipfile.ZipFile(zipstream, "w") as archive:
            for key, value in payloads.items():
                info = zipfile.ZipInfo(key)
                info.external_attr = 0o100644 << 16
                archive.writestr(info, value)
        directory = Path("fixture")
        tarpath, wheelpath = directory / "a.tar.gz", directory / "a.whl"
        real_tar, real_zip = tarfile.open, zipfile.ZipFile
        with (
            patch.object(
                Path,
                "rglob",
                lambda self, pattern: iter(
                    [tarpath] if pattern == "*.tar.gz" else [wheelpath]
                ),
            ),
            patch.object(
                measure.tarfile,
                "open",
                lambda path: real_tar(fileobj=io.BytesIO(tarstream.getvalue())),
            ),
            patch.object(
                measure.zipfile,
                "ZipFile",
                lambda path: real_zip(io.BytesIO(zipstream.getvalue())),
            ),
        ):
            result = measure.inspect_artifacts(directory, oracle)
            self.assertTrue(result["record"])
            self.assertTrue(result["metadata"])
            self.assertEqual(result["differences"], [])
            broken = copy.deepcopy(oracle)
            broken["sdist"][name]["mode"] = 0o755
            self.assertFalse(measure.inspect_artifacts(directory, broken)["modes"])
            broken = copy.deepcopy(oracle)
            broken["wheel"][next(iter(payloads))]["sha256"] = "wrong"
            self.assertFalse(measure.inspect_artifacts(directory, broken)["metadata"])

    def test_raw_hashes_do_not_normalize_line_endings(self):
        self.assertNotEqual(measure.digest(b"a\r\n"), measure.digest(b"a\n"))

    def test_native_binary_receipt_rejects_x64(self):
        data = bytearray(128)
        data[:2] = b"MZ"
        struct.pack_into("<I", data, 0x3C, 64)
        data[64:68] = b"PE\0\0"
        struct.pack_into("<H", data, 68, 0xAA64)
        with patch.object(Path, "read_bytes", return_value=bytes(data)):
            self.assertTrue(measure.binary_receipt(Path("fixture.exe"))["arm64_slice"])
        struct.pack_into("<H", data, 68, 0x8664)
        with patch.object(Path, "read_bytes", return_value=bytes(data)):
            with self.assertRaises(ValueError):
                measure.binary_receipt(Path("fixture.exe"))

    def test_timeout_kills_owned_tree_and_retains_elapsed(self):
        process, child, owner = Mock(), Mock(), Mock()
        process.pid, child.pid = 42, 43
        process.poll.return_value = None
        process.wait.return_value = -9
        child.is_running.return_value = True
        child.status.return_value = "running"
        owner.children.return_value = [child]
        psutil = types.SimpleNamespace(
            Process=Mock(return_value=owner),
            NoSuchProcess=LookupError,
            Error=RuntimeError,
            STATUS_ZOMBIE="zombie",
        )
        with (
            patch.dict(sys.modules, {"psutil": psutil}),
            patch.object(Path, "open", mock_open()),
            patch.object(measure.subprocess, "Popen", return_value=process),
            patch.object(measure.time, "perf_counter", side_effect=[0, 121, 122]),
        ):
            result = measure.run(["fixture"], Path("fixture.log"), Path("."), {})
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["wall"], 122)
        self.assertFalse(measure.succeeded(result))
        child.kill.assert_called_once()
        process.kill.assert_called_once()
        self.assertIsNone(result["cpu_seconds"])


if __name__ == "__main__":
    unittest.main()
