import io
from pathlib import Path
import shutil
import tarfile
import threading
import unittest

from ops import extract_selected, payloads
from selector import select


def archive_with(name="pkg/data.txt", mode=0o644, data=b"payload"):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        info = tarfile.TarInfo(name)
        info.mode, info.size, info.mtime = mode, len(data), 1234567890
        archive.addfile(info, io.BytesIO(data))
    stream.seek(0)
    return tarfile.open(fileobj=stream)


class OpsTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("test-work")
        self.root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_prefetch_fresh_reads_and_order(self):
        files = []
        for n in range(7):
            path = self.root / str(n)
            path.write_bytes(bytes([n]))
            files.append((str(n), path))
        for threaded in (False, True):
            self.assertEqual([(n, data) for n, _, data in payloads(files, threaded)],
                             [(str(n), bytes([n])) for n in range(7)])
        files[0][1].write_bytes(b"changed")
        self.assertEqual(next(payloads(files, True))[2], b"changed")

    def test_failure_and_early_close_join_workers(self):
        path = self.root / "ok"
        path.write_bytes(b"ok")
        for files, fail in [([("missing", self.root / "missing"), ("ok", path)], True),
                            ([("ok", path)] * 8, False)]:
            iterator = payloads(files, True)
            if fail:
                with self.assertRaises(FileNotFoundError):
                    list(iterator)
            else:
                next(iterator)
                iterator.close()
            self.assertFalse(any(t.name.startswith("sdist-read") for t in threading.enumerate()))

    def test_attrs_and_payload(self):
        for attrs in (True, False):
            destination = self.root / str(attrs)
            destination.mkdir()
            with archive_with() as archive:
                extract_selected(archive, destination, ["pkg/data.txt"], attrs)
            result = destination / "pkg" / "data.txt"
            self.assertEqual(result.read_bytes(), b"payload")
            self.assertEqual(int(result.stat().st_mtime) == 1234567890, attrs)

    def test_unsafe_permissions_rejected_before_writes(self):
        for mode in (0o755, 0o600, 0o640, 0o444):
            with archive_with(mode=mode) as archive:
                with self.assertRaises(ValueError):
                    extract_selected(archive, self.root, ["pkg/data.txt"], False)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_path_filter_kept_for_both_cells(self):
        for attrs in (True, False):
            with archive_with(name="../escape") as archive:
                with self.assertRaises(tarfile.OutsideDestinationError):
                    extract_selected(archive, self.root, ["../escape"], attrs)

    def test_invalid_archive_and_selector_guard(self):
        with self.assertRaises(tarfile.ReadError):
            tarfile.open(fileobj=io.BytesIO(b"invalid"))
        config = b'[build-system]\nbuild-backend="other.backend"\n'
        with archive_with(name="pkg/pyproject.toml", data=config) as archive:
            with self.assertRaises(AssertionError):
                select(archive, self.root)
        config = b'[build-system]\nbuild-backend="pdm.backend"\n[tool.pdm.build]\nincludes=["anything"]\n'
        with archive_with(name="pkg/pyproject.toml", data=config) as archive:
            with self.assertRaisesRegex(AssertionError, "Unsupported PDM"):
                select(archive, self.root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
