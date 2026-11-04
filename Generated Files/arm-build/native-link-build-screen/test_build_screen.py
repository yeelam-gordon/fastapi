import contextlib
import copy
import io
import unittest
from unittest.mock import patch

import build_screen


class NativeLinkReadiness(unittest.TestCase):
    def test_platform_native_modes_keep_both_isolated_and_fully_logged(self):
        for platform, expected in (("win32", "hardlink"), ("darwin", "clone")):
            context = dict(
                uv="uv",
                cache="cache",
                source="source",
                wheels="wheels",
                constraint="lock",
                platform=platform,
            )
            a = build_screen.build_command(context, "A", "artifacts")
            b = build_screen.build_command(context, "B", "artifacts")
            self.assertEqual(a[:-1], b[:-1])
            self.assertEqual(a[-2:], ["--link-mode", "copy"])
            self.assertEqual(b[-2:], ["--link-mode", expected])
            for flag in (
                "--no-build-isolation",
                "--no-build-logs",
                "--sdist",
                "--wheel",
            ):
                self.assertNotIn(flag, b)

    def test_fallback_is_unqualified_not_a_success_claim(self):
        result = build_screen.fallback_evidence(
            "warning: Failed to hardlink files; falling back to full copy.", "hardlink"
        )
        self.assertEqual(result["implementation"], "UNQUALIFIED_FALLBACK_OBSERVED")
        self.assertTrue(result["visible_fallback_lines"])
        self.assertIn(
            "debug-only", build_screen.fallback_evidence("", "clone")["limit"]
        )

    def test_default_refuses(self):
        with (
            patch.object(build_screen, "execute") as execute,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(SystemExit):
                build_screen.main([])
        execute.assert_not_called()

    def test_windows_gate_requires_both_floors_in_each_order(self):
        for times in ((10, 9.5, 8, 10), (3, 2.6, 8, 10), (10, 8, 9.8, 10)):
            rows = [
                {"arm": arm, "receipt": {"command_wall": value}}
                for arm, value in zip(build_screen.SCHEDULE, times)
            ]
            with self.assertRaisesRegex(RuntimeError, "both-pair materiality"):
                build_screen.require_windows_materiality(rows)

    def test_comparison_uses_both_mac_paths_and_both_orders(self):
        def report(platform, times):
            return {
                "platform": platform,
                "cohort": {"GITHUB_RUN_ID": "same"},
                "protocol": {"same": True},
                "status": "COMPLETE",
                "source_preserved": True,
                "affinity_restored": True,
                "implementation_no_visible_fallback": True,
                "rows": [
                    {
                        "arm": arm,
                        "audit": "PASS",
                        "receipt": {
                            "command_wall": value,
                            "returncode": 0,
                            "ownership_established": True,
                            "survivors": False,
                            "cleanup_complete": True,
                            "timed_out": False,
                            "errors": [],
                            "native_start_ns": 1,
                            "native_end_ns": 2,
                        },
                    }
                    for arm, value in zip(build_screen.SCHEDULE, times)
                ],
            }

        win, mac = report("win32", (9, 5, 7, 9)), report("darwin", (6, 4, 8, 8))
        compared = build_screen.compare_reports(win, mac)
        self.assertFalse(compared["orders"][0]["observed_no_slower_than_either"])
        self.assertTrue(compared["orders"][1]["observed_no_slower_than_either"])
        self.assertFalse(compared["observed_no_slower_both_orders"])
        other = copy.deepcopy(mac)
        other["cohort"]["GITHUB_RUN_ID"] = "different"
        with self.assertRaisesRegex(RuntimeError, "One measured cohort"):
            build_screen.compare_reports(win, other)
        other = copy.deepcopy(mac)
        other["source_preserved"] = False
        with self.assertRaisesRegex(RuntimeError, "preservation"):
            build_screen.compare_reports(win, other)
        for failed_order_index in (1, 2):
            rejected = copy.deepcopy(win)
            rejected["rows"][failed_order_index]["receipt"]["command_wall"] = 8.9
            rejected["windows_value_gate"] = True
            rejected["pairs"] = [{"windows_floor": True}, {"windows_floor": True}]
            with self.assertRaisesRegex(RuntimeError, "both-pair materiality"):
                build_screen.compare_reports(rejected, mac)


if __name__ == "__main__":
    unittest.main()
