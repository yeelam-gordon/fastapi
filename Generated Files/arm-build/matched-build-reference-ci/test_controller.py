"""Synthetic metadata vectors only; no cached interpreter or SDK executes."""

import copy
import unittest

import bootstrap
import case_contract
import controller_identity


class ControllerTests(unittest.TestCase):
    def observation(self):
        return {
            "version_info": [3, 13, 17],
            "releaselevel": "final",
            "platform": "win32",
            "abi": "win-arm64",
            "machine": "ARM64",
            "gil": True,
            "gil_disabled": 0,
            "jit": 0,
            "jit_enabled": False,
            "debug": 0,
            "optimization": 0,
            "isolated": 1,
            "dont_write_bytecode": True,
            "pycache_prefix": None,
            "no_site": 1,
            "prefix": r"C:\cache\Python\3.13.17\arm64",
            "base_prefix": r"C:\cache\Python\3.13.17\arm64",
            "executable": r"C:\cache\Python\3.13.17\arm64\python.exe",
        }

    def test_launcher_patch_is_not_the_measured_sdk_patch(self):
        observed = self.observation()
        self.assertIs(
            controller_identity.validate(observed, observed["prefix"], "3.13.17"),
            observed,
        )
        with self.assertRaisesRegex(ValueError, "exact patch"):
            bootstrap.observe_runtime(
                {"platform": "win32", "version_info": [3, 13, 17]}, "", {}, "win32"
            )

    def test_launcher_rejects_non_normal_or_mismatched_runtime_observations(self):
        for field, value in (
            ("gil", False),
            ("jit", 1),
            ("debug", 1),
            ("abi", "win-amd64"),
            ("releaselevel", "candidate"),
            ("version_info", [3, 13, 15]),
            ("prefix", r"C:\elsewhere"),
            ("no_site", 0),
        ):
            observed = copy.deepcopy(self.observation())
            observed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                controller_identity.validate(
                    observed, self.observation()["prefix"], "3.13.17"
                )

    def test_host_selection_binds_one_or_two_jobs_and_recorded_platform(self):
        for selection, platforms in (
            ("both", ("win32", "darwin")),
            ("windows", ("win32",)),
            ("darwin", ("darwin",)),
        ):
            self.assertEqual(case_contract.reference_platforms(selection), platforms)
            for platform in platforms:
                self.assertTrue(
                    case_contract.reference_allocation(
                        {"reference_host": selection, "maximum_jobs": len(platforms)},
                        selection,
                        platform,
                    )
                )
        for review, selection, platform in (
            ({"reference_host": "windows", "maximum_jobs": 2}, "windows", "win32"),
            ({"reference_host": "windows", "maximum_jobs": 1}, "windows", "darwin"),
            ({"reference_host": "both", "maximum_jobs": 2}, "windows", "win32"),
            ({"reference_host": "windows", "maximum_jobs": True}, "windows", "win32"),
        ):
            with (
                self.subTest(selection=selection, platform=platform),
                self.assertRaises(ValueError),
            ):
                case_contract.reference_allocation(review, selection, platform)
        for invalid in ("", "Windows", "all", None):
            with (
                self.subTest(invalid=invalid),
                self.assertRaisesRegex(ValueError, "Invalid reference-host"),
            ):
                case_contract.reference_platforms(invalid)
        self.assertTrue(
            case_contract.reference_allocation({"maximum_jobs": 2}, "both", "darwin")
        )


if __name__ == "__main__":
    unittest.main()
