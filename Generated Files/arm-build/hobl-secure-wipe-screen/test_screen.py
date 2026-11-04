import importlib.util
import marshal
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "secure_wipe_screen", Path(__file__).with_name("screen.py")
)
screen = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(screen)


class ProvenanceContracts(unittest.TestCase):
    def evidence(self, workers):
        return [
            {
                "worker": worker,
                "status": "OBSERVED" if worker == "gw0" else "NOT_IMPORTED",
                "image_sha256": "expected" if worker == "gw0" else None,
                "image_path": str(Path("overlay") / "_ffi.pyd")
                if worker == "gw0"
                else None,
                "dont_write_bytecode": False,
                "pycache_prefix": None,
                "switch_interval": 0.005,
                "gil": True,
            }
            for worker in ["controller", *(f"gw{i}" for i in range(workers))]
        ]

    def test_lazy_crypto_owner_allows_explicit_other_worker_abstention(self):
        for workers in (3, 4):
            with self.subTest(workers=workers):
                result = screen.admit(
                    self.evidence(workers),
                    {"gw0"},
                    "expected",
                    Path("overlay") / "_ffi.pyd",
                    workers,
                )
                self.assertEqual(result["observed_workers"], ["gw0"])

    def test_missing_worker_receipt_cannot_default_to_success(self):
        with self.assertRaises(AssertionError):
            screen.admit(
                self.evidence(4)[:-1],
                {"gw0"},
                "expected",
                Path("overlay") / "_ffi.pyd",
                4,
            )

    def test_crypto_owner_cannot_abstain(self):
        with self.assertRaises(AssertionError):
            screen.admit(
                self.evidence(4),
                {"gw0", "gw1"},
                "expected",
                Path("overlay") / "_ffi.pyd",
                4,
            )

    def test_wrong_sha_or_overlay_rejects_observed_image(self):
        for digest, path in (
            ("wrong", Path("overlay") / "_ffi.pyd"),
            ("expected", Path("other") / "_ffi.pyd"),
        ):
            with (
                self.subTest(digest=digest, path=path),
                self.assertRaises(AssertionError),
            ):
                screen.admit(self.evidence(4), {"gw0"}, digest, path, 4)

    def test_no_observed_image_is_not_a_valid_noop(self):
        rows = self.evidence(3)
        rows[1]["status"] = "NOT_IMPORTED"
        with self.assertRaises(AssertionError):
            screen.admit(rows, set(), "expected", Path("overlay") / "_ffi.pyd", 3)

    def test_measured_schedule_is_exactly_abba_after_two_warmups(self):
        self.assertEqual(
            screen.schedule(),
            [
                ("A", False),
                ("B", False),
                ("A", True),
                ("B", True),
                ("B", True),
                ("A", True),
            ],
        )

    def test_quarantine_rejects_unowned_temp_then_preserves_normal_bytecode(self):
        with TemporaryDirectory(dir=os.environ["HOBL_TEST_ROOT"]) as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            original = source / "test_lazy.py"
            original.write_text("answer = 42\n", encoding="utf-8")
            cache = source / "__pycache__"
            cache.mkdir()
            ordinary = cache / "ordinary.pyc"
            ordinary.write_bytes(b"ordinary cache must stay")
            info = original.stat()
            header = (
                importlib.util.MAGIC_NUMBER
                + b"\0" * 4
                + (int(info.st_mtime) & 0xFFFFFFFF).to_bytes(4, "little")
                + info.st_size.to_bytes(4, "little")
            )
            pending = (
                cache / f"test_lazy.{sys.implementation.cache_tag}-pytest-8.4.2.pyc.123"
            )
            pending.write_bytes(
                header
                + marshal.dumps(compile(original.read_text(), str(original), "exec"))
            )
            manifest = {"test_lazy.py": {"sha256": screen.digest(original)}}
            with self.assertRaises(AssertionError):
                screen.cache_state(source, manifest, set())
            output = root / "evidence"
            output.mkdir()
            result = screen.readiness(source, output, manifest, 1, {"123"})
            self.assertEqual(len(result["moves"]), 1)
            self.assertEqual(result["ordinary_completed_caches_preserved"], 1)
            self.assertEqual(ordinary.read_bytes(), b"ordinary cache must stay")
            self.assertFalse(pending.exists())

    def test_builder_contract_uses_exact_candidate_overlay_root(self):
        output = Path("binding-build")
        proof = {
            "schema": 1,
            "status": "PASS_FUNCTIONAL_PACKAGE",
            "reference_image_sha256": "publisher",
            "candidate_image_sha256": "candidate",
            "sdk_version": "10.0.26100.0",
            "target": "aarch64-pc-windows-msvc",
            "candidate_package_root": str(output / "candidate"),
        }
        self.assertEqual(
            screen.candidate_package(proof, output, "publisher"),
            output / "candidate" / "_argon2_cffi_bindings",
        )
        proof["candidate_package_root"] = str(Path("outside") / "candidate")
        with self.assertRaises(AssertionError):
            screen.candidate_package(proof, output, "publisher")

    def test_existing_builder_evidence_export_includes_all_receipts_not_private_trees(
        self,
    ):
        builder = Path(os.environ["HOBL_BUILDER_EVIDENCE_ROOT"])
        with TemporaryDirectory(dir=os.environ["HOBL_TEST_ROOT"]) as temporary:
            output = Path(temporary) / "export"
            copied = screen.export_builder_evidence(builder, output)
            actual_receipts = {path.name for path in builder.glob("*.receipt.json")}
            self.assertTrue(actual_receipts)
            self.assertTrue(actual_receipts <= copied.keys())
            expected = {
                name for name in screen.BUILDER_EVIDENCE if (builder / name).is_file()
            }
            self.assertEqual(set(copied), expected)
            self.assertEqual(
                {path.name for path in output.iterdir()}, expected | {"manifest.json"}
            )
            for name in copied:
                self.assertEqual(
                    screen.digest(output / name), screen.digest(builder / name)
                )
            self.assertNotIn("developer-env.txt", copied)
            self.assertFalse(any(path.is_dir() for path in output.iterdir()))
            workflow = (
                Path(__file__).resolve().parents[3]
                / ".github"
                / "workflows"
                / "hobl-secure-wipe-screen.yml"
            )
            artifact_paths = {
                line.strip()
                for line in workflow.read_text(encoding="utf-8").splitlines()
                if line.strip().startswith("evidence/")
            }
            for name in copied.keys() | {"manifest.json"}:
                self.assertIn("evidence/builder-evidence/" + name, artifact_paths)
            self.assertFalse(
                any(
                    "binding-build/" in name
                    or "-root/" in name
                    or "developer-env" in name
                    for name in artifact_paths
                )
            )
            for name in (
                "build-plan.json",
                "source-proof.json",
                "library-resolution.json",
                "candidate.stdout.txt",
                "reference.stdout.txt",
                "reference-probe.stdout.txt",
            ):
                self.assertIn(name, copied)

    def test_unreviewed_new_builder_receipt_cannot_be_silently_discarded(self):
        with TemporaryDirectory(dir=os.environ["HOBL_TEST_ROOT"]) as temporary:
            root = Path(temporary)
            builder = root / "builder"
            builder.mkdir()
            (builder / "unexpected.receipt.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(AssertionError):
                screen.export_builder_evidence(builder, root / "export")

    def test_private_payload_archive_failure_stops_before_covered_test(self):
        with TemporaryDirectory(dir=os.environ["HOBL_TEST_ROOT"]) as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            image = root / "_ffi.pyd"
            image.write_bytes(b"fixture image; not native proof")
            context = SimpleNamespace(
                args=SimpleNamespace(uv=Path("uv"), workers=4),
                output=root,
                source=source,
                before={},
                env={},
                images={"A": image},
                result={"rows": []},
                owned_pids=set(),
            )

            def built(*args):
                (root / "01-build.stderr").write_text(
                    "Building source distribution\nBuilding wheel from source distribution\n",
                    encoding="utf-8",
                )
                return 1.0

            with (
                patch.object(screen, "readiness"),
                patch.object(screen, "snapshot", return_value={}),
                patch.object(screen.parallel, "test_command", return_value=["python"]),
                patch.object(screen, "_command", side_effect=built) as command,
                patch.object(
                    screen, "archives", side_effect=AssertionError("invalid archive")
                ),
            ):
                with self.assertRaisesRegex(AssertionError, "invalid archive"):
                    screen.run_payload(context, 1, "A", False)
            self.assertEqual(command.call_count, 1)
            self.assertEqual(command.call_args.args[1], "01-build")
            self.assertEqual(command.call_args.args[4], 60)
            self.assertEqual(context.result["rows"], [])


if __name__ == "__main__":
    unittest.main()
