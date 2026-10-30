"""Regressions against the real hosted Mac package graph, without installing."""

import json
import unittest

import driver


class ReferenceVersionsTests(unittest.TestCase):
    def setUp(self):
        fixture = json.loads((driver.HERE / "macos-reference-graph.json").read_text())
        self.mac = {
            driver.canonical_name(k): v for k, v in fixture["distributions"].items()
        }
        self.expected = driver.constraints(driver.HERE / "reference-constraints.txt")

    def test_real_hosted_mac_graph_has_only_proven_marker_difference(self):
        graph = driver.verify_versions(
            self.mac, self.expected, system="Darwin", reference=True
        )
        self.assertEqual(graph["marker_governed_absences"], ["colorama"])
        self.assertEqual(graph["resolved"], {"uvloop": "0.23.0"})

    def test_windows_missing_colorama_rejected(self):
        installed = self.expected.copy()
        del installed["colorama"]
        with self.assertRaisesRegex(RuntimeError, "missing.*colorama"):
            driver.verify_versions(
                installed, self.expected, system="Windows", reference=True
            )

    def test_mac_present_wrong_colorama_version_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "version drift: colorama"):
            driver.verify_versions(
                {**self.mac, "colorama": "0.4.5"},
                self.expected,
                system="Darwin",
                reference=True,
            )

    def test_other_missing_packages_and_marker_parents_rejected(self):
        for missing in ("anyio", "pytest", "typer"):
            installed = self.mac.copy()
            del installed[missing]
            with (
                self.subTest(missing=missing),
                self.assertRaisesRegex(RuntimeError, "missing"),
            ):
                driver.verify_versions(
                    installed, self.expected, system="Darwin", reference=True
                )

    def test_marker_exception_is_bound_to_verified_parent_versions(self):
        expected, installed = self.expected.copy(), self.mac.copy()
        expected["typer"] = installed["typer"] = "0.27.4"
        with self.assertRaisesRegex(RuntimeError, "missing.*colorama"):
            driver.verify_versions(installed, expected, system="Darwin", reference=True)

    def test_other_present_version_drift_still_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "version drift: anyio"):
            driver.verify_versions(
                {**self.mac, "anyio": "4.15.1"},
                self.expected,
                system="Darwin",
                reference=True,
            )

    def test_unexplained_mac_extra_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "Unexpected reference"):
            driver.verify_versions(
                {**self.mac, "unexplained": "1"},
                self.expected,
                system="Darwin",
                reference=True,
            )

    def test_minimal_explicit_requirements_do_not_inherit_reference_exception(self):
        expected = driver.constraints(driver.HERE / "build-constraints.txt")
        installed = expected.copy()
        del installed["colorama"]
        with self.assertRaisesRegex(RuntimeError, "missing.*colorama"):
            driver.verify_versions(installed, expected, system="Darwin")
