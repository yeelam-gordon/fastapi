"""Fresh, offline caller isolation for the experimental SDK (not per-hook isolation)."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_process(argv, *, cwd, env, log):
    with log.open("wb") as stream:
        child = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        try:
            return child.wait()
        except BaseException as error:
            if os.name == "nt":
                killed = subprocess.run(
                    ["taskkill", "/PID", str(child.pid), "/T", "/F"],
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                if killed.returncode and child.poll() is None:
                    child.kill()
                    child.wait()
                    raise RuntimeError(
                        f"Process-tree termination failed: taskkill exit {killed.returncode}"
                    ) from error
            else:
                child.kill()
            child.wait()
            raise


def execute(args):
    started = time.perf_counter()
    report = {
        "schema_version": 1,
        "status": "running",
        "phases": [],
        "isolation": "fresh caller environment shared by both SDK hooks",
        "errors": [],
        "workers": args.workers,
    }
    owned = None
    owns_environment = False
    logs = None
    owns_logs = False
    report_path = args.report.resolve()
    try:
        source = args.source.resolve()
        output = args.out_dir.resolve()
        if (
            report_path == source
            or report_path.is_relative_to(source)
            or report_path == output
            or report_path.is_relative_to(output)
        ):
            raise ValueError("report must be outside source and output")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("x", encoding="utf-8") as stream:
            stream.write("{}\n")
        logs = report_path.with_name(report_path.name + ".logs")
        logs.mkdir(exist_ok=False)
        owns_logs = True
        if args.workers not in (1, 3):
            raise ValueError("workers must be 1 or 3")
        for key in (
            "uv",
            "python",
            "source",
            "source_manifest",
            "out_dir",
            "cache_dir",
            "wheelhouse",
        ):
            setattr(args, key, getattr(args, key).resolve())
        if args.out_dir.exists():
            raise ValueError("out-dir must initially be absent")
        for key in ("uv", "python", "source_manifest"):
            if not getattr(args, key).is_file():
                raise ValueError(f"{key} must be an existing file")
        for key in ("source", "wheelhouse"):
            if not getattr(args, key).is_dir():
                raise ValueError(f"{key} must be an existing directory")
        for path in (args.out_dir, report_path, args.cache_dir, args.wheelhouse):
            if path == args.source or path.is_relative_to(args.source):
                raise ValueError("working paths must be outside source")
        for path in (report_path, args.cache_dir, args.wheelhouse):
            if path == args.out_dir or path.is_relative_to(args.out_dir):
                raise ValueError("logs, cache and dependencies must be outside output")
        owned = report_path.parent / (".caller-env-" + uuid.uuid4().hex)
        report["environment"] = {
            "root": str(owned),
            "existed_before": owned.exists(),
            "exists_after_cleanup": None,
        }
        owned.mkdir(exist_ok=False)
        owns_environment = True
        scratch = owned / "scratch"
        scratch.mkdir()
        venv = owned / "venv"
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        env = os.environ.copy()
        removed = ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT")
        for name in removed:
            env.pop(name, None)
        changes = {
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "UV_OFFLINE": "1",
            "UV_NO_CONFIG": "1",
            "UV_PYTHON_DOWNLOADS": "never",
            "UV_CACHE_DIR": str(args.cache_dir),
            "TEMP": str(scratch),
            "TMP": str(scratch),
            "TMPDIR": str(scratch),
        }
        env.update(changes)
        report["environment_changes"] = {"unset": list(removed), "set": changes}
        report["identities"] = {
            "uv_sha256": sha256(args.uv),
            "base_python_sha256": sha256(args.python),
            "lock_sha256": sha256(HERE / "backend.lock"),
            "wrapper_sha256": sha256(Path(__file__)),
            "sdk_sha256": sha256(HERE.parent / "candidate" / "build.py"),
            "source_manifest_sha256": sha256(args.source_manifest),
        }

        def phase(name, argv):
            entry = {
                "phase": name,
                "argv": [str(v) for v in argv],
                "start_offset_seconds": time.perf_counter() - started,
                "log": str(logs / (name + ".log")),
                "returncode": None,
            }
            report["phases"].append(entry)
            clock = time.perf_counter()
            try:
                entry["returncode"] = run_process(
                    entry["argv"], cwd=scratch, env=env, log=Path(entry["log"])
                )
                if entry["returncode"]:
                    raise subprocess.CalledProcessError(
                        entry["returncode"], entry["argv"]
                    )
            finally:
                entry["seconds"] = time.perf_counter() - clock

        uv = [
            str(args.uv),
            "--no-config",
            "--offline",
            "--cache-dir",
            str(args.cache_dir),
        ]
        phase(
            "create",
            uv
            + [
                "venv",
                "--python",
                str(args.python),
                "--no-python-downloads",
                str(venv),
            ],
        )
        phase(
            "install",
            uv
            + [
                "pip",
                "install",
                "--python",
                str(python),
                "--require-hashes",
                "--no-index",
                "--only-binary",
                ":all:",
                "--find-links",
                str(args.wheelhouse),
                "-r",
                str(HERE / "backend.lock"),
            ],
        )
        probe = (
            "import sys,site,json,platform,sysconfig,importlib.metadata as m;"
            "from pathlib import Path;"
            "assert sys.version_info[:3]==(3,13,15),sys.version;"
            "assert platform.machine().lower() in ('arm64','aarch64'),platform.machine();"
            "assert sys.platform!='win32' or sysconfig.get_platform()=='win-arm64';"
            "assert m.version('pdm-backend')=='2.5.0';"
            "assert sys.prefix!=sys.base_prefix;"
            "assert not site.ENABLE_USER_SITE;"
            f"assert Path(sys.prefix).resolve()==Path({str(venv)!r}).resolve();"
            "print(json.dumps(dict(executable=sys.executable,prefix=sys.prefix,"
            "base_prefix=sys.base_prefix,version=sys.version,machine=platform.machine(),"
            "platform=sysconfig.get_platform(),backend=m.version('pdm-backend'),"
            "user_site=site.ENABLE_USER_SITE)))"
        )
        phase("identity", [str(python), "-I", "-c", probe])
        report["environment"]["identity"] = json.loads(
            (logs / "identity.log").read_text(encoding="utf-8")
        )
        phase(
            "sdk",
            [
                str(python),
                "-E",
                "-s",
                str(HERE.parent / "candidate" / "build.py"),
                "--source",
                str(args.source),
                "--source-manifest",
                str(args.source_manifest),
                "--out-dir",
                str(args.out_dir),
                "--workers",
                str(args.workers),
            ],
        )
        artifacts = args.out_dir / "artifacts"
        files = list(artifacts.iterdir())
        if (
            len(files) != 2
            or any(not p.is_file() for p in files)
            or len(list(artifacts.glob("*.tar.gz"))) != 1
            or len(list(artifacts.glob("*.whl"))) != 1
        ):
            raise ValueError("SDK must produce exactly one sdist and one wheel")
        report["artifacts"] = {str(p): sha256(p) for p in files}
        report["status"] = "passed"
    except BaseException as error:
        report["status"] = "failed"
        report["errors"].append(
            {
                "phase": "invocation",
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        if owns_environment:
            clock = time.perf_counter()
            cleanup = {
                "phase": "cleanup",
                "operation": "shutil.rmtree",
                "path": str(owned),
                "start_offset_seconds": clock - started,
            }
            report["phases"].append(cleanup)
            try:
                shutil.rmtree(owned)
                if owned.exists():
                    raise RuntimeError("Owned environment still exists after cleanup")
                cleanup["returncode"] = 0
            except BaseException as error:
                cleanup["returncode"] = 1
                report["status"] = "failed"
                report["errors"].append(
                    {
                        "phase": "cleanup",
                        "type": type(error).__name__,
                        "message": str(error),
                        "traceback": traceback.format_exc(),
                    }
                )
            finally:
                cleanup["seconds"] = time.perf_counter() - clock
                report["environment"]["exists_after_cleanup"] = owned.exists()
        report["wall_seconds"] = time.perf_counter() - started
        # Never overwrite an earlier sample, including on invalid arguments.
        if owns_logs:
            (logs / "errors.log").write_text(
                "\n".join(e["traceback"] for e in report["errors"]), encoding="utf-8"
            )
            report_path.write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )
        if report["errors"]:
            print(json.dumps(report["errors"]), file=sys.stderr)
    return 0 if report["status"] == "passed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "uv",
        "python",
        "source",
        "source-manifest",
        "out-dir",
        "cache-dir",
        "wheelhouse",
        "report",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=(1, 3), required=True)
    return execute(parser.parse_args())


if __name__ == "__main__":
    sys.exit(main())
