"""Time actual preflight statements only; instrumentation is diagnostic."""

import sys

sys.dont_write_bytecode = True

import ast
import json
import os
import time
from pathlib import Path

root = Path(sys.argv[1]).resolve()
os.chdir(root)
sys.path.insert(0, str(root / "code"))
import build

tree = ast.parse((root / "code" / "build.py").read_text())
function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build")
stop = next(i for i, n in enumerate(function.body)
            if isinstance(n, ast.ImportFrom) and n.module == "ops")
function.body = function.body[:stop]
module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
namespace = dict(vars(build))
exec(compile(module, str(root / "code" / "build.py"), "exec"), namespace)
phases, calls = {}, {"stat": 0, "lstat": 0}
for name in calls:
    original = getattr(os, name)

    def counted(*args, _name=name, _original=original, **kwargs):
        calls[_name] += 1
        return _original(*args, **kwargs)

    setattr(os, name, counted)
for name in ("source_files", "configuration"):
    original = namespace[name]

    def timed(*args, _name=name, _original=original, **kwargs):
        start, cpu = time.perf_counter(), time.process_time()
        before = dict(calls)
        try:
            return _original(*args, **kwargs)
        finally:
            phases[_name] = {
                "wall_seconds": time.perf_counter() - start,
                "process_cpu_seconds": time.process_time() - cpu,
                "python_os_calls": {n: calls[n] - before[n] for n in calls},
            }

    namespace[name] = timed
start, cpu = time.perf_counter(), time.process_time()
namespace["build"](root / "source", root / "source-manifest.json",
                   root / "unused-output", 3)
result = {
    "scope": "Actual build AST prefix before ops import; one diagnostic, no build",
    "wall_seconds": time.perf_counter() - start,
    "process_cpu_seconds": time.process_time() - cpu,
    "python_os_calls": calls,
    "phases": phases,
    "limitation": "Python API calls, not kernel operations; wrappers add overhead",
}
(root / "preflight.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
