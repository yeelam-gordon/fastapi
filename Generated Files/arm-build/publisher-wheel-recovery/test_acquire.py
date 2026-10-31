"""Offline synthetic transport tests; fixtures stay under this source directory."""

import copy
import hashlib
import importlib.util
import io
import json
import shutil
import ssl
import unittest
import urllib.error
import urllib.request
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("publisher_acquire", ROOT / "acquire.py")
acquire = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acquire)


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.workspace = ROOT / ("synthetic-" + uuid.uuid4().hex)
        self.workspace.mkdir()
        self.addCleanup(shutil.rmtree, self.workspace)
        self.output = self.workspace / "verified-publisher-wheels"
        self.bodies = [b"not executable publisher data", b"second inert payload"]
        self.items = [
            {
                "filename": filename,
                "url": "https://files.pythonhosted.org/packages/aa/bb/"
                + "c" * 60
                + "/"
                + filename,
                "size": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            }
            for filename, body in zip(
                ("first-1-py3-none-any.whl", "second-1-py3-none-any.whl"), self.bodies
            )
        ]
        self.manifest = {
            "schema": 1,
            "count": 2,
            "total_bytes": sum(map(len, self.bodies)),
            "files": self.items,
        }
        self.raw = json.dumps(self.manifest).encode("ascii")
        self.manifest_path = self.workspace / "publisher-manifest.json"
        self.manifest_path.write_bytes(self.raw)
        patcher = mock.patch.multiple(
            acquire,
            ROOT=self.workspace,
            OUTPUT=self.output,
            MANIFEST=self.manifest_path,
            MANIFEST_SHA256=hashlib.sha256(self.raw).hexdigest(),
            COUNT=2,
            TOTAL=self.manifest["total_bytes"],
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def response(self, index, body=None, status=200):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.status = status
        response.geturl.return_value = self.items[index]["url"]
        response.read.return_value = self.bodies[index] if body is None else body
        return response

    def run_acquire(self, responses):
        opener = mock.Mock()
        opener.open.side_effect = responses
        # All acquisition tests replace the transport, not verification or writes.
        with (
            mock.patch.object(acquire, "publisher_opener", return_value=opener),
            redirect_stdout(io.StringIO()),
        ):
            code = acquire.acquire()
        receipt = json.loads((self.output / acquire.RECEIPT).read_text("ascii"))
        return code, receipt, opener

    def assert_artifact(self, names):
        self.assertEqual(
            {path.name for path in self.output.iterdir()}, set(names) | {"receipt.json"}
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(acquire.check_output(), 0)

    def assert_manifest_rejected(self, manifest):
        raw = json.dumps(manifest).encode("ascii")
        # Exercise semantic validation independently of the immutable digest gate.
        with (
            mock.patch.object(
                acquire, "MANIFEST_SHA256", hashlib.sha256(raw).hexdigest()
            ),
            self.assertRaises(acquire.Rejected),
        ):
            acquire.validate_manifest(raw)

    def test_valid_manifest_bytes_and_no_package_execution(self):
        with (
            mock.patch(
                "builtins.exec", side_effect=AssertionError("execution forbidden")
            ),
            mock.patch(
                "builtins.__import__",
                side_effect=AssertionError("package import forbidden"),
            ),
        ):
            code, receipt, opener = self.run_acquire(
                [self.response(0), self.response(1)]
            )
        self.assertEqual(code, 0)
        self.assertEqual(receipt["status"], "VERIFIED")
        self.assertEqual(opener.open.call_count, 2)
        self.assertEqual(
            (self.output / self.items[0]["filename"]).read_bytes(), self.bodies[0]
        )
        self.assert_artifact([item["filename"] for item in self.items])

    def test_manifest_digest_mutation_stops_before_transport(self):
        self.manifest_path.write_bytes(self.raw + b" ")
        with (
            mock.patch.object(acquire, "publisher_opener") as opener,
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(acquire.acquire(), 1)
        opener.assert_not_called()
        receipt = json.loads((self.output / "receipt.json").read_text("ascii"))
        self.assertEqual(
            receipt["failure"],
            {"stage": "manifest", "file": None, "category": "manifest"},
        )
        self.manifest_path.write_bytes(self.raw)
        self.assert_artifact([])

    def test_wrong_filename_and_path_escape(self):
        wrong = copy.deepcopy(self.manifest)
        wrong["files"][0]["filename"] = "../escape.whl"
        self.assert_manifest_rejected(wrong)
        wrong["files"][0]["filename"] = "unicode-\u00e9.whl"
        self.assert_manifest_rejected(wrong)
        wrong["files"][0]["filename"] = "different.whl"
        self.assert_manifest_rejected(wrong)

    def test_duplicate_filename(self):
        wrong = copy.deepcopy(self.manifest)
        wrong["files"][1] = wrong["files"][0]
        self.assert_manifest_rejected(wrong)

    def test_manifest_count_total_size_and_hash_constraints(self):
        for key, value in (("count", 3), ("total_bytes", 1)):
            wrong = copy.deepcopy(self.manifest)
            wrong[key] = value
            self.assert_manifest_rejected(wrong)
        for key, value in (("size", True), ("size", 0), ("sha256", "bad")):
            wrong = copy.deepcopy(self.manifest)
            wrong["files"][0][key] = value
            self.assert_manifest_rejected(wrong)

    def test_unapproved_url_forms(self):
        for url in (
            self.items[0]["url"].replace("https:", "http:"),
            self.items[0]["url"].replace("files.pythonhosted.org", "evil.example"),
            self.items[0]["url"].replace(
                "files.pythonhosted.org", "user@files.pythonhosted.org"
            ),
            self.items[0]["url"] + "?secret=value",
            self.items[0]["url"] + "#fragment",
        ):
            wrong = copy.deepcopy(self.manifest)
            wrong["files"][0]["url"] = url
            self.assert_manifest_rejected(wrong)

    def test_redirect_rejects_http_and_foreign_host_before_follow(self):
        handler = acquire.PublisherRedirect()
        request = urllib.request.Request(self.items[0]["url"])
        for url in (
            self.items[0]["url"].replace("https:", "http:"),
            self.items[0]["url"].replace("files.pythonhosted.org", "evil.example"),
        ):
            with self.assertRaises(acquire.Rejected) as rejected:
                handler.redirect_request(request, None, 302, "redirect", {}, url)
            self.assertEqual(rejected.exception.category, "redirect")
        allowed = self.items[0]["url"].replace("/aa/bb/", "/dd/ee/")
        self.assertEqual(
            handler.redirect_request(
                request, None, 302, "redirect", {}, allowed
            ).full_url,
            allowed,
        )

    def test_short_response_retains_only_receipt(self):
        code, receipt, opener = self.run_acquire([self.response(0, b"short")])
        self.assertEqual(code, 1)
        self.assertEqual(receipt["failure"]["category"], "size")
        self.assertEqual(opener.open.call_count, 1)
        self.assert_artifact([])

    def test_oversized_response_has_bounded_read(self):
        response = self.response(0, self.bodies[0] + b"x")
        code, receipt, opener = self.run_acquire([response])
        response.read.assert_called_once_with(self.items[0]["size"] + 1)
        self.assertEqual(
            (code, receipt["failure"]["category"], opener.open.call_count),
            (1, "size", 1),
        )
        self.assert_artifact([])

    def test_same_size_corruption_after_verified_prefix(self):
        response = self.response(1, b"x" * self.items[1]["size"])
        code, receipt, opener = self.run_acquire([self.response(0), response])
        self.assertEqual(
            (code, receipt["status"], opener.open.call_count), (1, "FAILED", 2)
        )
        self.assertEqual(receipt["verified"], [acquire.verified_entry(self.items[0])])
        self.assertEqual(
            receipt["failure"],
            {
                "stage": "verify",
                "file": self.items[1]["filename"],
                "category": "sha256",
            },
        )
        self.assert_artifact([self.items[0]["filename"]])

    def test_transport_first_failure_no_retry_or_exception_export(self):
        code, receipt, opener = self.run_acquire(
            [urllib.error.URLError("PRIVATE raw error path/token")]
        )
        self.assertEqual((code, opener.open.call_count), (1, 1))
        self.assertEqual(
            receipt["failure"],
            {
                "stage": "transfer",
                "file": self.items[0]["filename"],
                "category": "transport",
            },
        )
        self.assertNotIn("PRIVATE", json.dumps(receipt))
        self.assert_artifact([])

    def test_http_status_failure(self):
        code, receipt, opener = self.run_acquire([self.response(0, status=500)])
        self.assertEqual(
            (code, receipt["failure"]["category"], opener.open.call_count),
            (1, "http", 1),
        )
        self.assert_artifact([])

    def test_output_must_be_absent_and_cannot_escape(self):
        self.output.mkdir()
        sentinel = self.output / "sentinel"
        sentinel.write_bytes(b"untouched")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(acquire.acquire(), 1)
        self.assertEqual(sentinel.read_bytes(), b"untouched")
        with (
            mock.patch.object(acquire, "OUTPUT", self.workspace.parent / "escape"),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(acquire.acquire(), 1)

    def test_artifact_audit_rejects_extra_member_and_tampered_receipt(self):
        self.run_acquire([self.response(0), self.response(1)])
        extra = self.output / "raw.log"
        extra.write_bytes(b"not allowed")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(acquire.check_output(), 1)
        extra.unlink()
        receipt = self.output / "receipt.json"
        data = json.loads(receipt.read_text("ascii"))
        data["raw_error"] = "not allowed"
        receipt.write_text(json.dumps(data), encoding="ascii")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(acquire.check_output(), 1)

    def test_acquisition_membership_failure_cannot_leave_success_receipt(self):
        response = self.response(0)

        def unexpected_member(request, timeout):
            (self.output / "raw.log").write_bytes(b"not an allowed artifact")
            return (
                response
                if request.full_url == self.items[0]["url"]
                else self.response(1)
            )

        code, receipt, opener = self.run_acquire(unexpected_member)
        self.assertEqual(
            (code, receipt["status"], opener.open.call_count), (1, "FAILED", 2)
        )
        self.assertEqual(
            receipt["failure"],
            {"stage": "membership", "file": None, "category": "membership"},
        )
        with redirect_stdout(io.StringIO()):
            self.assertEqual(acquire.check_output(), 1)

    def test_default_tls_context_and_no_proxy_configuration(self):
        real_context = ssl.create_default_context()
        with (
            mock.patch.object(
                acquire.ssl, "create_default_context", return_value=real_context
            ) as context_factory,
            mock.patch.object(acquire.urllib.request, "build_opener") as build,
        ):
            acquire.publisher_opener()
        context_factory.assert_called_once_with()
        handlers = build.call_args.args
        self.assertEqual(handlers[0].proxies, {})
        self.assertIs(handlers[1]._context, real_context)
        self.assertEqual(real_context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(real_context.check_hostname)
        real_context.check_hostname = False
        with (
            mock.patch.object(
                acquire.ssl, "create_default_context", return_value=real_context
            ),
            self.assertRaises(acquire.Rejected),
        ):
            acquire.publisher_opener()

    def test_original_manifest_is_accepted_without_network(self):
        # The production immutable manifest also traverses the actual validator.
        production_raw = (ROOT / "publisher-manifest.json").read_bytes()
        with mock.patch.multiple(
            acquire,
            MANIFEST_SHA256="cc9bf397aeaeba8a68fceffb94135b8a39c1d7fe6dc88d2b6a6dc17ad04b5c70",
            COUNT=14,
            TOTAL=2266989,
        ):
            self.assertEqual(len(acquire.validate_manifest(production_raw)), 14)


if __name__ == "__main__":
    unittest.main()
