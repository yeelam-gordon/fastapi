"""Run frozen fixture gates and genuine offline controller preparation, never measure."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab-root", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--source-checkout", type=Path, required=True)
    args = parser.parse_args()
    root = args.lab_root.resolve()
    code = root / "code"
    arm = code / "Generated Files" / "arm-build"
    protocol = arm / "protocol"
    python, uv = root / "env" / "Scripts" / "python.exe", root / "uv.exe"
    token = args.revision[:12] + "-" + uuid.uuid4().hex
    work = root / "attempts" / token
    work.mkdir(parents=True, exist_ok=False)
    evidence = Path(__file__).resolve().parent / "attempts" / token
    evidence.mkdir(parents=True, exist_ok=False)
    output = work / "controller-output"
    env = os.environ.copy()
    env.pop("PAIR_PROVISION_STARTED", None)
    env.update(
        TEMP=str(root / "scratch"),
        TMP=str(root / "scratch"),
        TMPDIR=str(root / "scratch"),
        UV_CACHE_DIR=str(root / "cache"),
        PIP_CACHE_DIR=str(root / "pip-cache"),
        UV_OFFLINE="1",
        UV_NO_INDEX="1",
        UV_NO_CONFIG="1",
        UV_PYTHON_DOWNLOADS="never",
        UV_FIND_LINKS=str(root / "wheelhouse"),
        PIP_NO_INDEX="1",
        PIP_FIND_LINKS=str(root / "wheelhouse"),
        PIP_DISABLE_PIP_VERSION_CHECK="1",
        PAIRED_TEST_UV=str(uv),
        PYTHONDONTWRITEBYTECODE="1",
    )
    receipt = {
        "schema": "actual-controller-preflight-v1",
        "status": "checking",
        "harness_revision": args.revision,
        "work": str(work),
        "controller_output": str(output),
        "commands": [],
        "campaign_samples": 0,
        "cpu_seconds": None,
        "campaign_authorized": False,
        "environment_changes": {
            key: env[key]
            for key in (
                "TEMP",
                "TMP",
                "TMPDIR",
                "UV_CACHE_DIR",
                "PIP_CACHE_DIR",
                "UV_OFFLINE",
                "UV_NO_INDEX",
                "UV_NO_CONFIG",
                "UV_PYTHON_DOWNLOADS",
                "UV_FIND_LINKS",
                "PIP_NO_INDEX",
                "PIP_FIND_LINKS",
                "PIP_DISABLE_PIP_VERSION_CHECK",
                "PAIRED_TEST_UV",
                "PYTHONDONTWRITEBYTECODE",
            )
        },
    }

    def run(argv, label, timeout=120):
        begin = time.perf_counter()
        with (evidence / (label + ".log")).open("xb") as log:
            result = subprocess.run(
                [str(value) for value in argv],
                cwd=work,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
        receipt["commands"].append(
            {
                "argv": [str(value) for value in argv],
                "cwd": str(work),
                "returncode": result.returncode,
                "wall": time.perf_counter() - begin,
                "log": label + ".log",
            }
        )
        if result.returncode:
            raise RuntimeError(f"{label} exited {result.returncode}; no retry")
        return (evidence / (label + ".log")).read_text(encoding="utf-8").strip()

    started = time.perf_counter()
    try:
        actual = run(["git", "-C", code, "rev-parse", "HEAD"], "revision")
        if actual != args.revision or len(actual) != 40:
            raise ValueError("Frozen checkout revision mismatch")
        if run(["git", "-C", code, "status", "--porcelain"], "clean-checkout"):
            raise ValueError("Frozen code checkout is not clean")
        receipt["uv_version_raw"] = run([uv, "--version"], "uv-version")
        for mode, flags in (("normal", ["-B"]), ("optimized", ["-B", "-O"])):
            for path in (
                protocol / "test_pairs.py",
                protocol / "test_owned_process.py",
                protocol / "test_isolated_build.py",
                arm / "candidate" / "test_candidate.py",
                arm / "candidate" / "test_reuse.py",
            ):
                run([python, *flags, path], mode + "-" + path.stem)
        run(
            [
                python,
                "-B",
                protocol / "measure_pairs.py",
                "--prepare",
                "--uv",
                uv,
                "--source-checkout",
                args.source_checkout,
                "--output",
                output,
            ],
            "actual-controller-prepare",
            timeout=300,
        )
        prepared = json.loads((output / "prepare.json").read_text())
        if prepared["status"] != "prepared":
            raise ValueError("Actual controller did not report prepared")
        if prepared["harness_revision"] != args.revision:
            raise ValueError("Controller prepared a different harness identity")
        sys.path.insert(0, str(protocol))
        import measure_pairs as controller

        if prepared["tool_hashes"] != controller.code_receipts():
            raise ValueError("Frozen tool inputs changed")
        manifest = json.loads((output / "source-manifest.json").read_text())
        if not controller.source_matches(output / "source", manifest):
            raise ValueError("Prepared source does not match canonical manifest")
        receipt["volumes"] = controller.volumes(
            [
                code,
                output,
                python,
                Path(sys.base_prefix),
                uv,
                root / "cache",
                root / "scratch",
                output / "wheelhouse",
            ]
        )
        receipt["runtime"] = controller.runtime_receipt()
        receipt["uv_binary"] = controller.binary_receipt(uv)
        receipt["tool_hashes"] = prepared["tool_hashes"]
        receipt["source"] = prepared["source"]
        receipt["wheels"] = prepared["wheels"]
        receipt["status"] = "prepared-awaiting-review-and-go"
    except Exception as exc:
        receipt["status"] = "blocked"
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        for name in (
            "prepare.json",
            "prepare-0.log",
            "prepare-1.log",
            "source-manifest.json",
        ):
            if (output / name).is_file():
                shutil.copyfile(output / name, evidence / name)
        receipt["preflight_and_preparation_wall"] = time.perf_counter() - started
        receipt["provision_scope"] = (
            "Existing native runtime and verified offline wheels reused; this "
            "attempt measures fixture gates and actual --prepare, not original "
            "runtime acquisition, prior provisioning or any package campaign."
        )
        receipt["orchestrator_sha256"] = hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest()
        (evidence / "preflight.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(json.dumps({"status": receipt["status"], "evidence": str(evidence)}))


if __name__ == "__main__":
    main()
