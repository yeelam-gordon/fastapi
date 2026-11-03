import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import capture
import decode
import module_map
import typed_events
import test_typed_events


class Modules(unittest.TestCase):
    setUp = test_typed_events.Typed.setUp
    records = test_typed_events.Typed.records
    write = test_typed_events.Typed.write
    def test_observer_uses_only_existing_accepted_sample_logic(self):
        records = self.records()
        records.insert(-1, test_typed_events.row(
            "sample", 150, 999, 999, {"instructionPointer": 123}, 2, 46))
        self.write(records)
        anchor = dict(pid=10, qpc_before=99, qpc_after=101, qpc_end=201,
                      creation_filetime=1000, filetime_after=1000, qpc_frequency=10000000)
        selected = []
        result = decode.analyze(self.path, anchor, event_reader=typed_events.events,
                                sample_observer=lambda *key: selected.append(key))
        self.assertEqual(selected, [(103, 11, 4106, 0), (123, 21, 8202, 1)])
        self.assertEqual(result["cpu_samples"], len(selected))

    def public(self):
        return dict(schema=1, cpu_units="SAMPLE_COUNTS", cpu_samples=2,
                    missing_samples=0, unexpected_samples=0,
                    lifetimes=[dict(process_index=0, cpu_samples=1),
                               dict(process_index=1, cpu_samples=1)],
                    modules=[dict(process_index=0, provenance="kernel-table",
                                  module="ntoskrnl", sample_context="DPC", samples=1),
                             dict(process_index=1, provenance="unresolved",
                                  module="unresolved", sample_context="PROCESS", samples=1)],
                    symbol_resolution="DISABLED", scheduling="UNSUPPORTED",
                    file_durations="UNSUPPORTED",
                    interpretation="MODULE_PROVENANCE_NOT_EXECUTION_MODE_CAUSE_OR_IO_LATENCY")

    def test_public_poison_missing_duplicate_counts_fail_closed(self):
        result = dict(cpu_samples=2, lifetimes=[dict(cpu_samples=1), dict(cpu_samples=1)])
        module_map.validate(self.public(), result)
        for mutate in (
            lambda v: v.update(pid=123),
            lambda v: v["modules"][0].update(path="PRIVATE"),
            lambda v: v["modules"][0].update(module="PRIVATE"),
            lambda v: v.update(missing_samples=1),
            lambda v: v["modules"].append(v["modules"][0]),
            lambda v: v["modules"].pop(),
            lambda v: v["lifetimes"][0].update(cpu_samples=2),
            lambda v: v["modules"][0].update(process_index=1),
            lambda v: v["modules"][0].update(sample_context="PRIVATE"),
            lambda v: v["modules"][0].pop("sample_context"),
        ):
            bad = copy.deepcopy(self.public())
            mutate(bad)
            with self.assertRaises(ValueError):
                module_map.validate(bad, result)
        for context in ("PROCESS", "DPC", "ISR", "DPC_ISR"):
            good = self.public()
            good["modules"][0]["sample_context"] = context
            module_map.validate(good, result)

    def test_module_failure_preserves_positive_analysis_and_proof(self):
        records = self.records()
        def fake(argv, **kwargs):
            if "-stop" in argv:
                Path(argv[2]).write_bytes(b"PRIVATE_ETL")
            elif len(argv) > 2 and str(argv[1]).endswith("traceevent-reader.dll"):
                if argv[2] == "--modules":
                    return SimpleNamespace(succeeded=False, returncode=79)
                Path(argv[3]).write_text("".join(json.dumps(r) + "\n" for r in records))
            return SimpleNamespace(succeeded=True, returncode=0)
        c = capture.Controller(self.folder, self.folder / "public", self.folder, Path("uv"), fake)
        anchor = dict(pid=10, qpc_before=99, qpc_after=101, qpc_end=201,
                      creation_filetime=1000, filetime_after=1000, qpc_frequency=10000000)
        with patch.object(capture, "analyze", wraps=decode.analyze):
            original = c.command
            def command(tool, argv, *args, **kwargs):
                original(tool, argv, *args, **kwargs)
                if tool == "python":
                    (self.folder / "build" / "anchor.json").write_text(json.dumps(anchor))
            c.command = command
            with self.assertRaises(capture.Failure) as failure:
                c.trace("build", ["uv", "build"], {})
        self.assertEqual(failure.exception.reason, "module_sample_identity")
        c.report("DOTNET", failure.exception.code, "FAILED", failure.exception.reason)
        stage = json.loads((c.public / "stage.json").read_text())
        self.assertEqual((stage["reason"], stage["native_code"]),
                         ("module_sample_identity", 79))
        self.assertEqual(c.stage, "build_modules")
        self.assertTrue((c.public / "build.json").is_file())
        self.assertTrue((c.public / "capture-proof.json").is_file())
        self.assertFalse((c.public / "build-modules.json").exists())
        private = json.loads((self.folder / "build" / "verified-samples.json").read_text())
        self.assertEqual(private["counts"], [1, 1])
        self.assertEqual(c.reader_env["_NT_SYMBOL_PATH"], "")


if __name__ == "__main__":
    unittest.main()
