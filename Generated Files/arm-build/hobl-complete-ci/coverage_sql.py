"""Optional coverage.py 7.17 SQL treatment, never a collector replacement."""

import hashlib
import importlib.metadata
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import warnings
from pathlib import Path

OWNER_SHA = "c78339d21fe75e063fd204148226668023c5ad9f9d806d0631813419aa21d406"
PATCH_SHA = "9e3865fcf1432130bd98cddb1ea510c1541bcd9f9cd996a1d8c0f9dc72b07d5e"
CANDIDATE_SHA = "707000819164d3479cb123cb31aabf736f69a3a6a80cb144cf67817fefbd83b5"
OLD = '''                con.execute_void(
                    """
                    INSERT OR REPLACE INTO line_bits'''
NEW = '''                conflict_action = "IGNORE" if existing and line_bits == existing[0][0] else "REPLACE"
                con.execute_void(
                    f"""
                    INSERT OR {conflict_action} INTO line_bits'''


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def payloads(root):
    return {
        p.relative_to(root).as_posix(): sha(p)
        for p in sorted(root.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }


def transform(raw, patch):
    require(hashlib.sha256(patch).hexdigest() == PATCH_SHA, "incorrect V2 patch")
    normalized = raw.replace(b"\r\n", b"\n")
    require(
        hashlib.sha256(normalized).hexdigest() == OWNER_SHA, "unexpected owner source"
    )
    text = normalized.decode("utf-8")
    require(text.count(OLD) == 1, "unexpected SQL patch target")
    result = text.replace(OLD, NEW).encode("utf-8")
    require(
        hashlib.sha256(result).hexdigest() == CANDIDATE_SHA,
        "unexpected normalized V2 result",
    )
    return result.replace(b"\n", b"\r\n") if b"\r\n" in raw else result


def prepare(root):
    import coverage

    require(coverage.__version__ == "7.17.0", "coverage owner version")
    original = Path(coverage.__file__).parent
    before = payloads(original)
    require(len(before) == 54, "unexpected installed coverage package payload")
    patch = Path(__file__).with_name("candidate-v2.patch").read_bytes()
    for arm in ("stock", "candidate"):
        target = root / arm / "coverage"
        shutil.copytree(
            original, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
        )
        if arm == "candidate":
            path = target / "sqldata.py"
            path.write_bytes(transform(path.read_bytes(), patch))
    stock, candidate = (
        payloads(root / arm / "coverage") for arm in ("stock", "candidate")
    )
    require(stock == before, "stock copy changed")
    require(stock.keys() == candidate.keys(), "overlay package members")
    require(
        [key for key in stock if stock[key] != candidate[key]] == ["sqldata.py"],
        "overlay scope",
    )
    require(payloads(original) == before, "original package changed")
    distribution = importlib.metadata.distribution("coverage")
    licenses = [p for p in distribution.files if ".dist-info/licenses/" in p.as_posix()]
    require(licenses, "installed coverage license missing")
    for arm in ("stock", "candidate"):
        for license_file in licenses:
            target = root / arm / "licenses" / Path(license_file).name
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(distribution.locate_file(license_file), target)
    license_payloads = payloads(root / "stock" / "licenses")
    require(
        payloads(root / "candidate" / "licenses") == license_payloads,
        "coverage license copies",
    )
    save(
        root / "payloads.json",
        {"stock": stock, "candidate": candidate, "licenses": license_payloads},
    )


def attest(root, arm, source):
    import coverage
    import coverage.sqldata
    import coverage.tracer

    # A script entrypoint lacks the cwd insertion made by the measured `-m` command.
    sys.path.insert(0, str(source))
    import fastapi

    package = root / arm / "coverage"
    expected = json.loads((root / "payloads.json").read_bytes())[arm]
    require(
        Path(coverage.__file__).resolve() == (package / "__init__.py").resolve(),
        "coverage origin",
    )
    require(payloads(package) == expected, "coverage overlay changed")
    require(coverage.__version__ == "7.17.0", "coverage version")
    require(not os.environ.get("COVERAGE_CORE"), "default coverage core required")
    require(sys.version_info[:3] == (3, 12, 10), "coverage Python ABI")
    require(
        Path(coverage.tracer.__file__).suffix in {".pyd", ".so"},
        "native collector required",
    )
    require(
        Path(fastapi.__file__).resolve()
        == (source / "fastapi" / "__init__.py").resolve(),
        "FastAPI source origin",
    )
    require(fastapi.__version__ == "0.119.1", "FastAPI source version")
    return {
        "coverage_origin": f"overlays/{arm}/coverage/__init__.py",
        "sqldata_sha256": sha(Path(coverage.sqldata.__file__)),
        "sqldata_normalized_lf_sha256": hashlib.sha256(
            Path(coverage.sqldata.__file__).read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest(),
        "native_collector_sha256": sha(Path(coverage.tracer.__file__)),
        "coverage_version": coverage.__version__,
        "python_abi": sys.implementation.cache_tag,
        "native_collector": "coverage.tracer.CTracer",
        "fastapi_origin": "source/fastapi/__init__.py",
        "fastapi_version": fastapi.__version__,
    }


def oracle(folder, source):
    paths = sorted((folder / "private").glob(".coverage*"))
    require(
        len(paths) == 2 and all(p.is_file() for p in paths),
        "exactly main and CLI coverage shards required",
    )
    from coverage import Coverage, CoverageData

    before = [sha(path) for path in paths]
    schemas = []
    for path in paths:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            schema = db.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
            ).fetchall()
            schemas.append(hashlib.sha256(json.dumps(schema).encode()).hexdigest())
    save(
        folder / "coverage-data-identities.json",
        {"data_sha256": before, "schema_sha256": schemas},
    )
    data = CoverageData(no_disk=True)
    for path in paths:
        part = CoverageData(basename=str(path))
        part.read()
        data.update(part)
    require(not data.has_arcs(), "unexpected coverage branch mode")
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
        "coverage features changed",
    )
    files, excluded = {}, {}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for filename in sorted(data.measured_files()):
            path = Path(filename).resolve()
            require(
                path.is_relative_to(source), "coverage file outside canonical source"
            )
            name = path.relative_to(source).as_posix()
            files[name] = {
                str(n): sorted(c) for n, c in data.contexts_by_lineno(filename).items()
            }
            excluded[name] = config.analysis2(filename)[2]
        save(
            folder / "private" / "coverage-warnings.json",
            [str(w.message) for w in caught],
        )
        save(folder / "coverage-warning-summary.json", {"count": len(caught)})
        require(not caught, "new private coverage warning")
    require(
        [sha(path) for path in paths] == before,
        "raw coverage data changed during analysis",
    )
    return {
        "files": files,
        "contexts": sorted(data.measured_contexts()),
        "excluded": excluded,
    }


def compare(old, new):
    require(old["files"].keys() == new["files"].keys(), "coverage file set differs")
    require(old["contexts"] == new["contexts"], "coverage context set differs")
    require(old["excluded"] == new["excluded"], "coverage exclusions differ")
    differences = []
    for name, before in old["files"].items():
        after = new["files"][name]
        for line in sorted(before.keys() | after.keys(), key=int):
            if before.get(line) != after.get(line):
                differences.append(
                    {
                        "file": name,
                        "line": int(line),
                        "before": before.get(line),
                        "after": after.get(line),
                        "excluded": int(line) in old["excluded"][name],
                    }
                )
    return differences


class Treatment:
    def __init__(self, args, output):
        self.args, self.output = args, output
        self.root = output / "overlays"
        (output / "private").mkdir()
        self.run("prepare", [str(self.root)], os.environ.copy(), output)
        self.protected = json.loads((self.root / "payloads.json").read_bytes())

    def run(self, action, arguments, env, folder):
        result = subprocess.run(
            [str(self.args.python), "-B", str(Path(__file__)), action, *arguments],
            cwd=self.args.source,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        (folder / "private" / f"coverage-{action}.stderr").write_text(
            result.stderr, encoding="utf-8"
        )
        (folder / "private" / f"coverage-{action}.stdout").write_text(
            result.stdout, encoding="utf-8"
        )
        require(
            result.returncode == 0 and not result.stderr,
            f"coverage {action} failed; private stderr retained",
        )
        return json.loads(result.stdout) if result.stdout else None

    def environment(self, env, folder, arm):
        env = env.copy()
        for key in list(env):
            if key.startswith(("COVERAGE_", "COV_CORE_")):
                env.pop(key)
        private = folder / "private"
        private.mkdir()
        overlay = str(self.root / arm)
        env.update(
            PYTHONPATH=overlay + os.pathsep + "./docs_src",
            COVERAGE_FILE=str(private / ".coverage"),
        )
        if self.args.style == "macos":
            script = private / "coverage-env.sh"
            script.write_text(
                'coverage() { PYTHONPATH="$HOBL_COVERAGE_OVERLAY'
                + os.pathsep
                + '$PYTHONPATH" command coverage "$@"; }\n',
                encoding="utf-8",
            )
            env.update(BASH_ENV=str(script), HOBL_COVERAGE_OVERLAY=overlay)
        identity = self.run(
            "attest", [str(self.root), arm, str(self.args.source)], env, folder
        )
        save(folder / "coverage-identity.json", identity)
        return env

    def finish(self, folder, env):
        # Always merge/analyse using the unmodified stock public API, outside phase().
        env = env.copy()
        env["PYTHONPATH"] = str(self.root / "stock") + os.pathsep + "./docs_src"
        current = self.run("oracle", [str(folder), str(self.args.source)], env, folder)
        save(folder / "coverage-oracle.json", current)
        baseline_path = self.output / "loop-1" / "coverage-oracle.json"
        baseline = json.loads(baseline_path.read_bytes())
        differences = compare(baseline, current)
        save(folder / "coverage-differences.json", differences)
        require(
            all(row["excluded"] for row in differences),
            "reportable coverage difference",
        )
        for arm in ("stock", "candidate"):
            require(
                payloads(self.root / arm / "coverage") == self.protected[arm],
                "coverage payload changed",
            )
            require(
                payloads(self.root / arm / "licenses") == self.protected["licenses"],
                "coverage licenses changed",
            )


if __name__ == "__main__":
    action, *arguments = sys.argv[1:]
    if action == "prepare":
        prepare(Path(arguments[0]))
    elif action == "attest":
        print(json.dumps(attest(Path(arguments[0]), arguments[1], Path(arguments[2]))))
    elif action == "oracle":
        print(json.dumps(oracle(Path(arguments[0]), Path(arguments[1]))))
    else:
        raise RuntimeError("unknown coverage action")
