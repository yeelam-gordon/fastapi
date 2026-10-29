"""Tiny import-cache flag probe; not a packaging build or performance measurement."""

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path


def main():
    here = Path(__file__).resolve().parent
    root = here / (".probe-" + uuid.uuid4().hex)
    root.mkdir()
    report = {"python": sys.executable, "cases": []}
    try:
        for label, flags in (
            ("sdk-before", ["-E", "-s"]),
            ("sdk-explicit-B", ["-B", "-E", "-s"]),
            ("identity-before", ["-I"]),
            ("identity-explicit-B", ["-B", "-I"]),
        ):
            source = root / label
            source.mkdir()
            module = source / "fixture_module.py"
            payload = b"value = 42\n"
            module.write_bytes(payload)
            script = (
                "import sys,json;"
                f"sys.path.insert(0,{str(source)!r});"
                "import fixture_module;"
                "print(json.dumps(dict(dont_write_bytecode=sys.dont_write_bytecode,"
                "value=fixture_module.value)))"
            )
            command = [sys.executable, *flags, "-c", script]
            env = os.environ.copy()
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            result = subprocess.run(command, env=env, capture_output=True)
            (here / (label + ".log")).write_bytes(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError(f"{label} exited {result.returncode}")
            row = {
                "label": label,
                "command": command,
                "returncode": result.returncode,
                "identity": json.loads(result.stdout),
                "pyc_files": [
                    str(p.relative_to(source)) for p in source.rglob("*.pyc")
                ],
                "source_unchanged": module.read_bytes() == payload,
            }
            report["cases"].append(row)
            blocked = "-B" in flags
            if (
                row["identity"]["dont_write_bytecode"] != blocked
                or bool(row["pyc_files"]) == blocked
                or not row["source_unchanged"]
            ):
                raise RuntimeError(f"Unexpected bytecode policy: {row}")
    finally:
        shutil.rmtree(root)
        report["probe_root_removed"] = not root.exists()
        (here / "probe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        "Both -E and -I ignore environment-only suppression; explicit -B prevents pyc writes."
    )


if __name__ == "__main__":
    main()
