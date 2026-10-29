"""Owned-C diagnostic; cProfile output is not a clean timing sample."""

import sys

sys.dont_write_bytecode = True

import cProfile
import hashlib
import importlib.metadata
import json
import os
import platform
import pstats
import sysconfig
import time
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(sys.argv[1]).resolve()
    kind = sys.argv[2]
    os.chdir(root)
    sys.path.insert(0, str(root / "code"))
    import build

    receipt = {
        "kind": kind,
        "identity": {
            "version": sys.version,
            "executable": sys.executable,
            "base_prefix": sys.base_prefix,
            "machine": platform.machine(),
            "platform": sysconfig.get_platform(),
            "backend": importlib.metadata.version("pdm-backend"),
        },
        "hashes": {
            str(p.relative_to(root)): digest(p)
            for p in [*(root / "code").glob("*.py"), root / "source.tar",
                      root / "source-manifest.json"]
        },
    }
    assert receipt["identity"]["backend"] == "2.5.0"
    assert sys.version_info[:3] == (3, 13, 15)
    assert sysconfig.get_platform() == "win-arm64"
    profile = cProfile.Profile() if kind == "profile" else None
    start, cpu = time.perf_counter(), time.process_time()
    if profile:
        profile.enable()
    result = build.build(root / "source", root / "source-manifest.json",
                         root / f"{kind}-output", 3)
    if profile:
        profile.disable()
    receipt["build"] = {
        "wall_seconds": time.perf_counter() - start,
        "process_cpu_seconds": time.process_time() - cpu,
        "workers": 3,
        "artifacts": result,
    }
    if profile:
        profile.dump_stats(str(root / "diagnostic.pstats"))
        stats = pstats.Stats(profile)
        rows = [
            {"file": file, "line": line, "function": name,
             "primitive_calls": cc, "calls": nc,
             "self_seconds": tt, "cumulative_seconds": ct}
            for (file, line, name), (cc, nc, tt, ct, _) in stats.stats.items()
        ]
        receipt["python_profile_total_calls"] = stats.total_calls
        receipt["top40_cumulative"] = sorted(
            rows, key=lambda row: row["cumulative_seconds"], reverse=True
        )[:40]
        receipt["attribution"] = [
            row for row in rows
            if row["function"] in {
                "source_files", "source_files_nested", "checked_children",
                "configuration", "safe_path", "resolve", "stat", "lstat",
                "is_file", "is_dir", "select", "extract_selected",
                "build_artifact", "build", "compress", "write", "gettarinfo",
            }
        ]
    # Strict full-mode/payload/RECORD verification is deliberately outside clock.
    from validate import compare, inventory

    receipt["oracle"] = compare(
        json.loads((root / "gold.json").read_text(encoding="utf-8")),
        inventory(root / f"{kind}-output" / "artifacts"),
    )
    assert receipt["oracle"]["strict_pass"], receipt["oracle"]
    receipt["artifact_hashes"] = {
        p.name: digest(p) for p in (root / f"{kind}-output" / "artifacts").iterdir()
    }
    (root / f"{kind}.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
