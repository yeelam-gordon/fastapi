"""Verify committed caller gates without editing or executing package producers."""

import copy
import hashlib
import importlib
import json
import shutil
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

REVISION = "102ddabcb3a03b33915cb11534925c0951c2df72"
HERE = Path(__file__).resolve().parent


def main():
    scratch = HERE / (".frozen-" + uuid.uuid4().hex)
    scratch.mkdir()
    try:
        hashes = {}
        names = (
            "measure_pairs.py",
            "compare_pairs.py",
            "test_pairs.py",
            "owned_process.py",
            "isolated_build.py",
            "test_isolated_build.py",
            "backend.lock",
        )
        for relative in (
            *(f"protocol/{name}" for name in names),
            "candidate/build.py",
        ):
            path = "Generated Files/arm-build/" + relative
            data = subprocess.run(
                ["git", "--no-pager", "show", f"{REVISION}:{path}"],
                capture_output=True,
                check=True,
            ).stdout
            target = scratch.joinpath(*relative.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            hashes[path] = hashlib.sha256(data).hexdigest()
        sys.path.insert(0, str(scratch / "protocol"))
        pairs = importlib.import_module("test_pairs")
        wrapper_tests = importlib.import_module("test_isolated_build")

        class GateCases(unittest.TestCase):
            def test_fixed_flags_and_effective_policy(self):
                for system in ("Windows", "Darwin"):
                    report = pairs.report(system)
                    original = report["samples"][1]
                    pairs.measure.validate_wrapper(original, report, set())
                    for case in (
                        "old-identity",
                        "wrong-identity",
                        "old-sdk",
                        "wrong-sdk",
                        "missing-policy",
                        "false-policy",
                    ):
                        with self.subTest(system=system, case=case):
                            sample = copy.deepcopy(original)
                            receipt = sample["wrapper_report"]
                            identity = receipt["environment"]["identity"]
                            if case == "missing-policy":
                                identity.pop("dont_write_bytecode")
                            elif case == "false-policy":
                                identity["dont_write_bytecode"] = False
                            else:
                                index = 2 if case.endswith("identity") else 3
                                argv = receipt["phases"][index]["argv"]
                                if case.startswith("old"):
                                    argv.remove("-B")
                                else:
                                    argv[argv.index("-B")] = "-b"
                            with self.assertRaises(ValueError):
                                pairs.measure.validate_wrapper(sample, report, set())

        loader = unittest.defaultTestLoader
        suite = unittest.TestSuite(
            loader.loadTestsFromTestCase(kind)
            for kind in (
                wrapper_tests.WrapperTests,
                pairs.ComparisonTests,
                GateCases,
            )
        )
        print(json.dumps({"revision": REVISION, "blob_sha256": hashes}, indent=2))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1
    finally:
        shutil.rmtree(scratch)


if __name__ == "__main__":
    sys.exit(main())
