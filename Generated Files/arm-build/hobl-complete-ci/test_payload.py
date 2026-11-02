import hashlib
import io
import json
import tarfile
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import run_payload as payload


class PayloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.source = root / "source"
        self.output = root / "output"
        self.source.mkdir()
        self.output.mkdir()
        (self.source / "fastapi").mkdir()
        self.original = self.source / "fastapi" / "__init__.py"
        self.original.write_text("__version__ = '0.119.1'\n", encoding="utf-8")
        manifest = {
            "fastapi/__init__.py": hashlib.sha256(
                self.original.read_bytes()
            ).hexdigest()
        }
        self.manifest = root / "manifest.json"
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        dist = self.source / "dist"
        dist.mkdir()
        with zipfile.ZipFile(dist / "fastapi-0.119.1-py3-none-any.whl", "w") as archive:
            archive.writestr("fastapi/__init__.py", self.original.read_bytes())
        with tarfile.open(dist / "fastapi-0.119.1.tar.gz", "w:gz") as archive:
            member = tarfile.TarInfo("fastapi-0.119.1/fastapi/__init__.py")
            data = self.original.read_bytes()
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        self.args = types.SimpleNamespace(
            source=self.source,
            output=self.output,
            manifest=self.manifest,
            python=root / "venv" / "Scripts" / "python.exe",
            loops=1,
            index="https://pypi.org/simple",
            style="windows",
            prep_qualification="test",
        )
        self.identity = types.SimpleNamespace(
            returncode=0,
            stderr="",
            stdout=json.dumps(
                {
                    "machine": "ARM64",
                    "pointer_bits": 64,
                    "fastapi_origin": str(self.original),
                    "packages": {},
                }
            ),
        )

    @staticmethod
    def fake_phase(command, source, env, folder, name):
        (folder / f"{name}.stdout").write_text(
            "================ 2513 passed, 130 skipped in 90s ================\n"
            if name == "test"
            else "build complete\n",
            encoding="utf-8",
        )
        (folder / f"{name}.stderr").write_text("", encoding="utf-8")
        seconds = 2.5 if name == "build" else 90.0
        return {"exitcode": 0, "seconds": seconds, "hobl_rounded_seconds": seconds}

    def exercise(self, side_effect=None):
        with patch.object(payload.subprocess, "run", return_value=self.identity):
            with patch.object(
                payload, "phase", side_effect=side_effect or self.fake_phase
            ) as phases:
                payload.worker(self.args)
                return phases

    def test_windows_runs_complete_work_and_sums_both_phases(self):
        phases = self.exercise()
        self.assertEqual(
            phases.call_args_list[0].args[0], [str(self.args.python), "-m", "build"]
        )
        self.assertEqual(
            phases.call_args_list[1].args[0],
            [str(self.args.python), "-m", "coverage", "run", "-m", "pytest", "tests"],
        )
        result = json.loads((self.output / "result.json").read_bytes())
        self.assertEqual(result["median_scenario_runtime_seconds"], 92.5)
        self.assertFalse(result["under_10_seconds"])
        self.assertEqual(
            result["loops"][0]["outcomes"], {"passed": 2513, "skipped": 130}
        )

    def test_mac_uses_the_canonical_test_script(self):
        self.args.style = "macos"
        phases = self.exercise()
        self.assertEqual(phases.call_args_list[1].args[0], ["bash", "scripts/test.sh"])

    def test_build_failure_never_runs_tests_or_publishes_success(self):
        with self.assertRaisesRegex(RuntimeError, "build failed"):
            self.exercise(lambda *args: {"exitcode": 1})
        self.assertFalse((self.output / "result.json").exists())

    def test_changed_source_is_rejected(self):
        def mutate(*args):
            result = self.fake_phase(*args)
            if args[-1] == "test":
                self.original.write_text("changed\n", encoding="utf-8")
            return result

        with self.assertRaisesRegex(RuntimeError, "canonical source changed"):
            self.exercise(mutate)
        self.assertFalse((self.output / "result.json").exists())

    def test_interpreter_path_does_not_follow_venv_symlink(self):
        wanted = self.args.python
        original_resolve = Path.resolve
        base_python = self.source / "base-python"

        def fake_resolve(path, *args, **kwargs):
            if path == wanted:
                return base_python
            return original_resolve(path, *args, **kwargs)

        self.args.worker = True
        with patch.object(Path, "resolve", fake_resolve):
            with patch.object(payload, "worker") as worker:
                payload.main(self.args)
        self.assertEqual(worker.call_args.args[0].python, wanted.absolute())


if __name__ == "__main__":
    unittest.main()
