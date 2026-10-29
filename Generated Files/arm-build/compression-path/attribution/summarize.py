"""Verify and summarize retained evidence without executing another build."""

import hashlib
import json
from pathlib import Path
import sys
import zipfile


def main():
    evidence = Path(sys.argv[1])
    preparation = json.loads((evidence / "preparation.json").read_text())
    root = Path(preparation["root"])
    profile = json.loads((evidence / "profile.json").read_text())
    stats = json.loads((evidence / "stats.json").read_text())
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    if digest(evidence / "build.prof") != profile["profile_sha256"]:
        raise ValueError("Raw profile hash mismatch")
    checked = []
    with zipfile.ZipFile(next((root / "wheelhouse").glob("*.whl"))) as wheel:
        for name in wheel.namelist():
            if name.endswith(".py"):
                installed = root / "env" / "Lib" / "site-packages" / name
                if installed.read_bytes() != wheel.read(name):
                    raise ValueError(f"Official backend source changed: {name}")
                checked.append(name)
    leaves = []
    for entry in stats:
        if entry["file"] == "~" and "zlib" in entry["function"]:
            leaves.append(dict(
                function=entry["function"], calls=entry["total_calls"],
                self_seconds=entry["self_seconds"],
                fraction_of_region_wall=entry["self_seconds"] / profile["wall_seconds"],
            ))
    codec_total = sum(e["self_seconds"] for e in leaves)
    gzip = root / "runtime" / "Lib" / "gzip.py"
    lines = gzip.read_text().splitlines()
    proof = [{"line": i + 1, "text": line}
             for i, line in enumerate(lines)
             if any(s in line for s in ("-zlib.MAX_WBITS", "zlib.crc32", "zlib.compressobj"))]
    output = dict(
        profile_entry_count=len(stats), timer="cProfile default elapsed/performance timer",
        wall_seconds=profile["wall_seconds"],
        process_cpu_seconds=profile["process_cpu_seconds"],
        native_zlib_leaves=leaves, native_zlib_self_seconds=codec_total,
        native_zlib_fraction_of_region_wall=codec_total / profile["wall_seconds"],
        no_profiled_native_calls=[name for name in ("decompress", "adler32")
                                 if not any(name in e["function"] for e in leaves)],
        official_backend_python_files_verified=checked,
        gzip_source_sha256=digest(gzip), gzip_source_codec_lines=proof,
        filesystem={"drive": "C:", "filesystem": "NTFS",
                    "observation": "Get-Volume -DriveLetter C; no protection changes"},
        validation="No second build or profile; retained raw profile hash verified",
    )
    (evidence / "summary.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({k: v for k, v in output.items()
                      if k != "official_backend_python_files_verified"}, indent=2))


if __name__ == "__main__":
    main()
