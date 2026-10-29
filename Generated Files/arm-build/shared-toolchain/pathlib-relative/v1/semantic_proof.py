"""Fresh-process source-prefix proof; never imports installed pathlib."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "cpython")
assert sys.version_info[:3] == (3, 13, 15), sys.version
assert "pathlib" not in sys.modules
sys.path.insert(0, os.path.join(SOURCE, "Lib"))
work = os.path.join(SOURCE, "proof-work")
os.makedirs(work, exist_ok=True)
os.environ["TEMP"] = os.environ["TMP"] = work
os.chdir(work)

import pathlib
import pathlib._local
import unittest
from test.test_pathlib import test_pathlib

assert os.path.normcase(pathlib._local.__file__) == os.path.normcase(
    os.path.join(SOURCE, "Lib", "pathlib", "_local.py")
), pathlib._local.__file__
print("EXECUTABLE", sys.executable)
print("VERSION", sys.version)
print("PATHLIB_ORIGIN", pathlib._local.__file__)
P = pathlib.PureWindowsPath
for left, right in [("C:Σ", "C:ς"), ("C:Σ/Leaf", "C:ς"),
                    ("C:/İ/Leaf", "c:/i\u0307")]:
    print("UNICODE_BASELINE_OR_CANDIDATE", ascii(left), ascii(right),
          ascii(str(P(left).relative_to(P(right)))))

loader = unittest.TestLoader()
suite = unittest.TestSuite()
for cls in (test_pathlib.PurePathTest, test_pathlib.PurePosixPathTest,
            test_pathlib.PureWindowsPathTest, test_pathlib.PurePathSubclassTest):
    suite.addTests(loader.loadTestsFromTestCase(cls))
for cls in (test_pathlib.PathTest, test_pathlib.WindowsPathTest,
            test_pathlib.PosixPathTest, test_pathlib.PathSubclassTest):
    for name in loader.getTestCaseNames(cls):
        if name.startswith(("test_relative_to", "test_is_relative_to",
                            "test_with_segments")):
            suite.addTest(cls(name))
result = unittest.TextTestRunner(verbosity=2).run(suite)
print("RESULT", result.testsRun, "failures", len(result.failures),
      "errors", len(result.errors), "skips", len(result.skipped))
import hashlib
import json

modules = {}
for name, module in tuple(sys.modules.items()):
    filename = getattr(module, "__file__", None)
    if filename and filename.startswith(SOURCE + os.sep) and filename.endswith(".py"):
        with open(filename, "rb") as source_file:
            modules[os.path.relpath(filename, SOURCE)] = hashlib.sha256(
                source_file.read()).hexdigest()
label = sys.argv[1] if len(sys.argv) > 1 else "candidate"
with open(os.path.join(HERE, label + "-modules.json"), "w", encoding="utf-8") as output:
    json.dump({"source_modules_sha256": modules, "tests": result.testsRun,
               "failures": len(result.failures), "errors": len(result.errors),
               "skips": [(test.id(), reason) for test, reason in result.skipped]},
              output, indent=2)
sys.exit(not result.wasSuccessful())
