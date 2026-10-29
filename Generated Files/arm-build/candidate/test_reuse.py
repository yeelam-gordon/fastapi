import json
import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from build import build


class ReuseTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("scratch/reuse-unit").resolve()
        self.source = self.root / "source"
        (self.source / "demo").mkdir(parents=True)
        (self.source / "demo/__init__.py").write_text("VALUE = 1\n")
        (self.source / "pyproject.toml").write_text(
            '[build-system]\nrequires=["pdm-backend==2.5.0"]\n'
            'build-backend="pdm.backend"\n[project]\nname="demo"\nversion="1"\n'
        )
        self.manifest = self.root / "manifest.json"
        self.save_manifest()

    def save_manifest(self):
        self.manifest.write_text(
            json.dumps(
                {
                    p.relative_to(self.source).as_posix(): {"mode": 0o644}
                    for p in self.source.rglob("*")
                    if p.is_file()
                }
            )
        )

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_repeat_unchanged_manifest(self):
        original = self.manifest.read_bytes()
        for workers in (1, 3, 1):
            build(
                self.source,
                self.manifest,
                self.root / f"out-{workers}-{len(list(self.root.iterdir()))}",
                workers,
            )
        self.assertEqual(self.manifest.read_bytes(), original)

    def test_case_alias_hook_rejected_before_execution(self):
        for name in ("PDM_BUILD.PY", "Pdm_Build.py"):
            hook = self.source / name
            hook.write_text(
                "def pdm_build_initialize(context):\n"
                "    (context.dist_dir / 'hook-ran.txt').write_text('executed')\n"
            )
            self.save_manifest()
            output = self.root / "out"
            with self.assertRaisesRegex(ValueError, "hooks"):
                build(self.source, self.manifest, output, 3)
            self.assertFalse(output.exists())
            hook.unlink()

    def test_unknown_backend_state_is_preserved_and_rejected(self):
        state = self.source / ".pdm-build"
        state.mkdir()
        extra = state / "unowned.txt"
        extra.write_text("must not delete")
        with self.assertRaisesRegex(ValueError, "backend state"):
            build(self.source, self.manifest, self.root / "out", 3)
        self.assertEqual(extra.read_text(), "must not delete")

    def test_backend_state_cannot_be_claimed_or_cleanup_disabled(self):
        state = self.source / ".pdm-build"
        state.mkdir()
        sentinel = state / ".gitignore"
        sentinel.write_text("not PDM state")
        with self.assertRaisesRegex(ValueError, "sentinel"):
            build(self.source, self.manifest, self.root / "out", 3)
        sentinel.write_text("*\n")
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "cannot own"):
            build(self.source, self.manifest, self.root / "out", 3)
        with patch.dict(os.environ, {"PDM_BUILD_NO_CLEAN": "1"}):
            with self.assertRaisesRegex(ValueError, "cleanup"):
                build(self.source, self.manifest, self.root / "out", 3)

    def test_backend_junction_rejected_without_touching_target(self):
        import subprocess

        target = self.root / "target"
        target.mkdir()
        (target / "sentinel").write_text("untouched")
        link = self.source / ".pdm-build"
        if os.name == "nt":
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                check=True,
                capture_output=True,
            )
        else:
            link.symlink_to(target, target_is_directory=True)
        try:
            with self.assertRaisesRegex(ValueError, "link|reparse"):
                build(self.source, self.manifest, self.root / "out", 3)
            self.assertEqual((target / "sentinel").read_text(), "untouched")
        finally:
            if os.name == "nt":
                link.rmdir()
            else:
                link.unlink()


if __name__ == "__main__":
    unittest.main(verbosity=2)
