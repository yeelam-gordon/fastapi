"""Supported installer control; portable extraction of the validated V2 gates."""

import argparse
import base64
import csv
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import zipfile
from pathlib import Path

from frozen import verify_record
from guards import WHEEL_HASHES, binary_guard, native_guard, require, sha

UV_HASHES = {
    "Windows": "ec27977d62b5f6091bce410a8e69d40d07541803314e0120905c0ad0affaa5cc",
    "Darwin": "3996850e6d85e60b0142b40af4bd984822d65f736b52209921c47312450685cb",
}
WRONG_SHA = "0" * 64


def native_uv(path):
    require(path.is_absolute(), "UV must be an absolute native executable")
    binary_guard(path)
    require(
        sha(path) == UV_HASHES[platform.system()],
        "Wrong official native uv 0.13.6 binary",
    )


def reject_bypass(env):
    require("UV_NO_VERIFY_HASHES" not in env, "UV_NO_VERIFY_HASHES is forbidden")


def phases(stdout, stderr, arm, uv, wheel, other):
    text = stdout + "\n" + stderr
    branch = "venv+pip" if arm == "A" else "venv+uv"
    require(
        text.count("Creating isolated environment: " + branch) == 2
        and text.count("Creating isolated environment:") == 2
        and text.count("Building wheel from sdist") == 1
        and text.count("Building sdist") == 1,
        "Wrong installer build payload",
    )
    blocks = re.findall(
        r"\* Installing packages in isolated environment:\r?\n(.*?)(?=^\*|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    requirements = [re.findall(r"^\s*-\s+(\S+)\s*$", b, re.MULTILINE) for b in blocks]
    versions = re.findall(
        r"\* Installed build dependency versions:\r?\n(.*?)(?=^\*|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    require(
        requirements == [["pdm-backend"], ["pdm-backend"]]
        and [re.findall(r"^\s*-\s+(\S+)\s*$", b, re.MULTILINE) for b in versions]
        == [["pdm-backend==2.5.0"], ["pdm-backend==2.5.0"]],
        "Unknown build-system/get_requires closure",
    )
    if arm == "B":
        require(
            text.count("Using external uv from " + str(uv)) == 2
            and text.count("Using Python 3.12.10 environment at:") == 2,
            "Absolute uv/native underlying Python not proven",
        )
        selected = re.findall(
            r"^[<\s]*\+\s+pdm-backend==2\.5\.0\s+\(from ([^)]+)\)",
            text.lower(),
            re.MULTILINE,
        )
        expected = wheel.as_uri().lower() + "#sha256=" + WHEEL_HASHES["A"]
        require(
            selected == [expected, expected],
            "Two exact uv hashed-URL selections missing",
        )
        require(
            str(other).lower().replace("\\", "/")
            not in text.lower().replace("\\", "/"),
            "Wrong installer arm's wheel used",
        )
        require(
            "http/1.1" not in text.lower() and '"get ' not in text.lower(),
            "Network lookup in offline installer control",
        )
    return {
        "branch": branch,
        "closed_inputs": requirements,
        "hash_mode": "pip mandatory Require"
        if arm == "A"
        else "provided-hash Verify for this closed PDM input, not generic Require",
    }


def installed_record(site, isolated_path):
    record = site / "pdm_backend-2.5.0.dist-info" / "RECORD"
    rows = list(csv.reader(record.read_text(encoding="utf-8").splitlines()))
    seen = set()
    for name, digest, size in rows:
        path = (site / name).resolve()
        require(path.is_relative_to(isolated_path), "RECORD escapes isolation")
        require(name not in seen and path.is_file(), "Invalid installed RECORD path")
        seen.add(name)
        if digest:
            data = path.read_bytes()
            expected = (
                "sha256="
                + base64.urlsafe_b64encode(hashlib.sha256(data).digest())
                .rstrip(b"=")
                .decode()
            )
            require(
                digest == expected and size == str(len(data)),
                "Installed RECORD mismatch",
            )
        else:
            require(
                name.endswith((".pyc", ".dist-info/RECORD")),
                "Unexpected unhashed installed file",
            )
    return {"rows": len(rows), "sha256": sha(record), "all_hashed_rows_valid": True}


def probe(case, source, wheel, output):
    from build import _ctx
    from build.env import DefaultIsolatedEnv
    from pyproject_hooks import BuildBackendHookCaller

    native_guard()
    uv = Path(os.environ["UV"])
    native_uv(uv)
    reject_bypass(os.environ)
    require(
        "UV_REQUIRE_HASHES" not in os.environ, "B must use normal provided-hash Verify"
    )
    require(sha(wheel) == WHEEL_HASHES["A"], "Stock input wheel changed")
    cache = Path(os.environ["UV_CACHE_DIR"])
    warm = any(p.is_file() for p in cache.rglob("*")) if cache.exists() else False
    require(warm == (case == "negative-warm"), "Wrong private probe cache state")
    messages = []

    def logger(message, **kwargs):
        messages.append(message)
        print(message, file=sys.stderr, flush=True)

    _ctx.VERBOSITY.set(1)
    _ctx.LOGGER.set(logger)
    proof = {
        "case": case,
        "cache_was_warm": warm,
        "mode": "normal provided-hash Verify; not all-future-dependencies Require",
        "wheel_sha256": sha(wheel),
    }
    with DefaultIsolatedEnv(installer="uv") as isolated:
        backend = isolated._env_backend
        require(
            type(backend).__name__ == "_UvBackend"
            and Path(backend._uv_bin).resolve() == uv.resolve(),
            "Wrong external uv",
        )
        binary_guard(isolated.python_executable)
        code = (
            "import json,platform,sys; print(json.dumps(dict("
            "version=platform.python_version(),machine=platform.machine(),"
            "base=sys._base_executable)))"
        )
        identity = json.loads(
            subprocess.check_output([isolated.python_executable, "-c", code])
        )
        require(
            identity["version"] == "3.12.10"
            and identity["machine"].lower() in ("arm64", "aarch64")
            and Path(identity["base"]).resolve()
            == Path(sys._base_executable).resolve(),
            "Wrong isolated underlying interpreter",
        )
        proof["isolated_python"] = identity
        site = Path(backend.purelib)
        failure = None
        try:
            isolated.install(["pdm-backend"])
        except subprocess.CalledProcessError as error:
            failure = error
        if case == "positive":
            require(failure is None, "Positive provided-hash installation failed")
            with zipfile.ZipFile(wheel) as archive:
                verify_record(archive)
                for name in archive.namelist():
                    if not name.endswith(("/", ".dist-info/RECORD")):
                        require(
                            (site / name).read_bytes() == archive.read(name),
                            "Stock installed payload differs: " + name,
                        )
            proof["installed_RECORD"] = installed_record(site, Path(isolated.path))
            hook = BuildBackendHookCaller(
                str(source), "pdm.backend", python_executable=isolated.python_executable
            )
            closure = {
                "sdist": hook.get_requires_for_build_sdist(),
                "wheel": hook.get_requires_for_build_wheel(),
            }
            require(
                closure == {"sdist": [], "wheel": []}, "Unknown get_requires closure"
            )
            proof["get_requires"] = closure
        else:
            text = "\n".join(messages).lower()
            require(
                failure is not None
                and "hash mismatch" in text
                and WRONG_SHA in text
                and WHEEL_HASHES["A"] in text,
                "Wrong hash did not fail with expected AND computed SHA256",
            )
            require(
                not any(p.is_file() for p in site.rglob("*")),
                "Negative installed payloads",
            )
            proof["hash_mismatch_proven"] = True
        require(sha(wheel) == WHEEL_HASHES["A"], "Source wheel was corrupted")
        proof.update(passed=True, installer_exit=failure.returncode if failure else 0)
    output.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case", choices=("positive", "negative-cold", "negative-warm"), required=True
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    probe(args.case, args.source, args.wheel, args.output)
