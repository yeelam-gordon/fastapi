"""Fail-closed common-source and installed-payload gates for runtime pairs."""

import hashlib
import importlib.metadata
import json
import os
import platform
import re
import struct
import subprocess
import sys
import sysconfig
import warnings
from pathlib import Path

SOURCE_REVISION = "864b569cf8453654fc3bc2c64108c0f644e2918c"
OLD = b"sys.version_info > (3, 13)"
NEW = b"sys.version_info >= (3, 14)"
OLD_SHA = "264ae5fbf31d05cc19ec81cc29a21491e59d1e592bba925c64d89518d82173c5"
NEW_SHA = "7012ca9f7d15dd718298f773ca1de7db5eeaf40024d6282eaa0ab1ac7db10a34"
PATCH_SHA = "7f4e1b6f55fea34968927fa808f8c6f9e1732d0380c5ece01d62993c9d691316"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def corrected(raw, original_sha=OLD_SHA):
    normalized = raw.replace(b"\r\n", b"\n")
    require(sha(normalized) == original_sha, "unexpected original guard hash")
    require(normalized.count(OLD) == 1, "unexpected guard target")
    result = normalized.replace(OLD, NEW)
    require(sha(result) == NEW_SHA, "unexpected corrected guard hash")
    return result.replace(b"\n", b"\r\n") if b"\r\n" in raw else result


def prepare_source(source, root):
    def git(*args):
        return subprocess.run(
            ["git", "-C", str(source), *args],
            check=True,
            capture_output=True,
            timeout=30,
        ).stdout

    require(
        git("rev-parse", "HEAD").decode().strip() == SOURCE_REVISION, "source revision"
    )
    names = [name for name in git("ls-files", "-z").decode().split("\0") if name]
    original = {name: sha((source / name).read_bytes()) for name in names}
    require(len(original) == 2557, "original source count")
    require(
        not git("status", "--porcelain", "--untracked-files=no"), "source already dirty"
    )
    blob = git("show", f"{SOURCE_REVISION}:tests/utils.py")
    require(sha(blob) == OLD_SHA, "unknown committed guard")
    path = source / "tests" / "utils.py"
    require(
        path.read_bytes().replace(b"\r\n", b"\n") == blob,
        "guard committed blob mismatch",
    )
    patch = Path(__file__).with_name("common-guard.patch").read_bytes()
    require(sha(patch) == PATCH_SHA, "guard patch transport hash")
    # Bind the original blob as well as the exact known corrected result.
    path.write_bytes(corrected(path.read_bytes(), sha(blob)))
    common = {name: sha((source / name).read_bytes()) for name in names}
    require(
        [name for name in names if original[name] != common[name]]
        == ["tests/utils.py"],
        "source correction scope",
    )
    save(root / "original-source-files.json", original)
    save(root / "source-files.json", common)
    save(
        root / "common-source.json",
        {
            "revision": SOURCE_REVISION,
            "unpatched_tag": False,
            "original_manifest_sha256": sha(
                (root / "original-source-files.json").read_bytes()
            ),
            "original_guard_sha256": original["tests/utils.py"],
            "corrected_guard_sha256": common["tests/utils.py"],
            "original_committed_blob_sha256": OLD_SHA,
            "corrected_normalized_lf_sha256": NEW_SHA,
            "unchanged_files": 2556,
            "declared_change": "tests/utils.py >=3.14 guard",
            "patch_sha256": PATCH_SHA,
        },
    )


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def compare_pins(old, new):
    require(
        {normalize(k): v for k, v in old.items()}
        == {normalize(k): v for k, v in new.items()},
        "runtime package pins differ",
    )


def identity(source, expected):
    require(
        sys.version_info[:3] == tuple(map(int, expected.split("."))), "runtime version"
    )
    require(
        platform.machine().lower() in {"arm64", "aarch64"}
        and struct.calcsize("P") == 8,
        "native ARM64 runtime",
    )
    require(
        not sysconfig.get_config_var("Py_GIL_DISABLED")
        and getattr(sys, "_is_gil_enabled", lambda: True)(),
        "normal GIL runtime required",
    )
    require(
        not sysconfig.get_config_var("PYTHON_JIT")
        and not getattr(getattr(sys, "_jit", None), "is_enabled", lambda: False)(),
        "JIT disabled required",
    )
    import coverage
    import coverage.tracer
    from packaging.tags import parse_tag, sys_tags

    sys.path.insert(0, str(source))
    import fastapi

    require(
        Path(fastapi.__file__).resolve()
        == (source / "fastapi" / "__init__.py").resolve()
        and fastapi.__version__ == "0.119.1",
        "source import origin",
    )
    require(
        coverage.__version__ == "7.17.0"
        and Path(coverage.tracer.__file__).suffix in {".pyd", ".so"},
        "original native coverage required",
    )
    packages, wheels = {}, {}
    compatible = set(sys_tags())
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata["Name"]
        packages[name] = distribution.version
        wheel = distribution.read_text("WHEEL")
        if wheel:
            tags = [line[5:] for line in wheel.splitlines() if line.startswith("Tag: ")]
            require(
                any(parse_tag(tag) & compatible for tag in tags),
                f"incompatible wheel: {name}",
            )
            wheels[name] = {
                "tags": tags,
                "wheel": wheel,
                "record": distribution.read_text("RECORD"),
                "record_sha256": sha((distribution.read_text("RECORD") or "").encode()),
            }
    expected_pins = {}
    for line in (
        Path(__file__).with_name("runtime-constraints.txt").read_text().splitlines()
    ):
        name, version = line.strip().split("==")
        if (normalize(name) == "uvloop" and sys.platform == "win32") or (
            normalize(name) == "colorama" and sys.platform != "win32"
        ):
            continue
        expected_pins[name] = version
    expected_pins["fastapi"] = "0.119.1"
    compare_pins(expected_pins, packages)
    runtime_files = {
        "executable": Path(sys.executable),
        "base_executable": Path(sys._base_executable),
        "native_coverage": Path(coverage.tracer.__file__),
    }
    if sys.platform == "win32":
        runtime_files["runtime_dll"] = (
            Path(sys.base_prefix) / "python313.dll"
            if expected.startswith("3.13.")
            else Path(sys.base_prefix) / "python312.dll"
        )
    return {
        "version": platform.python_version(),
        "executable": sys.executable,
        "machine": platform.machine(),
        "gil": True,
        "jit": False,
        "os": platform.platform(),
        "logical_cpu_count": os.cpu_count(),
        "processor": platform.processor() or None,
        "packages": packages,
        "wheels": wheels,
        "runtime_sha256": {
            name: sha(path.read_bytes()) for name, path in runtime_files.items()
        },
    }


def oracle(folder, source):
    paths = sorted((folder / "private").glob(".coverage.*"))
    require(
        len(paths) == 2 and all(path.is_file() for path in paths),
        "exactly main and CLI coverage shards required",
    )
    from coverage import Coverage, CoverageData

    before = {path.name: sha(path.read_bytes()) for path in paths}
    data = CoverageData(no_disk=True)
    for path in paths:
        part = CoverageData(basename=str(path))
        part.read()
        data.update(part)
    require(not data.has_arcs(), "unexpected branch coverage")
    config = Coverage(config_file=str(source / "pyproject.toml"))
    require(
        [
            config.get_option("run:" + key)
            for key in ("branch", "parallel", "dynamic_context", "source", "omit")
        ]
        == [
            False,
            True,
            "test_function",
            ["docs_src", "tests", "fastapi"],
            [
                "docs_src/response_model/tutorial003_04.py",
                "docs_src/response_model/tutorial003_04_py310.py",
            ],
        ],
        "coverage configuration changed",
    )
    files, excluded = {}, {}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for filename in sorted(data.measured_files()):
            path = Path(filename).resolve()
            require(path.is_relative_to(source), "coverage outside common source")
            name = path.relative_to(source).as_posix()
            files[name] = {
                str(n): sorted(c) for n, c in data.contexts_by_lineno(filename).items()
            }
            excluded[name] = config.analysis2(filename)[2]
        save(
            folder / "private" / "coverage-warnings.json",
            [str(w.message) for w in caught],
        )
        require(not caught, "coverage warning")
    require(
        before == {path.name: sha(path.read_bytes()) for path in paths},
        "coverage shards modified",
    )
    return {
        "files": files,
        "contexts": sorted(data.measured_contexts()),
        "excluded": excluded,
        "shards": before,
    }


def compare(old, new):
    require(old["files"].keys() == new["files"].keys(), "coverage file set differs")
    require(old["contexts"] == new["contexts"], "coverage context set differs")
    require(old["excluded"] == new["excluded"], "coverage exclusions differ")
    return [
        {
            "file": name,
            "line": int(line),
            "before": before.get(line),
            "after": new["files"][name].get(line),
            "excluded": int(line) in old["excluded"][name],
        }
        for name, before in old["files"].items()
        for line in sorted(before.keys() | new["files"][name].keys(), key=int)
        if before.get(line) != new["files"][name].get(line)
    ]


def probe(python, action, source, argument, env, folder):
    completed = subprocess.run(
        [str(python), "-B", str(Path(__file__)), action, str(source), str(argument)],
        cwd=source,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    (folder / f"{action}.stdout").write_text(completed.stdout, encoding="utf-8")
    (folder / f"{action}.stderr").write_text(completed.stderr, encoding="utf-8")
    require(
        completed.returncode == 0 and not completed.stderr,
        f"payload {action} failed; streams retained",
    )
    return json.loads(completed.stdout)


if __name__ == "__main__":
    action, source, argument = sys.argv[1:]
    source = Path(source).resolve()
    if action == "prepare":
        prepare_source(source, Path(argument))
    elif action == "identity":
        print(json.dumps(identity(source, argument)))
    elif action == "oracle":
        print(json.dumps(oracle(Path(argument), source)))
    else:
        raise RuntimeError("unknown runtime-pair action")
