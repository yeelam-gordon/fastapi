import base64
import csv
import hashlib
import io
import tarfile
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import artifact_gate
import prepare_uv


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.pyproject = b'[project]\nname="fastapi"\ndynamic=["version"]\n'
        (self.source / "pyproject.toml").write_bytes(self.pyproject)
        self.canonical = {"pyproject.toml": artifact_gate.digest(self.pyproject)}

    def make_wheel(self, *, generator="2.5.0", corrupt_record=False):
        path = self.root / "fastapi.whl"
        entries = {
            "fastapi/__init__.py": b"__version__='0.119.1'\n",
            "fastapi.dist-info/WHEEL": f"Generator: pdm-backend ({generator})\n".encode(),
        }
        stream = io.StringIO()
        writer = csv.writer(stream)
        for name, data in entries.items():
            value = (
                base64.urlsafe_b64encode(hashlib.sha256(data).digest())
                .rstrip(b"=")
                .decode()
            )
            writer.writerow(
                [name, "sha256=" + ("wrong" if corrupt_record else value), len(data)]
            )
        writer.writerow(["fastapi.dist-info/RECORD", "", ""])
        entries["fastapi.dist-info/RECORD"] = stream.getvalue().encode()
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
        return path

    def make_sdist(self, *, mode=0o644, extra_metadata=""):
        path = self.root / "fastapi.tar.gz"
        data = (
            '[project]\nname="fastapi"\ndynamic=[]\nversion="0.119.1"\n'
            + extra_metadata
        ).encode()
        with tarfile.open(path, "w:gz") as archive:
            entry = tarfile.TarInfo("fastapi/pyproject.toml")
            entry.mode = mode
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
        return path

    def test_complete_member_gate_includes_generated_metadata_and_modes(self):
        self.make_wheel()
        self.make_sdist()
        baseline = artifact_gate.artifact_set(self.root, self.source, self.canonical)
        self.make_sdist(mode=0o755)
        changed = artifact_gate.artifact_set(self.root, self.source, self.canonical)
        with self.assertRaisesRegex(RuntimeError, "content/mode/type differs"):
            artifact_gate.equivalent(changed, baseline)

    def test_corrupt_record_fails(self):
        wheel = self.make_wheel(corrupt_record=True)
        with self.assertRaisesRegex(RuntimeError, "RECORD mismatch"):
            artifact_gate.archive_members(wheel, self.source, self.canonical)

    def test_wrong_installed_backend_generator_fails(self):
        wheel = self.make_wheel(generator="2.4.0")
        with self.assertRaisesRegex(RuntimeError, "installed backend Generator"):
            artifact_gate.archive_members(wheel, self.source, self.canonical)

    def test_unexpected_sdist_pyproject_change_fails(self):
        archive = self.make_sdist(extra_metadata='description="changed"\n')
        with self.assertRaisesRegex(RuntimeError, "unexpected generated pyproject"):
            artifact_gate.archive_members(archive, self.source, self.canonical)


class UvIdentityTests(unittest.TestCase):
    def exercise(
        self, *, recorded="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", bundled=True
    ):
        executable = Path(__file__).absolute().with_name("uv.exe")
        entry = types.SimpleNamespace(
            name="uv.exe",
            hash=types.SimpleNamespace(mode="sha256", value=recorded),
        )
        distribution = types.SimpleNamespace(
            version="0.13.6",
            files=[entry],
            locate_file=lambda _: (
                executable if bundled else executable.with_name("other.exe")
            ),
        )
        with (
            patch.object(
                prepare_uv.importlib.metadata, "distribution", return_value=distribution
            ),
            patch.object(
                prepare_uv.importlib,
                "import_module",
                return_value=types.SimpleNamespace(find_uv_bin=lambda: str(executable)),
            ),
            patch.object(
                prepare_uv,
                "attest",
                return_value={"sha256": "00" * 32, "executable": str(executable)},
            ),
        ):
            return prepare_uv.installed_identity()

    def test_bundled_record_matches_attested_executable(self):
        self.assertEqual(self.exercise()["distribution_version"], "0.13.6")

    def test_record_mismatch_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "installed distribution RECORD"):
            self.exercise(recorded="wrong")

    def test_global_fallback_binary_is_not_accepted_as_bundled(self):
        with self.assertRaisesRegex(RuntimeError, "installed distribution RECORD"):
            self.exercise(bundled=False)


if __name__ == "__main__":
    unittest.main()
