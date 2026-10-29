import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import git_context


class GitContextTests(unittest.TestCase):
    def test_only_read_only_commands_and_no_environment_dump(self):
        with TemporaryDirectory() as folder:
            executable = Path(folder) / "git.exe"
            executable.write_bytes(b"fixture")
            completed = git_context.subprocess.CompletedProcess([], 0, b"0\n", b"")
            with (
                patch.object(git_context.shutil, "which", return_value=str(executable)),
                patch.object(
                    git_context.subprocess, "run", return_value=completed
                ) as run,
            ):
                result = git_context.collect(Path(folder), 2)
            self.assertEqual(result["status"], "measured")
            self.assertFalse(result["performance_eligible"])
            self.assertEqual(run.call_count, 6)
            self.assertEqual(
                result["commands"][-1]["argv"][-4:],
                ["submodule", "foreach", "--recursive", "exit 0"],
            )
            self.assertNotIn("PATH", json.dumps(result))

    def test_failure_retains_the_original_command_and_stops(self):
        with TemporaryDirectory() as folder:
            executable = Path(folder) / "git.exe"
            executable.write_bytes(b"fixture")
            completed = git_context.subprocess.CompletedProcess([], 3, b"", b"failure")
            with (
                patch.object(git_context.shutil, "which", return_value=str(executable)),
                patch.object(
                    git_context.subprocess, "run", return_value=completed
                ) as run,
            ):
                result = git_context.collect(Path(folder), 3)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["commands"][0]["returncode"], 3)
            self.assertEqual(result["commands"][0]["stderr"], "failure")
            self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
