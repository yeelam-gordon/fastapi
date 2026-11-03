import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from identity_map import exact_mapping
from screen import HERE, load, schedule, source_snapshot, test_command, tiny_outcome


class ScreenContracts(unittest.TestCase):
    def test_source_snapshot_rejects_and_names_changed_bytes(self):
        source = Path("owned-source")
        expected = load(HERE / "source-manifest.json")

        def changed_digest(path):
            name = path.relative_to(source).as_posix()
            return "0" * 64 if name == "fastapi/applications.py" else expected[name]

        with patch("screen.digest", side_effect=changed_digest):
            with self.assertRaisesRegex(AssertionError, r"fastapi/applications\.py"):
                source_snapshot(source)

    def test_schedule_excludes_two_warmups_then_ab_ba(self):
        self.assertEqual(schedule()[:2], [("serial", False), ("parallel", False)])
        self.assertEqual(
            schedule()[2:],
            [
                ("serial", True),
                ("parallel", True),
                ("parallel", True),
                ("serial", True),
            ],
        )

    def test_command_only_worker_options_change(self):
        args = SimpleNamespace(output=Path("evidence"), workers=3)
        folder = Path("same-output")
        serial, parallel = [
            test_command(args, folder, arm) for arm in ("serial", "parallel")
        ]
        self.assertEqual(serial[:-1], parallel[:-3])
        self.assertEqual(
            parallel[-3:], ["3", "--dist=loadgroup", "--max-worker-restart=0"]
        )
        self.assertIn("tests", serial)
        self.assertNotIn("--cov-context", serial)

    def test_group_mapping_rejects_suffix_relabel(self):
        node = "tests/test_path.py::test_text_get"
        self.assertEqual(
            exact_mapping([node], [node + "@shared-main-app"], True),
            {node + "@shared-main-app": node},
        )
        with self.assertRaises(AssertionError):
            exact_mapping([node], [node + "@arbitrary"], True)

    def test_tiny_outcome_rejects_dropped_tests(self):
        tree = ET.ElementTree(
            ET.fromstring(
                '<testsuites><testsuite><testcase name="one"/></testsuite></testsuites>'
            )
        )
        with patch("screen.ET.parse", return_value=tree):
            with self.assertRaises(AssertionError):
                tiny_outcome(Path("unused"))


if __name__ == "__main__":
    unittest.main()
