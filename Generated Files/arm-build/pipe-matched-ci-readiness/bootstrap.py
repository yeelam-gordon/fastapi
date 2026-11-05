"""Unchanged actual-Python binding before the stock coverage module."""

import json
import os
import runpy
import sys
from pathlib import Path

out = Path(os.environ["CORRECTNESS_OUTPUT"])
(out / "bootstrap.json").write_text(
    json.dumps(
        {
            "actual_python_pid": os.getpid(),
            "parent_pid": os.getppid(),
            "orig_argv": sys.orig_argv,
            "pytest_not_preimported": "pytest" not in sys.modules,
            "fastapi_not_preimported": "fastapi" not in sys.modules,
            "pycache_prefix": sys.pycache_prefix,
        }
    )
    + "\n",
    encoding="utf-8",
)
assert "pytest" not in sys.modules and "fastapi" not in sys.modules
sys.path.insert(0, os.environ["CORRECTNESS_SOURCE"])
sys.argv = ["coverage", *sys.argv[1:]]
runpy.run_module("coverage", run_name="__main__", alter_sys=True)
