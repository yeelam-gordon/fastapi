"""Post-build verification, deliberately outside the measured process."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import zipfile

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
sys.path.insert(0, str(LAB))
import benchmark


def raw_members(directory):
    with zipfile.ZipFile(next(directory.glob("*.whl"))) as archive:
        wheel = {m.filename: hashlib.sha256(archive.read(m)).hexdigest()
                 for m in archive.infolist() if not m.is_dir()}
    with tarfile.open(next(directory.glob("*.tar.gz"))) as archive:
        sdist = {m.name: (m.mode, m.uid, m.gid,
                         hashlib.sha256(archive.extractfile(m).read()).hexdigest())
                 for m in archive if m.isfile()}
    return wheel, sdist


def main():
    original = LAB / "round-2" / "overhead" / "selective.py"
    def selector(path):
        return next(n for n in ast.parse(path.read_text()).body
                    if isinstance(n, ast.FunctionDef) and n.name == "select")
    assert ast.dump(selector(original)) == ast.dump(selector(HERE / "selective_inputs.py"))
    for label in ("diagnostic-4", "diagnostic-8"):
        timing = json.loads((HERE / f"{label}-timings.json").read_text())
        assert not any(timing["coordinator_modules_loaded"].values())
    reference = (LAB / "results" / "ci-40814588064" / "macos" / "ci" /
                 "artifacts" / "prepare-baseline")
    expected = raw_members(reference)
    canonical = benchmark.artifact_manifest(reference)
    rows = []
    for label in ["prepare", *[f"trial-{i}" for i in range(1, 6)],
                  "diagnostic-4", "diagnostic-8"]:
        directory = HERE / "work" / label / "artifacts"
        benchmark.compare_manifests(canonical, benchmark.artifact_manifest(directory))
        actual = raw_members(directory)
        assert actual == expected, f"Raw bytes or full sdist permissions differ: {label}"
        rows.append({"label": label,
                     "all_raw_member_bytes_and_full_sdist_modes_uid_gid_equal": True})
    receipt = {"reference": str(reference), "verification": rows,
               "selector_function_ast_identical_to_round_2": True,
               "diagnostic_workers_exclude_benchmark_and_statistics": True,
               "code_sha256": {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                               for name in ("writer.cjs", "experiment.py", "selective_inputs.py",
                                            "test_writer.py", "verify.py")}}
    (HERE / "raw-verification.json").write_text(json.dumps(receipt, indent=2))
    print("PASS: all eight builds, raw wheel bytes (including RECORD), full sdist modes/uid/gid")


if __name__ == "__main__":
    main()
