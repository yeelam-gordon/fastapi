"""Owned, untimed preparation and serial C: readiness; never a performance comparison."""

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tarfile
import time
import uuid
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parent
HERE = EVIDENCE / "readiness-v2"
PROTOCOL = EVIDENCE.parent
MASTER = Path(r"Q:\fastapi\Generated Files\arm-build")
SOURCE_REPO = Path(r"Q:\fastapi\Generated Files\worktrees\source-fastapi")
REV = "79cab5bed28b24d92c185d236feb33f5783dfeb3"
BASE = Path(r"C:\fastapi-arm-build-lab\caller-readiness-2a73e36a")
PYTHON = Path(
    r"C:\Users\yeelam\AppData\Roaming\uv\python\cpython-3.13-windows-aarch64-none\python.exe"
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    HERE.mkdir(exist_ok=False)
    root = BASE
    if root.exists():
        root = BASE / ("retry-" + uuid.uuid4().hex)
    root.mkdir()
    code = root / "code"
    (code / "protocol").mkdir(parents=True)
    shutil.copytree(
        PROTOCOL.parent / "candidate",
        code / "candidate",
        ignore=shutil.ignore_patterns("__pycache__", "scratch"),
    )
    for name in ("isolated_build.py", "backend.lock"):
        shutil.copy2(PROTOCOL / name, code / "protocol" / name)
    tools, wheels = root / "tools", root / "wheels"
    tools.mkdir()
    wheels.mkdir()
    receipts = {}
    for original, target in (
        (MASTER / "tools" / "uv.exe", tools / "uv.exe"),
        (
            Path(
                r"C:\fastapi-arm-build-lab\copilot-2a73e36a\wheelhouse\pdm_backend-2.5.0-py3-none-any.whl"
            ),
            wheels / "pdm_backend-2.5.0-py3-none-any.whl",
        ),
    ):
        shutil.copy2(original, target)
        assert digest(original) == digest(target)
        receipts[str(target)] = digest(target)
    assert (
        receipts[str(next(wheels.iterdir()))]
        == "5b8746b567a16a1fd506ce66ee28e89d46374526f52238aa1b96cc2c08245c63"
    )
    archive_path = root / "source.tar"
    subprocess.run(
        [
            "git",
            "-c",
            "core.autocrlf=false",
            "-C",
            str(SOURCE_REPO),
            "archive",
            "--format=tar",
            f"--output={archive_path}",
            REV,
        ],
        check=True,
    )
    source = root / "source"
    source.mkdir()
    with tarfile.open(archive_path) as archive:
        archive.extractall(source, filter="data")
    tree = subprocess.check_output(
        ["git", "-C", str(SOURCE_REPO), "ls-tree", "-rz", REV]
    )
    manifest = {}
    for row in tree.split(b"\0"):
        if not row:
            continue
        meta, name = row.split(b"\t", 1)
        mode, kind, _ = meta.split()
        assert kind == b"blob" and mode in (b"100644", b"100755")
        name = name.decode()
        manifest[name] = {
            "mode": 0o755 if mode == b"100755" else 0o644,
            "sha256": digest(source / name),
        }
    manifest_path = root / "source-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    receipts["source_archive_sha256"] = digest(archive_path)
    receipts["source_manifest_sha256"] = digest(manifest_path)
    receipts["base_python_sha256"] = digest(PYTHON)
    receipts["base_python_dll_sha256"] = digest(PYTHON.parent / "python313.dll")
    receipts["backend_lock_sha256"] = digest(code / "protocol" / "backend.lock")
    receipts["producer_commit"] = "3c10320c9ce03966a4d5f51cd8e8076a1095d235"
    receipts["code"] = {str(p.relative_to(code)): digest(p) for p in code.rglob("*.py")}
    oracle = (
        MASTER
        / "results"
        / "ci-40814588064"
        / "macos"
        / "ci"
        / "artifacts"
        / "prepare-baseline"
    )
    spec = importlib.util.spec_from_file_location(
        "validator", code / "candidate" / "validate.py"
    )
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    expected = validator.inventory(oracle)
    (HERE / "oracle-manifest.json").write_text(json.dumps(expected, indent=2))
    summary = {"root": str(root), "revision": REV, "receipts": receipts, "samples": []}
    temp = root / "temp"
    temp.mkdir()
    env = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME"):
        env.pop(name, None)
    env.update(TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp), PYTHONNOUSERSITE="1")
    baseline = [
        str(tools / "uv.exe"),
        "--no-config",
        "--offline",
        "--cache-dir",
        str(root / "cache"),
        "build",
        str(source),
        "--python",
        str(PYTHON),
        "--no-python-downloads",
        "--no-index",
        "--find-links",
        str(wheels),
        "--build-constraints",
        str(code / "protocol" / "backend.lock"),
        "--out-dir",
        str(root / "B-output"),
    ]
    baseline_files = {
        p.relative_to(source).as_posix(): digest(p)
        for p in source.rglob("*")
        if p.is_file()
    }
    environment_roots = set()
    for label, workers in (("S1", 1), ("S3", 3), ("B", None), ("S3-after-B", 3)):
        if label == "B":
            clock = time.perf_counter()
            with (HERE / "B.log").open("wb") as stream:
                result = subprocess.run(
                    baseline, cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT
                )
            summary["baseline"] = {
                "command": baseline,
                "returncode": result.returncode,
                "whole_invocation_wall_seconds": time.perf_counter() - clock,
            }
            if result.returncode == 0:
                summary["baseline"]["validation"] = validator.compare(
                    expected, validator.inventory(root / "B-output")
                )
            (HERE / "summary.json").write_text(json.dumps(summary, indent=2))
            if result.returncode:
                raise RuntimeError(f"Stock B failed: {result.returncode}")
            continue
        report_path = root / f"{label}.json"
        output = root / f"{label}-output"
        command = [
            str(PYTHON),
            str(code / "protocol" / "isolated_build.py"),
            "--uv",
            str(tools / "uv.exe"),
            "--python",
            str(PYTHON),
            "--source",
            str(source),
            "--source-manifest",
            str(manifest_path),
            "--out-dir",
            str(output),
            "--workers",
            str(workers),
            "--cache-dir",
            str(root / "cache"),
            "--wheelhouse",
            str(wheels),
            "--report",
            str(report_path),
        ]
        clock = time.perf_counter()
        with (HERE / f"{label}-outer.log").open("wb") as stream:
            result = subprocess.run(
                command, cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT
            )
        wall = time.perf_counter() - clock
        shutil.copy2(report_path, HERE / report_path.name)
        shutil.copytree(
            report_path.with_name(report_path.name + ".logs"), HERE / (label + ".logs")
        )
        row = {
            "label": label,
            "command": command,
            "returncode": result.returncode,
            "whole_invocation_wall_seconds": wall,
        }
        summary["samples"].append(row)
        receipt = json.loads(report_path.read_text(encoding="utf-8"))
        row["phase_clocks"] = receipt["phases"]
        row["identities"] = receipt["identities"]
        row["environment"] = receipt["environment"]
        row["fresh_unique_environment"] = (
            receipt["environment"]["root"] not in environment_roots
            and receipt["environment"]["existed_before"] is False
            and receipt["environment"]["exists_after_cleanup"] is False
            and not Path(receipt["environment"]["root"]).exists()
        )
        environment_roots.add(receipt["environment"]["root"])
        if result.returncode == 0:
            actual = validator.inventory(output / "artifacts")
            verdict = validator.compare(expected, actual)
            row["validation"] = verdict
            row["sdist_members"] = len(actual["sdist"])
            row["wheel_members"] = len(actual["wheel"])
            (HERE / f"{label}-inventory.json").write_text(json.dumps(actual, indent=2))
        current = {
            p.relative_to(source).as_posix(): digest(p)
            for p in source.rglob("*")
            if p.is_file()
        }
        row["source_unchanged"] = current == baseline_files
        row["canonical_payloads_unchanged"] = {n: current[n] for n in manifest} == {
            n: v["sha256"] for n, v in manifest.items()
        }
        row["manifest_unchanged"] = (
            digest(manifest_path) == receipts["source_manifest_sha256"]
        )
        (HERE / "summary.json").write_text(json.dumps(summary, indent=2))
        assert result.returncode == 0, row
        assert (
            row["validation"]["strict_pass"]
            and row["canonical_payloads_unchanged"]
            and row["manifest_unchanged"]
            and row["fresh_unique_environment"]
        )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
