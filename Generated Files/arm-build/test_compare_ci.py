"""Stdlib synthetic-report tests; fixture directories stay beside this file."""

import base64
import copy
import hashlib
import io
import json
import shutil
import tarfile
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

import compare_ci

MANIFEST = {
    "demo-1-py3-none-any.whl": {"demo.py": "a" * 64},
    "demo-1.tar.gz": {"demo.py": "0:" + "a" * 64},
}


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / (".compare-ci-test-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.windows = self.root / "windows"
        self.macos = self.root / "macos"
        self.fixture(self.windows, "win-arm64", 10, 5)
        self.fixture(self.macos, "macosx-15.0-arm64", 8, 4)

    def fixture(self, root, platform, baseline, candidate):
        ci = root / "ci"
        (ci / "artifacts").mkdir(parents=True)
        report = {
            "status": "passed",
            "metadata": {
                "git_sha": "b" * 40,
                "python": "3.13.2 (build text)",
                "uv": "uv 0.6.1 (different platform build hash)",
                "machine": "ARM64" if platform.startswith("win") else "arm64",
                "interpreter_platform": platform,
                "platform": platform,
                "cpu": {"logical_count": 12},
                "build_system": {"build-backend": "pdm.backend"},
                "installed_versions": {"pdm-backend": "2.4.3"},
            },
            "commands": [],
            "artifacts": [],
        }
        for phase in ["prepare-baseline", "prepare-candidate"] + [
            f"repeat-{index:02d}-{variant}"
            for index in range(1, 6)
            for variant in ("baseline", "candidate")
        ]:
            variant = phase.split("-")[-1]
            argv = [
                "uv",
                "build",
                "source",
                "--out-dir",
                phase,
                "--offline",
            ]
            if variant == "candidate":
                argv.append("--no-build-isolation")
            report["commands"].append(
                {
                    "phase": phase,
                    "argv": argv,
                    "returncode": 0,
                    "wall_seconds": baseline if variant == "baseline" else candidate,
                }
            )
            relative = f"artifacts/{phase}.manifest.json"
            (ci / "artifacts" / f"{phase}.manifest.json").write_text(
                json.dumps(MANIFEST), encoding="utf-8"
            )
            report["artifacts"].append(
                {
                    "phase": phase,
                    "variant": variant,
                    "measured": phase.startswith("repeat-"),
                    "equivalent": True,
                    "manifest": relative,
                    "archives": {
                        name: {"sha256": "c" * 64, "bytes": 1} for name in MANIFEST
                    },
                }
            )
        self.write(root, report)
        bootstrap = root / "bootstrap"
        bootstrap.mkdir()
        (bootstrap / "smoke.json").write_text(
            json.dumps(
                {
                    "status": "passed",
                    "commands": [
                        {"phase": phase, "returncode": 0, "seconds": 1}
                        for phase in (
                            "smoke-dependencies",
                            "install-artifact",
                            "artifact-smoke",
                        )
                    ],
                }
            ),
            encoding="utf-8",
        )

    def write(self, root, report):
        (root / "ci" / "report.json").write_text(json.dumps(report), encoding="utf-8")

    def mutate(self, root, change):
        path = root / "ci" / "report.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        change(report)
        self.write(root, report)

    def compare(self):
        return compare_ci.compare(self.windows, self.macos)

    def test_ratios_ranges_and_unknown_archives(self):
        result = self.compare()
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(
            result["windows_over_macos_build_only_medians"]["baseline"], 1.25
        )
        self.assertEqual(result["windows"]["local_isolation"]["fraction_saved"], 0.5)
        self.assertEqual(
            result["windows"]["build_only"]["candidate"]["range_seconds"],
            {"min": 5, "max": 5},
        )
        self.assertEqual(result["windows"]["bootstrap"]["status"], "unknown")
        self.assertEqual(result["windows_le_macos_goal"]["candidate"], "unknown")
        report = self.windows / "ci" / "report.json"
        self.assertEqual(
            result["inputs"]["windows"][0]["sha256"],
            hashlib.sha256(report.read_bytes()).hexdigest(),
        )

    def test_mismatch_and_failed_samples(self):
        original = json.loads((self.windows / "ci" / "report.json").read_text())
        changes = [
            lambda r: r.update(status="failed"),
            lambda r: r["metadata"].update(git_sha="d" * 40),
            lambda r: r["metadata"].update(python="3.13.3 (build)"),
            lambda r: r["metadata"].update(uv="uv 0.6.2"),
            lambda r: r["metadata"]["installed_versions"].update(
                {"pdm-backend": "2.4.4"}
            ),
            lambda r: r["metadata"].update(interpreter_platform="win-amd64"),
            lambda r: r["commands"][-1].update(returncode=1),
            lambda r: r["commands"][-1].update(wall_seconds=float("nan")),
            lambda r: r["commands"][-1]["argv"].remove("--offline"),
            lambda r: r["commands"].pop(),
            lambda r: r["artifacts"].pop(),
            lambda r: r["artifacts"][-1].update(equivalent=False),
            lambda r: r["artifacts"][-1].update(manifest="../outside.json"),
        ]
        for change in changes:
            with self.subTest(change=change):
                self.write(self.windows, copy.deepcopy(original))
                self.mutate(self.windows, change)
                self.assertEqual(self.compare()["status"], "failed")

    def test_ambiguous_report(self):
        (self.windows / "report.json").write_text("{}")
        self.assertIn("exactly one", self.compare()["error"])

    def test_native_macos_universal2_and_rosetta(self):
        self.mutate(
            self.macos,
            lambda r: r["metadata"].update(
                interpreter_platform="macosx-10.13-universal2", machine="arm64"
            ),
        )
        self.assertEqual(self.compare()["status"], "unknown")
        self.mutate(self.macos, lambda r: r["metadata"].update(machine="x86_64"))
        self.assertEqual(self.compare()["status"], "failed")

    def test_local_manifest_mismatch(self):
        path = self.windows / "ci" / "artifacts" / "repeat-01-candidate.manifest.json"
        manifest = copy.deepcopy(MANIFEST)
        manifest["demo-1-py3-none-any.whl"]["demo.py"] = "d" * 64
        path.write_text(json.dumps(manifest))
        self.assertEqual(self.compare()["status"], "failed")

    def test_cross_os_modes_explicit_but_content_changes_rejected(self):
        manifest = copy.deepcopy(MANIFEST)
        manifest["demo-1.tar.gz"]["demo.py"] = "111:" + "a" * 64
        checked = compare_ci.cross_manifests(MANIFEST, manifest)
        self.assertFalse(checked["exact_normalized_equality"])
        self.assertEqual(
            checked["executable_mode_differences"][0]["macos_executable_bits"], "111"
        )
        manifest["demo-1.tar.gz"]["demo.py"] = "111:" + "d" * 64
        with self.assertRaises(compare_ci.ComparisonError):
            compare_ci.cross_manifests(MANIFEST, manifest)

    def test_smoke_failure_rejected(self):
        (self.macos / "bootstrap" / "smoke.json").write_text('{"status":"failed"}')
        self.assertEqual(self.compare()["status"], "failed")

    def test_present_reference_uses_archive_verifier(self):
        directory = self.windows / "ci" / "artifacts" / "prepare-baseline"
        directory.mkdir()
        with patch.object(
            compare_ci.benchmark,
            "artifact_manifest",
            side_effect=compare_ci.benchmark.VerificationError("bad RECORD"),
        ) as verifier:
            result = self.compare()
        verifier.assert_called_once_with(directory)
        self.assertEqual(result["status"], "failed")
        self.assertIn("bad RECORD", result["error"])

    def test_real_archives_and_digest_mismatch(self):
        for root in (self.windows, self.macos):
            directory = root / "ci" / "artifacts" / "prepare-baseline"
            directory.mkdir()
            payload = b"print('hello')\n"
            encoded = (
                base64.urlsafe_b64encode(hashlib.sha256(payload).digest())
                .rstrip(b"=")
                .decode()
            )
            record_name = "demo-1.dist-info/RECORD"
            with zipfile.ZipFile(directory / "demo-1-py3-none-any.whl", "w") as archive:
                archive.writestr("demo.py", payload)
                archive.writestr(
                    record_name,
                    f"demo.py,sha256={encoded},{len(payload)}\n{record_name},,\n",
                )
            with tarfile.open(directory / "demo-1.tar.gz", "w:gz") as archive:
                member = tarfile.TarInfo("demo-1/demo.py")
                member.size = len(payload)
                member.mode = 0o644
                archive.addfile(member, io.BytesIO(payload))
            manifest = compare_ci.benchmark.artifact_manifest(directory)
            for path in (root / "ci" / "artifacts").glob("*.manifest.json"):
                path.write_text(json.dumps(manifest), encoding="utf-8")
            hashes = {
                path.name: {
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "bytes": path.stat().st_size,
                }
                for path in directory.iterdir()
            }
            self.mutate(
                root,
                lambda report, hashes=hashes: [
                    row.update(archives=hashes) for row in report["artifacts"]
                ],
            )
        self.assertEqual(self.compare()["status"], "passed")
        self.mutate(
            self.windows,
            lambda report: report["artifacts"][0]["archives"]["demo-1.tar.gz"].update(
                sha256="d" * 64
            ),
        )
        self.assertIn("digest/size mismatch", self.compare()["error"])

    def test_goals_require_verified_archives_and_smoke(self):
        original = compare_ci.load_run

        def verified(*args):
            run, manifest, metadata = original(*args)
            run["raw_reference_archives"]["status"] = "passed"
            return run, manifest, metadata

        with patch.object(compare_ci, "load_run", side_effect=verified):
            result = self.compare()
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["windows_le_macos_goal"]["candidate"], "not-met")
            self.mutate(
                self.windows,
                lambda r: [
                    row.update(
                        wall_seconds=4 if row["phase"].endswith("candidate") else 8
                    )
                    for row in r["commands"]
                ],
            )
            result = self.compare()
            self.assertEqual(result["windows_le_macos_goal"]["candidate"], "met")
            self.assertEqual(
                result["windows_over_macos_build_only_medians"]["candidate"], 1
            )

    def test_cli_writes_new_summary_even_on_rejection(self):
        output = self.root / "summary.json"
        args = [
            "--windows",
            str(self.windows),
            "--macos",
            str(self.macos),
            "--output",
            str(output),
        ]
        self.assertEqual(compare_ci.main(args), 1)
        before = output.read_bytes()
        self.assertEqual(compare_ci.main(args), 1)
        self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
