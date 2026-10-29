"""Untimed, intrusive diagnostic only: observe transient backend bytecode."""

import json
import os
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(r"C:\fastapi-arm-build-lab\runtime-ab-2a73e36a\attempt-2")


def main():
    report = json.loads((ROOT / "evidence" / "results.json").read_text())
    observations = []
    for kind in ("uv", "pip"):
        for name in ("stock", "managed"):
            original = next(row for row in report["trials"]
                            if row["command"] == kind and row["runtime"] == name)
            label = f"pyc-diagnostic-{kind}-{name}"
            output = ROOT / "outputs" / label
            output.mkdir()
            argv = [arg.replace(original["label"], label) for arg in original["argv"]]
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith(("PIP_", "UV_", "PYTHON"))}
            env.update(report["environment"])
            env.update(UV_CACHE_DIR=str(ROOT / "cache" / name / kind / "uv"),
                       PIP_CACHE_DIR=str(ROOT / "cache" / name / kind / "pip"))
            seen = set()
            peak = [0]
            stop = threading.Event()

            def observe():
                while not stop.is_set():
                    paths = set()
                    for directory in (ROOT / "temp", ROOT / "cache" / name / kind):
                        try:
                            paths.update(str(path.relative_to(ROOT))
                                         for path in directory.rglob("*.pyc")
                                         if "pdm" in str(path).lower())
                        except FileNotFoundError:
                            pass
                    seen.update(paths)
                    peak[0] = max(peak[0], len(paths))
                    stop.wait(0.1)

            thread = threading.Thread(target=observe)
            thread.start()
            start = time.perf_counter()
            try:
                with (ROOT / "evidence" / (label + ".stdout.txt")).open("wb") as out, (
                        ROOT / "evidence" / (label + ".stderr.txt")).open("wb") as err:
                    result = subprocess.run(argv, env=env, cwd=ROOT / "source",
                                            stdout=out, stderr=err, timeout=120)
            finally:
                stop.set()
                thread.join()
            assert result.returncode == 0
            observations.append(dict(runtime=name, command=kind, argv=argv,
                                     peak_observed_pdm_pycs=peak[0],
                                     distinct_paths=sorted(seen),
                                     diagnostic_only=True,
                                     wall_seconds=time.perf_counter() - start))
            print(label, peak[0], flush=True)
    (ROOT / "evidence" / "transient-pycs.json").write_text(
        json.dumps(observations, indent=2))


if __name__ == "__main__":
    main()
