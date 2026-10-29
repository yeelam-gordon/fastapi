"""One public-backend cProfile diagnostic, with offline owned C: preparation."""

import cProfile
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import pstats
import shutil
import subprocess
import sys
import tarfile
import time
import uuid


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def child(root):
    # Profiler imports and construction are deliberately outside the region.
    profile = cProfile.Profile()
    os.chdir(root / "source")
    wall, cpu = time.perf_counter(), time.process_time()
    profile.enable()
    import pdm.backend
    artifact = pdm.backend.build_sdist(str(root / "output"))
    profile.disable()
    wall, cpu = time.perf_counter() - wall, time.process_time() - cpu
    profile.dump_stats(str(root / "build.prof"))
    stats = pstats.Stats(profile)
    entries = [
        dict(file=key[0], line=key[1], function=key[2],
             primitive_calls=value[0], total_calls=value[1],
             self_seconds=value[2], cumulative_seconds=value[3],
             callers=[dict(file=k[0], line=k[1], function=k[2], values=v)
                      for k, v in value[4].items()])
        for key, value in stats.stats.items()
    ]
    save(root / "stats.json", entries)
    with (root / "stats.txt").open("w", encoding="utf-8") as stream:
        pstats.Stats(profile, stream=stream).sort_stats("cumulative").print_stats()
    import importlib.metadata
    import zlib
    save(root / "profile.json", dict(
        wall_seconds=wall, process_cpu_seconds=cpu,
        cprofile_timer="default elapsed/performance timer; not thread/process CPU",
        artifact=artifact, version=sys.version, machine=platform.machine(),
        executable=sys.executable, base_prefix=sys.base_prefix,
        backend_version=importlib.metadata.version("pdm-backend"),
        backend_origin=pdm.backend.__file__, backend_sha256=sha(pdm.backend.__file__),
        python_dll_sha256=sha(Path(sys.base_prefix) / "python313.dll"),
        zlib_origin=zlib.__spec__.origin, zlib_version=zlib.ZLIB_VERSION,
        zlib_runtime_version=zlib.ZLIB_RUNTIME_VERSION,
        zlib_binary_container="python313.dll (built-in module)",
        dont_write_bytecode=sys.dont_write_bytecode,
        pycache_prefix=sys.pycache_prefix,
        profile_sha256=sha(root / "build.prof"),
        codec_entries=[e for e in entries if any(
            name in e["function"].lower()
            for name in ("compress", "flush", "crc32", "adler32"))],
    ))


def inventory(path):
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        if not all(m.isfile() for m in members):
            raise ValueError("Non-file sdist entry")
        result = {
            m.name: dict(sha256=hashlib.sha256(archive.extractfile(m).read()).hexdigest(),
                         mode=m.mode, uid=m.uid, gid=m.gid, uname=m.uname,
                         gname=m.gname, size=m.size)
            for m in members
        }
        if len(result) != len(members):
            raise ValueError("Duplicate members")
        return result


def main():
    here = Path(__file__).resolve().parent
    shared = Path(r"Q:\fastapi\Generated Files\arm-build")
    root = Path(r"C:\fastapi-arm-build-lab") / ("codec-attribution-" + uuid.uuid4().hex[:12])
    root.mkdir()
    evidence = here / root.name
    evidence.mkdir()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("PYTHON", "UV_", "PIP_"))
           and k not in ("VIRTUAL_ENV",)}
    for folder in ("tools", "wheelhouse", "cache", "temp", "source", "output"):
        (root / folder).mkdir()
    env.update(TEMP=str(root / "temp"), TMP=str(root / "temp"),
               TMPDIR=str(root / "temp"), UV_CACHE_DIR=str(root / "cache"),
               UV_OFFLINE="1", UV_NO_CONFIG="1", UV_PYTHON_DOWNLOADS="never",
               PYTHONNOUSERSITE="1")
    receipt = dict(root=str(root), commands=[], environment=env,
                   removed_environment_names=[k for k in os.environ if k not in env])
    # Keep only relevant environment values, not unrelated machine credentials.
    receipt["environment"] = {k: v for k, v in env.items()
                              if k.startswith(("PYTHON", "UV_")) or k in ("TEMP", "TMP", "TMPDIR")}

    def run(argv, name, cwd=root):
        argv = [str(x) for x in argv]
        with (evidence / (name + ".log")).open("wb") as stream:
            result = subprocess.run(argv, env=env, cwd=cwd,
                                    stdout=stream, stderr=subprocess.STDOUT)
        receipt["commands"].append(dict(argv=argv, returncode=result.returncode))
        save(evidence / "preparation.json", receipt)
        result.check_returncode()

    uv = root / "tools" / "uv.exe"
    shutil.copy2(shared / "tools" / "uv.exe", uv)
    run([uv, "--version"], "uv-version")
    run([uv, "python", "find", "3.13.15"], "python-find")
    base = Path((evidence / "python-find.log").read_text().strip())
    shutil.copytree(base.parent, root / "runtime")
    python = root / "runtime" / "python.exe"
    lock = root / "backend.lock"
    shutil.copy2(here / "backend.lock", lock)
    wheel = root / "wheelhouse" / "pdm_backend-2.5.0-py3-none-any.whl"
    shutil.copy2(shared / "wheelhouse" / "ci-40814042898" / wheel.name, wheel)
    if sha(wheel) != "5b8746b567a16a1fd506ce66ee28e89d46374526f52238aa1b96cc2c08245c63":
        raise ValueError("Backend wheel identity mismatch")
    run([uv, "venv", "--python", python, root / "env"], "venv")
    runtime = root / "env" / "Scripts" / "python.exe"
    run([uv, "pip", "install", "--python", runtime, "--no-index",
         "--find-links", root / "wheelhouse", "--require-hashes", "-r", lock], "install")
    source = Path(r"Q:\fastapi\Generated Files\worktrees\source-fastapi")
    revision = "79cab5bed28b24d92c185d236feb33f5783dfeb3"
    archive = root / "source.tar"
    run(["git", "-c", "core.autocrlf=false", "-C", source, "archive",
         "--format=tar", f"--output={archive}", revision], "source-archive")
    with tarfile.open(archive) as tar:
        if tar.pax_headers.get("comment") != revision:
            raise ValueError("Wrong source commit")
        source_manifest = {
            m.name: hashlib.sha256(tar.extractfile(m).read()).hexdigest()
            for m in tar if m.isfile()
        }
        tar.extractall(root / "source", filter="data")
    actual = {p.relative_to(root / "source").as_posix(): sha(p)
              for p in (root / "source").rglob("*") if p.is_file()}
    if actual != source_manifest:
        raise ValueError("Source extraction changed bytes")
    save(evidence / "source-manifest.json", source_manifest)
    helper = root / "tools" / "attribute.py"
    shutil.copy2(here / "attribute.py", helper)
    receipt.update(source_revision=revision, hashes={
        "uv": sha(uv), "python": sha(python), "python_dll": sha(root / "runtime" / "python313.dll"),
        "backend_wheel": sha(wheel), "source_archive": sha(archive),
        "helper": sha(helper), "lock": sha(lock),
    }, source_path=str(source), bytecode_policy="default; inherited PYTHON* removed")
    save(evidence / "preparation.json", receipt)
    run([runtime, helper, "--child", root], "build")
    for name in ("profile.json", "stats.json", "stats.txt", "build.prof"):
        shutil.copy2(root / name, evidence / name)
    profile = json.loads((root / "profile.json").read_text())
    if profile["backend_version"] != "2.5.0" or "3.13.15" not in profile["version"] or profile["machine"] != "ARM64":
        raise ValueError("Runtime/backend identity mismatch")
    oracle = shared / "results" / "ci-40814588064" / "macos" / "ci" / "artifacts" / "prepare-baseline"
    reference = next(oracle.glob("*.tar.gz"))
    built = root / "output" / profile["artifact"]
    expected, actual = inventory(reference), inventory(built)
    validator = root / "tools" / "validate.py"
    shutil.copy2(shared / "candidate" / "validate.py", validator)
    spec = importlib.util.spec_from_file_location("validator", validator)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    verdict = module.compare({"sdist": expected}, {"sdist": actual})
    known = {"fastapi-0.162.0/scripts/" + n for n in
             ("format.sh", "lint.sh", "test-cov-html.sh", "test-cov.sh", "test.sh")}
    differences = verdict["differences"]
    known_only = len(differences) == 5 and {d.get("name") for d in differences} == known
    for d in differences:
        left, right = dict(d["expected"]), dict(d["actual"])
        known_only &= left.pop("mode") == 0o755 and right.pop("mode") == 0o644 and left == right
    save(evidence / "inventory.json", actual)
    save(evidence / "verification.json", dict(
        sdist_members=len(actual), oracle_members=len(expected), comparison=verdict,
        payload_metadata_except_known_modes_pass=known_only,
        oracle=str(reference), oracle_sha256=sha(reference),
        artifact=str(built), artifact_sha256=sha(built),
        validator_sha256=sha(validator),
    ))
    if not known_only:
        raise ValueError("Unexpected oracle differences; retained verdict")
    print(str(evidence))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        child(Path(sys.argv[2]))
    else:
        main()
