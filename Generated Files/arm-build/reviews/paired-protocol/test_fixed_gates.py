"""Forward acceptance gates, deliberately red on the reviewed harness.

Set PAIR_REVIEW_PROTOCOL to a committed protocol directory for later verification.
Fixtures model wrapper a08208414c28b5bf3525345a65380e8b52538971 schema 1.
No subprocess, package build, environment installation or benchmark is invoked.
"""

import copy
import hashlib
import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROTOCOL = Path(
    os.environ.get(
        "PAIR_REVIEW_PROTOCOL", str(Path(__file__).resolve().parents[2] / "protocol")
    )
)
sys.path.insert(0, str(PROTOCOL))
compare = importlib.import_module("compare_pairs")
measure = importlib.import_module("measure_pairs")


def sha(label):
    return hashlib.sha256(label.encode()).hexdigest()


def path(system, *parts):
    separator = "\\" if system == "Windows" else "/"
    root = "C:\\pairs" if system == "Windows" else "/Users/runner/pairs"
    return separator.join((root, *parts))


def evidence(system):
    tools = {name: sha(name) for name in measure.REQUIRED_TOOL_INPUTS}
    tools["Generated Files/arm-build/protocol/isolated_build.py"] = sha("wrapper")
    tools["Generated Files/arm-build/protocol/backend.lock"] = sha("backend lock")
    executable = path(system, "runtime", "python.exe" if system == "Windows" else "python")
    library = path(system, "runtime", "python313.dll" if system == "Windows" else "libpython3.13.dylib")
    uv = path(system, "uv.exe" if system == "Windows" else "uv")
    def binary(name, filename):
        return {
            "path": filename,
            "sha256": sha(system + name),
            "arm64_slice": True,
        }
    runtime = {
        "version": "3.13.15",
        "native_arm64": True,
        "machine": "ARM64" if system == "Windows" else "arm64",
        "tag": "win-arm64" if system == "Windows" else "macosx-11.0-universal2",
        "translated": False,
        "executable": executable,
        "executable_sha256": sha(system + "python"),
        "executable_binary": binary("python", executable),
        "shared_library": library,
        "shared_library_sha256": sha(system + "library"),
        "shared_library_binary": binary("library", library),
    }
    source = {
        "revision": measure.SOURCE,
        "archive_sha256": sha("canonical archive"),
        "manifest_sha256": sha("canonical manifest"),
        "files": 1269,
    }
    result = {
        "schema": measure.SCHEMA,
        "status": "complete",
        "system": system,
        "source": source,
        "harness_revision": "a" * 40,
        "tool_hashes": tools,
        "runtime": runtime,
        "uv": {"version": "0.13.6", **binary("uv", uv)},
        "schedule": measure.ORDERS,
        "scopes": {
            "B": "standard_uv_isolated_wall",
            "S1": "sdk_caller_isolated_wall",
            "S3": "sdk_caller_isolated_wall",
        },
        "samples": [],
    }
    result["preparation"] = {
        "schema": measure.SCHEMA,
        "status": "prepared",
        "source": copy.deepcopy(source),
        "runtime": copy.deepcopy(runtime),
        "harness_revision": result["harness_revision"],
        "tool_hashes": copy.deepcopy(tools),
    }
    schedule = [(-1, ("B", "S1", "S3")), *enumerate(measure.ORDERS)]
    for block, order in schedule:
        for variant in order:
            sample_dir = path(system, "samples", f"{block + 1}-{variant}")
            def join(*parts, base=sample_dir):
                separator = "\\" if system == "Windows" else "/"
                return base + separator + separator.join(parts)
            sample = {
                "block": block,
                "variant": variant,
                "timed": block >= 0,
                "wall": 2.0,
                "returncode": 0,
                "timed_out": False,
                "cleanup_errors": [],
                "metric": result["scopes"][variant],
                "correctness": {
                    **dict.fromkeys(
                        ("source", "membership", "payloads", "modes", "ownership",
                         "metadata", "record", "smoke"), True
                    ),
                    "differences": [],
                    "canonical_record_sha256": sha("canonical record"),
                },
            }
            if variant != "B":
                workers = 1 if variant == "S1" else 3
                wrapper = path(system, "tools", "protocol", "isolated_build.py")
                sdk = path(system, "tools", "candidate", "build.py")
                lock = path(system, "tools", "protocol", "backend.lock")
                manifest = path(system, "source-manifest.json")
                output = join("out")
                caller = join(".caller-env-" + f"{len(result['samples']):032x}")
                sep = "\\" if system == "Windows" else "/"
                venv = caller + sep + "venv"
                python = venv + sep + (
                    "Scripts\\python.exe" if system == "Windows" else "bin/python"
                )
                uv_argv = [
                    uv, "--no-config", "--offline", "--cache-dir",
                    path(system, "uv-cache"),
                ]
                phases = [
                    ("create", uv_argv + ["venv", "--python", executable,
                                         "--no-python-downloads", venv]),
                    ("install", uv_argv + ["pip", "install", "--python", python,
                                          "--require-hashes", "--no-index",
                                          "--only-binary", ":all:", "--find-links",
                                          path(system, "wheelhouse"), "-r", lock]),
                    ("identity", [python, "-I", "-c", "identity probe"]),
                    ("sdk", [python, "-E", "-s", sdk, "--source", join("source"),
                             "--source-manifest", manifest, "--out-dir", output,
                             "--workers", str(workers)]),
                ]
                receipt = {
                    "schema_version": 1,
                    "status": "passed",
                    "isolation": "fresh caller environment shared by both SDK hooks",
                    "workers": workers,
                    "errors": [],
                    "wall_seconds": 1.2,
                    "environment": {
                        "root": caller,
                        "existed_before": False,
                        "exists_after_cleanup": False,
                        "identity": {
                            "executable": python,
                            "prefix": venv,
                            "base_prefix": path(system, "runtime"),
                            "version": "3.13.15 (fixture)",
                            "machine": runtime["machine"],
                            "platform": runtime["tag"],
                            "backend": "2.5.0",
                            "user_site": False,
                        },
                    },
                    "environment_changes": {
                        "unset": ["PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV",
                                  "UV_PROJECT_ENVIRONMENT"],
                        "set": {
                            "PYTHONNOUSERSITE": "1",
                            "PYTHONDONTWRITEBYTECODE": "1",
                            "UV_OFFLINE": "1",
                            "UV_NO_CONFIG": "1",
                            "UV_PYTHON_DOWNLOADS": "never",
                            "UV_CACHE_DIR": path(system, "uv-cache"),
                            **dict.fromkeys(
                                ("TEMP", "TMP", "TMPDIR"), caller + sep + "scratch"
                            ),
                        },
                    },
                    "identities": {
                        "uv_sha256": result["uv"]["sha256"],
                        "base_python_sha256": runtime["executable_sha256"],
                        "lock_sha256": tools["Generated Files/arm-build/protocol/backend.lock"],
                        "wrapper_sha256": tools["Generated Files/arm-build/protocol/isolated_build.py"],
                        "sdk_sha256": tools["Generated Files/arm-build/candidate/build.py"],
                        "source_manifest_sha256": source["manifest_sha256"],
                    },
                    "phases": [
                        {"phase": name, "argv": argv, "returncode": 0,
                         "start_offset_seconds": 0.1 + i * 0.2, "seconds": 0.1,
                         "log": join("wrapper.json.logs", name + ".log")}
                        for i, (name, argv) in enumerate(phases)
                    ] + [
                        {"phase": "cleanup", "operation": "shutil.rmtree",
                         "path": caller, "returncode": 0,
                         "start_offset_seconds": 0.9, "seconds": 0.1}
                    ],
                    "artifacts": {
                        join("out", "artifacts", "fastapi-0.162.0.tar.gz"): sha("sdist"),
                        join("out", "artifacts", "fastapi-0.162.0-py3-none-any.whl"): sha("wheel"),
                    },
                }
                sample["argv"] = [
                    executable, wrapper, "--uv", uv, "--python", executable,
                    "--source", join("source"), "--source-manifest", manifest,
                    "--out-dir", output, "--workers", str(workers),
                    "--cache-dir", path(system, "uv-cache"),
                    "--wheelhouse", path(system, "wheelhouse"),
                    "--report", join("wrapper.json"),
                ]
                sample["wrapper_report"] = receipt
                sample["correctness"]["archive_sha256"] = copy.deepcopy(
                    receipt["artifacts"]
                )
            result["samples"].append(sample)
    return result


class FixedBehaviorGates(unittest.TestCase):
    def setUp(self):
        def fixture_git(root, *args):
            self.assertEqual(root, measure.ROOT)
            self.assertEqual(
                args, ("ls-tree", "-r", "--name-only", "a" * 40)
            )
            return "\n".join(sorted(measure.REQUIRED_TOOL_INPUTS)).encode()

        git_patch = patch.object(measure, "git", side_effect=fixture_git)
        git_patch.start()
        self.addCleanup(git_patch.stop)

    def rejected(self, mutate, both=False):
        windows, mac = evidence("Windows"), evidence("Darwin")
        mutate(windows)
        if both:
            mutate(mac)
        with self.assertRaises((ValueError, TypeError, KeyError)):
            compare.compare(windows, mac)

    def test_valid_distinct_platform_binaries_accept(self):
        windows, mac = evidence("Windows"), evidence("Darwin")
        self.assertNotEqual(windows["uv"]["sha256"], mac["uv"]["sha256"])
        self.assertNotEqual(
            windows["runtime"]["executable_sha256"],
            mac["runtime"]["executable_sha256"],
        )
        self.assertNotEqual(
            windows["runtime"]["shared_library_sha256"],
            mac["runtime"]["shared_library_sha256"],
        )
        self.assertTrue(compare.compare(windows, mac)["complete"])

    def test_required_inventory_and_digest_forms_reject(self):
        for name in sorted(measure.REQUIRED_TOOL_INPUTS):
            for value in (None, "", "g" * 64, "a" * 63, "a" * 65):
                with self.subTest(input=name, digest=value):
                    def mutate(report, item=name, digest=value):
                        if digest is None:
                            report["tool_hashes"].pop(item)
                        else:
                            report["tool_hashes"][item] = digest
                    self.rejected(mutate, both=True)
        incomplete = measure.REQUIRED_TOOL_INPUTS - {
            "Generated Files/arm-build/protocol/isolated_build.py"
        }
        with patch.object(measure, "git", return_value="\n".join(incomplete).encode()):
            with self.assertRaises(ValueError):
                measure.tool_inventory("a" * 40)

    def test_lifecycle_rejects(self):
        cases = {
            "missing": lambda s: s.pop("wrapper_report"),
            "malformed": lambda s: s.update(wrapper_report=["passed"]),
            "failed": lambda s: s["wrapper_report"].update(status="failed"),
            "errors": lambda s: s["wrapper_report"].update(errors=["failure"]),
            "schema": lambda s: s["wrapper_report"].update(schema_version=999),
            "wrong-workers": lambda s: s["wrapper_report"].update(workers=3),
            "missing-environment": lambda s: s["wrapper_report"].pop("environment"),
            "malformed-environment": lambda s: s["wrapper_report"].update(environment=[]),
            "preexisting": lambda s: s["wrapper_report"]["environment"].update(existed_before=True),
            "not-cleaned": lambda s: s["wrapper_report"]["environment"].update(exists_after_cleanup=True),
            "wrong-prefix": lambda s: s["wrapper_report"]["environment"]["identity"].update(prefix="wrong"),
            "base-equals-prefix": lambda s: s["wrapper_report"]["environment"]["identity"].update(
                base_prefix=s["wrapper_report"]["environment"]["identity"]["prefix"]
            ),
            "wrong-python": lambda s: s["wrapper_report"]["environment"]["identity"].update(executable="wrong"),
            "wrong-backend": lambda s: s["wrapper_report"]["environment"]["identity"].update(backend="2.4.0"),
            "user-site": lambda s: s["wrapper_report"]["environment"]["identity"].update(user_site=True),
            "missing-phases": lambda s: s["wrapper_report"].pop("phases"),
            "malformed-phases": lambda s: s["wrapper_report"].update(phases={}),
            "missing-phase": lambda s: s["wrapper_report"]["phases"].pop(1),
            "phase-failed": lambda s: s["wrapper_report"]["phases"][1].update(returncode=1),
            "phase-reordered": lambda s: s["wrapper_report"]["phases"].reverse(),
            "missing-cleanup": lambda s: s["wrapper_report"]["phases"].pop(),
            "cleanup-failed": lambda s: s["wrapper_report"]["phases"][-1].update(returncode=1),
            "cleanup-wrong-path": lambda s: s["wrapper_report"]["phases"][-1].update(path="unrelated"),
            "missing-clock": lambda s: s["wrapper_report"].pop("wall_seconds"),
            "malformed-clock": lambda s: s["wrapper_report"].update(wall_seconds="1.2"),
            "clock-nan": lambda s: s["wrapper_report"].update(wall_seconds=float("nan")),
            "clock-negative": lambda s: s["wrapper_report"]["phases"][0].update(seconds=-0.1),
            "clock-overlap": lambda s: s["wrapper_report"]["phases"][1].update(start_offset_seconds=0.1),
            "clock-after-exit": lambda s: s["wrapper_report"]["phases"][-1].update(start_offset_seconds=1.3),
            "clock-outside-parent": lambda s: s["wrapper_report"].update(wall_seconds=3),
        }
        for name, mutate_sample in cases.items():
            with self.subTest(case=name):
                self.rejected(lambda r, mutate=mutate_sample: mutate(r["samples"][1]))

    def test_reused_environment_rejects(self):
        def mutate(r):
            samples = [s for s in r["samples"] if s["variant"] == "S1"]
            samples[1]["wrapper_report"] = copy.deepcopy(samples[0]["wrapper_report"])
        self.rejected(mutate, both=True)

    def test_identities_reject(self):
        cases = {
            "missing-tools": lambda r: r.pop("tool_hashes"),
            "empty-tools": lambda r: r.update(tool_hashes={}),
            "missing-wrapper": lambda r: r["tool_hashes"].pop("Generated Files/arm-build/protocol/isolated_build.py"),
            "invalid-tool": lambda r: r["tool_hashes"].update(
                {"Generated Files/arm-build/protocol/isolated_build.py": "invalid"}
            ),
            "missing-revision": lambda r: r.pop("harness_revision"),
            "invalid-revision": lambda r: r.update(harness_revision=""),
            "wrong-source": lambda r: r["source"].update(revision="b" * 40),
            "missing-source-hash": lambda r: r["source"].pop("manifest_sha256"),
            "invalid-source-hash": lambda r: r["source"].update(archive_sha256="invalid"),
            "missing-runtime-hash": lambda r: r["runtime"].pop("executable_sha256"),
            "invalid-runtime-hash": lambda r: r["runtime"].update(shared_library_sha256="invalid"),
            "inconsistent-runtime-hash": lambda r: r["runtime"]["executable_binary"].update(sha256=sha("wrong")),
            "translated": lambda r: r["runtime"].update(translated=True),
            "wrong-version": lambda r: r["runtime"].update(version="3.13.14"),
            "missing-uv-hash": lambda r: r["uv"].pop("sha256"),
            "invalid-uv-hash": lambda r: r["uv"].update(sha256="invalid"),
            "non-arm-uv": lambda r: r["uv"].update(arm64_slice=False),
            "missing-wrapper-identities": lambda r: r["samples"][1]["wrapper_report"].pop("identities"),
            "missing-wrapper-lock": lambda r: r["samples"][1]["wrapper_report"]["identities"].pop("lock_sha256"),
            "wrapper-source-mismatch": lambda r: r["samples"][1]["wrapper_report"]["identities"].update(source_manifest_sha256=sha("wrong")),
            "wrapper-code-mismatch": lambda r: r["samples"][1]["wrapper_report"]["identities"].update(wrapper_sha256=sha("wrong")),
            "wrapper-runtime-mismatch": lambda r: r["samples"][1]["wrapper_report"]["identities"].update(base_python_sha256=sha("wrong")),
            "wrapper-uv-mismatch": lambda r: r["samples"][1]["wrapper_report"]["identities"].update(uv_sha256=sha("wrong")),
        }
        for name, mutate in cases.items():
            with self.subTest(case=name):
                self.rejected(mutate)


if __name__ == "__main__":
    unittest.main(verbosity=2)
