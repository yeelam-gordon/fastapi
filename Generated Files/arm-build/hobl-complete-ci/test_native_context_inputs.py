import unittest
from pathlib import Path
from unittest.mock import patch

import native_context_inputs as native


class NativeInputTests(unittest.TestCase):
    def test_patch_rejects_transport_change_before_using_source(self):
        with self.assertRaisesRegex(RuntimeError, "transport"):
            native.patched({}, b"not the approved patch")

    def test_exact_context_and_newline_preservation(self):
        name = "coverage/collector.py"
        diff = (
            f"--- stock/{name}\n+++ candidate/{name}\n"
            "@@ -1,2 +1,2 @@\n same\n-old\n+new\n"
        ).encode()
        for transport in (diff, diff.replace(b"\n", b"\r\n")):
            with (
                patch.object(native, "PATCH_SHA", native.sha(transport)),
                patch.object(native, "CHANGED", {name}),
            ):
                for eol in (b"\n", b"\r\n"):
                    with self.subTest(eol=eol, transport=transport):
                        raw = eol.join((b"same", b"old", b""))
                        self.assertEqual(
                            native.patched({name: raw}, transport)[name],
                            eol.join((b"same", b"new", b"")),
                        )
                with self.assertRaisesRegex(RuntimeError, "context mismatch"):
                    native.patched({name: b"same\nunexpected\n"}, transport)

    def test_missing_source_fails_without_writing_output(self):
        with (
            patch.object(
                native,
                "load_inputs",
                return_value={"stock": {"coverage/collector.py": "unknown"}},
            ),
            patch.object(Path, "mkdir") as mkdir,
            self.assertRaisesRegex(RuntimeError, "missing/linked"),
        ):
            native.stage(
                Path(__file__).with_name("nonexistent-native-source"),
                Path(__file__).with_name("nonexistent-native-output"),
            )
        mkdir.assert_not_called()

    def test_manifest_rejects_path_escape(self):
        manifest = {
            "revision": native.REVISION,
            "stock": {"../escape": "old"},
            "candidate": {"../escape": "new"},
        }
        with (
            patch.object(native, "CHANGED", {"../escape"}),
            patch.object(native.json, "loads", return_value=manifest),
            patch.object(Path, "read_bytes", return_value=b"{}"),
            self.assertRaisesRegex(RuntimeError, "unsafe source path"),
        ):
            native.load_inputs()
