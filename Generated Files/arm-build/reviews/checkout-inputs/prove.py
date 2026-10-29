"""Local checkout/input proof only: no builds, network, or runtime parity claim."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SCRATCH = HERE / ".scratch"
RECEIPTS = HERE / "receipts"
SOURCE = "79cab5bed28b24d92c185d236feb33f5783dfeb3"
ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_CONFIG")}
ENV["PYTHONDONTWRITEBYTECODE"] = "1"


def git(root, *args, eol="false", data=None):
    return subprocess.run(
        ["git", "-c", f"core.autocrlf={eol}", "-C", str(root), *args],
        input=data, capture_output=True, check=True, env=ENV,
    ).stdout


def hashes(root, revision, names):
    raw = git(root, "cat-file", "--batch",
              data="".join(f"{revision}:{n}\n" for n in names).encode())
    result = {}
    offset = 0
    for name in names:
        end = raw.index(b"\n", offset)
        header = raw[offset:end].split()
        assert header[1] == b"blob", (name, header)
        size = int(header[2])
        content = raw[end + 1:end + 1 + size]
        result[name] = hashlib.sha256(content).hexdigest()
        offset = end + size + 2
    assert offset == len(raw)
    return result


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def main():
    for key in list(os.environ):
        if key.startswith("GIT_CONFIG"):
            del os.environ[key]
    os.environ.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.autocrlf",
                      GIT_CONFIG_VALUE_0="false")
    assert not SCRATCH.exists(), "Use a fresh owned scratch directory"
    SCRATCH.mkdir()
    RECEIPTS.mkdir(exist_ok=True)
    before = git(ROOT, "status", "--porcelain", "--untracked-files=no")
    revision = git(ROOT, "rev-parse", "HEAD").decode().strip()
    workflow_name = ".github/workflows/arm-build-experiment.yml"
    workflow = git(ROOT, "show", f"{revision}:{workflow_name}").decode()
    blocks = re.findall(r"          sparse-checkout: \|\n((?:            .*\n)+)", workflow)
    assert len(blocks) == 2 and blocks[0] == blocks[1]
    patterns = "\n".join(line.strip() for line in blocks[0].splitlines()) + "\n"
    assert 'GIT_CONFIG_KEY_0: core.autocrlf' in workflow
    assert 'GIT_CONFIG_VALUE_0: "false"' in workflow
    report = {
        "harness_revision": revision, "source_revision": SOURCE,
        "platform": sys.platform, "python": sys.version,
        "git": git(ROOT, "version").decode().strip(),
        "scope": "Two Windows Git EOL configurations, NOT a macOS runtime test",
        "workflow_disables_autocrlf": True, "sparse_patterns": patterns.splitlines(),
        "checkouts": [],
    }
    for eol in ("false", "true"):
        checkout = SCRATCH / f"tools-{eol}"
        git(ROOT, "clone", "--shared", "--no-checkout", "--quiet", str(ROOT), str(checkout), eol=eol)
        git(checkout, "sparse-checkout", "init", "--no-cone", eol=eol)
        git(checkout, "sparse-checkout", "set", "--no-cone", "--stdin",
            eol=eol, data=patterns.encode())
        git(checkout, "checkout", "--quiet", "--detach", revision, eol=eol)
        protocol = checkout / "Generated Files" / "arm-build" / "protocol"
        sys.path.insert(0, str(protocol))
        helper = module(protocol / "measure_pairs.py", f"proof_{eol}")
        try:
            helper.tool_inventory(revision)
        except ValueError as error:
            report.setdefault("production_inventory_errors", []).append(str(error))
        names = git(checkout, "ls-tree", "-r", "--full-tree", "--name-only", revision).decode().splitlines()
        inventory = sorted(set(helper.REQUIRED_TOOL_INPUTS) | {
            n for n in names
            if n.startswith(helper.PREFIX) and (
                (n.removeprefix(helper.PREFIX).count("/") == 0 and n.endswith(".lock"))
                or (n.removeprefix(helper.PREFIX).count("/") == 1
                    and n.removeprefix(helper.PREFIX).split("/")[0] in ("candidate", "protocol")
                    and (n.endswith(".py") or ("/protocol/" in n and n.endswith(".lock")))))
        })
        assert set(inventory) <= set(names)
        canonical = hashes(ROOT, revision, inventory)
        def required_hashes():
            return {n: hashlib.sha256((checkout / n).read_bytes()).hexdigest() for n in inventory}
        actual = required_hashes()
        differing = sorted(n for n in inventory if actual[n] != canonical[n])
        assert differing == ([] if eol == "false" else [workflow_name])
        materialized = sorted(
            row[2:].decode()
            for row in git(checkout, "ls-files", "-t", "-z").split(b"\0")
            if row.startswith(b"H ")
        )
        controls = [p for p in materialized if p.endswith(".gitattributes")]
        control_hashes = {n: hashlib.sha256((checkout / n).read_bytes()).hexdigest() for n in controls}
        assert set(materialized) == set(inventory) | set(controls)
        assert all((checkout / p).is_file() for p in inventory)
        victim = checkout / "Generated Files" / "arm-build" / "protocol" / "owned_process.py"
        victim.rename(victim.with_suffix(".missing"))
        try:
            required_hashes()
        except (ValueError, FileNotFoundError):
            pass
        else:
            raise AssertionError("Missing required input did not fail")
        finally:
            victim.with_suffix(".missing").rename(victim)
        attrs = git(checkout, "check-attr", "--stdin", "text", "eol",
                    data=("\n".join(materialized) + "\n").encode())
        (RECEIPTS / f"attributes-{eol}.txt").write_bytes(attrs)
        report["checkouts"].append({
            "command_scoped_core_autocrlf": eol,
            "hashes": actual, "materialized_paths": materialized,
            "noncanonical_paths": differing,
            "all_LF_declared_hashes_equal_git_blobs": True,
            "attribute_control_raw_hashes": control_hashes, "missing_helper_rejected": True,
            "only_inventory_and_attribute_controls_materialized": True,
        })
    assert all(report["checkouts"][0]["hashes"][n] == report["checkouts"][1]["hashes"][n]
               for n in inventory if n != workflow_name)
    source = SCRATCH / "package-source"
    git(ROOT, "clone", "--shared", "--no-checkout", "--quiet", str(ROOT), str(source))
    git(source, "checkout", "--quiet", "--detach", SOURCE)
    assert not git(source, "status", "--porcelain")
    output = SCRATCH / "canonical"
    output.mkdir()
    identity = helper.canonical_source(source, output)
    manifest = json.loads((output / "source-manifest.json").read_bytes())
    tracked = git(source, "ls-tree", "-rz", SOURCE)
    modes = {}
    for row in tracked.split(b"\0"):
        if row:
            head, name = row.split(b"\t")
            mode = int(head.split()[0], 8)
            assert mode in (0o100644, 0o100755)
            modes[name.decode()] = mode & 0o777
    assert set(manifest) == set(modes)
    assert not any(n.startswith("Generated Files/") for n in manifest)
    source_hashes = hashes(source, SOURCE, sorted(manifest))
    assert all(v["sha256"] == source_hashes[n] and v["mode"] == modes[n]
               for n, v in manifest.items())
    assert helper.source_matches(output / "source", manifest)
    assert not git(source, "status", "--porcelain")
    assert not list(source.rglob(".pdm-build"))
    (RECEIPTS / "source-manifest.json").write_bytes((output / "source-manifest.json").read_bytes())
    report["source"] = {
        **identity, "complete_git_tree": True, "regular_git_modes_verified": True,
        "all_archive_payload_hashes_equal_git_blobs": True,
        "no_generated_inputs": True, "source_checkout_clean_before_after": True,
        "no_pdm_build": True,
    }
    test_checkout = SCRATCH / "tools-false"
    protocol = test_checkout / "Generated Files" / "arm-build" / "protocol"
    for test in ("test_pairs.py", "test_isolated_build.py", "test_owned_process.py"):
        result = subprocess.run([sys.executable, "-B", str(protocol / test)],
                                cwd=protocol, env=ENV, capture_output=True)
        (RECEIPTS / f"{test}.stdout.log").write_bytes(result.stdout)
        (RECEIPTS / f"{test}.stderr.log").write_bytes(result.stderr)
        report.setdefault("test_results", {})[test] = result.returncode
    assert git(ROOT, "status", "--porcelain", "--untracked-files=no") == before
    report["original_tracked_status_unchanged"] = True
    report["tests"] = ["test_pairs.py", "test_isolated_build.py", "test_owned_process.py"]
    report["unverified"] = [
        "Native macOS/ARM execution", "Hosted checkout action execution",
        "Actual CI C: NTFS placement", "Dependency acquisition/full artifact builds",
        "Performance, protection causality, PGO binary mapping",
    ]
    (RECEIPTS / "proof.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "blocked" if report.get("production_inventory_errors") else "passed",
                      "inputs": len(inventory), "source_files": len(manifest),
                      "test_results": report["test_results"]}))
    return 1 if report.get("production_inventory_errors") or any(report["test_results"].values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
