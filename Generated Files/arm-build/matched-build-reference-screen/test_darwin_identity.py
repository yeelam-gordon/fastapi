"""Deterministic mocks only: no child launch or native Darwin API invocation."""

import ctypes
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import darwin_identity as identity


class DarwinIdentityTests(unittest.TestCase):
    def setUp(self):
        self.child = Mock(spec=subprocess.Popen)
        self.child.pid = 4321
        self.child.returncode = None
        self.child.poll.return_value = None
        self.expected = Path(sys.executable).resolve(strict=True)
        self.library = Mock()
        self.library.proc_pidinfo.side_effect = self.write_bsd
        self.library.proc_pidpath.side_effect = self.write_path
        self.load = self.enterContext(
            patch.object(identity, "_load_libproc", return_value=self.library)
        )
        self.enterContext(patch.object(identity.os, "getpid", return_value=1234))
        self.enterContext(
            patch.object(
                identity.time, "time_ns", return_value=1_700_000_000_123_456_789
            )
        )

    def write_bsd(self, pid, flavor, argument, buffer, size):
        self.assertEqual((pid, flavor, argument, size), (4321, 3, 0, 136))
        information = identity.ProcBsdInfo(
            pbi_pid=4321,
            pbi_ppid=1234,
            pbi_start_tvsec=1_699_999_999,
            pbi_start_tvusec=123456,
        )
        ctypes.memmove(buffer, ctypes.byref(information), size)
        return size

    def write_path(self, pid, buffer, size):
        self.assertEqual((pid, size), (4321, 4096))
        encoded = str(self.expected).encode("utf-8")
        ctypes.memmove(buffer, encoded + b"\0", len(encoded) + 1)
        return len(encoded)

    def capture(self):
        return identity.capture_child_identity(self.child, self.expected)

    def test_pinned_abi_layout(self):
        self.assertEqual(ctypes.sizeof(identity.ProcBsdInfo), 136)
        self.assertEqual(ctypes.alignment(identity.ProcBsdInfo), 8)
        self.assertEqual(identity.ProcBsdInfo.pbi_pid.offset, 12)
        self.assertEqual(identity.ProcBsdInfo.pbi_ppid.offset, 16)
        self.assertEqual(identity.ProcBsdInfo.pbi_comm.offset, 48)
        self.assertEqual(identity.ProcBsdInfo.pbi_name.offset, 64)
        self.assertEqual(identity.ProcBsdInfo.pbi_nice.offset, 116)
        self.assertEqual(identity.ProcBsdInfo.pbi_start_tvsec.offset, 120)
        self.assertEqual(identity.ProcBsdInfo.pbi_start_tvusec.offset, 128)

    def test_deterministic_identity_and_unix_interval(self):
        observed = self.capture()
        self.assertEqual(
            observed,
            identity.ChildIdentity(
                4321,
                1234,
                str(self.expected),
                str(self.expected),
                (1_699_999_999_123_456, 1_699_999_999_123_457),
            ),
        )
        self.assertEqual(
            [entry[0] for entry in self.library.mock_calls],
            ["proc_pidinfo", "proc_pidpath", "proc_pidinfo"],
        )
        self.assertEqual(self.child.poll.call_count, 5)
        self.child.wait.assert_not_called()
        self.child.communicate.assert_not_called()

    def test_observed_alias_retained_with_canonical_equality_required(self):
        observed_alias = f"{self.expected.parent}\\SDK-alias\\\\.\\python3"
        other_image = Path(__file__).resolve(strict=True)
        original_resolve = Path.resolve
        resolved_alias = self.expected

        def write_alias(pid, buffer, size):
            self.assertEqual((pid, size), (4321, 4096))
            encoded = observed_alias.encode("utf-8")
            ctypes.memmove(buffer, encoded + b"\0", len(encoded) + 1)
            return len(encoded)

        def resolve(path, *, strict=False):
            self.assertTrue(strict)
            if path == Path(observed_alias):
                return resolved_alias
            return original_resolve(path, strict=strict)

        self.library.proc_pidpath.side_effect = write_alias
        with patch.object(Path, "resolve", autospec=True, side_effect=resolve):
            observed = self.capture()
            self.assertEqual(observed.observed_executable, observed_alias)
            self.assertEqual(observed.executable, str(self.expected))
            self.assertNotEqual(observed.observed_executable, observed.executable)
            resolved_alias = other_image
            with self.assertRaisesRegex(identity.IdentityError, "image mismatch"):
                self.capture()

    def test_bsd_zero_short_error_and_oversize_on_either_read(self):
        for read in (1, 2):
            for returned in (-1, 0, 135, 137):
                with self.subTest(read=read, returned=returned):
                    calls = 0

                    def incomplete(*arguments, returned=returned, read=read):
                        nonlocal calls
                        calls += 1
                        size = self.write_bsd(*arguments)
                        return returned if calls == read else size

                    self.library.proc_pidinfo.side_effect = incomplete
                    with self.assertRaisesRegex(identity.IdentityError, "proc_pidinfo"):
                        self.capture()

    def test_pid_parent_start_and_exiting_rejected_on_either_read(self):
        for read in (1, 2):
            for field, value in (
                ("pbi_pid", 0),
                ("pbi_pid", 9999),
                ("pbi_ppid", 0),
                ("pbi_ppid", 9999),
                ("pbi_start_tvsec", 0),
                ("pbi_start_tvusec", 1_000_000),
                ("pbi_flags", 4),
            ):
                with self.subTest(read=read, field=field, value=value):
                    calls = 0

                    def altered(*arguments, read=read, field=field, value=value):
                        nonlocal calls
                        calls += 1
                        size = self.write_bsd(*arguments)
                        if calls == read:
                            information = ctypes.cast(
                                arguments[3], ctypes.POINTER(identity.ProcBsdInfo)
                            ).contents
                            setattr(information, field, value)
                        return size

                    self.library.proc_pidinfo.side_effect = altered
                    with self.assertRaises(identity.IdentityError):
                        self.capture()

    def test_changed_start_seconds_or_microseconds(self):
        for field in ("pbi_start_tvsec", "pbi_start_tvusec"):
            with self.subTest(field=field):
                calls = 0

                def changed(*arguments, field=field):
                    nonlocal calls
                    calls += 1
                    size = self.write_bsd(*arguments)
                    if calls == 2:
                        information = ctypes.cast(
                            arguments[3], ctypes.POINTER(identity.ProcBsdInfo)
                        ).contents
                        setattr(information, field, getattr(information, field) - 1)
                    return size

                self.library.proc_pidinfo.side_effect = changed
                with self.assertRaisesRegex(identity.IdentityError, "start changed"):
                    self.capture()

    def test_future_or_unrepresentably_large_birth(self):
        for seconds in (1_700_000_001, 2**64 - 1):
            with self.subTest(seconds=seconds):

                def future(*arguments, seconds=seconds):
                    size = self.write_bsd(*arguments)
                    ctypes.cast(
                        arguments[3], ctypes.POINTER(identity.ProcBsdInfo)
                    ).contents.pbi_start_tvsec = seconds
                    return size

                self.library.proc_pidinfo.side_effect = future
                with self.assertRaisesRegex(
                    identity.IdentityError, "later than capture"
                ):
                    self.capture()

    def test_microsecond_boundary_intervals(self):
        for microseconds in (0, 999999):
            with self.subTest(microseconds=microseconds):

                def boundary(*arguments, microseconds=microseconds):
                    size = self.write_bsd(*arguments)
                    ctypes.cast(
                        arguments[3], ctypes.POINTER(identity.ProcBsdInfo)
                    ).contents.pbi_start_tvusec = microseconds
                    return size

                self.library.proc_pidinfo.side_effect = boundary
                lower = 1_699_999_999_000_000 + microseconds
                self.assertEqual(
                    self.capture().start_unix_interval_us, (lower, lower + 1)
                )

    def test_exits_before_or_during_each_capture_stage(self):
        for stage in range(5):
            with self.subTest(stage=stage):
                self.child.poll.side_effect = [None] * stage + [0]
                self.library.reset_mock()
                with self.assertRaisesRegex(identity.IdentityError, "child exited"):
                    self.capture()
                self.assertEqual(self.child.poll.call_count, stage + 1)
                if stage == 0:
                    self.library.proc_pidinfo.assert_not_called()
                self.child.poll.reset_mock()

    def test_already_reaped_child(self):
        self.child.returncode = 0
        with self.assertRaisesRegex(identity.IdentityError, "child exited"):
            self.capture()
        self.load.assert_not_called()

    def test_invalid_child_and_pid(self):
        with self.assertRaisesRegex(identity.IdentityError, "Popen"):
            identity.capture_child_identity(object(), self.expected)
        for pid in (0, -1, True, 2**31, 1234):
            with self.subTest(pid=pid):
                self.child.pid = pid
                with self.assertRaises(identity.IdentityError):
                    self.capture()
        self.load.assert_not_called()

    def test_child_pid_changes_during_capture(self):
        def changed(*arguments):
            size = self.write_bsd(*arguments)
            self.child.pid = 5432
            return size

        self.library.proc_pidinfo.side_effect = changed
        with self.assertRaisesRegex(identity.IdentityError, "child exited or changed"):
            self.capture()
        self.library.proc_pidpath.assert_not_called()

    def test_expected_image_missing_directory_or_not_executable(self):
        with self.assertRaises(FileNotFoundError):
            identity.capture_child_identity(
                self.child, Path(__file__).with_name("nonexistent-image")
            )
        with self.assertRaisesRegex(identity.IdentityError, "executable file"):
            identity.capture_child_identity(self.child, Path(__file__).parent)
        with (
            patch.object(identity.os, "access", return_value=False),
            self.assertRaisesRegex(identity.IdentityError, "executable file"),
        ):
            self.capture()
        self.load.assert_not_called()

    def test_wrong_existing_image(self):
        self.expected = Path(__file__).resolve(strict=True)
        with self.assertRaisesRegex(identity.IdentityError, "image mismatch"):
            identity.capture_child_identity(self.child, sys.executable)

    def test_image_return_length_errors(self):
        for length in (-1, 0, 4096, 4097):
            with self.subTest(length=length):
                self.library.proc_pidpath.side_effect = None
                self.library.proc_pidpath.return_value = length
                with self.assertRaisesRegex(identity.IdentityError, "length"):
                    self.capture()

    def test_native_call_exceptions_fail_closed(self):
        for function in (self.library.proc_pidinfo, self.library.proc_pidpath):
            with self.subTest(function=function):
                original = function.side_effect
                function.side_effect = OSError("mock native error")
                with self.assertRaisesRegex(OSError, "mock native error"):
                    self.capture()
                function.side_effect = original

    def test_strict_image_bytes_and_existence(self):
        for raw, length, error in (
            (b"\xff\0", 1, UnicodeDecodeError),
            (b"abc", 3, identity.IdentityError),
            (b"a\0b\0", 3, identity.IdentityError),
            (b"abc\0", 2, identity.IdentityError),
            (b"relative\0", 8, identity.IdentityError),
            (
                str(self.expected.with_name("nonexistent-image")).encode() + b"\0",
                len(str(self.expected.with_name("nonexistent-image")).encode()),
                FileNotFoundError,
            ),
        ):
            with self.subTest(raw=raw):

                def malformed(pid, buffer, size, raw=raw, length=length):
                    ctypes.memmove(buffer, raw, len(raw))
                    return length

                self.library.proc_pidpath.side_effect = malformed
                with self.assertRaises(error):
                    self.capture()

    def test_native_loader_guard(self):
        with (
            patch.object(identity.sys, "platform", "win32"),
            patch.object(identity.ctypes, "CDLL") as loader,
        ):
            # Call the original function, not the capture test's loader mock.
            with self.assertRaisesRegex(identity.IdentityError, "requires Darwin"):
                ORIGINAL_LOAD_LIBPROC()
            loader.assert_not_called()

    def test_native_signatures_without_native_load(self):
        with (
            patch.object(identity.sys, "platform", "darwin"),
            patch.object(identity.ctypes, "CDLL", return_value=self.library) as loader,
        ):
            self.assertIs(ORIGINAL_LOAD_LIBPROC(), self.library)
            loader.assert_called_once_with("/usr/lib/libproc.dylib", use_errno=True)
        self.assertEqual(
            self.library.proc_pidinfo.argtypes,
            [
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint64,
                ctypes.c_void_p,
                ctypes.c_int,
            ],
        )
        self.assertIs(self.library.proc_pidinfo.restype, ctypes.c_int)
        self.assertEqual(
            self.library.proc_pidpath.argtypes,
            [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32],
        )
        self.assertIs(self.library.proc_pidpath.restype, ctypes.c_int)


ORIGINAL_LOAD_LIBPROC = identity._load_libproc


if __name__ == "__main__":
    unittest.main()
