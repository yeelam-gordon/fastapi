"""One offline stock-uv pathlib v2 screen; reused P22 build/validation runner."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tarfile
import time
import uuid

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
REV = "79cab5bed28b24d92c185d236feb33f5783dfeb3"
SOURCE = Path(r"Q:\fastapi\Generated Files\worktrees\source-fastapi")
PREPARED = Path(r"C:\fastapi-arm-build-lab\frontends-2a73e36a\c87512b2b70d")
PYTHON = Path(
    r"C:\Users\yeelam\AppData\Roaming\uv\python\cpython-3.13-windows-aarch64-none\python.exe"
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    identifier = uuid.uuid4().hex[:12]
    root = Path(r"C:\fastapi-arm-build-lab") / ("pathlib-v2-" + identifier)
    evidence = HERE / ("v2-build-" + identifier)
    root.mkdir(exist_ok=False)
    evidence.mkdir(exist_ok=False)
    for folder in ("tools", "wheelhouse", "cache", "samples"):
        (root / folder).mkdir()
    report = {
        "status": "preparing",
        "root": str(root),
        "revision": REV,
        "samples": [],
        "schedule": ["AB", "BA", "AB", "BA", "AB"],
        "decision_rule": "candidate only if B median >=5% faster and at least 4/5 paired savings positive; otherwise reject",
        "ephemeral_pyc_counts": "unmeasured",
        "aggregate_cpu": "unmeasured",
    }

    def save():
        (evidence / "results.json").write_text(json.dumps(report, indent=2) + "\n")

    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("UV_", "PIP_", "PYTHON"))
    }
    report["removed_inherited_python_variables"] = {
        k: v for k, v in os.environ.items() if k.startswith("PYTHON")
    }
    env.update(PYTHONNOUSERSITE="1")
    env["PATH"] = str(root / "tools") + os.pathsep + env["PATH"]
    preflight_temp = root / "preflight-temp"
    preflight_temp.mkdir()
    env.update(TEMP=str(preflight_temp), TMP=str(preflight_temp), TMPDIR=str(preflight_temp))
    expected_base = "0530b4186ec5845e000bedf5817ff1ac970b9a39a6891ba6789a1776abdea42b"
    expected_candidate = "b6616ee0240d1ced9e2ff3f02dcfbbe0f30e7c5d8b751e6f9f986cce4f4a1e3e"
    source_relative = Path("Lib") / "pathlib" / "_local.py"
    if sha(PYTHON.parent / source_relative) != expected_base:
        raise ValueError("actual managed source mismatch; no normalization")
    candidate_source = HERE / "cpython" / source_relative
    if sha(candidate_source) != expected_candidate:
        raise ValueError("reviewed candidate source mismatch")
    runtimes = {}
    manifests = {}
    for arm in "AB":
        prefix = root / ("runtime-" + arm)
        shutil.copytree(PYTHON.parent, prefix, copy_function=shutil.copy2)
        if arm == "B":
            (prefix / source_relative).write_bytes(candidate_source.read_bytes())
        runtimes[arm] = prefix / PYTHON.name
        files = [p for p in prefix.rglob("*") if p.is_file()]
        if any(p.stat().st_nlink != 1 for p in files):
            raise ValueError("runtime copy contains hardlinks")
        manifests[arm] = {p.relative_to(prefix).as_posix(): sha(p) for p in files}
        (evidence / ("runtime-" + arm + ".json")).write_text(json.dumps(manifests[arm], indent=2))
    changed = {p for p in manifests["A"].keys() | manifests["B"].keys()
               if manifests["A"].get(p) != manifests["B"].get(p)}
    if changed != {"Lib/pathlib/_local.py"}:
        raise ValueError("runtime copies differ beyond reviewed source")
    report["runtime_copy_policy"] = {
        "A": str(runtimes["A"]), "B": str(runtimes["B"]),
        "only_initial_difference": sorted(changed), "all_copy_files_link_count": 1,
        "base_source_sha256": expected_base, "candidate_source_sha256": expected_candidate,
        "note": "Full independent copies, including existing pyc; default bytecode writes may subsequently change derived caches.",
    }
    uv = root / "tools" / "uv.exe"
    shutil.copy2(PREPARED / "tools" / "uv.exe", uv)
    wheel = root / "wheelhouse" / "pdm_backend-2.5.0-py3-none-any.whl"
    shutil.copy2(PREPARED / "wheelhouse" / wheel.name, wheel)
    if sha(uv) != "ec27977d62b5f6091bce410a8e69d40d07541803314e0120905c0ad0affaa5cc":
        raise ValueError("uv hash differs from existing frontend receipt")
    if sha(wheel) != "5b8746b567a16a1fd506ce66ee28e89d46374526f52238aa1b96cc2c08245c63":
        raise ValueError("backend wheel hash differs from existing receipt")
    validator_path = root / "tools" / "validate.py"
    shutil.copy2(LAB / "candidate" / "validate.py", validator_path)
    spec = importlib.util.spec_from_file_location("validator", validator_path)
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    oracle_path = Path(
        r"Q:\fastapi\Generated Files\arm-build\results\ci-40814588064\macos\ci\artifacts\prepare-baseline"
    )
    oracle = validator.inventory(oracle_path)
    (evidence / "oracle.json").write_text(json.dumps(oracle, indent=2))
    report["oracle"] = {
        "path": str(oracle_path),
        "artifacts": {p.name: sha(p) for p in oracle_path.iterdir() if p.is_file()},
        "note": "Existing independent Mac standard-build oracle; exact member/payload/metadata checks below establish applicability, with five expected stock Windows mode failures retained.",
    }
    constraint = root / "constraints.txt"
    constraint.write_text("pdm-backend==2.5.0\n")
    archive_path = root / "source.tar"
    archive_argv = [
        "git", "-c", "core.autocrlf=false", "-C", str(SOURCE),
        "archive", "--format=tar", f"--output={archive_path}", REV,
    ]
    subprocess.run(archive_argv, check=True, env=env)
    report["archive_argv"] = archive_argv
    with tarfile.open(archive_path) as archive:
        if archive.pax_headers.get("comment") != REV:
            raise ValueError("archive source commit mismatch")
        source_manifest = {
            m.name: {
                "sha256": hashlib.sha256(archive.extractfile(m).read()).hexdigest(),
                "mode": m.mode,
                "size": m.size,
            }
            for m in archive if m.isfile()
        }
    (evidence / "source-manifest.json").write_text(json.dumps(source_manifest, indent=2))
    report["hashes"] = {
        "uv": sha(uv), "python": sha(PYTHON),
        "python313.dll": sha(PYTHON.parent / "python313.dll"),
        "backend_wheel": sha(wheel), "source_archive": sha(archive_path),
        "source_manifest": sha(evidence / "source-manifest.json"),
        "validator": sha(validator_path), "orchestrator": sha(Path(__file__)),
        "constraints": sha(constraint),
    }
    identity_env = dict(env, PYTHONDONTWRITEBYTECODE="1")
    report["uv_version"] = subprocess.check_output(
        [str(uv), "--version"], env=identity_env, text=True
    ).strip()
    identity = subprocess.check_output(
        [str(PYTHON), "-B", "-I", "-c",
         "import sys,sysconfig,json,platform;print(json.dumps(dict(version=sys.version,executable=sys.executable,platform=sysconfig.get_platform(),machine=platform.machine())))"],
        env=identity_env, text=True,
    )
    report["python_identity"] = json.loads(identity)
    if "3.13.15" not in identity or "win-arm64" not in identity:
        raise ValueError("wrong runtime")
    probe = (
        "import sys,sysconfig,json,pathlib._local,hashlib,ctypes;"
        "b=ctypes.create_unicode_buffer(32768);"
        "ctypes.windll.kernel32.GetModuleFileNameW(ctypes.c_void_p(sys.dllhandle),b,len(b));"
        "p=pathlib._local.__file__;"
        "print(json.dumps(dict(version=sys.version,executable=sys.executable,"
        "platform=sysconfig.get_platform(),prefix=sys.base_prefix,"
        "pathlib_origin=p,pathlib_sha256=hashlib.sha256(open(p,'rb').read()).hexdigest(),"
        "shared_library=b.value)))"
    )
    report["runtime_identities"] = {}
    for arm in "AB":
        selected = subprocess.check_output(
            [str(uv), "--no-config", "--offline", "--cache-dir", str(root / "cache"), "python", "find",
             "--no-python-downloads", str(runtimes[arm])], env=identity_env, text=True).strip()
        if Path(selected).resolve() != runtimes[arm].resolve():
            raise ValueError("uv selected an unexpected Python")
        receipt = json.loads(subprocess.check_output(
            [selected, "-B", "-I", "-c", probe], env=identity_env, text=True))
        expected = expected_base if arm == "A" else expected_candidate
        if (receipt["pathlib_sha256"] != expected
                or Path(receipt["pathlib_origin"]).resolve() != (runtimes[arm].parent / source_relative).resolve()
                or Path(receipt["shared_library"]).resolve() != (runtimes[arm].parent / "python313.dll").resolve()
                or receipt["platform"] != "win-arm64" or "3.13.15" not in receipt["version"]):
            raise ValueError("uv-selected runtime/pathlib/shared-library identity mismatch")
        receipt["uv_find_argv"] = [str(uv), "--no-config", "--offline", "--cache-dir", str(root / "cache"), "python", "find",
                                   "--no-python-downloads", str(runtimes[arm])]
        receipt["probe_argv"] = [selected, "-B", "-I", "-c", probe]
        receipt["exe_sha256"] = sha(runtimes[arm])
        receipt["dll_sha256"] = sha(runtimes[arm].parent / "python313.dll")
        report["runtime_identities"][arm] = receipt
    report["common_environment"] = {
        k: v for k, v in env.items()
        if k.startswith(("UV_", "PIP_", "PYTHON")) or k == "PATH"
    }
    report["policy_delta"] = {
        "A": {"PYTHONDONTWRITEBYTECODE": None, "PYTHONPYCACHEPREFIX": None},
        "B": {"PYTHONDONTWRITEBYTECODE": None, "PYTHONPYCACHEPREFIX": None},
        "scope": "per subprocess env dictionary; no os.environ modification",
    }
    save()
    expected_mode_names = {
        "fastapi-0.162.0/scripts/" + n
        for n in ("format.sh", "lint.sh", "test-cov-html.sh", "test-cov.sh", "test.sh")
    }
    reference = None

    def sample(label, arm, timed):
        nonlocal reference
        work = root / "samples" / label
        work.mkdir()
        source, output, temp = (work / n for n in ("source", "output", "temp"))
        for path in (source, output, temp):
            path.mkdir()
        with tarfile.open(archive_path) as archive:
            archive.extractall(source, filter="data")
        actual_source = {
            p.relative_to(source).as_posix(): sha(p)
            for p in source.rglob("*") if p.is_file()
        }
        if actual_source != {n: v["sha256"] for n, v in source_manifest.items()}:
            raise ValueError("source bytes differ")
        child_env = dict(env, TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp))
        child_env.pop("PYTHONDONTWRITEBYTECODE", None)
        child_env.pop("PYTHONPYCACHEPREFIX", None)
        argv = [
            str(uv), "--no-config", "--offline", "--cache-dir", str(root / "cache"),
            "build", str(source), "--python", str(runtimes[arm]), "--no-python-downloads",
            "--no-index", "--find-links", str(wheel.parent),
            "--build-constraints", str(constraint), "--out-dir", str(output),
            "--no-create-gitignore",
        ]
        row = {
            "label": label, "arm": arm, "timed": timed, "argv": argv,
            "cwd": str(source), "temp": str(temp), "source_bytes_verified": True,
            "policy": report["policy_delta"][arm],
            "stdout": label + ".stdout.log", "stderr": label + ".stderr.log",
        }
        report["samples"].append(row)
        save()
        with (evidence / row["stdout"]).open("wb") as out, (evidence / row["stderr"]).open("wb") as err:
            start = time.perf_counter()
            result = subprocess.run(argv, cwd=source, env=child_env, stdout=out, stderr=err, timeout=120)
            row["wall_seconds"] = time.perf_counter() - start
        row["returncode"] = result.returncode
        save()
        if result.returncode:
            raise RuntimeError(label + " failed; no replacement")
        inventory = validator.inventory(output)
        oracle_check = validator.compare(oracle, inventory)
        differences = oracle_check["differences"]
        if {d.get("name") for d in differences} != expected_mode_names:
            raise ValueError("unexpected oracle differences")
        for d in differences:
            expected, actual = dict(d["expected"]), dict(d["actual"])
            if d["kind"] != "sdist" or expected.pop("mode") != 0o755 or actual.pop("mode") != 0o644 or expected != actual:
                raise ValueError("oracle difference beyond known five script modes")
        if reference is None:
            reference = inventory
        same_os = validator.compare(reference, inventory)
        if not same_os["strict_pass"]:
            raise ValueError("normal Windows semantics regressed")
        post_source = {
            n: sha(source / n) for n in source_manifest
        }
        if post_source != actual_source:
            raise ValueError("input source bytes changed")
        row["validation"] = {
            "oracle_strict_pass": False, "oracle_differences": differences,
            "oracle_payload_metadata_members_record_pass": True,
            "same_windows_full_inventory_pass": True,
            "source_payloads_unchanged": True,
            "sdist_members": len(inventory["sdist"]),
            "wheel_members": len(inventory["wheel"]),
            "artifact_sha256": {p.name: sha(p) for p in output.iterdir()},
        }
        (evidence / (label + ".inventory.json")).write_text(json.dumps(inventory, indent=2))
        save()
        print(label, round(row["wall_seconds"], 6), "validated", flush=True)

    try:
        report["status"] = "running"
        for arm in "AB":
            sample("warmup-" + arm, arm, False)
        for pair, order in enumerate(report["schedule"], 1):
            for arm in order:
                sample(f"pair-{pair}-{arm}", arm, True)
        summary = {}
        for arm in "AB":
            values = [r["wall_seconds"] for r in report["samples"] if r["timed"] and r["arm"] == arm]
            summary[arm] = {"samples": values, "median": statistics.median(values), "min": min(values), "max": max(values)}
        pairs = []
        for pair in range(1, 6):
            a, b = [next(r["wall_seconds"] for r in report["samples"] if r["label"] == f"pair-{pair}-{arm}") for arm in "AB"]
            pairs.append({"pair": pair, "A_minus_B_seconds": a - b, "saving_percent": 100 * (a - b) / a})
        saving = 100 * (summary["A"]["median"] - summary["B"]["median"]) / summary["A"]["median"]
        report.update(status="complete", summary=summary, pairs=pairs, median_saving_percent=saving,
                      verdict="candidate" if saving >= 5 and sum(p["A_minus_B_seconds"] > 0 for p in pairs) >= 4 else "reject")
        save()
        print(json.dumps({k: report[k] for k in ("summary", "pairs", "median_saving_percent", "verdict")}, indent=2))
    except BaseException as exc:
        report.update(status="failed-no-retry", error=repr(exc))
        save()
        raise


if __name__ == "__main__":
    main()
