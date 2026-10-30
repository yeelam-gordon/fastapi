"""Presentation contracts never alter benchmark environments or raw comparison."""

import json

import driver
from guards import raw_equal
from test_reference import Fixture


class HelpPresentationTests(Fixture):
    def test_only_supported_term_setting_changes_in_a_copy(self):
        inherited = {
            "TERM": "xterm-256color",
            "GITHUB_ACTIONS": "true",
            "FORCE_COLOR": "1",
            "PY_COLORS": "1",
            "OTHER": "unchanged",
        }
        before = inherited.copy()
        configured = driver.help_probe_env(inherited)
        self.assertEqual(inherited, before)
        self.assertEqual(configured, {**before, "TERM": "dumb"})

    def test_timed_cli_environment_remains_byte_unchanged(self):
        run = driver.Run(self.root)
        run.source = self.root / "source"
        run.overlay = {"A": self.root / "overlay-A"}
        run.full_env = {
            "TERM": "xterm-256color",
            "GITHUB_ACTIONS": "true",
            "FORCE_COLOR": "1",
        }
        env = run.cli_env("A", "timed-cli", covered=True)
        before = json.dumps(env, sort_keys=True).encode()
        driver.help_probe_env(env)
        self.assertEqual(json.dumps(env, sort_keys=True).encode(), before)
        self.assertEqual(env["TERM"], "xterm-256color")
        self.assertEqual(run.full_env["TERM"], "xterm-256color")
        self.assertIn("PYTEST_CURRENT_TEST", env)

    def test_raw_comparison_rejects_ephemeral_ids_and_genuine_text_change(self):
        prefix = b"\x1b]8;id="
        suffix = b";https://fastapi.tiangolo.com/fastapi-cli/\x1b\\docs\x1b]8;;\x1b\\"
        with self.assertRaises(RuntimeError):
            raw_equal(
                (prefix + b"6941240" + suffix, b""),
                (prefix + b"11370988" + suffix, b""),
            )
        with self.assertRaises(RuntimeError):
            raw_equal(
                (b"Usage: fastapi dev\n", b""), (b"Usage: fastapi changed\n", b"")
            )
