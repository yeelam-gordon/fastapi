"""Replay captured wrapper interpreter flags against a real owned tiny module."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "review_guards", HERE / "test_review_guards.py"
)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def main():
    fixture = review.fixtures.WrapperTests()
    fixture.setUp()
    observations = []
    try:
        captured = {}

        def capture(argv, **kwargs):
            captured[kwargs["log"].stem] = argv
            return fixture.fake_process(argv, **kwargs)

        with patch.object(review.wrapper, "run_process", side_effect=capture):
            if review.wrapper.execute(fixture.args):
                raise RuntimeError("Wrapper fixture failed")
        for phase in ("identity", "sdk"):
            argv = captured[phase]
            flags = argv[1 : argv.index("-c")] if phase == "identity" else argv[1:4]
            directory = fixture.root / ("real-" + phase)
            directory.mkdir()
            module = directory / "tiny_public_module.py"
            module.write_text("VALUE = 42\n", encoding="utf-8")
            code = (
                "import importlib.util,json,sys;"
                f"s=importlib.util.spec_from_file_location('tiny',{str(module)!r});"
                "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
                "print(json.dumps(dict(dont_write_bytecode=sys.dont_write_bytecode,"
                "value=m.VALUE)))"
            )
            result = subprocess.run(
                [sys.executable, *flags, "-c", code],
                cwd=directory,
                capture_output=True,
                text=True,
                check=True,
            )
            actual = json.loads(result.stdout)
            caches = list(directory.rglob("__pycache__"))
            bytecode = list(directory.rglob("*.pyc"))
            if actual["dont_write_bytecode"] is not True or caches or bytecode:
                raise RuntimeError("Effective bytecode suppression failed")
            observations.append(
                {
                    "phase": phase,
                    "actual_wrapper_flags": flags,
                    "actual_child": actual,
                    "pycache_directories": [],
                    "pyc_files": [],
                }
            )
        print(json.dumps({"executable": sys.executable, "cases": observations}, indent=2))
    finally:
        fixture.doCleanups()


if __name__ == "__main__":
    main()
