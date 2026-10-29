"""Functional-only proof against the owned pinned checkout; no installed PDM edits."""

import contextlib
import hashlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import threading
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
CHECKOUT = HERE / ".upstream"
WORK = HERE / ".proof-work" / "functional"
sys.path.insert(0, str(CHECKOUT / "src"))
from pdm.backend import sdist  # noqa: E402

BASE = "8c6653726f71afdb2059b44dc9c7706693e95be6"
assert subprocess.check_output(
    ["git", "-C", str(CHECKOUT), "rev-parse", "HEAD"], text=True
).strip() == BASE
stock_source = subprocess.check_output(
    ["git", "-C", str(CHECKOUT), "show", "HEAD:src/pdm/backend/sdist.py"]
)
stock = ModuleType("stock_sdist")
exec(compile(stock_source, "<official-pinned-sdist>", "exec"), stock.__dict__)


class ProbePath:
    def __init__(self, path, read=None, before_open=None):
        self.path = path
        self.read_hook = read
        self.before_open = before_open
        self.requests = []
        self.opened = 0
        self.closed = 0
        self.threads = []

    def __fspath__(self):
        return str(self.path)

    @contextlib.contextmanager
    def open(self, mode):
        if self.before_open:
            self.before_open()
        self.opened += 1
        self.threads.append(threading.current_thread())
        with self.path.open(mode) as source:
            owner = self

            class Reader:
                def read(self, size):
                    owner.requests.append(size)
                    if owner.read_hook:
                        return owner.read_hook(source, size)
                    return source.read(size)

            try:
                yield Reader()
            finally:
                self.closed += 1


def members(path):
    with tarfile.open(path) as archive:
        return [
            (
                info.name, info.type, info.mode, info.uid, info.gid,
                info.uname, info.gname, info.size, info.mtime, info.linkname,
                info.pax_headers,
                archive.extractfile(info).read() if info.isreg() else None,
            )
            for info in archive
        ]


class PrefetchProof(unittest.TestCase):
    def setUp(self):
        self.root = WORK / self._testMethodName
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)

    def file(self, name, data=b"abcd", **kwargs):
        path = self.root / name
        path.write_bytes(data)
        return ProbePath(path, **kwargs)

    def artifact(self, files, module=sdist, directory="out", added=None):
        destination = self.root / directory
        destination.mkdir(exist_ok=True)
        builder = object.__new__(module.SdistBuilder)
        builder._package_metadata = SimpleNamespace(
            as_rfc822=lambda: "Metadata-Version: 2.3\nName: demo\nVersion: 1\n"
        )
        builder._show_add_file = (
            (lambda relative, path: added.append(relative)) if added is not None
            else lambda *args: None
        )
        context = SimpleNamespace(
            dist_dir=destination,
            config=SimpleNamespace(metadata={"name": "demo", "version": "1"}),
        )
        return builder.build_artifact(context, files)

    def test_cap_overcap_zero_and_immutable_differential(self):
        paths = [
            self.file("a-cap", b"a" * 65536),
            self.file("b-large", b"b" * 65537),
            self.file("c-zero", b""),
        ]
        files = [(p.path.name, p) for p in paths]
        result = self.artifact(files)
        reference = self.artifact(
            [(p.path.name, p.path) for p in paths], stock, "stock"
        )
        self.assertEqual(members(result), members(reference))
        self.assertEqual(paths[0].requests, [65536])
        self.assertEqual(paths[2].requests, [0])
        self.assertTrue(all(0 < n <= 16384 for n in paths[1].requests))
        self.assertIs(paths[1].threads[0], threading.main_thread())
        self.assertIsNot(paths[0].threads[0], threading.main_thread())
        for path in paths:
            self.assertEqual((path.opened, path.closed), (1, 1))

    def test_appended_tail_is_ignored(self):
        path = self.file("a", b"abc")

        def append():
            with path.path.open("ab") as output:
                output.write(b"tail" * 20000)

        path.before_open = append
        result = self.artifact([("a", path)])
        self.assertEqual(path.requests, [3])
        with tarfile.open(result) as archive:
            self.assertEqual(archive.extractfile("demo-1/a").read(), b"abc")
        self.assertEqual(path.closed, 1)

    def test_short_payload_keeps_tar_error(self):
        path = self.file("a", read=lambda source, size: source.read(size - 1))
        with self.assertRaisesRegex(OSError, "unexpected end of data"):
            self.artifact([("a", path)])
        self.assertEqual(path.closed, 1)

    def test_later_metadata_and_read_failures_are_ordered(self):
        original = tarfile.TarFile.gettarinfo
        for kind in ("metadata", "read"):
            with self.subTest(kind=kind):
                added = []
                first = self.file("a")
                later = self.file("b")

                def metadata(archive, name=None, *args, **kwargs):
                    if name is later and kind == "metadata":
                        self.assertEqual(added, [])
                        raise FileNotFoundError("later metadata")
                    return original(archive, name, *args, **kwargs)

                def read(source, size):
                    raise PermissionError("later read")

                if kind == "read":
                    later.read_hook = read
                with patch.object(tarfile.TarFile, "gettarinfo", metadata):
                    with self.assertRaisesRegex(
                        FileNotFoundError if kind == "metadata" else PermissionError,
                        "later " + kind,
                    ):
                        self.artifact(
                            [("a", first), ("b", later)], directory=kind, added=added
                        )
                self.assertEqual(added, ["a"])
                self.assertEqual(first.closed, 1)
                self.assertEqual(later.opened, later.closed)

    def test_hardlink_and_symlink_metadata_only(self):
        path = self.file("a")
        hard = self.root / "b"
        os.link(path.path, hard)
        files = [("a", path), ("b", ProbePath(hard))]
        symbolic = self.root / "c"
        try:
            symbolic.symlink_to(path.path.name)
        except OSError as error:
            print("GAP: symlink unavailable:", type(error).__name__, flush=True)
        else:
            files.append(("c", ProbePath(symbolic)))
        result = self.artifact(files)
        reference = self.artifact(
            [(name, probe.path) for name, probe in files], stock, "stock"
        )
        self.assertEqual(members(result), members(reference))
        for _, link in files[1:]:
            self.assertEqual(link.opened, 0)

    def test_writer_failure_cancels_and_joins_running_readers(self):
        started = threading.Event()
        release = threading.Event()
        shutdown = threading.Event()
        later_failed = threading.Event()
        pools = []
        real_pool = sdist.ThreadPoolExecutor

        class Pool(real_pool):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.submitted = 0
                pools.append(self)

            def submit(self, *args, **kwargs):
                self.submitted += 1
                return super().submit(*args, **kwargs)

            def shutdown(self, **kwargs):
                shutdown.set()
                return super().shutdown(**kwargs)

        def blocked(source, size):
            started.set()
            if not release.wait(5):
                raise AssertionError("proof coordination timeout")
            return source.read(size)

        def failing(source, size):
            later_failed.set()
            raise PermissionError("speculative later error")

        paths = [self.file("a"), self.file("b", read=blocked),
                 self.file("c", read=failing)]
        coordination_errors = []

        def unblock():
            try:
                if not shutdown.wait(5):
                    raise AssertionError("shutdown was not reached")
                self.assertEqual(paths[1].closed, 0)
            except BaseException as error:
                coordination_errors.append(error)
            finally:
                release.set()

        coordinator = threading.Thread(target=unblock)
        coordinator.start()

        def writer(archive, info, fileobj=None):
            self.assertTrue(started.wait(5))
            self.assertTrue(later_failed.wait(5))
            raise LookupError("primary writer error")

        try:
            with patch.object(sdist, "ThreadPoolExecutor", Pool), patch.object(
                tarfile.TarFile, "addfile", writer
            ):
                with self.assertRaisesRegex(LookupError, "primary writer error"):
                    self.artifact([(p.path.name, p) for p in paths])
        finally:
            release.set()
            coordinator.join(5)
        self.assertFalse(coordinator.is_alive())
        self.assertEqual(coordination_errors, [])
        self.assertEqual(pools[0].submitted, 3)
        self.assertTrue(all(not thread.is_alive() for thread in pools[0]._threads))
        for path in paths:
            self.assertEqual(path.opened, path.closed)

    def test_hooks_replacement_generated_files_and_fresh_dynamic_metadata(self):
        project = self.root / "project"
        package = project / "pkg"
        package.mkdir(parents=True)
        (project / "pyproject.toml").write_text(
            '[project]\nname="demo"\ndynamic=["version"]\n'
            '[tool.pdm.version]\nsource="file"\npath="pkg/__init__.py"\n'
            '[tool.pdm.build]\nincludes=["pkg"]\n'
        )
        (package / "payload.txt").write_text("original")
        (package / "remove.txt").write_text("remove")
        (project / "pdm_build.py").write_text(
            'def pdm_build_update_files(context, files):\n'
            '    context.ensure_build_dir()\n'
            '    replacement = context.build_dir / "replacement.txt"\n'
            '    replacement.write_text("replaced")\n'
            '    files["pkg/payload.txt"] = replacement\n'
            '    files.pop("pkg/remove.txt")\n'
            '    (context.build_dir / "generated.txt").write_text("generated")\n'
            'def pdm_build_finalize(context, artifact):\n'
            '    (context.root / "finalized").write_text(artifact.name)\n'
        )
        for version in ("1.0", "2.0"):
            (package / "__init__.py").write_text(f'__version__ = "{version}"\n')
            results = []
            for module, label in ((sdist, "patched"), (stock, "stock")):
                with contextlib.redirect_stdout(io.StringIO()):
                    with module.SdistBuilder(project) as builder:
                        results.append(builder.build(str(self.root / label)))
            self.assertEqual(members(results[0]), members(results[1]))
            with tarfile.open(results[0]) as archive:
                prefix = "demo-" + version + "/"
                self.assertEqual(
                    archive.extractfile(prefix + "pkg/payload.txt").read(), b"replaced"
                )
                self.assertIn(prefix + "generated.txt", archive.getnames())
                self.assertNotIn(prefix + "pkg/remove.txt", archive.getnames())
                self.assertIn(
                    ("Version: " + version).encode(),
                    archive.extractfile(prefix + "PKG-INFO").read(),
                )
            self.assertTrue((project / "finalized").exists())

    def test_writer_failure_cancels_unstarted_task(self):
        started = threading.Event()
        release = threading.Event()
        shutdown = threading.Event()
        pools = []
        real_pool = sdist.ThreadPoolExecutor

        class SaturatedPool(real_pool):
            def __init__(self, *, max_workers):
                self.requested_workers = max_workers
                super().__init__(max_workers=1)
                self.futures = []
                pools.append(self)

            def submit(self, *args, **kwargs):
                future = super().submit(*args, **kwargs)
                self.futures.append(future)
                return future

            def shutdown(self, **kwargs):
                # super() cancels the queued third task before joining the second.
                shutdown.set()
                return super().shutdown(**kwargs)

        def blocked(source, size):
            started.set()
            if not release.wait(5):
                raise AssertionError("proof coordination timeout")
            return source.read(size)

        paths = [self.file("a"), self.file("b", read=blocked), self.file("c")]
        real_join = threading.Thread.join

        def join(thread, *args, **kwargs):
            if shutdown.is_set() and thread in pools[0]._threads:
                release.set()
            return real_join(thread, *args, **kwargs)

        def writer(archive, info, fileobj=None):
            self.assertTrue(started.wait(5))
            raise LookupError("writer failure")

        try:
            with patch.object(sdist, "ThreadPoolExecutor", SaturatedPool), \
                    patch.object(tarfile.TarFile, "addfile", writer), \
                    patch.object(threading.Thread, "join", join):
                with self.assertRaisesRegex(LookupError, "writer failure"):
                    self.artifact([(p.path.name, p) for p in paths])
        finally:
            release.set()
        self.assertEqual(pools[0].requested_workers, 3)
        self.assertTrue(pools[0].futures[2].cancelled())
        self.assertEqual(paths[2].opened, 0)
        self.assertTrue(all(not thread.is_alive() for thread in pools[0]._threads))
        self.assertEqual(paths[1].closed, 1)


if __name__ == "__main__":
    os.environ["SOURCE_DATE_EPOCH"] = "1700000000"
    print("base:", BASE)
    print("stock sdist SHA256:", hashlib.sha256(stock_source).hexdigest())
    print("patched source:", sdist.__file__)
    unittest.main(verbosity=2)
