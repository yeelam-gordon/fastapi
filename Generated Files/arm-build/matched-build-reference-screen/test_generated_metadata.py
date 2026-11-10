import copy
import dataclasses
import hashlib
import shutil
import unittest
import uuid
from pathlib import Path

import screen
from archive_headers import TAR_FIELDS, WHEEL_FIELDS
from owned_process import Receipt


class GeneratedMetadataTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent / (
            "test-work-metadata-" + uuid.uuid4().hex
        )
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.reference_folder, self.folder = self.root / "WA", self.root / "WB"
        self.reference = self.inventory(1700000000.25)
        self.actual = self.inventory(1700000010.25)
        self.write_row(self.reference_folder, self.reference, 1700000000)
        self.write_row(self.folder, self.actual, 1700000010)
        screen.require_generated_headers(
            self.reference, None, self.reference_folder, None
        )

    def inventory(self, timestamp):
        member = dict.fromkeys(TAR_FIELDS, 0)
        member.update(
            sha256="a" * 64,
            mtime=timestamp,
            pax_headers={"mtime": str(timestamp)},
            mode=0o644,
            type="0",
            linkname="",
            uname="",
            gname="",
            size=7,
        )
        wheel = dict.fromkeys(WHEEL_FIELDS, 0)
        wheel.update(
            sha256="b" * 64, date_time=[1980, 1, 1, 0, 0, 0], extra="", comment=""
        )
        other = {**member, "mtime": 0, "pax_headers": {}}
        return {
            "sdist": {
                screen.GENERATED_PYPROJECT: member,
                "fastapi-0.119.1/README.md": other,
            },
            "wheel": {"fastapi/__init__.py": wheel},
        }

    def write_row(self, folder, inventory, birth):
        folder.mkdir()
        process = {
            "pid": 42,
            "image": "C:\\tools\\uv.exe",
            "birth_filetime": screen.FILETIME_EPOCH + birth * 10_000_000,
        }
        receipt = Receipt(
            0,
            False,
            2,
            0.01,
            True,
            False,
            True,
            (),
            native_start_ns=9_000_000_000_000_000,
            native_end_ns=9_000_002_000_000_000,
            actual_process=process,
        )
        environment = screen.environment_evidence(
            {"UV_CACHE_DIR": "C:\\private\\cache"}
        )
        command = {
            "argv": [process["image"], "build", "--offline"],
            "cwd": "C:\\private\\source",
            "environment": environment,
        }
        native = {
            **process,
            **command,
            "start_ns": receipt.native_start_ns,
            "end_ns": receipt.native_end_ns,
            "status": "COMPLETE",
            "returncode": 0,
        }
        for name, value in (
            ("command.json", command),
            ("native.json", native),
            ("ownership.json", dataclasses.asdict(receipt)),
            ("stdout.actual-process.json", process),
            ("full-headers.json", inventory),
        ):
            screen.save(folder / name, value)
        (folder / "stdout").write_bytes(b"native stdout")
        (folder / "stderr").write_bytes(b"")
        artifacts = folder / "artifacts"
        artifacts.mkdir()
        retained = {}
        for name, relative, data in (
            (".gitignore", "dist.gitignore", b"*"),
            (
                "fastapi-0.119.1.tar.gz",
                "artifacts\\fastapi-0.119.1.tar.gz",
                b"raw sdist",
            ),
            (
                "fastapi-0.119.1-py3-none-any.whl",
                "artifacts\\fastapi-0.119.1-py3-none-any.whl",
                b"raw wheel",
            ),
        ):
            (folder / relative).write_bytes(data)
            retained[name] = {
                "retained": relative,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            }
        screen.save(folder / "dist-output.json", retained)

    def compare(self):
        screen.save(self.folder / "full-headers.json", self.actual)
        screen.require_generated_headers(
            self.actual,
            self.reference,
            self.folder,
            self.reference_folder,
        )

    def test_default_time_change_has_independent_utc_bounds_and_no_map_rewrite(self):
        actual, reference = copy.deepcopy(self.actual), copy.deepcopy(self.reference)
        self.compare()
        self.assertEqual(self.actual, actual)
        self.assertEqual(self.reference, reference)
        proof = screen.load(self.folder / "generated-metadata-proof.json")
        self.assertEqual(
            proof["UTC_window_ns"], [1700000010_000000000, 1700000012_000000000]
        )
        self.assertEqual(
            proof["native_QPC_ns"], [9_000_000_000_000_000, 9_000_002_000_000_000]
        )
        self.assertNotEqual(proof["UTC_window_ns"][0], proof["native_QPC_ns"][0])
        self.assertEqual(
            proof["raw_header"], actual["sdist"][screen.GENERATED_PYPROJECT]
        )

    def test_time_outside_actual_process_window_is_fatal(self):
        member = self.actual["sdist"][screen.GENERATED_PYPROJECT]
        member.update(mtime=1700000013.0, pax_headers={"mtime": "1700000013.0"})
        with self.assertRaisesRegex(RuntimeError, "outside actual UV UTC lifetime"):
            self.compare()

    def test_inconsistent_pax_even_below_float_precision_is_fatal(self):
        self.actual["sdist"][screen.GENERATED_PYPROJECT]["pax_headers"]["mtime"] = (
            "1700000010.250000001"
        )
        with self.assertRaisesRegex(RuntimeError, "PAX/parser mtime differs"):
            self.compare()

    def test_additional_pax_key_is_not_a_waiver(self):
        self.actual["sdist"][screen.GENERATED_PYPROJECT]["pax_headers"]["atime"] = (
            "1700000010.25"
        )
        with self.assertRaisesRegex(RuntimeError, "PAX/finite mtime"):
            self.compare()

    def test_nonfinite_mtime_is_fatal(self):
        self.actual["sdist"][screen.GENERATED_PYPROJECT].update(
            mtime=float("inf"),
            pax_headers={"mtime": "Infinity"},
        )
        with self.assertRaisesRegex(RuntimeError, "PAX/finite mtime"):
            self.compare()

    def test_non_timestamp_header_change_is_fatal(self):
        self.actual["sdist"][screen.GENERATED_PYPROJECT]["mode"] = 0o755
        with self.assertRaisesRegex(ValueError, "Full frozen archive"):
            self.compare()

    def test_other_member_timestamp_remains_exact(self):
        self.actual["sdist"]["fastapi-0.119.1/README.md"]["mtime"] = 1
        with self.assertRaisesRegex(ValueError, "Full frozen archive"):
            self.compare()

    def test_generated_member_content_remains_exact(self):
        self.actual["sdist"][screen.GENERATED_PYPROJECT]["sha256"] = "changed"
        with self.assertRaisesRegex(ValueError, "Full frozen archive"):
            self.compare()

    def test_wheel_headers_remain_exact(self):
        self.actual["wheel"]["fastapi/__init__.py"]["comment"] = "changed"
        with self.assertRaisesRegex(ValueError, "Full frozen archive"):
            self.compare()

    def test_member_keycount_change_is_fatal(self):
        del self.actual["sdist"]["fastapi-0.119.1/README.md"]
        with self.assertRaisesRegex(ValueError, "archive names differ"):
            self.compare()

    def test_reference_timestamp_is_independently_revalidated(self):
        member = self.reference["sdist"][screen.GENERATED_PYPROJECT]
        member.update(mtime=1700000020.0, pax_headers={"mtime": "1700000020.0"})
        screen.save(self.reference_folder / "full-headers.json", self.reference)
        with self.assertRaisesRegex(RuntimeError, "outside actual UV UTC lifetime"):
            self.compare()

    def test_native_held_identity_mismatch_is_fatal(self):
        native = screen.load(self.folder / "native.json")
        native["pid"] += 1
        screen.save(self.folder / "native.json", native)
        with self.assertRaisesRegex(RuntimeError, "native evidence association"):
            self.compare()

    def test_retained_raw_archive_change_is_fatal(self):
        (self.folder / "artifacts" / "fastapi-0.119.1.tar.gz").write_bytes(b"changed")
        with self.assertRaisesRegex(RuntimeError, "retained raw bytes differ"):
            self.compare()

    def test_ambient_epoch_is_rejected_without_stripping(self):
        inherited = {"SOURCE_DATE_EPOCH": "123", "TEMP": "C:\\scratch"}
        with self.assertRaisesRegex(RuntimeError, "ambient benchmark overrides"):
            screen.environment(Path("C:\\cache"), inherited)
        with self.assertRaisesRegex(
            RuntimeError, "unsupported ambient metadata override"
        ):
            screen.environment_evidence(inherited)
        self.assertEqual(inherited["SOURCE_DATE_EPOCH"], "123")


if __name__ == "__main__":
    unittest.main()
