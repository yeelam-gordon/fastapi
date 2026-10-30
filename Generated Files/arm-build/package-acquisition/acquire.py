"""Acquire one exact locked publisher wheel with normal verified HTTPS."""

import argparse
import hashlib
import io
import json
import ssl
import sys
import unittest
import urllib.request
import zipfile
from pathlib import Path

FILENAME = "graphql_core-3.3.1-py3-none-any.whl"
SIZE = 349047
SHA256 = "43ebcd0d9a0662a71b1a2f6562ba863d253057ec11cbc45835b2e2683a0a3770"
URL = (
    "https://files.pythonhosted.org/packages/57/0e/"
    "e51b006267e7fa785abf5d1f86a7d60b84f7f893e3ba4fe23df9be2000cf/" + FILENAME
)


def verify_payload(data, size, digest):
    if len(data) != size:
        raise ValueError(f"Publisher size mismatch: {len(data)} != {size}")
    actual = hashlib.sha256(data).hexdigest()
    if actual != digest:
        raise ValueError(f"Publisher SHA256 mismatch: {actual}")


def acquire(output):
    output.mkdir(parents=True, exist_ok=False)
    receipt = output / "result.json"
    context = ssl.create_default_context()
    if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
        raise RuntimeError("Certificate and hostname verification are required")
    result = {
        "status": "started",
        "url": URL,
        "filename": FILENAME,
        "expected_bytes": SIZE,
        "expected_sha256": SHA256,
        "python": sys.version,
        "certificate_verification": "CERT_REQUIRED",
        "hostname_verification": True,
        "scope": "One publisher download; no package installation or execution",
    }
    receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    try:
        with urllib.request.urlopen(URL, context=context, timeout=45) as response:
            if response.status != 200 or response.url != URL:
                raise ValueError("Unexpected publisher response or redirect")
            data = response.read(SIZE + 1)
        verify_payload(data, SIZE, SHA256)
        with zipfile.ZipFile(io.BytesIO(data)) as wheel:
            bad_member = wheel.testzip()
            if bad_member is not None:
                raise ValueError("Wheel CRC failure: " + bad_member)
        with (output / FILENAME).open("xb") as target:
            target.write(data)
        result.update(
            status="verified", bytes=len(data), sha256=hashlib.sha256(data).hexdigest()
        )
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        result.update(
            status="failed", error_type=type(error).__name__, error=str(error)
        )
        raise
    finally:
        if result["status"] == "started":
            result["status"] = "failed-see-command-traceback"
        receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


class IntegrityTests(unittest.TestCase):
    def test_exact_body_accepted(self):
        body = b"fixture"
        verify_payload(body, len(body), hashlib.sha256(body).hexdigest())

    def test_truncated_body_rejected(self):
        with self.assertRaisesRegex(ValueError, "size mismatch"):
            verify_payload(b"fixture", 8, hashlib.sha256(b"fixture").hexdigest())

    def test_same_size_corruption_rejected(self):
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            verify_payload(b"Fixture", 7, hashlib.sha256(b"fixture").hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        unittest.main(argv=[sys.argv[0]], exit=True)
    elif args.output:
        acquire(args.output)
    else:
        parser.error("--output or --self-test is required")


if __name__ == "__main__":
    main()
