import contextlib
import io
import unittest
from unittest.mock import patch

import build_screen


class BuildReadiness(unittest.TestCase):
    def test_default_refuses_without_building(self):
        with patch.object(build_screen, "execute") as execute:
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    build_screen.main([])
            self.assertEqual(result.exception.code, 2)
            execute.assert_not_called()

    def test_real_no_isolation_treatment_preserves_complete_build(self):
        context = dict(
            uv="uv", cache="cache", source="source", wheels="wheels", constraint="lock"
        )
        a = build_screen.build_command(context, "A", "artifacts")
        b = build_screen.build_command(context, "B", "artifacts")
        self.assertEqual(b, a + ["--no-build-isolation"])
        self.assertNotIn("--sdist", b)
        self.assertNotIn("--wheel", b)

    def test_both_order_pairs_must_meet_windows_floor(self):
        rows = [
            {"arm": "A", "receipt": {"command_wall": 7}},
            {"arm": "B", "receipt": {"command_wall": 5}},
            {"arm": "B", "receipt": {"command_wall": 6.9}},
            {"arm": "A", "receipt": {"command_wall": 7}},
        ]
        self.assertEqual(
            [p["windows_floor"] for p in build_screen.materiality(rows)], [True, False]
        )


if __name__ == "__main__":
    unittest.main()
