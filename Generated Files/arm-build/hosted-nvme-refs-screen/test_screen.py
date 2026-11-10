import argparse
import base64
import csv
import dataclasses
import hashlib
import importlib.util
import io
import marshal
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import time
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest.mock import create_autospec, patch

import screen
from owned_process import Receipt


class DriverTests(unittest.TestCase):
    def test_isolated_administrative_entrypoint_resolves_sealed_siblings(self):
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(screen.HERE / "screen.py"), "--help"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertIn("--candidate-cache", result.stdout)
        self.assertEqual(result.stderr, "")

    def setUp(self):
        self.root = Path(__file__).resolve().parent / ("test-work-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.args = argparse.Namespace(
            output=self.root,
            python=Path("C:\\runtime\\python.exe"),
            uv=Path("C:\\tools\\uv.exe"),
            wheels=Path("C:\\wheels"),
        )
        self.envs = {
            "C": {"UV_CACHE_DIR": "C:\\same\\cache"},
            "D": {"UV_CACHE_DIR": "D:\\same\\cache"},
        }
        self.argv = screen.command(
            self.args, Path("C:\\evidence\\build-constraints.txt")
        )
        self.birth_seconds = 1700000000
        self.metadata_time = 1700000000.0
        self.receipt = Receipt(
            0,
            False,
            0.1,
            0.01,
            True,
            False,
            True,
            (),
            native_start_ns=1,
            native_end_ns=10,
            actual_process={
                "pid": 42,
                "image": str(self.args.uv),
                "birth_filetime": screen.FILETIME_EPOCH
                + self.birth_seconds * 10_000_000,
            },
        )
        self.canonical = {"source.py": "hash"}
        self.audit_impl = None
        self.source_after_impl = None
        self.runtime_guard = create_autospec(screen.RuntimeGuard, instance=True)
        self.runtime_guard.roots = {"C:\\runtime": Path("C:\\runtime")}
        self.live_roots = None

    def extract(self, archive, destination):
        destination.mkdir()
        (destination / "dist").mkdir()

    def owned(self, argv, **kwargs):
        folder = kwargs["stdout_path"].parent
        receipt = dataclasses.replace(
            self.receipt,
            actual_process={
                **self.receipt.actual_process,
                "birth_filetime": screen.FILETIME_EPOCH
                + self.birth_seconds * 10_000_000,
            },
        )
        (folder / "stdout").write_bytes(b"")
        (folder / "stderr").write_bytes(b"")
        screen.save(folder / "stdout.actual-process.json", receipt.actual_process)
        native = {
            "status": "COMPLETE",
            "returncode": 0,
            "argv": argv,
            "cwd": str(kwargs["cwd"]),
            "environment": self.envs[folder.name[-1]],
            **receipt.actual_process,
            "start_ns": 1,
            "end_ns": 10,
        }
        return receipt, native

    def fake_audit(self, source, canonical, reference, folder, reference_folder):
        screen.save(folder / "generated-metadata-proof.json", {"bindings": {}})
        return {"sdist": {}, "wheel": {}}, {}

    def output_proof(self, source, canonical, inventory, folder):
        return {
            "tracked": canonical,
            "outputs": {
                "dist/" + path.name: screen.digest(path)
                for path in (source / "dist").iterdir()
            },
            "retained_generated": {},
            "pyc_associations": {},
        }

    def run_driver(self, *, failure=None, native=None, deadline=None):
        with (
            patch.object(screen, "extract", side_effect=self.extract),
            patch.object(screen, "manifest", return_value=self.canonical),
            patch.object(
                screen, "run_native", side_effect=native or self.owned
            ) as owned,
            patch.object(
                screen,
                "source_after",
                side_effect=self.source_after_impl or self.output_proof,
            ),
            patch.object(
                screen,
                "archive_audit",
                side_effect=failure or self.audit_impl or self.fake_audit,
            ) as audit,
        ):
            try:
                result = screen.execute(
                    self.args,
                    self.canonical,
                    time.perf_counter() + 480 if deadline is None else deadline,
                    self.envs,
                    self.argv,
                    self.runtime_guard,
                    live_roots=self.live_roots,
                    runtime_roots=(Path("C:\\runtime"),),
                )
                return result, owned.call_count, audit.call_count
            finally:
                self.owned_calls, self.audit_calls = owned.call_count, audit.call_count

    def test_failed_receipt_stops_before_audit_next_command_or_value(self):
        self.receipt = dataclasses.replace(self.receipt, returncode=1)
        with self.assertRaisesRegex(RuntimeError, "fatal receipt"):
            self.run_driver()
        self.assertEqual(self.owned_calls, 1)
        self.assertEqual(self.audit_calls, 0)
        self.assertTrue((self.root / "build-00-C" / "ownership.json").is_file())
        self.assertFalse((self.root / "rows.json").exists())
        self.assertFalse((self.root / "result.json").exists())

    def test_deadline_prevents_first_launch(self):
        with self.assertRaisesRegex(RuntimeError, "deadline prevents launch"):
            self.run_driver(deadline=time.perf_counter() + 99)
        self.assertEqual(self.owned_calls, 0)
        self.assertEqual(self.audit_calls, 0)

    def test_source_placement_requires_full_environment_cache_and_fixed_base_argv(self):
        self.args.control_cache = self.args.candidate_cache = Path("Q:\\common\\cache")
        common = {
            "UV_CACHE_DIR": str(self.args.control_cache),
            "TEMP": "C:\\temp",
            "TMP": "C:\\temp",
            "PRIVATE": "unchanged",
        }
        envs = {"C": dict(common), "D": dict(common)}
        argv = screen.command(self.args, self.root / "build-constraints.txt")
        screen.source_launch_contract(self.args, envs, argv)
        for key in ("PRIVATE", "TEMP", "TMP", "UV_CACHE_DIR"):
            with self.subTest(key=key):
                changed = {"C": dict(common), "D": dict(common)}
                changed["D"][key] += "-changed"
                with self.assertRaisesRegex(RuntimeError, "identical full environment"):
                    screen.source_launch_contract(self.args, changed, argv)
        with self.assertRaisesRegex(RuntimeError, "identical base argv"):
            screen.source_launch_contract(
                self.args, envs, argv + ["--out-dir", "Q:\\dist"]
            )
        for env in envs.values():
            env["UV_CACHE_DIR"] = "Q:\\wrong"
        with self.assertRaisesRegex(RuntimeError, "common explicit cache"):
            screen.source_launch_contract(self.args, envs, argv)
        root = Path("C:\\owned\\source")
        selected = screen.source_command(argv, root)
        screen.verify_source_selection(argv, selected, root, self.root, self.root)
        for index in (0, len(argv), len(argv) + 1, len(argv) + 2):
            with self.subTest(argument_index=index):
                wrong = list(selected)
                wrong[index] += "-wrong"
                with self.assertRaisesRegex(RuntimeError, "exact SRC/out-dir"):
                    screen.verify_source_selection(
                        argv, wrong, root, self.root, self.root
                    )
        with self.assertRaisesRegex(RuntimeError, "common launch cwd"):
            screen.verify_source_selection(
                argv, selected, root, self.root / "wrong", self.root
            )

    def test_source_path_admission_rejects_wrong_volume_suffix_overlap_and_links(self):
        args = argparse.Namespace(
            source=Path("C:\\original"),
            output=Path("C:\\evidence"),
            python=Path("C:\\runtime\\python.exe"),
            uv=Path("C:\\tools\\uv.exe"),
            wheels=Path("C:\\wheels"),
            control_cache=Path("Q:\\cache"),
            candidate_cache=Path("Q:\\cache"),
        )
        roots = {"C": Path("C:\\owned\\source"), "D": Path("Q:\\owned\\source")}
        with (
            patch.object(Path, "is_dir", return_value=True),
            patch.object(Path, "exists", return_value=False),
            patch.object(Path, "is_symlink", return_value=False),
            patch.object(Path, "is_junction", return_value=False),
        ):
            screen.validate_source_paths(args, roots, (Path("C:\\runtime"),))
            for candidate in (Path("C:\\owned\\source"), Path("Q:\\other\\source")):
                with self.subTest(candidate=candidate):
                    with self.assertRaisesRegex(RuntimeError, "equal-suffix"):
                        screen.validate_source_paths(
                            args, {**roots, "D": candidate}, (Path("C:\\runtime"),)
                        )
            args.source = roots["C"].parent
            with self.assertRaisesRegex(RuntimeError, "disjoint"):
                screen.validate_source_paths(args, roots, (Path("C:\\runtime"),))
            args.source = Path("C:\\original")
            for kind in ("is_symlink", "is_junction"):
                with self.subTest(kind=kind):
                    with patch.object(
                        Path,
                        kind,
                        new=lambda path: path == roots["C"].parent,
                    ):
                        with self.assertRaisesRegex(RuntimeError, "reparse"):
                            screen.validate_source_paths(
                                args, roots, (Path("C:\\runtime"),)
                            )

    def test_source_driver_binds_explicit_placement_and_seals_both_last_payloads(self):
        self.use_real_audit()
        self.live_roots = {"C": self.root / "local-C", "D": self.root / "local-Q"}
        self.args.control_cache = self.args.candidate_cache = self.root / "cache"
        self.envs = {
            arm: {"UV_CACHE_DIR": str(self.args.control_cache)} for arm in ("C", "D")
        }
        self.argv = screen.command(self.args, self.root / "build-constraints.txt")
        self.extract = lambda archive, destination: self.packaging_fixture(destination)
        with patch.object(screen, "validate_source_paths") as validation:
            rows, calls, audits = self.run_driver()
        validation.assert_called_once()
        self.assertEqual((calls, audits), (14, 14))
        screen.seal_rows(self.root, rows, live_roots=self.live_roots)
        with self.assertRaisesRegex(RuntimeError, "explicit final root"):
            screen.seal_rows(self.root, rows)
        command_file = self.root / rows[0]["folder"] / "command.json"
        original_command = command_file.read_bytes()
        command_proof = screen.load(command_file)
        command_proof["argv"][-1] = str(self.root / "wrong-dist")
        screen.save(command_file, command_proof)
        original_digest = rows[0]["command_sha256"]
        rows[0]["command_sha256"] = screen.digest(command_file)
        metadata_file = command_file.parent / "generated-metadata-proof.json"
        original_metadata = metadata_file.read_bytes()
        metadata = screen.load(metadata_file)
        metadata["bindings"]["command.json"] = rows[0]["command_sha256"]
        screen.save(metadata_file, metadata)
        original_metadata_digest = rows[0]["generated_metadata_sha256"]
        rows[0]["generated_metadata_sha256"] = screen.digest(metadata_file)
        with self.assertRaisesRegex(RuntimeError, "exact SRC/out-dir"):
            screen.seal_rows(self.root, rows, live_roots=self.live_roots)
        command_file.write_bytes(original_command)
        rows[0]["command_sha256"] = original_digest
        metadata_file.write_bytes(original_metadata)
        rows[0]["generated_metadata_sha256"] = original_metadata_digest
        for row in rows:
            self.assertEqual(
                row["selected_source_root"], str(self.live_roots[row["arm"]])
            )
            proof = screen.load(self.root / row["folder"] / "command.json")
            self.assertEqual(proof["requested_launch_cwd"], str(self.root))
            self.assertEqual(
                proof["argv"],
                screen.source_command(self.argv, self.live_roots[row["arm"]]),
            )
            self.assertEqual(
                row["factor"],
                "LOCAL_C_SOURCE" if row["arm"] == "C" else "LOCAL_Q_SOURCE",
            )
        with self.assertRaisesRegex(RuntimeError, "root binding"):
            screen.seal_rows(
                self.root,
                rows,
                live_roots={
                    "C": self.live_roots["D"],
                    "D": self.live_roots["C"],
                },
            )
        for root in self.live_roots.values():
            path = root / "pyproject.toml"
            original = path.read_bytes()
            path.write_bytes(b"tampered last payload")
            with self.assertRaisesRegex(RuntimeError, "last payload"):
                screen.seal_rows(self.root, rows, live_roots=self.live_roots)
            path.write_bytes(original)
        bindings = screen.retain_source_payloads(self.root, rows, self.live_roots)
        for root in self.live_roots.values():
            shutil.rmtree(root)
        screen.seal_rows(
            self.root, rows, live_roots=self.live_roots, retained_roots=bindings
        )
        for arm in ("C", "D"):
            path = Path(bindings[arm]["retained"]) / "pyproject.toml"
            original = path.read_bytes()
            path.write_bytes(b"tampered retained payload")
            with self.assertRaisesRegex(RuntimeError, "last payload"):
                screen.seal_rows(
                    self.root,
                    rows,
                    live_roots=self.live_roots,
                    retained_roots=bindings,
                )
            path.write_bytes(original)
        relocated = self.root.with_name(self.root.name + "-retained")
        shutil.copytree(self.root, relocated)
        self.addCleanup(shutil.rmtree, relocated)
        screen.seal_rows(
            relocated, rows, live_roots=self.live_roots, retained_roots=bindings
        )

    def test_source_driver_rejects_wrong_requested_common_launch_cwd(self):
        self.live_roots = {"C": self.root / "local-C", "D": self.root / "local-Q"}
        self.args.control_cache = self.args.candidate_cache = self.root / "cache"
        self.envs = {
            arm: {"UV_CACHE_DIR": str(self.args.control_cache)} for arm in ("C", "D")
        }
        self.argv = screen.command(self.args, self.root / "build-constraints.txt")

        def wrong_cwd(argv, **kwargs):
            receipt, native = self.owned(argv, **kwargs)
            native["cwd"] = str(self.live_roots["D"])
            return receipt, native

        with patch.object(screen, "validate_source_paths"):
            with self.assertRaisesRegex(RuntimeError, "requested source launch fields"):
                self.run_driver(native=wrong_cwd)
        self.assertEqual((self.owned_calls, self.audit_calls), (1, 0))

    def test_real_source_adapter_binds_helper_identity_and_rejects_wrong_selection(
        self,
    ):
        helper = self.root / "launch_probe.py"
        helper.write_text(
            "import json, os, sys\n"
            "print(json.dumps({'argv': sys.argv, 'cwd': os.getcwd(), 'pid': os.getpid()}))\n",
            encoding="utf-8",
        )
        base = [sys.executable, "-I", "-B", str(helper)]
        control, candidate = self.root / "control", self.root / "candidate"
        control.mkdir()
        candidate.mkdir()
        selected = screen.source_command(base, control)
        receipt, native = screen.run_native(
            selected,
            cwd=self.root,
            env=dict(os.environ),
            stdout_path=self.root / "probe-control.stdout",
            stderr_path=self.root / "probe-control.stderr",
            timeout=10,
            native_clock=True,
        )
        self.assertTrue(receipt.succeeded, receipt)
        observed = screen.load(self.root / "probe-control.stdout")
        self.assertEqual(observed["pid"], receipt.actual_process["pid"])
        self.assertEqual(observed["pid"], native["pid"])
        self.assertEqual(Path(receipt.actual_process["image"]), Path(sys.executable))
        screen.verify_source_selection(
            [str(helper)], observed["argv"], control, observed["cwd"], self.root
        )
        self.assertEqual((self.root / "probe-control.stderr").read_bytes(), b"")

        receipt, native = screen.run_native(
            screen.source_command(base, candidate),
            cwd=self.root,
            env=dict(os.environ),
            stdout_path=self.root / "probe-wrong.stdout",
            stderr_path=self.root / "probe-wrong.stderr",
            timeout=10,
            native_clock=True,
        )
        self.assertTrue(receipt.succeeded, receipt)
        observed = screen.load(self.root / "probe-wrong.stdout")
        self.assertEqual(observed["pid"], receipt.actual_process["pid"])
        self.assertEqual(observed["pid"], native["pid"])
        self.assertEqual(Path(receipt.actual_process["image"]), Path(sys.executable))
        with self.assertRaisesRegex(
            RuntimeError, "exact SRC/out-dir/common launch cwd"
        ):
            screen.verify_source_selection(
                [str(helper)], observed["argv"], control, observed["cwd"], self.root
            )
        self.assertEqual((self.root / "probe-wrong.stderr").read_bytes(), b"")

    def test_source_bytecode_requires_actual_arm_filename(self):
        source = self.root / "sample.py"
        source.write_bytes(b"value = 42\n")
        cache = self.root / "sample.pyc"
        proof = {"pyc_associations": {"sample.pyc": {"source": "sample.py"}}}
        cache.write_bytes(
            b"\0" * 16
            + marshal.dumps(compile(source.read_bytes(), str(source), "exec"))
        )
        screen.source_bytecode_filenames(self.root, proof)
        cache.write_bytes(
            b"\0" * 16
            + marshal.dumps(
                compile(
                    source.read_bytes(), str(self.root / "other" / "sample.py"), "exec"
                )
            )
        )
        with self.assertRaisesRegex(RuntimeError, "actual arm root"):
            screen.source_bytecode_filenames(self.root, proof)

    def test_header_failure_stops_actual_driver(self):
        with self.assertRaisesRegex(ValueError, "Full frozen"):
            self.run_driver(failure=ValueError("Full frozen archive headers differ"))
        self.assertEqual(self.owned_calls, 1)
        self.assertFalse((self.root / "rows.json").exists())

    def test_record_failure_stops_actual_driver(self):
        with self.assertRaisesRegex(RuntimeError, "RECORD mismatch"):
            self.run_driver(failure=RuntimeError("RECORD mismatch"))
        self.assertEqual(self.owned_calls, 1)
        self.assertFalse((self.root / "rows.json").exists())

    def test_observed_argv_change_is_fatal(self):
        def changed(argv, **kwargs):
            receipt, data = self.owned(argv, **kwargs)
            data["argv"] = [*self.argv, "--no-build-isolation"]
            return receipt, data

        with self.assertRaisesRegex(RuntimeError, "actual CLI/environment differs"):
            self.run_driver(native=changed)
        self.assertEqual(self.owned_calls, 1)
        self.assertEqual(self.audit_calls, 0)

    def test_successful_driver_preserves_fixed_fourteen_build_schedule(self):
        rows, calls, audits = self.run_driver()
        self.assertEqual(calls, 14)
        self.assertEqual(audits, 14)
        self.assertEqual(self.runtime_guard.before_row.call_count, 14)
        self.assertEqual(self.runtime_guard.after_row.call_count, 14)
        self.assertEqual(
            [(row["arm"], row["measured"], row["pair"]) for row in rows],
            screen.schedule(),
        )

    def test_runtime_prelaunch_failure_prevents_native_command(self):
        self.runtime_guard.before_row.side_effect = RuntimeError(
            "runtime/input changed"
        )
        with self.assertRaisesRegex(RuntimeError, "runtime/input changed"):
            self.run_driver()
        self.assertEqual(self.owned_calls, 0)
        self.runtime_guard.after_row.assert_not_called()

    def test_measured_runtime_failure_prevents_next_command_and_valid_row(self):
        def after_row(arm, measured, pair, folder):
            if measured:
                raise RuntimeError("measured runtime/input changed")

        self.runtime_guard.after_row.side_effect = after_row
        with self.assertRaisesRegex(RuntimeError, "measured runtime/input changed"):
            self.run_driver()
        self.assertEqual(self.owned_calls, 3)
        self.assertEqual(len(screen.load(self.root / "rows.json")), 2)
        self.assertFalse((self.root / "result.json").exists())

    def test_real_runtime_guard_accepts_only_warmup_output_through_driver(self):
        runtime = self.root / "runtime-fixture"
        runtime.mkdir()
        source = runtime / "module.py"
        source.write_bytes(b"value = 7\n")
        self.args.python = Path(sys.executable)
        self.argv = screen.command(
            self.args, Path("C:\\evidence\\build-constraints.txt")
        )
        with (
            patch.object(sys, "prefix", str(runtime)),
            patch.object(sys, "base_prefix", str(runtime)),
        ):
            self.runtime_guard = screen.RuntimeGuard(
                self.args.python,
                {"version": sys.version, "runtime_roots": [str(runtime)]},
                self.root,
                {
                    "runtime": {str(runtime): {"module.py": screen.digest(source)}},
                    "tool": "sealed",
                },
                lambda: {"tool": "sealed"},
            )

            def owned(argv, **kwargs):
                if kwargs["stdout_path"].parent.name == "build-00-C":
                    cache = Path(
                        importlib.util.cache_from_source(str(source), optimization="")
                    )
                    cache.parent.mkdir()
                    header = importlib.util.MAGIC_NUMBER + struct.pack(
                        "<III",
                        0,
                        int(source.stat().st_mtime) & 0xFFFFFFFF,
                        source.stat().st_size,
                    )
                    code = compile(
                        source.read_bytes(),
                        str(source),
                        "exec",
                        dont_inherit=True,
                        optimize=0,
                    )
                    cache.write_bytes(header + marshal.dumps(code))
                return self.owned(argv, **kwargs)

            rows, calls, audits = self.run_driver(native=owned)
            self.assertEqual((len(rows), calls, audits), (14, 14, 14))
            self.runtime_guard.final()
        self.assertTrue((self.root / "runtime-seal-after-WB.json").exists())

    def test_native_observation_keeps_uv_as_guardian_root(self):
        with patch.object(
            screen.owned_process, "run_owned", return_value=self.receipt
        ) as owned:
            receipt, native = screen.run_native(
                self.argv,
                cwd=self.root,
                env=self.envs["C"],
                native_clock=True,
            )
        owned.assert_called_once_with(
            self.argv,
            cwd=self.root,
            env=self.envs["C"],
            native_clock=True,
        )
        self.assertTrue(receipt.succeeded)
        self.assertEqual(native["status"], "COMPLETE")
        self.assertEqual(native["pid"], 42)
        self.assertEqual(
            {key: native[key] for key in self.receipt.actual_process},
            self.receipt.actual_process,
        )
        self.assertEqual((native["start_ns"], native["end_ns"]), (1, 10))

    def test_missing_qualified_actual_process_is_not_complete(self):
        receipt = dataclasses.replace(self.receipt, actual_process=None)
        with patch.object(screen.owned_process, "run_owned", return_value=receipt):
            _, native = screen.run_native(
                self.argv,
                cwd=self.root,
                env=self.envs["C"],
                native_clock=True,
            )
        self.assertEqual(native["status"], "FAILED")

    def packaging_fixture(
        self,
        destination,
        *,
        corrupt_record=False,
        changed_header=False,
        changed_content=False,
    ):
        destination.mkdir()
        dist = destination / "dist"
        dist.mkdir()
        (dist / ".gitignore").write_bytes(b"*")
        original = b'[project]\nname="fastapi"\ndynamic=["version"]\n'
        (destination / "pyproject.toml").write_bytes(original)
        generated = b'[project]\nname="fastapi"\ndynamic=[]\nversion="0.119.1"\n'
        with tarfile.open(dist / "fastapi-0.119.1.tar.gz", "w:gz") as archive:
            for index in range(1196):
                name = "pyproject.toml" if index == 0 else f"payload-{index}"
                data = generated if index == 0 else b"payload"
                if index == 1 and changed_content:
                    data = b"changed payload bytes"
                member = tarfile.TarInfo("fastapi-0.119.1/" + name)
                member.size = len(data)
                if index == 0:
                    member.mtime = self.metadata_time
                archive.addfile(member, io.BytesIO(data))
        members = {f"fastapi/payload-{index}": b"payload" for index in range(56)}
        members["fastapi-0.119.1.dist-info/WHEEL"] = b"Generator: pdm-backend (2.5.0)\n"
        record_name = "fastapi-0.119.1.dist-info/RECORD"
        record = io.StringIO()
        writer = csv.writer(record)
        for name, data in members.items():
            value = (
                base64.urlsafe_b64encode(hashlib.sha256(data).digest())
                .rstrip(b"=")
                .decode()
            )
            writer.writerow(
                [name, "sha256=" + ("wrong" if corrupt_record else value), len(data)]
            )
        writer.writerow([record_name, "", ""])
        members[record_name] = record.getvalue().encode()
        with zipfile.ZipFile(dist / "fastapi-0.119.1-py3-none-any.whl", "w") as archive:
            for name, data in members.items():
                member = zipfile.ZipInfo(name)
                if changed_header:
                    member.comment = b"changed"
                archive.writestr(member, data)

    def use_real_audit(self):
        self.canonical = {
            "pyproject.toml": hashlib.sha256(
                b'[project]\nname="fastapi"\ndynamic=["version"]\n'
            ).hexdigest()
        }
        self.audit_impl = screen.archive_audit

    def test_default_generated_times_are_proved_without_rewriting_archives(self):
        self.use_real_audit()
        built = []

        def extract(archive, destination):
            self.birth_seconds = 1700000000 + 10 * len(built)
            self.metadata_time = float(self.birth_seconds)
            self.packaging_fixture(destination)
            built.append(destination)

        self.extract = extract
        rows, calls, audits = self.run_driver()
        self.assertEqual((len(rows), calls, audits), (14, 14, 14))
        screen.seal_rows(self.root, rows)
        first, second = self.root / "build-00-C", self.root / "build-01-D"
        a = screen.load(first / "full-headers.json")["sdist"][
            screen.GENERATED_PYPROJECT
        ]
        b = screen.load(second / "full-headers.json")["sdist"][
            screen.GENERATED_PYPROJECT
        ]
        self.assertNotEqual(a["mtime"], b["mtime"])
        self.assertNotEqual(a["pax_headers"], b["pax_headers"])
        with tarfile.open(second / "artifacts" / "fastapi-0.119.1.tar.gz") as archive:
            self.assertEqual(
                archive.getmember(screen.GENERATED_PYPROJECT).mtime, b["mtime"]
            )
        proof = second / "generated-metadata-proof.json"
        self.assertEqual(rows[1]["generated_metadata_sha256"], screen.digest(proof))
        (first / "stdout").write_bytes(b"changed after audit")
        with self.assertRaisesRegex(
            RuntimeError, "generated metadata evidence changed"
        ):
            screen.seal_rows(self.root, rows)

    def test_real_record_validation_is_fatal_through_driver(self):
        self.use_real_audit()

        def extract(archive, destination):
            self.packaging_fixture(destination, corrupt_record=True)

        self.extract = extract
        with self.assertRaisesRegex(RuntimeError, "RECORD mismatch"):
            self.run_driver()
        self.assertEqual(self.owned_calls, 1)
        self.assertFalse((self.root / "rows.json").exists())
        first = self.root / "build-00-C"
        self.assertEqual(len(list((first / "artifacts").iterdir())), 2)
        self.assertEqual((first / "dist.gitignore").read_bytes(), b"*")

    def test_real_full_header_difference_is_fatal_through_driver(self):
        self.use_real_audit()
        builds = []

        def extract(archive, destination):
            self.packaging_fixture(destination, changed_header=bool(builds))
            builds.append(destination)

        self.extract = extract
        with self.assertRaisesRegex(ValueError, "Full frozen archive"):
            self.run_driver()
        self.assertEqual(self.owned_calls, 2)
        self.assertEqual(len(screen.load(self.root / "rows.json")), 1)
        self.assertTrue((self.root / "build-01-D" / "full-headers.json").is_file())

    def test_real_content_difference_is_not_a_timestamp_exception(self):
        self.use_real_audit()
        built = []

        def extract(archive, destination):
            self.packaging_fixture(destination, changed_content=bool(built))
            built.append(destination)

        self.extract = extract
        with self.assertRaisesRegex(ValueError, "Full frozen archive"):
            self.run_driver()
        self.assertEqual(self.owned_calls, 2)
        self.assertEqual(len(screen.load(self.root / "rows.json")), 1)

    def test_real_uv_ignore_and_raw_pyc_survive_all_driver_payload_replacements(self):
        self.use_real_audit()
        original_after, original_manifest = screen.source_after, screen.manifest
        sample = b"answer = 42\n"
        self.canonical["sample.py"] = hashlib.sha256(sample).hexdigest()

        def extract(archive, destination):
            self.packaging_fixture(destination)
            source = destination / "sample.py"
            source.write_bytes(sample)
            cache = destination / "__pycache__"
            cache.mkdir()
            header = importlib.util.MAGIC_NUMBER + struct.pack(
                "<III",
                0,
                int(source.stat().st_mtime) & 0xFFFFFFFF,
                len(sample),
            )
            (cache / "sample.cpython-313.pyc").write_bytes(
                header + marshal.dumps(compile(sample, str(source), "exec")),
            )

        def audit_source(source, canonical, inventory, folder):
            with patch.object(screen, "manifest", original_manifest):
                return original_after(source, canonical, inventory, folder)

        self.extract = extract
        self.source_after_impl = audit_source
        rows, calls, audits = self.run_driver()
        self.assertEqual((calls, audits), (14, 14))
        screen.seal_rows(self.root, rows)
        first = self.root / "build-00-C"
        self.assertEqual((first / "dist.gitignore").read_bytes(), b"*")
        self.assertEqual(len(list((first / "artifacts").iterdir())), 2)
        proof = screen.load(first / "source-after.json")
        association = proof["pyc_associations"]["__pycache__/sample.cpython-313.pyc"]
        retained = first / association["retained"]
        self.assertEqual(screen.digest(retained), association["pyc_sha256"])
        self.assertEqual(association["source_sha256"], self.canonical["sample.py"])
        with tarfile.open(first / "artifacts" / "fastapi-0.119.1.tar.gz") as archive:
            self.assertEqual(len(archive.getmembers()), 1196)

    def test_changed_uv_ignore_is_fatal_before_next_build(self):
        self.use_real_audit()

        def extract(archive, destination):
            self.packaging_fixture(destination)
            (destination / "dist" / ".gitignore").write_bytes(b"*\n")

        self.extract = extract
        with self.assertRaisesRegex(RuntimeError, "pinned UV dist ignore"):
            self.run_driver()
        self.assertEqual(self.owned_calls, 1)
        self.assertFalse((self.root / "rows.json").exists())


class ContractTests(unittest.TestCase):
    def test_new_outer_budget_accepts_600_before_storage_checks(self):
        args = argparse.Namespace(
            seconds=600,
            output=Path(__file__).parent / ("test-work-budget-" + uuid.uuid4().hex),
            control_cache=Path("C:\\control"),
            candidate_cache=Path("D:\\control"),
        )
        self.addCleanup(shutil.rmtree, args.output)
        with (
            patch.object(screen, "validate_paths"),
            patch.object(
                screen, "volume_identity", side_effect=RuntimeError("storage sentinel")
            ) as storage,
        ):
            with self.assertRaisesRegex(RuntimeError, "storage sentinel"):
                screen.main(args)
        storage.assert_called_once()
        self.assertEqual(
            screen.load(args.output / "result.json")["error"], "storage sentinel"
        )

    def test_invalid_budget_stops_before_creating_evidence(self):
        output = Path(__file__).parent / ("test-work-budget-" + uuid.uuid4().hex)
        for seconds in (0, -1, float("nan"), float("inf"), 600.001):
            with self.subTest(seconds=seconds):
                with patch.object(screen, "validate_paths"):
                    with self.assertRaisesRegex(RuntimeError, "600s maximum"):
                        screen.main(argparse.Namespace(seconds=seconds, output=output))
                self.assertFalse(output.exists())

    def test_setup_uv_handoff_reproduces_and_resolves_observed_ci_rejection(self):
        inherited = {
            "UV_PYTHON_INSTALL_DIR": "C:\\action-python",
            "UV_TOOL_BIN_DIR": "C:\\action-tool-bin",
            "uv_tool_dir": "C:\\action-tools",
            "UV_CACHE_DIR": "C:\\setup-cache",
            "TEMP": "C:\\scratch",
            "TMP": "C:\\scratch",
            "PATH": "original-path",
            "GITHUB_TOKEN": "private-token",
        }
        original = dict(inherited)
        with self.assertRaisesRegex(RuntimeError, "ambient benchmark overrides"):
            screen.environment(Path("C:\\same\\cache"), inherited)
        clean, evidence = screen.setup_uv_handoff(inherited)
        control = screen.environment(Path("C:\\same\\cache"), clean)
        candidate = screen.environment(Path("D:\\same\\cache"), clean)
        self.assertEqual(inherited, original)
        self.assertEqual(
            evidence["removed_location_variables"],
            ["UV_PYTHON_INSTALL_DIR", "UV_TOOL_BIN_DIR", "uv_tool_dir"],
        )
        self.assertNotIn("action-python", str(evidence))
        self.assertNotIn("private-token", str(evidence))
        self.assertEqual(
            screen.environment_delta(control, candidate),
            {"changed_keys": ["UV_CACHE_DIR"], "all_non_cache_values_equal": True},
        )
        self.assertEqual(
            {name: value for name, value in control.items() if name != "UV_CACHE_DIR"},
            {name: original[name] for name in ("TEMP", "TMP", "PATH", "GITHUB_TOKEN")},
        )

    def test_setup_uv_handoff_keeps_unknown_policy_overrides_fatal(self):
        for name in ("UV_NO_CACHE", "UV_PYTHON", "UV_INDEX_URL", "PYTHONPATH"):
            with self.subTest(name=name):
                clean, _ = screen.setup_uv_handoff(
                    {"UV_TOOL_DIR": "C:\\action-tools", name: "injected"}
                )
                with self.assertRaisesRegex(
                    RuntimeError, "ambient benchmark overrides"
                ):
                    screen.environment(Path("C:\\same\\cache"), clean)

    def test_environment_evidence_binds_without_disclosing_credentials(self):
        env = {
            "UV_CACHE_DIR": "D:\\same\\cache",
            "TEMP": "C:\\scratch",
            "ACTIONS_RUNTIME_TOKEN": "private-token",
        }
        evidence = screen.environment_evidence(env)
        self.assertNotIn("private-token", str(evidence))
        self.assertNotIn("ACTIONS_RUNTIME_TOKEN", str(evidence))
        self.assertNotIn(hashlib.sha256(b"private-token").hexdigest(), str(evidence))
        self.assertEqual(evidence["values"]["TEMP"], "C:\\scratch")
        self.assertEqual(env["ACTIONS_RUNTIME_TOKEN"], "private-token")

    def test_inherited_cache_override_preserves_every_other_value(self):
        inherited = {
            "UV_CACHE_DIR": "C:\\setup-uv",
            "TEMP": "C:\\scratch",
            "GITHUB_TOKEN": "private-token",
            "ACTIONS_RUNTIME_TOKEN": "other-token",
        }
        control = screen.environment(Path("C:\\same\\cache"), inherited)
        candidate = screen.environment(Path("D:\\same\\cache"), inherited)
        self.assertEqual(
            screen.environment_delta(control, candidate),
            {"changed_keys": ["UV_CACHE_DIR"], "all_non_cache_values_equal": True},
        )
        self.assertEqual(
            {key: value for key, value in control.items() if key != "UV_CACHE_DIR"},
            {key: value for key, value in inherited.items() if key != "UV_CACHE_DIR"},
        )
        self.assertEqual(inherited["UV_CACHE_DIR"], "C:\\setup-uv")

    def test_cache_is_only_environment_delta_and_cli_is_common(self):
        inherited = {"TEMP": "C:\\scratch", "TMP": "C:\\scratch", "PATH": "original"}
        control = screen.environment(Path("C:\\same\\cache"), inherited)
        candidate = screen.environment(Path("D:\\same\\cache"), inherited)
        self.assertEqual(
            inherited, {"TEMP": "C:\\scratch", "TMP": "C:\\scratch", "PATH": "original"}
        )
        self.assertEqual(
            {key for key in control if control[key] != candidate[key]}, {"UV_CACHE_DIR"}
        )
        args = argparse.Namespace(
            uv=Path("C:\\uv.exe"),
            python=Path("C:\\python.exe"),
            wheels=Path("C:\\wheels"),
        )
        self.assertEqual(
            screen.command(args, Path("C:\\constraints.txt")),
            [
                "C:\\uv.exe",
                "build",
                "--python",
                "C:\\python.exe",
                "--no-python-downloads",
                "--offline",
                "--build-constraints",
                "C:\\constraints.txt",
                "--find-links",
                "C:\\wheels",
            ],
        )

    def test_ambient_override_is_rejected_not_silently_removed(self):
        with self.assertRaisesRegex(RuntimeError, "ambient benchmark overrides"):
            screen.environment(Path("C:\\cache"), {"PYTHONPATH": "injected"})

    def test_statistics_require_complete_valid_frozen_schedule(self):
        rows = [
            {
                "arm": arm,
                "measured": measured,
                "pair": pair,
                "status": "VALID",
                "seconds": 10 if arm == "C" else 9,
            }
            for arm, measured, pair in screen.schedule()
        ]
        result = screen.summarize(rows)
        self.assertTrue(result["material"])
        self.assertEqual(result["wins"], 6)
        self.assertEqual(
            [pair["order"] for pair in result["pairs"]],
            ["AB", "BA", "AB", "BA", "AB", "BA"],
        )
        with self.assertRaisesRegex(RuntimeError, "complete frozen schedule"):
            screen.summarize(rows[:-1])
        rows[-1]["status"] = "FAILED"
        with self.assertRaisesRegex(RuntimeError, "invalid row"):
            screen.summarize(rows)

    def test_small_gain_never_passes_material_gate(self):
        rows = [
            {
                "arm": arm,
                "measured": measured,
                "pair": pair,
                "status": "VALID",
                "seconds": 10 if arm == "C" else 9.6,
            }
            for arm, measured, pair in screen.schedule()
        ]
        self.assertFalse(screen.summarize(rows)["material"])

    def test_support_copies_are_exactly_qualified(self):
        self.assertEqual(
            {name: screen.digest(screen.HERE / name) for name in screen.SUPPORT},
            screen.SUPPORT,
        )


if __name__ == "__main__":
    unittest.main()
