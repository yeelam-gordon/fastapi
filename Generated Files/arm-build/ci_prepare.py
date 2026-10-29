"""Time provisioning separately and export native wheels for offline local use."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import sysconfig
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    if not sysconfig.get_platform().lower().endswith(("arm64", "aarch64")):
        raise RuntimeError(
            f"Native ARM64 interpreter required, got {sysconfig.get_platform()}"
        )
    output = ROOT / "results" / "bootstrap"
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / ("smoke.json" if args.smoke else "provision.json")
    report = {
        "status": "running",
        "python": sys.version,
        "machine": platform.machine(),
        "interpreter_platform": sysconfig.get_platform(),
        "platform": platform.platform(),
        "logical_cores": os.cpu_count(),
        "runner_image": os.environ.get("ImageVersion"),
        "runner_label": os.environ.get("RUNNER_OS"),
        "commands": [],
    }

    def run(command: list[str], phase: str) -> None:
        record = {"argv": command, "phase": phase}
        report["commands"].append(record)
        started = time.perf_counter()
        log = output / f"{phase}.log"
        with log.open("wb") as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
        record.update(
            returncode=result.returncode, seconds=time.perf_counter() - started
        )
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if result.returncode:
            print(log.read_text(encoding="utf-8", errors="replace"), file=sys.stderr)
            raise RuntimeError(f"{phase} failed with {result.returncode}")

    try:
        if args.smoke:
            wheels = list(
                (ROOT / "results" / "ci" / "artifacts" / "prepare-baseline").glob(
                    "*.whl"
                )
            )
            if len(wheels) != 1:
                raise RuntimeError("Expected one verified FastAPI wheel")
            run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    sys.executable,
                    "--require-hashes",
                    "--only-binary",
                    ":all:",
                    "-r",
                    str(ROOT / "smoke.lock"),
                ],
                "smoke-dependencies",
            )
            run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    sys.executable,
                    "--no-deps",
                    str(wheels[0]),
                ],
                "install-artifact",
            )
            # Run outside the checkout so importing FastAPI verifies the installed wheel.
            script = output / "artifact_smoke.py"
            script.write_text(
                "import fastapi\n"
                "from fastapi import FastAPI\n"
                "from fastapi.testclient import TestClient\n"
                "from pathlib import Path\n"
                f"assert not Path(fastapi.__file__).is_relative_to(Path({str(ROOT.parents[1] / 'fastapi')!r}))\n"
                "app = FastAPI()\n"
                "@app.get('/items/{item_id}')\n"
                "def read(item_id: int):\n"
                "    return {'item_id': item_id}\n"
                "with TestClient(app) as client:\n"
                "    assert client.get('/items/7').json() == {'item_id': 7}\n"
                "    assert client.get('/items/invalid').status_code == 422\n"
                "    assert client.get('/openapi.json').status_code == 200\n"
                "print(fastapi.__file__)\n",
                encoding="utf-8",
            )
            run([sys.executable, "-I", str(script)], "artifact-smoke")
        else:
            run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    sys.executable,
                    "--require-hashes",
                    "--only-binary",
                    ":all:",
                    "-r",
                    str(ROOT / "tooling.lock"),
                ],
                "install-tools",
            )
            run([sys.executable, "-m", "pip", "check"], "dependency-check")
            if sys.platform == "win32":
                wheelhouse = ROOT / "wheelhouse"
                wheelhouse.mkdir(exist_ok=True)
                run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "download",
                        "--only-binary=:all:",
                        "--require-hashes",
                        "-r",
                        str(ROOT / "tooling.lock"),
                        "-r",
                        str(ROOT / "smoke.lock"),
                        "--dest",
                        str(wheelhouse),
                    ],
                    "download-wheelhouse",
                )
                hashes = {
                    path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in sorted(wheelhouse.glob("*.whl"))
                }
                (wheelhouse / "sha256.json").write_text(
                    json.dumps(hashes, indent=2) + "\n", encoding="utf-8"
                )
        report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
