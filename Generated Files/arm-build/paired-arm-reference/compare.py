"""Unchanged P23 transfer comparator (function SHA256 in SOURCE/READINESS.md)."""

import gzip

import frozen as p23
from guards import require, sha


def compare_outputs(reference_dir, actual_dir):
    expected, actual = p23.full_inventory(reference_dir), p23.full_inventory(actual_dir)
    require(expected == actual, "Meaningful full member/metadata/RECORD difference")
    require(
        {k: list(v) for k, v in expected.items()}
        == {k: list(v) for k, v in actual.items()},
        "Archive order changed",
    )
    a = next(reference_dir.glob("*.tar.gz")).read_bytes()
    b = next(actual_dir.glob("*.tar.gz")).read_bytes()
    differences = [i for i, (x, y) in enumerate(zip(a, b, strict=False)) if x != y]
    require(
        len(a) == len(b) and set(differences) <= {4, 5, 6, 7},
        "Raw gzip difference beyond predeclared wrapper mtime",
    )
    require(
        gzip.decompress(a) == gzip.decompress(b),
        "Decompressed tar bytes differ",
    )
    require(
        sha(next(reference_dir.glob("*.whl"))) == sha(next(actual_dir.glob("*.whl"))),
        "Raw wheel bytes differ",
    )
    return {"full_pass": True, "raw_gzip_different_offsets": differences}
