import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import prepare_backend as backend


class BackendPreparationTests(unittest.TestCase):
    def fixture(self):
        raw = b"publisher-pinned fixture"
        digest = hashlib.sha256(raw).hexdigest()
        row = {
            "filename": backend.FILENAME,
            "digests": {"sha256": digest},
            "url": "https://files.pythonhosted.org/packages/fixture.whl",
            "size": len(raw),
        }
        return raw, digest, row

    def test_exact_publisher_bytes_and_exclusive_publication(self):
        raw, digest, row = self.fixture()
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(backend, "WHEEL_SHA256", digest),
            patch.object(
                backend,
                "fetch",
                side_effect=[json.dumps({"urls": [row]}).encode(), raw],
            ) as fetch,
        ):
            output = Path(temporary) / "wheels"
            result = backend.prepare(output)
            self.assertEqual((output / backend.FILENAME).read_bytes(), raw)
            self.assertEqual(result["sha256"], digest)
            with self.assertRaises(FileExistsError):
                backend.prepare(output)
            self.assertEqual(fetch.call_count, 2)

    def test_changed_bytes_fail_before_publication(self):
        raw, digest, row = self.fixture()
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(backend, "WHEEL_SHA256", digest),
            patch.object(
                backend,
                "fetch",
                side_effect=[json.dumps({"urls": [row]}).encode(), raw[:-1] + b"!"],
            ),
        ):
            output = Path(temporary) / "wheels"
            with self.assertRaisesRegex(ValueError, "wheel bytes"):
                backend.prepare(output)
            self.assertFalse(output.exists())

    def test_foreign_publisher_is_not_fetched(self):
        _, digest, row = self.fixture()
        row["url"] = "https://other.invalid/fixture.whl"
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(backend, "WHEEL_SHA256", digest),
            patch.object(
                backend, "fetch", return_value=json.dumps({"urls": [row]}).encode()
            ) as fetch,
        ):
            output = Path(temporary) / "wheels"
            with self.assertRaisesRegex(ValueError, "publisher URL"):
                backend.prepare(output)
            self.assertEqual(fetch.call_count, 1)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
