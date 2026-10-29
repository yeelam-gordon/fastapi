"""One fixed timeit screen; source-prefix only, no runtime monkeypatch."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "cpython")
assert sys.version_info[:3] == (3, 13, 15)
assert "pathlib" not in sys.modules
sys.path.insert(0, os.path.join(SOURCE, "Lib"))

import ast
import hashlib
import json
import pathlib
import pathlib._local as local
import statistics
import subprocess
import timeit

BASE = "4061bc4c35f7c26f25264666d4ba083b93d2f6f9"
assert os.path.normcase(local.__file__) == os.path.normcase(
    os.path.join(SOURCE, "Lib", "pathlib", "_local.py"))
with open(local.__file__, "rb") as source_file:
    candidate_bytes = source_file.read()
candidate_hash = hashlib.sha256(candidate_bytes).hexdigest()
assert candidate_hash == "ffdec1568d6c4f6826ecfb8dfeaa77f9647ebc90598766ab353787927b019b3c"
baseline_bytes = subprocess.check_output(
    ["git", "-C", SOURCE, "show", BASE + ":Lib/pathlib/_local.py"])
assert hashlib.sha256(baseline_bytes).hexdigest() == (
    "0530b4186ec5845e000bedf5817ff1ac970b9a39a6891ba6789a1776abdea42b")
tree = ast.parse(baseline_bytes)
pure = next(node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "PurePath")
function = next(node for node in pure.body
                if isinstance(node, ast.FunctionDef) and node.name == "relative_to")
namespace = dict(vars(local))
exec(compile(ast.Module(body=[function], type_ignores=[]),
             "<pinned-baseline-relative_to>", "exec"), namespace)
baseline = namespace["relative_to"]
candidate = local.PurePath.relative_to
assert local.PurePath.relative_to is candidate

NUMBER = 10000
ORDER = ["AB", "BA", "AB", "BA", "AB"]
report = {
    "status": "predeclared",
    "python": sys.version,
    "executable": sys.executable,
    "module_origin": local.__file__,
    "baseline_sha256": hashlib.sha256(baseline_bytes).hexdigest(),
    "candidate_sha256": candidate_hash,
    "number": NUMBER,
    "order": ORDER,
    "decision_rule": {
        "windows_success_median_improvement_at_least": 0.10,
        "any_windows_success_regression_at_most": 0.20,
        "any_fallback_regression_at_most": 0.20,
        "scope": "A gate only; not a standard-build speedup or adoption criterion",
    },
    "case_set": {
        "classes": ["WindowsPath", "PureWindowsPath", "PurePosixPath"],
        "cases": ["shallow", "deep", "equal", "root",
                  "nonancestor", "walk_up", "subclass"],
        "deep_components": 16,
    },
    "cases": [],
    "caveats": [
        "Hot cached reusable path objects, no timed constructors.",
        "timeit default GC-disabled loop; same invoke wrapper for both arms.",
        "One warm call per arm/case; five fixed paired repeats, no retries.",
        "No full build, process CPU, Mac or parity inference from microtimings.",
    ],
}
output = os.path.join(HERE, "MICRO-RESULTS.json")


def save():
    with open(output, "w", encoding="utf-8", newline="\n") as result_file:
        json.dump(report, result_file, indent=2)


def invoke(method, path, other, kwargs):
    try:
        return ("ok", str(method(path, other, **kwargs)))
    except ValueError as error:
        return ("ValueError", str(error))


save()
for cls in (pathlib.WindowsPath, pathlib.PureWindowsPath, pathlib.PurePosixPath):
    root = "C:/" if cls.parser is local.ntpath else "/"
    deep_base = root + "/".join("part" + str(i) for i in range(16))
    cases = [
        ("shallow", cls(root + "a/Leaf"), cls(root + "a"), {}),
        ("deep", cls(deep_base + "/Leaf"), cls(root + "part0"), {}),
        ("equal", cls(root + "a/Leaf"), cls(root + "a/Leaf"), {}),
        ("root", cls(deep_base + "/Leaf"), cls(root), {}),
        ("nonancestor", cls(root + "a/Leaf"), cls(root + "other"), {}),
        ("walk_up", cls(root + "a/Leaf"), cls(root + "other"), {"walk_up": True}),
    ]

    class Subclass(cls):
        pass

    cases.append(("subclass", Subclass(root + "a/Leaf"), cls(root + "a"), {}))
    for name, path, other, kwargs in cases:
        expected = invoke(baseline, path, other, kwargs)
        assert invoke(candidate, path, other, kwargs) == expected
        row = {"class": cls.__name__, "case": name, "self": str(path),
               "other": str(other), "kwargs": kwargs,
               "result": expected, "repeats": []}
        timers = {
            arm: timeit.Timer("invoke(method, path, other, kwargs)",
                             globals=dict(invoke=invoke, method=method, path=path,
                                          other=other, kwargs=kwargs))
            for arm, method in (("A", baseline), ("B", candidate))
        }
        for order in ORDER:
            pair = {"order": order}
            for arm in order:
                pair[arm] = timers[arm].timeit(number=NUMBER)
            row["repeats"].append(pair)
        for arm in "AB":
            values = [pair[arm] for pair in row["repeats"]]
            row[arm] = {"median_seconds": statistics.median(values),
                        "range_seconds": [min(values), max(values)]}
        row["saving_fraction"] = (
            1 - row["B"]["median_seconds"] / row["A"]["median_seconds"])
        report["cases"].append(row)
        save()
windows = [row for row in report["cases"] if row["class"] != "PurePosixPath"
           and row["case"] in ("shallow", "deep", "equal", "root")]
fallbacks = [row for row in report["cases"]
             if row["case"] in ("nonancestor", "walk_up", "subclass")]
aggregate = statistics.median(row["saving_fraction"] for row in windows)
regressions = [row["class"] + "." + row["case"] for row in windows + fallbacks
               if row["saving_fraction"] < -0.20]
report.update(status="complete",
              windows_success_median_saving_fraction=aggregate,
              substantial_regressions=regressions,
              phase_b_gate_pass=aggregate >= 0.10 and not regressions)
save()
for row in report["cases"]:
    print(row["class"], row["case"], "saving_percent",
          round(row["saving_fraction"] * 100, 2))
print("PHASE_B_GATE", report["phase_b_gate_pass"],
      "WINDOWS_SUCCESS_MEDIAN_SAVING", aggregate,
      "SUBSTANTIAL_REGRESSIONS", regressions)
