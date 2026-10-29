"""Fixture-only tests: no SDK invocation, environment installation or benchmark."""

import copy
import csv
import hashlib
import io
import os
import shutil
import struct
import subprocess
import tarfile
import unittest
import uuid
import zipfile
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

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
    result = {
        "schema": measure.SCHEMA,
        "status": "complete",
        "system": system,
        "source": {
            "revision": measure.SOURCE,
            "archive_sha256": "a" * 64,
            "manifest_sha256": "b" * 64,
        },
        "harness_revision": "a" * 40,
        "tool_hashes": dict.fromkeys(measure.REQUIRED_TOOL_INPUTS, "c" * 64),
        "runtime": {
            "version": "3.13.15",
            "native_arm64": True,
            "executable_sha256": "d" * 64,
            "shared_library_sha256": "e" * 64,
            "machine": "arm64",
            "tag": "win-arm64" if system == "Windows" else "macosx-11.0-universal2",
            "translated": False,
        },
        "uv": {
            "version": "0.13.6",
            "version_output": "uv 0.13.6\n",
            "sha256": "f" * 64,
            "arm64_slice": True,
        },
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
    return attach_receipts(result, system)


def attach_receipts(result, system):
    path = measure.PureWindowsPath if system == "Windows" else measure.PurePosixPath
    base = path("C:/fixture" if system == "Windows" else "/fixture")
    runtime = result["runtime"]
    runtime["executable"] = str(base / "python")
    for kind in ("executable", "shared_library"):
        runtime[kind + "_binary"] = {
            "sha256": runtime[kind + "_sha256"],
            "arm64_slice": True,
            "path": str(base / kind),
        }
    result["uv"]["path"] = str(base / "uv")
    for number, sample in enumerate(result["samples"]):
        owned = measure.Receipt(0, False, sample["wall"], 0.1, True, False, True, ())
        sample.update(
            command_wall=owned.command_wall,
            infrastructure_wall=owned.infrastructure_wall,
            owned_family=asdict(owned),
            ownership_succeeded=owned.succeeded,
        )
        if sample["variant"] == "B":
            continue
        directory = base / f"sample-{number}"
        root = directory / (".caller-env-" + f"{number:032x}")
        venv = root / "venv"
        python = str(
            venv / ("Scripts/python.exe" if system == "Windows" else "bin/python")
        )
        here = base / "tools" / "protocol"
        args = {
            "--uv": str(base / "uv"),
            "--python": runtime["executable"],
            "--source": str(directory / "source"),
            "--source-manifest": str(base / "manifest"),
            "--out-dir": str(directory / "out"),
            "--workers": sample["variant"][1:],
            "--cache-dir": str(base / "cache"),
            "--wheelhouse": str(base / "wheels"),
            "--report": str(directory / "wrapper.json"),
        }
        sample["argv"] = [runtime["executable"], str(here / "isolated_build.py")]
        sample["argv"] += [part for pair in args.items() for part in pair]
        uv = [
            args["--uv"],
            "--no-config",
            "--offline",
            "--cache-dir",
            args["--cache-dir"],
        ]
        commands = [
            uv
            + [
                "venv",
                "--python",
                runtime["executable"],
                "--no-python-downloads",
                str(venv),
            ],
            uv
            + [
                "pip",
                "install",
                "--python",
                python,
                "--require-hashes",
                "--no-index",
                "--only-binary",
                ":all:",
                "--find-links",
                args["--wheelhouse"],
                "-r",
                str(here / "backend.lock"),
            ],
            [python, "-B", "-I", "-c", "frozen identity probe"],
            [
                python,
                "-B",
                "-E",
                "-s",
                str(here.parent / "candidate" / "build.py"),
                "--source",
                args["--source"],
                "--source-manifest",
                args["--source-manifest"],
                "--out-dir",
                args["--out-dir"],
                "--workers",
                args["--workers"],
            ],
            None,
        ]
        artifacts = {
            str(directory / "out" / "artifacts" / name): "a" * 64
            for name in ("package.tar.gz", "package.whl")
        }
        sample["correctness"]["archive_sha256"] = artifacts
        sample["wrapper_report"] = {
            "schema_version": 1,
            "status": "passed",
            "errors": [],
            "isolation": "fresh caller environment shared by both SDK hooks",
            "workers": int(args["--workers"]),
            "wall_seconds": 0.6,
            "environment": {
                "root": str(root),
                "existed_before": False,
                "exists_after_cleanup": False,
                "identity": {
                    "prefix": str(venv),
                    "executable": python,
                    "base_prefix": str(base),
                    "version": "3.13.15 (fixture)",
                    "backend": "2.5.0",
                    "user_site": False,
                    "dont_write_bytecode": True,
                    "machine": "arm64",
                    "platform": runtime["tag"],
                },
            },
            "identities": {
                "uv_sha256": "f" * 64,
                "base_python_sha256": "d" * 64,
                "lock_sha256": "c" * 64,
                "wrapper_sha256": "c" * 64,
                "sdk_sha256": "c" * 64,
                "source_manifest_sha256": "b" * 64,
            },
            "artifacts": artifacts,
            "phases": [
                {
                    "phase": name,
                    "argv": command,
                    "returncode": 0,
                    "start_offset_seconds": i * 0.1,
                    "seconds": 0.05,
                }
                for i, (name, command) in enumerate(
                    zip(
                        ("create", "install", "identity", "sdk", "cleanup"),
                        commands,
                        strict=True,
                    )
                )
            ],
        }
        sample["wrapper_report"]["phases"][-1].update(
            operation="shutil.rmtree", path=str(root)
        )
    return result


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        inventory = patch.object(
            measure, "tool_inventory", return_value=measure.REQUIRED_TOOL_INPUTS
        )
        inventory.start()
        self.addCleanup(inventory.stop)

    def test_committed_bytecode_flags_accept_and_missing_or_wrong_flags_reject(self):
        for system in ("Windows", "Darwin"):
            evidence = report(system)
            sample = evidence["samples"][1]
            measure.validate_wrapper(sample, evidence, set())
            for phase in ("identity", "sdk"):
                for replacement in (None, "-b"):
                    with self.subTest(
                        system=system, phase=phase, replacement=replacement
                    ):
                        broken = copy.deepcopy(sample)
                        argv = next(
                            p["argv"]
                            for p in broken["wrapper_report"]["phases"]
                            if p["phase"] == phase
                        )
                        self.assertEqual(argv[1], "-B")
                        if replacement is None:
                            argv.pop(1)
                        else:
                            argv[1] = replacement
                        with self.assertRaises(ValueError):
                            measure.validate_wrapper(broken, evidence, set())
            for observed in (None, False):
                with self.subTest(system=system, bytecode_identity=observed):
                    broken = copy.deepcopy(sample)
                    identity = broken["wrapper_report"]["environment"]["identity"]
                    if observed is None:
                        identity.pop("dont_write_bytecode")
                    else:
                        identity["dont_write_bytecode"] = observed
                    with self.assertRaises(ValueError):
                        measure.validate_wrapper(broken, evidence, set())

    def test_comparison_rejects_failed_owned_family_receipts(self):
        for field, value in (
            ("ownership_established", False),
            ("survivors", True),
            ("survivors", None),
            ("cleanup_complete", False),
            ("errors", ["owner failure"]),
            ("timed_out", True),
            ("command_wall", None),
            ("infrastructure_wall", None),
        ):
            with self.subTest(field=field, value=value):
                windows = report("Windows")
                windows["samples"][0]["owned_family"][field] = value
                with self.assertRaises(ValueError):
                    compare.compare(windows, report("Darwin"))

    def test_pp001_missing_failed_reused_and_inconsistent_receipts_rejected(self):
        def mutate(r, case):
            sample = r["samples"][1]
            receipt = sample["wrapper_report"]
            if case == "missing":
                del sample["wrapper_report"]
            elif case == "failed":
                sample["wrapper_report"] = {"status": "failed", "environment": "reused"}
            elif case == "reuse":
                r["samples"][2]["wrapper_report"]["environment"]["root"] = receipt[
                    "environment"
                ]["root"]
            elif case == "reuse-whole":
                for field in ("wrapper_report", "argv", "correctness"):
                    r["samples"][4][field] = copy.deepcopy(sample[field])
            elif case == "errors":
                receipt["errors"] = [{"phase": "cleanup", "message": "failed"}]
            elif case == "existed":
                receipt["environment"]["existed_before"] = True
            elif case == "cleanup":
                receipt["environment"]["exists_after_cleanup"] = True
            elif case == "phase":
                receipt["phases"][1]["returncode"] = 1
            elif case == "missing-phase":
                receipt["phases"].pop()
            elif case == "workers":
                receipt["workers"] = 3
            elif case == "source":
                receipt["phases"][3]["argv"][-7] = "wrong"
            elif case == "hash":
                receipt["identities"]["sdk_sha256"] = "0" * 64
            elif case == "clock":
                receipt["wall_seconds"] = sample["wall"] + 1
            elif case == "phase-clock":
                receipt["phases"][3]["seconds"] = 10
            elif case == "identity":
                receipt["environment"]["identity"]["backend"] = "2.4"
            elif case == "artifact":
                receipt["artifacts"] = {}

        for case in (
            "missing",
            "failed",
            "reuse",
            "reuse-whole",
            "errors",
            "existed",
            "cleanup",
            "phase",
            "missing-phase",
            "workers",
            "source",
            "hash",
            "clock",
            "phase-clock",
            "identity",
            "artifact",
        ):
            with self.subTest(case=case):
                windows = report("Windows")
                mutate(windows, case)
                with self.assertRaises((ValueError, KeyError)):
                    compare.compare(windows, report("Darwin"))

    def test_pp002_equal_incomplete_identities_rejected(self):
        for case in ("empty", "inventory", "revision", "runtime", "uv", "uv-version"):
            with self.subTest(case=case):
                windows, mac = report("Windows"), report("Darwin")
                for item in (windows, mac):
                    if case == "empty":
                        item["tool_hashes"] = {}
                        item["harness_revision"] = ""
                    elif case == "inventory":
                        item["tool_hashes"].pop(next(iter(item["tool_hashes"])))
                    elif case == "revision":
                        item["harness_revision"] = "short"
                    elif case == "runtime":
                        item["runtime"]["executable_sha256"] = "not-a-sha256"
                    elif case == "uv":
                        item["uv"].pop("arm64_slice")
                    elif case == "uv-version":
                        item["uv"]["version_output"] = "uv 0.13.60\n"
                with self.assertRaises((ValueError, KeyError)):
                    compare.compare(windows, mac)

    def test_native_runtime_binary_digests_may_differ_by_os(self):
        windows, mac = report("Windows"), report("Darwin")
        for kind, value in (("executable", "1" * 64), ("shared_library", "2" * 64)):
            mac["runtime"][kind + "_sha256"] = value
            mac["runtime"][kind + "_binary"]["sha256"] = value
        mac["uv"]["sha256"] = "3" * 64
        for sample in mac["samples"]:
            if sample["variant"] != "B":
                sample["wrapper_report"]["identities"].update(
                    base_python_sha256="1" * 64, uv_sha256="3" * 64
                )
        self.assertTrue(
            compare.compare(windows, mac)["sdk_caller_isolated_sample_parity"]
        )

    def test_best_mac_is_not_frozen(self):
        windows, mac = report("Windows"), report("Darwin")
        for sample in mac["samples"]:
            if sample["variant"] == "S1":
                sample["wall"] = 2
                sample["command_wall"] = 2
                sample["owned_family"]["command_wall"] = 2
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
    def test_exact_pinned_uv_version_with_optional_official_metadata(self):
        for output in (
            "uv 0.13.6",
            "uv 0.13.6\n",
            "uv 0.13.6\r\n",
            "uv 0.13.6 (329bf9448 2026-10-26)",
            "uv 0.13.6 (329bf9448 2026-10-26 aarch64-pc-windows-msvc)\r\n",
            "uv 0.13.6 (329bf9448 2026-10-26 aarch64-apple-darwin)\n",
        ):
            with self.subTest(output=output):
                self.assertEqual(measure.parse_uv_version(output), "0.13.6")
        for output in (
            "uv 0.13.60",
            "uv 0.13.6rc1",
            "uv 0.13.6-rc.1",
            "uv 0.13.7",
            "uv 0.13.6+local",
            "uv 0.13.6\nextra",
            "uv 0.13.6\n\n",
            "uv 0.13.6 ()",
            "uv 0.13.6 (garbage)",
            "uv 0.13.6 ",
            " uv 0.13.6",
            "uv 0.13.6 (329bf9448 2026-02-30)",
            "uv 0.13.6 (329bf9448 2026-10-26 target)",
            "",
        ):
            with self.subTest(output=output):
                with self.assertRaises(ValueError):
                    measure.parse_uv_version(output)

    @unittest.skipUnless(
        os.environ.get("PAIRED_TEST_UV"), "Explicit verified uv path required"
    )
    def test_real_verified_uv_nonbuild_preflight(self):
        executable = Path(os.environ["PAIRED_TEST_UV"])
        raw = subprocess.check_output([str(executable), "--version"]).decode("utf-8")
        self.assertEqual(measure.parse_uv_version(raw), "0.13.6")
        self.assertTrue(measure.binary_receipt(executable)["arm64_slice"])

    def test_real_git_sparse_inventory_from_nested_tool_directory(self):
        root = Path(__file__).resolve().parent / (".inventory-test-" + uuid.uuid4().hex)
        root.mkdir()

        def cleanup():
            def retry(function, name, error):
                Path(name).chmod(0o700)
                function(name)

            shutil.rmtree(root, onexc=retry)

        self.addCleanup(cleanup)
        extra = measure.PREFIX + "candidate/new_helper.py"
        expected = measure.REQUIRED_TOOL_INPUTS | {extra}
        for name in expected | {"historical/evidence.log"}:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"fixture\n")

        def git(*args):
            return subprocess.check_output(
                ["git", "-c", "core.autocrlf=false", "-C", str(root), *args]
            )

        git("init", "--quiet")
        git("add", "--all")
        git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=" + str(root / "no-hooks"),
            "commit",
            "--quiet",
            "-m",
            "fixture",
        )
        revision = git("rev-parse", "HEAD").decode().strip()
        subprocess.run(
            [
                "git",
                "-c",
                "core.autocrlf=false",
                "-C",
                str(root),
                "sparse-checkout",
                "set",
                "--no-cone",
                "--stdin",
            ],
            input="\n".join("/" + name for name in sorted(expected)).encode(),
            check=True,
        )
        self.assertFalse((root / "historical" / "evidence.log").exists())
        with patch.object(measure, "ROOT", root / "Generated Files" / "arm-build"):
            self.assertEqual(measure.tool_inventory(revision), expected)
            receipts = measure.code_receipts()
            self.assertEqual(set(receipts), expected)
            self.assertEqual(set(receipts.values()), {measure.digest(b"fixture\n")})
            (root / measure.PREFIX / "protocol" / "owned_process.py").unlink()
            with self.assertRaises(FileNotFoundError):
                measure.code_receipts()

    def test_pinned_inventory_includes_new_helpers_and_rejects_missing_required(self):
        revision = "a" * 40
        extra = measure.PREFIX + "candidate/new_helper.py"
        names = sorted(measure.REQUIRED_TOOL_INPUTS | {extra, "historical/result.json"})
        with patch.object(measure, "git", return_value="\n".join(names).encode()):
            self.assertEqual(
                measure.tool_inventory(revision), measure.REQUIRED_TOOL_INPUTS | {extra}
            )
        names.remove(measure.PREFIX + "protocol/isolated_build.py")
        with patch.object(measure, "git", return_value="\n".join(names).encode()):
            with self.assertRaises(ValueError):
                measure.tool_inventory(revision)

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
            patch.object(Path, "read_bytes", return_value=b"raw archive fixture"),
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

    def test_owned_receipts_control_acceptance_and_keep_clocks_separate(self):
        good = measure.Receipt(0, False, 3.0, 0.2, True, False, True, ())
        failures = [
            {"returncode": 1},
            {"timed_out": True},
            {"ownership_established": False},
            {"survivors": True},
            {"survivors": None},
            {"cleanup_complete": False},
            {"errors": ("ownership failed",)},
            {"command_wall": None},
            {"infrastructure_wall": None},
            {"infrastructure_wall": -1},
        ]
        for changes in [{}, *failures]:
            with self.subTest(changes=changes):
                receipt = replace(good, **changes)
                with patch.object(measure, "run_owned", return_value=receipt) as runner:
                    result = measure.run(
                        ["fixture"], Path("fixture.log"), Path("."), {}
                    )
                self.assertEqual(measure.succeeded(result), not changes)
                self.assertEqual(result["wall"], receipt.command_wall)
                self.assertEqual(
                    result["infrastructure_wall"], receipt.infrastructure_wall
                )
                self.assertEqual(result["owned_family"], asdict(receipt))
                runner.assert_called_once_with(
                    ["fixture"],
                    cwd=Path("."),
                    env={},
                    stdout_path=Path("fixture.log"),
                    stderr_path=Path("fixture.stderr.log"),
                    timeout=120,
                )
                self.assertIsNone(result["cpu_seconds"])


if __name__ == "__main__":
    unittest.main()
