"""Pinned public Linux assets; native execution is required, never WSL startup."""

import json
import os
import platform
import tarfile
import urllib.request
from pathlib import Path

from guards import binary_guard, require, sha

ASSETS = {
    "python": (
        "https://github.com/astral-sh/python-build-standalone/releases/download/20250529/"
        "cpython-3.12.10%2B20250529-aarch64-unknown-linux-gnu-install_only_stripped.tar.gz",
        "235d0666528a8e948896f68c08964dc8dd14a54c68e5cbd4924594d2e20f81b9",
        "python/bin/python3.12",
        "5d66d5cf068a0303d145a34c9aa22e226a0f23ba7e0e9e573325b18002437313",
    ),
    "uv": (
        "https://github.com/astral-sh/uv/releases/download/0.13.6/"
        "uv-aarch64-unknown-linux-gnu.tar.gz",
        "229e194255c7958d86d56e8790d969a6f74736592133f0dfd0076f754c642c1d",
        "uv-aarch64-unknown-linux-gnu/uv",
        "7d60258dc76bca41d7b3591cdd829fa9633827fad944970bf5e1fb2a8c01476d",
    ),
}


def main():
    require(
        platform.system() == "Linux" and platform.machine() == "aarch64",
        "Bootstrap requires already running native AArch64 Linux",
    )
    root = Path(os.environ["GITHUB_WORKSPACE"]) / "paired-reference"
    root.mkdir()
    receipt = {}
    for name, (url, digest, member, executable_hash) in ASSETS.items():
        archive = root / (name + ".tar.gz")
        urllib.request.urlretrieve(url, archive)
        require(sha(archive) == digest, "Official Linux archive hash mismatch")
        with tarfile.open(archive, "r:gz") as tar:
            require(
                tar.getmember(member).isfile(), "Expected regular native executable"
            )
            tar.extractall(root, filter="data")
        executable = root / member
        binary_guard(executable, "Linux")
        require(
            sha(executable) == executable_hash, "Native Linux executable hash drift"
        )
        receipt[name] = {
            "url": url,
            "archive_sha256": digest,
            "executable": str(executable),
            "executable_sha256": executable_hash,
        }
    (root / "bootstrap-download.json").write_text(json.dumps(receipt, indent=2) + "\n")
    with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as out:
        out.write(f"PAIRED_ROOT={root}\n")
        out.write(f"PAIRED_PYTHON={receipt['python']['executable']}\n")
        out.write(f"P50_UV={receipt['uv']['executable']}\n")


if __name__ == "__main__":
    main()
