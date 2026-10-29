import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import unittest

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "work" / "test-fixtures"


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FIXTURES.mkdir(parents=True, exist_ok=True)
        cls.payload = FIXTURES / "payload"
        cls.payload.write_bytes(bytes(range(256)) * 3)

    def invoke(self, rows, workers=4):
        return subprocess.run(
            [shutil.which("node"), str(HERE / "writer.cjs")],
            input=json.dumps({"root": str(FIXTURES), "workers": workers, "files": rows}).encode(),
            capture_output=True)

    def row(self, name="package/data.bin", mode=0o644, source=None):
        return {"name": name, "mode": mode, "source": str(source or self.payload)}

    def test_long_unicode_modes_and_payload(self):
        names = ["package/plain", "package/" + "a" * 160 + "/file",
                 "package/日本語/é" + "界" * 120]
        for workers in (4, 8):
            with self.subTest(workers=workers):
                result = self.invoke([self.row(n, 0o755 if i == 1 else 0o644)
                                      for i, n in enumerate(names)], workers)
                self.assertEqual(result.returncode, 0, result.stderr)
                with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:gz") as archive:
                    self.assertEqual(archive.getnames(), names)
                    for i, member in enumerate(archive):
                        self.assertEqual(archive.extractfile(member).read(), self.payload.read_bytes())
                        self.assertEqual(member.mode, 0o755 if i == 1 else 0o644)
                        self.assertEqual((member.uid, member.gid, member.mtime), (0, 0, 0))

    def test_rejected_paths_modes_duplicates_and_sources(self):
        cases = [[self.row(n)] for n in
                 ("../escape", "/absolute", "a/../b", "a\\b", "C:/file", "a//b", "a\nb")]
        cases += [[self.row(mode=0o777)], [self.row(), self.row()],
                  [self.row(source=FIXTURES)], [self.row(source=HERE / "writer.cjs")],
                  [self.row(source=FIXTURES / "missing")]]
        for rows in cases:
            with self.subTest(rows=rows):
                result = self.invoke(rows)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")
                self.assertTrue(result.stderr)

    def test_unsupported_concurrency(self):
        result = self.invoke([self.row()], 16)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")

    def test_empty_payload_and_malformed_request(self):
        empty = FIXTURES / "empty"
        empty.write_bytes(b"")
        result = self.invoke([self.row(source=empty)])
        self.assertEqual(result.returncode, 0, result.stderr)
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:gz") as archive:
            self.assertEqual(archive.extractfile("package/data.bin").read(), b"")
        result = subprocess.run(
            [shutil.which("node"), str(HERE / "writer.cjs")],
            input=b"{not JSON", capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")


if __name__ == "__main__":
    unittest.main()
