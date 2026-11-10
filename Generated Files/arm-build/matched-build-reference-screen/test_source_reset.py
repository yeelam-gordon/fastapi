"""Owned fresh-file fixtures and synthetic deletion errors only; no held locks."""

import builtins
import dataclasses
import errno
import shutil
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import screen


class SourceResetTests(unittest.TestCase):
    def setUp(self):
        self.root = screen.HERE / ("test-work-reset-" + uuid.uuid4().hex)
        self.output = self.root / "output"
        self.previous = self.output / "build-00-C"
        self.folder = self.output / "build-01-D"
        self.live = self.output / "canonical-source"
        self.file = self.live / "docs" / "pt" / "docs" / "index.md"
        self.file.parent.mkdir(parents=True)
        self.file.write_bytes(b"ordinary owned fixture")
        self.previous.mkdir()
        self.folder.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.receipt = screen.owned_process.Receipt(
            0,
            False,
            0.1,
            0.01,
            True,
            False,
            True,
            (),
        )
        self.row = {"folder": self.previous.name, "status": "VALID"}
        for field, name in screen.ROW_EVIDENCE:
            value = dataclasses.asdict(self.receipt) if field == "ownership" else {}
            screen.save(self.previous / name, value)
            self.row[field + "_sha256"] = screen.digest(self.previous / name)
        self.deadline = screen.time.perf_counter() + 600

    def error(self, code=32):
        error = PermissionError(
            errno.EACCES, "synthetic deletion failure", str(self.file)
        )
        if code is not None:
            error.winerror = code
        return error

    def test_32_then_release_retries_only_the_action_and_logs_before_native(self):
        original_unlink = screen.os.unlink
        error = self.error()
        calls = []

        def unlink(path, *args, **kwargs):
            calls.append(str(path))
            if len(calls) == 1:
                raise error
            return original_unlink(path, *args, **kwargs)

        with (
            patch.object(screen.os, "unlink", new=unlink),
            patch.object(screen, "run_native") as native,
            patch.object(
                screen.time,
                "sleep",
                side_effect=lambda delay: native.assert_not_called(),
            ) as sleep,
        ):
            screen.reset_source(
                self.output, self.folder, [self.row], self.receipt, self.deadline
            )
            native.assert_not_called()
        self.assertEqual(calls, [str(self.file), str(self.file)])
        sleep.assert_called_once_with(0.05)
        log = screen.load(self.folder / "source-reset.json")
        self.assertTrue(log["completed"])
        self.assertFalse(self.live.exists())
        self.assertEqual(log["extra_attempts"], 1)
        event = log["events"][0]
        self.assertEqual(event["path"], str(self.file))
        self.assertEqual(event["initial_error"]["winerror"], 32)
        self.assertEqual(event["initial_error"]["errno"], errno.EACCES)
        self.assertIn("synthetic deletion failure", event["initial_error"]["repr"])
        self.assertIn(
            "unlink",
            [frame["function"] for frame in event["initial_error"]["traceback_frames"]],
        )
        attempt = event["attempts"][0]
        self.assertTrue(attempt["completed"])
        self.assertEqual(attempt["delay_ms"], 50)
        self.assertGreaterEqual(attempt["delay_monotonic_ns"], 0)
        self.assertLessEqual(attempt["wait_end_ns"], attempt["action_start_ns"])
        self.assertLessEqual(attempt["action_end_ns"], log["ended_ns"])

    def test_permanent_32_has_exact_global_three_extra_attempts_and_raw_failure(self):
        error = self.error()
        with (
            patch.object(screen.os, "unlink", side_effect=error) as unlink,
            patch.object(screen.time, "sleep") as sleep,
            self.assertRaises(PermissionError) as caught,
        ):
            screen.reset_source(
                self.output, self.folder, [self.row], self.receipt, self.deadline
            )
        self.assertIs(caught.exception, error)
        self.assertEqual(unlink.call_count, 4)
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list], [0.05, 0.1, 0.2]
        )
        log = screen.load(self.folder / "source-reset.json")
        self.assertFalse(log["completed"])
        self.assertEqual(log["extra_attempts"], 3)
        self.assertEqual(log["planned_wait_ms"], 350)
        self.assertEqual(log["terminal_error"]["winerror"], 32)
        self.assertTrue(self.file.exists())

    def test_rmdir_32_then_release_retries_only_directory_action(self):
        original_rmdir = screen.os.rmdir
        error = self.error()
        error.filename = str(self.live)
        calls = []

        def rmdir(path, *args, **kwargs):
            if Path(path) == self.live:
                calls.append(str(path))
                if len(calls) == 1:
                    raise error
            return original_rmdir(path, *args, **kwargs)

        with (
            patch.object(screen.os, "rmdir", new=rmdir),
            patch.object(screen.shutil, "rmtree", wraps=screen.shutil.rmtree) as remove,
            patch.object(screen.time, "sleep") as sleep,
        ):
            screen.reset_source(
                self.output, self.folder, [self.row], self.receipt, self.deadline
            )
        self.assertEqual(calls, [str(self.live), str(self.live)])
        self.assertEqual(remove.call_count, 1)
        sleep.assert_called_once_with(0.05)
        self.assertFalse(self.live.exists())

    def test_non32_after_first_retry_is_raw_terminal_failure(self):
        first, terminal = self.error(), self.error(5)
        with (
            patch.object(screen.os, "unlink", side_effect=[first, terminal]) as unlink,
            patch.object(screen.time, "sleep") as sleep,
            self.assertRaises(PermissionError) as caught,
        ):
            screen.reset_source(
                self.output, self.folder, [self.row], self.receipt, self.deadline
            )
        self.assertIs(caught.exception, terminal)
        self.assertEqual(unlink.call_count, 2)
        sleep.assert_called_once_with(0.05)
        log = screen.load(self.folder / "source-reset.json")
        self.assertEqual(log["events"][0]["initial_error"]["winerror"], 32)
        self.assertEqual(log["terminal_error"]["winerror"], 5)
        self.assertEqual(log["extra_attempts"], 1)
        self.assertFalse(log["completed"])

    def test_budget_is_shared_across_files_not_restarted_per_callback(self):
        self.file.unlink()
        for name in ("one", "two", "three", "four"):
            (self.live / name).write_bytes(b"fixture")
        original_unlink = screen.os.unlink
        seen, calls = set(), []

        def unlink(path, *args, **kwargs):
            calls.append(str(path))
            if str(path) not in seen:
                seen.add(str(path))
                raise self.error()
            return original_unlink(path, *args, **kwargs)

        with (
            patch.object(screen.os, "unlink", new=unlink),
            patch.object(screen.time, "sleep") as sleep,
            self.assertRaises(PermissionError),
        ):
            screen.reset_source(
                self.output, self.folder, [self.row], self.receipt, self.deadline
            )
        log = screen.load(self.folder / "source-reset.json")
        self.assertEqual(len(calls), 7)
        self.assertEqual(
            [len(event["attempts"]) for event in log["events"]], [1, 1, 1, 0]
        )
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list], [0.05, 0.1, 0.2]
        )
        self.assertEqual(log["extra_attempts"], 3)
        self.assertEqual(log["planned_wait_ms"], 350)
        self.assertFalse(log["completed"])

    def test_access_denied_and_unspecific_permission_are_never_retried(self):
        for code in (5, None):
            error = self.error(code)
            with (
                self.subTest(winerror=code),
                patch.object(screen.os, "unlink", side_effect=error) as unlink,
                patch.object(screen.time, "sleep") as sleep,
                self.assertRaises(PermissionError) as caught,
            ):
                screen.reset_source(
                    self.output, self.folder, [self.row], self.receipt, self.deadline
                )
            self.assertIs(caught.exception, error)
            self.assertEqual(unlink.call_count, 1)
            sleep.assert_not_called()
            self.assertFalse(
                screen.load(self.folder / "source-reset.json")["completed"]
            )

    def test_other_platform_fails_32_immediately(self):
        error = self.error()
        with (
            patch.object(screen.sys, "platform", "darwin"),
            patch.object(screen.os, "unlink", side_effect=error) as unlink,
            patch.object(screen.time, "sleep") as sleep,
            self.assertRaises(PermissionError) as caught,
        ):
            screen.reset_source(
                self.output, self.folder, [self.row], self.receipt, self.deadline
            )
        self.assertIs(caught.exception, error)
        self.assertEqual(unlink.call_count, 1)
        sleep.assert_not_called()

    def test_error_capture_never_opens_source_or_lazily_imports_after_WB(self):
        try:
            raise self.error()
        except PermissionError as error:
            with (
                patch.object(
                    builtins, "open", side_effect=AssertionError("no source reader")
                ),
                patch.object(
                    builtins, "__import__", side_effect=AssertionError("no late import")
                ),
            ):
                record = screen.reset_error(error)
        self.assertEqual(record["winerror"], 32)
        self.assertTrue(record["traceback_frames"])

    def test_target_replacement_during_wait_is_not_deleted(self):
        error = self.error()
        retained = self.live / "retained-original"

        def replace_during_wait(delay):
            self.file.rename(retained)
            self.file.write_bytes(b"replacement must remain")

        with (
            patch.object(screen.os, "unlink", side_effect=error) as unlink,
            patch.object(screen.time, "sleep", side_effect=replace_during_wait),
            self.assertRaisesRegex(RuntimeError, "target identity changed"),
        ):
            screen.reset_source(
                self.output, self.folder, [self.row], self.receipt, self.deadline
            )
        self.assertEqual(unlink.call_count, 1)
        self.assertEqual(self.file.read_bytes(), b"replacement must remain")
        self.assertTrue(retained.exists())

    def test_callback_outside_owned_root_is_rejected_without_action(self):
        outside = self.output / "outside"
        outside.write_bytes(b"untouched")
        with (
            patch.object(
                screen.shutil,
                "rmtree",
                side_effect=lambda path, *, onexc: onexc(
                    screen.os.unlink, str(outside), self.error()
                ),
            ),
            patch.object(screen.time, "sleep") as sleep,
            self.assertRaisesRegex(RuntimeError, "outside owned root"),
        ):
            screen.reset_source(
                self.output, self.folder, [self.row], self.receipt, self.deadline
            )
        self.assertEqual(outside.read_bytes(), b"untouched")
        sleep.assert_not_called()
        self.assertEqual(
            screen.load(self.folder / "source-reset.json")["events"][0][
                "initial_error"
            ]["winerror"],
            32,
        )

    def test_reparse_ancestor_is_rejected_before_retry(self):
        original = Path.is_junction
        with (
            patch.object(
                screen.shutil,
                "rmtree",
                side_effect=lambda path, *, onexc: onexc(
                    screen.os.unlink, str(self.file), self.error()
                ),
            ),
            patch.object(
                Path,
                "is_junction",
                new=lambda path: path == self.file.parent or original(path),
            ),
            patch.object(screen.time, "sleep") as sleep,
            self.assertRaisesRegex(RuntimeError, "link/junction"),
        ):
            screen.reset_source(
                self.output, self.folder, [self.row], self.receipt, self.deadline
            )
        sleep.assert_not_called()
        self.assertTrue(self.file.exists())

    def test_non_junction_reparse_attribute_is_also_rejected(self):
        original = Path.lstat

        def lstat(path):
            value = original(path)
            if path == self.file:
                return SimpleNamespace(
                    st_mode=value.st_mode,
                    st_file_attributes=value.st_file_attributes | 0x400,
                )
            return value

        with (
            patch.object(
                screen.shutil,
                "rmtree",
                side_effect=lambda path, *, onexc: onexc(
                    screen.os.unlink, str(self.file), self.error()
                ),
            ),
            patch.object(Path, "lstat", new=lstat),
            patch.object(screen.time, "sleep") as sleep,
            self.assertRaisesRegex(RuntimeError, "reparse point"),
        ):
            screen.reset_source(
                self.output, self.folder, [self.row], self.receipt, self.deadline
            )
        sleep.assert_not_called()

    def test_scandir_callback_is_not_a_retryable_deletion_action(self):
        with (
            patch.object(
                screen.shutil,
                "rmtree",
                side_effect=lambda path, *, onexc: onexc(
                    screen.os.scandir, str(self.live), self.error()
                ),
            ),
            patch.object(screen.time, "sleep") as sleep,
            self.assertRaisesRegex(RuntimeError, "incorrect deletion callback"),
        ):
            screen.reset_source(
                self.output, self.folder, [self.row], self.receipt, self.deadline
            )
        sleep.assert_not_called()

    def test_insufficient_deadline_fails_before_wait(self):
        with (
            patch.object(screen.os, "unlink", side_effect=self.error()) as unlink,
            patch.object(screen.time, "perf_counter", return_value=1000),
            patch.object(screen.time, "sleep") as sleep,
            self.assertRaisesRegex(RuntimeError, "deadline prevents launch"),
        ):
            screen.reset_source(
                self.output, self.folder, [self.row], self.receipt, 1100
            )
        sleep.assert_not_called()
        self.assertEqual(unlink.call_count, 1)
        log = screen.load(self.folder / "source-reset.json")
        self.assertEqual(log["extra_attempts"], 0)
        self.assertEqual(log["events"][0]["attempts"], [])

    def test_deadline_is_rechecked_after_wait_before_filesystem_action(self):
        with (
            patch.object(screen.os, "unlink", side_effect=self.error()) as unlink,
            patch.object(screen.time, "perf_counter", side_effect=[1000, 1001]),
            patch.object(screen.time, "sleep") as sleep,
            self.assertRaisesRegex(RuntimeError, "deadline prevents launch"),
        ):
            screen.reset_source(
                self.output, self.folder, [self.row], self.receipt, 1100.1
            )
        sleep.assert_called_once_with(0.05)
        self.assertEqual(unlink.call_count, 1)
        log = screen.load(self.folder / "source-reset.json")
        self.assertEqual(log["extra_attempts"], 0)
        self.assertFalse(log["events"][0]["attempts"][0]["action_called"])

    def test_unsuccessful_previous_family_prevents_any_deletion(self):
        receipt = dataclasses.replace(self.receipt, survivors=True)
        with (
            patch.object(screen.shutil, "rmtree") as remove,
            self.assertRaisesRegex(RuntimeError, "naturally drained receipt"),
        ):
            screen.reset_source(
                self.output, self.folder, [self.row], receipt, self.deadline
            )
        remove.assert_not_called()
        self.assertFalse(screen.load(self.folder / "source-reset.json")["completed"])

    def test_unproved_previous_row_prevents_any_deletion(self):
        with (
            patch.object(screen.shutil, "rmtree") as remove,
            self.assertRaisesRegex(RuntimeError, "fully proved rows"),
        ):
            screen.reset_source(
                self.output,
                self.folder,
                [{**self.row, "status": "FAILED"}],
                self.receipt,
                self.deadline,
            )
        remove.assert_not_called()

    def test_prior_reset_log_tampering_is_rejected_before_deletion_and_at_final_seal(
        self,
    ):
        screen.save(self.previous / "source-reset.json", {"tampered": True})
        with (
            patch.object(screen.shutil, "rmtree") as remove,
            self.assertRaisesRegex(RuntimeError, "source-reset.json"),
        ):
            screen.reset_source(
                self.output, self.folder, [self.row], self.receipt, self.deadline
            )
        remove.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, "source-reset.json"):
            screen.seal_rows(self.output, [self.row])

    def test_no_retry_success_and_initial_absent_source_are_both_logged(self):
        with patch.object(screen.time, "sleep") as sleep:
            screen.reset_source(
                self.output, self.folder, [self.row], self.receipt, self.deadline
            )
            log = screen.load(self.folder / "source-reset.json")
            self.assertTrue(log["completed"])
            self.assertTrue(log["performed"])
            self.assertEqual(log["events"], [])
            screen.reset_source(self.output, self.previous, [], None, self.deadline)
        sleep.assert_not_called()
        initial = screen.load(self.previous / "source-reset.json")
        self.assertTrue(initial["completed"])
        self.assertFalse(initial["performed"])
        self.assertEqual(initial["extra_attempts"], 0)


if __name__ == "__main__":
    unittest.main()
