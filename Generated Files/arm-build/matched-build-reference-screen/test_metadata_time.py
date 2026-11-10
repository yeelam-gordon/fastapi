"""Source arithmetic tests only; no process launch or native timestamp capture."""

import unittest
from copy import deepcopy

from metadata_time import utc_window_ns


class MetadataTimeTests(unittest.TestCase):
    def test_windows_matches_inherited_formula_independent_of_native_origin(self):
        process = {"birth_filetime": 133444736001234567}
        for start in (-1234, 9_000_000_000_000_000):
            with self.subTest(start=start):
                self.assertEqual(
                    utc_window_ns(process, start, start + 321, platform="win32"),
                    (1_700_000_000_123_456_700, 1_700_000_000_123_457_021),
                )

    def test_darwin_retains_microsecond_quantization_not_native_epoch(self):
        process = {
            "start_unix_interval_us": [1_700_000_000_123_456, 1_700_000_000_123_457]
        }
        original = deepcopy(process)
        for start in (-1234, 9_000_000_000_000_000):
            with self.subTest(start=start):
                lower, upper = utc_window_ns(
                    process, start, start + 321, platform="darwin"
                )
                self.assertEqual(lower, 1_700_000_000_123_456_000)
                self.assertEqual(upper, 1_700_000_000_123_457_320)
                self.assertEqual(upper - lower, 999 + 321)
        self.assertEqual(process, original)

    def test_invalid_native_clocks_and_duration_fail_closed(self):
        process = {"start_unix_interval_us": [10, 11]}
        for start, end in (
            (False, 1),
            (0, True),
            (0.0, 1),
            (0, float("inf")),
            (0, 0),
            (1, 0),
            (0, 30_000_000_001),
        ):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                utc_window_ns(process, start, end, platform="darwin")
        self.assertEqual(
            utc_window_ns(process, 0, 30_000_000_000, platform="darwin"),
            (10_000, 30_000_010_999),
        )

    def test_malformed_or_mixed_birth_schemas_fail_closed(self):
        invalid_darwin = [
            {},
            {"start_unix_interval_us": "10,11"},
            {"start_unix_interval_us": [10]},
            {"start_unix_interval_us": [10, 11, 12]},
            {"start_unix_interval_us": [10, 12]},
            {"start_unix_interval_us": [10, 9]},
            {"start_unix_interval_us": [0, 1]},
            {"start_unix_interval_us": [True, 2]},
            {"start_unix_interval_us": [10, 11.0]},
            {"start_unix_interval_us": [10, 11], "birth_filetime": 123},
        ]
        for process in invalid_darwin:
            with self.subTest(process=process), self.assertRaises(ValueError):
                utc_window_ns(process, 1, 2, platform="darwin")
        for birth in (None, True, 0, 116444736000000000, 2**64, 133444736001234567.0):
            with self.subTest(birth=birth), self.assertRaises(ValueError):
                utc_window_ns({"birth_filetime": birth}, 1, 2, platform="win32")
        with self.assertRaises(ValueError):
            utc_window_ns(
                {
                    "birth_filetime": 133444736001234567,
                    "start_unix_interval_us": [10, 11],
                },
                1,
                2,
                platform="win32",
            )

    def test_unknown_platform_has_no_field_inferred_fallback(self):
        for platform in ("linux", "", None):
            with self.subTest(platform=platform), self.assertRaises(ValueError):
                utc_window_ns(
                    {"birth_filetime": 133444736001234567}, 1, 2, platform=platform
                )


if __name__ == "__main__":
    unittest.main()
