"""Reproduce CPython flag semantics using only an owned, disposable tiny module."""

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent / (".probe-" + uuid.uuid4().hex)
    root.mkdir()
    results = []
    try:
        for label, flags in (
            ("environment_only", []),
            ("sdk_flags", ["-E", "-s"]),
            ("explicit_B", ["-B", "-E", "-s"]),
        ):
            directory = root / label
            directory.mkdir()
            (directory / "tiny_public_module.py").write_text(
                "VALUE = 42\n", encoding="utf-8"
            )
            env = os.environ.copy()
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            code = (
                "import json,sys,tiny_public_module;"
                "print(json.dumps(dict(dont_write_bytecode=sys.dont_write_bytecode,"
                "value=tiny_public_module.VALUE)))"
            )
            child = subprocess.run(
                [sys.executable, *flags, "-c", code],
                cwd=directory,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            item = json.loads(child.stdout)
            item.update(
                case=label,
                flags=flags,
                pyc_files=[str(p.relative_to(root)) for p in directory.rglob("*.pyc")],
            )
            results.append(item)
        expected = [False, True, False]
        if [bool(item["pyc_files"]) for item in results] != expected:
            raise RuntimeError(f"Unexpected bytecode behavior: {results!r}")
        print(
            json.dumps(
                {"python": sys.version, "executable": sys.executable, "cases": results},
                indent=2,
            )
        )
    finally:
        shutil.rmtree(root)


if __name__ == "__main__":
    main()
