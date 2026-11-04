"""Build and functionally qualify a private Windows ARM64 Argon2 binding."""

import argparse
import base64
import dataclasses
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import re
import shutil
import struct
import sys
import sysconfig
from pathlib import Path

HERE = Path(__file__).resolve().parent
GUARD_SHA256 = "45d6db4f6452c4f7116ca23c6e2aa74cda90a15548bd5c9bb3b3574973ef458e"
BINDING_COMMIT = "fb50afcbb80aee5e87d6f8b1d15e7238321387c9"
VENDOR_COMMIT = "f57e61e19229e23c4445b85494dbf7c07de721cb"
VERSIONS = {
    "argon2-cffi-bindings": "26.1.0",
    "argon2-cffi": "25.1.0",
    "cffi": "2.1.1",
    "pwdlib": "0.3.1",
}
PASSWORD = "public-secure-wipe-transfer-password"
SALT = b"public-test-salt!"
ENCODED = "$argon2id$v=19$m=65536,t=3,p=4$cHVibGljLXRlc3Qtc2FsdCE$UAjeLE1c2dX3f0S84lLLH3pCvvsONL1+BrgaNKbj3tE"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2), encoding="utf-8")


def machine(path):
    data = Path(path).read_bytes()
    offset = struct.unpack_from("<I", data, 60)[0]
    if data[offset : offset + 4] != b"PE\0\0":
        raise ValueError(f"Not a PE image: {Path(path).name}")
    return struct.unpack_from("<H", data, offset + 4)[0]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sdk-version", default="10.0.26100.0")
    parser.add_argument("--clang", type=Path)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"10\.0\.\d+\.0", args.sdk_version):
        parser.error("--sdk-version must be an exact installed Windows SDK version")
    for path in (args.source, args.python, args.output, args.clang):
        if path and any(character in str(path) for character in '"%!\r\n'):
            parser.error(
                "Paths cannot contain quotes, percent, exclamation or newlines"
            )
    return args


def prepare_output(output, source, python):
    output, source, python = (Path(path).resolve() for path in (output, source, python))
    if output.exists():
        raise ValueError("--output must be a NEW directory")
    if output.is_relative_to(source) or output.is_relative_to(python.parent.parent):
        raise ValueError("--output cannot modify source or reference environment")
    output.mkdir(parents=True)
    return output


def require_receipt(receipt):
    if not receipt.succeeded:
        raise RuntimeError("Owned invocation failed or did not naturally drain")


def reference_files(site):
    return {
        str(path.relative_to(site)): digest(path)
        for package in ("_argon2_cffi_bindings", "argon2", "pwdlib")
        for path in (site / package).rglob("*")
        if path.is_file()
    }


def probe():
    from _argon2_cffi_bindings import _ffi

    image = Path(_ffi.__file__).resolve()
    site = Path(sysconfig.get_path("platlib")).resolve()
    if image.parent != site / "_argon2_cffi_bindings":
        raise ValueError("Reference binding is not in the prepared environment")
    print(
        json.dumps(
            {
                "image": str(image),
                "image_sha256": digest(image),
                "machine": machine(image),
                "site": str(site),
                "reference_files": reference_files(site),
                "include": sysconfig.get_path("include"),
                "library": str(Path(sys.base_prefix) / "libs" / "python3.lib"),
                "python_machine": machine(sys.executable),
                "gil_disabled": bool(sysconfig.get_config_var("Py_GIL_DISABLED")),
                "versions": {
                    name: importlib.metadata.version(name) for name in VERSIONS
                },
            }
        )
    )


def has_pyinit(path):
    data = Path(path).read_bytes()
    pe = struct.unpack_from("<I", data, 60)[0]
    optional = pe + 24
    section_start = optional + struct.unpack_from("<H", data, pe + 20)[0]

    def offset(rva):
        for index in range(struct.unpack_from("<H", data, pe + 6)[0]):
            entry = section_start + index * 40
            length, address, raw_length, raw = struct.unpack_from(
                "<IIII", data, entry + 8
            )
            if address <= rva < address + max(length, raw_length):
                return raw + rva - address
        raise ValueError("Unmapped export RVA")

    exports = offset(struct.unpack_from("<I", data, optional + 112)[0])
    count = struct.unpack_from("<I", data, exports + 24)[0]
    table = offset(struct.unpack_from("<I", data, exports + 32)[0])
    for index in range(count):
        position = offset(struct.unpack_from("<I", data, table + index * 4)[0])
        if data[position : data.index(b"\0", position)] == b"PyInit__ffi":
            return True
    return False


def functional(candidate=None):
    if candidate:
        sys.path.insert(0, str(Path(candidate).resolve()))
    from _argon2_cffi_bindings import _ffi
    from argon2 import PasswordHasher, Type
    from argon2.low_level import hash_secret_raw
    from pwdlib import PasswordHash

    image = Path(_ffi.__file__).resolve()
    if (
        candidate
        and image.parent != Path(candidate).resolve() / "_argon2_cffi_bindings"
    ):
        raise ValueError("Candidate extension was not actually imported")
    hasher, pwd = PasswordHasher(), PasswordHash.recommended()
    if (hasher.time_cost, hasher.memory_cost, hasher.parallelism, hasher.salt_len) != (
        3,
        65536,
        4,
        16,
    ):
        raise ValueError("Unexpected PasswordHasher configuration defaults")

    def outcome(call):
        try:
            return call()
        except Exception as error:
            return type(error).__name__

    cases = {
        "argon2_correct": hasher.verify(ENCODED, PASSWORD),
        "argon2_wrong": outcome(
            lambda: hasher.verify(ENCODED, "wrong-public-password")
        ),
        "argon2_malformed": outcome(
            lambda: hasher.verify("malformed-public-hash", PASSWORD)
        ),
        "argon2_encoded": hasher.hash(PASSWORD, salt=SALT),
        "pwdlib_correct": pwd.verify(PASSWORD, ENCODED),
        "pwdlib_wrong": pwd.verify("wrong-public-password", ENCODED),
        "pwdlib_malformed": outcome(
            lambda: pwd.verify(PASSWORD, "malformed-public-hash")
        ),
        "pwdlib_encoded": pwd.hash(PASSWORD, salt=SALT),
    }
    raw = hash_secret_raw(PASSWORD.encode(), SALT, 3, 65536, 4, 32, Type.ID, 19)
    if raw != base64.b64decode(ENCODED.rsplit("$", 1)[1] + "=="):
        raise ValueError("Full raw output differs")
    if (
        cases["argon2_correct"] is not True
        or cases["pwdlib_correct"] is not True
        or cases["pwdlib_wrong"] is not False
        or cases["argon2_wrong"] != "VerifyMismatchError"
        or cases["argon2_malformed"] != "InvalidHashError"
        or cases["pwdlib_malformed"] != "UnknownHashError"
        or cases["argon2_encoded"] != ENCODED
        or cases["pwdlib_encoded"] != ENCODED
    ):
        raise ValueError("Functional cases differ")
    print(
        json.dumps(
            {
                "image_sha256": digest(image),
                "machine": machine(image),
                "pyinit": has_pyinit(image),
                "candidate_loaded": bool(candidate),
                "cases": cases,
                "raw_hex": raw.hex(),
                "versions": {
                    name: importlib.metadata.version(name) for name in VERSIONS
                },
                "fixture_salt_bytes": len(SALT),
                "performance_measurements": 0,
            }
        )
    )


def validate_functional(reference, candidate, before, after):
    if before != after:
        raise ValueError("Installed reference files changed")
    for key in ("cases", "raw_hex", "versions"):
        if reference[key] != candidate[key]:
            raise ValueError(f"Reference/candidate {key} mismatch")
    if (
        not candidate["candidate_loaded"]
        or candidate["machine"] != 0xAA64
        or not candidate["pyinit"]
    ):
        raise ValueError("Native candidate import/export proof failed")


def discover_vs(owned, output, explicit_clang=None):
    roots = []
    installer = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    vswhere = installer / r"Microsoft Visual Studio\Installer\vswhere.exe"
    if vswhere.is_file():
        owned(
            "vswhere",
            [str(vswhere), "-all", "-products", "*", "-format", "json", "-utf8"],
        )
        roots.extend(
            Path(item["installationPath"])
            for item in json.loads(
                (output / "vswhere.stdout.txt").read_text(encoding="utf-8-sig")
            )
        )
    for name in ("ProgramFiles", "ProgramFiles(x86)"):
        base = (
            Path(os.environ.get(name, r"C:\Program Files")) / "Microsoft Visual Studio"
        )
        roots.extend(
            path.parents[3]
            for path in base.glob(r"*\*\VC\Auxiliary\Build\vcvarsall.bat")
        )
    for root in dict.fromkeys(roots):
        compiler_candidates = (
            [explicit_clang]
            if explicit_clang
            else [
                root / r"VC\Tools\Llvm\ARM64\bin\clang-cl.exe",
                root / r"VC\Tools\Llvm\bin\clang-cl.exe",
            ]
        )
        if (
            (root / r"VC\Auxiliary\Build\vcvarsall.bat").is_file()
            and (
                root
                / r"Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
            ).is_file()
            and (
                root / r"Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"
            ).is_file()
            and any(
                path.is_file() and machine(path) == 0xAA64
                for path in compiler_candidates
            )
        ):
            return root
    raise FileNotFoundError(
        "Existing Visual Studio with CMake/Ninja/native ARM64 Clang not found"
    )


def sdk_root(version):
    import winreg

    roots = []
    for access in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Microsoft SDKs\Windows\v10.0",
                0,
                winreg.KEY_READ | access,
            ) as key:
                roots.append(Path(winreg.QueryValueEx(key, "InstallationFolder")[0]))
        except OSError:
            pass
    roots.append(
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / r"Windows Kits\10"
    )
    for root in roots:
        if (root / "Lib" / version / r"um\arm64\volatileaccessu.lib").is_file():
            return root
    raise FileNotFoundError(
        f"Installed ARM64 volatileaccessu.lib missing for SDK {version}"
    )


def verify_source(source, owned, output):
    identities = {}
    if (source / ".git").exists():
        git = shutil.which("git")
        if not git:
            raise FileNotFoundError(
                "Read-only input Git verification requires installed git"
            )
        for scope, root, expected in (
            ("binding", source, BINDING_COMMIT),
            ("libargon2", source / r"extras\libargon2", VENDOR_COMMIT),
        ):
            owned(f"{scope}-head", [git, "-C", str(root), "rev-parse", "HEAD"])
            if (output / f"{scope}-head.stdout.txt").read_text().strip() != expected:
                raise ValueError(f"Wrong pinned {scope} commit")
            owned(f"{scope}-tree", [git, "-C", str(root), "ls-tree", "-r", "HEAD"])
            for line in (output / f"{scope}-tree.stdout.txt").read_text().splitlines():
                metadata, relative = line.split("\t", 1)
                mode, kind, expected_blob = metadata.split()
                if mode == "160000":
                    if relative != "extras/libargon2" or expected_blob != VENDOR_COMMIT:
                        raise ValueError("Unexpected submodule identity")
                    continue
                if kind != "blob":
                    raise ValueError("Unexpected source entry")
                data = (root / relative).read_bytes()
                blob = hashlib.sha1(
                    b"blob " + str(len(data)).encode() + b"\0" + data
                ).hexdigest()
                if blob != expected_blob:
                    raise ValueError(
                        f"Source differs from pinned blob: {scope}:{relative}"
                    )
                identities[f"{scope}:{relative}"] = hashlib.sha256(data).hexdigest()
        mode = "pinned_input_git_commit_and_all_worktree_blobs"
    else:
        manifest = source.parent / "canonical-provenance.json"
        if (
            digest(manifest)
            != "fc754d13b604394827642ec22b9807995f5ed449b670e1b87e41acbc8145cfcf"
        ):
            raise ValueError("Verified retained source manifest unavailable or changed")
        provenance = json.loads(manifest.read_text())
        if (provenance["binding_commit"], provenance["libargon2_commit"]) != (
            BINDING_COMMIT,
            VENDOR_COMMIT,
        ):
            raise ValueError("Manifest commit identities differ")
        for scope in ("binding", "libargon2"):
            root = source if scope == "binding" else source / r"extras\libargon2"
            for relative, expected in provenance["strict_blob_identity"][scope][
                "files"
            ].items():
                data = (root / relative).read_bytes()
                if (
                    hashlib.sha1(
                        b"blob " + str(len(data)).encode() + b"\0" + data
                    ).hexdigest()
                    != expected
                ):
                    raise ValueError(f"Retained source blob differs: {relative}")
                identities[f"{scope}:{relative}"] = hashlib.sha256(data).hexdigest()
        mode = "sha256_anchored_previously_verified_106_file_manifest"
    save(
        output / "source-proof.json",
        {
            "binding_commit": BINDING_COMMIT,
            "vendor_commit": VENDOR_COMMIT,
            "verification_mode": mode,
            "files_sha256": identities,
        },
    )


def build(args, output):
    if os.name != "nt":
        raise RuntimeError("This builder supports Windows only")
    source, python = args.source.resolve(), args.python.resolve()
    guardian = next(
        (
            path
            for path in (
                HERE.with_name("protocol") / "owned_process.py",
                HERE.with_name("hobl-complete-ci") / "owned_process.py",
            )
            if path.is_file()
        ),
        None,
    )
    if not guardian or digest(guardian) != GUARD_SHA256:
        raise ValueError("Original portable guardian missing or changed")
    spec = importlib.util.spec_from_file_location("secure_wipe_builder_guard", guardian)
    guard = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = guard
    spec.loader.exec_module(guard)
    scratch = output / "scratch"
    scratch.mkdir()
    environment = dict(
        os.environ, PYTHONDONTWRITEBYTECODE="1", TEMP=str(scratch), TMP=str(scratch)
    )
    for name in ("ARGON2_CFFI_USE_SYSTEM", "ARGON2_CFFI_USE_SSE2"):
        environment.pop(name, None)

    def owned(name, command, timeout=30, env=None):
        receipt = guard.run_owned(
            command,
            cwd=str(output),
            env=env or environment,
            stdout_path=output / f"{name}.stdout.txt",
            stderr_path=output / f"{name}.stderr.txt",
            timeout=timeout,
        )
        save(output / f"{name}.receipt.json", dataclasses.asdict(receipt))
        require_receipt(receipt)

    verify_source(source, owned, output)
    vs = discover_vs(owned, output, args.clang.resolve() if args.clang else None)
    clang = (
        args.clang.resolve()
        if args.clang
        else next(
            (
                path
                for path in (
                    vs / r"VC\Tools\Llvm\ARM64\bin\clang-cl.exe",
                    vs / r"VC\Tools\Llvm\bin\clang-cl.exe",
                )
                if path.is_file()
            ),
            None,
        )
    )
    if not clang or machine(clang) != 0xAA64:
        raise ValueError("Existing native ARM64 clang-cl required")
    cmake = vs / r"Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
    ninja = vs / r"Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"
    for tool in (cmake, ninja, python):
        if not tool.is_file():
            raise FileNotFoundError(f"Existing tool missing: {tool.name}")
    sdk = sdk_root(args.sdk_version)
    library = sdk / "Lib" / args.sdk_version / r"um\arm64\volatileaccessu.lib"
    owned("compiler-version", [str(clang), "--version"])
    compiler_version = (output / "compiler-version.stdout.txt").read_text()
    if not re.search(r"Target:\s*(?:aarch64|arm64)-.*windows", compiler_version):
        raise ValueError("Compiler does not target native Windows ARM64")
    owned(
        "reference-probe",
        [str(python), "-B", str(Path(__file__).resolve()), "--_probe"],
    )
    reference = json.loads((output / "reference-probe.stdout.txt").read_text())
    if (
        reference["versions"] != VERSIONS
        or reference["machine"] != 0xAA64
        or reference["python_machine"] != 0xAA64
        or reference["gil_disabled"]
    ):
        raise ValueError("Qualified native reference versions/ABI differ")
    for path in (Path(reference["include"]) / "Python.h", Path(reference["library"])):
        if not path.is_file():
            raise FileNotFoundError(
                f"Prepared Python development input missing: {path.name}"
            )
    package_root = output / "candidate"
    package = package_root / "_argon2_cffi_bindings"
    package.mkdir(parents=True)
    for path in Path(reference["image"]).parent.rglob("*.py"):
        target = package / path.relative_to(Path(reference["image"]).parent)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        if digest(path) != digest(target):
            raise ValueError("Reference Python copy differs")
    arguments = [
        str(cmake),
        "-S",
        str(source),
        "-B",
        str(output / "build"),
        "-G",
        "Ninja",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_SYSTEM_PROCESSOR=ARM64",
        f"-DCMAKE_C_COMPILER={clang}",
        f"-DCMAKE_MAKE_PROGRAM={ninja}",
        f"-DPython_EXECUTABLE={python}",
        "-DSKBUILD_PROJECT_NAME=argon2-cffi-bindings",
        "-DSKBUILD_PROJECT_VERSION=26.1.0",
        "-DSKBUILD_SABI_COMPONENT=Development.SABIModule",
        "-DSKBUILD_SABI_VERSION=3.10",
        "-DCMAKE_C_FLAGS=/DVOLATILE_ACCESSOR_LIB",
        "-DCMAKE_MODULE_LINKER_FLAGS=volatileaccessu.lib",
        "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        f"-DCMAKE_INSTALL_PREFIX={package_root}",
    ]
    save(
        output / "build-plan.json",
        {
            "schema": 1,
            "compiler_version": compiler_version,
            "arguments": arguments,
            "tools_sha256": {
                str(path): digest(path) for path in (clang, cmake, ninja, python)
            },
            "headers_sha256": {
                name: digest(sdk / "Include" / args.sdk_version / "um" / name)
                for name in ("winnt.h", "winbase.h")
            },
            "static_library_sha256": digest(library),
            "guardian_sha256": digest(guardian),
            "guardian_path": str(guardian),
            "source_default_internal_wipe_flag": 1,
            "fixture": "default-cost Argon2id/v19/t3/m65536/p4/hash32; public salt17; configuration default salt16",
        },
    )

    def quoted(items):
        return " ".join(f'"{item}"' for item in items)

    vcvars = vs / r"VC\Auxiliary\Build\vcvarsall.bat"
    command = output / "prepare.cmd"
    command.write_text(
        "\n".join(
            [
                "@echo off",
                f'call "{vcvars}" arm64 {args.sdk_version} > "%~dp0developer-env.txt" 2>&1',
                "if errorlevel 1 exit /b %errorlevel%",
                'set INCLUDE > "%~dp0selected-include.txt"',
                'set LIB > "%~dp0selected-lib.txt"',
                'set WindowsSDKVersion > "%~dp0selected-sdk.txt"',
                quoted(arguments),
                "if errorlevel 1 exit /b %errorlevel%",
                quoted([str(cmake), "--build", str(output / "build"), "--verbose"]),
                "if errorlevel 1 exit /b %errorlevel%",
                quoted([str(cmake), "--install", str(output / "build")]),
                "exit /b %errorlevel%",
            ]
        )
        + "\n"
    )
    owned(
        "preparation",
        [os.environ["ComSpec"], "/d", "/c", "call", str(command)],
        timeout=90,
        env=dict(environment, VSCMD_SKIP_SENDTELEMETRY="1"),
    )
    selected = (
        (output / "selected-sdk.txt").read_text().strip().split("=", 1)[1].rstrip("\\")
    )
    if selected != args.sdk_version:
        raise ValueError("Actual selected SDK differs")
    lib_line = next(
        line
        for line in (output / "selected-lib.txt").read_text().splitlines()
        if line.startswith("LIB=")
    )
    search = [output / "build", *(Path(item) for item in lib_line[4:].split(";"))]
    resolved_library = next(
        (
            path / "volatileaccessu.lib"
            for path in search
            if (path / "volatileaccessu.lib").is_file()
        ),
        None,
    )
    if not resolved_library or resolved_library.resolve() != library.resolve():
        raise ValueError(
            "Actual library search resolves a different volatileaccessu.lib"
        )
    save(
        output / "library-resolution.json",
        {
            "path": str(resolved_library.resolve()),
            "sha256": digest(resolved_library),
            "selected_sdk": selected,
        },
    )
    compile_commands = json.loads(
        (output / "build" / "compile_commands.json").read_text()
    )
    if (
        len(compile_commands) != 7
        or not any("ref.c" in item["file"] for item in compile_commands)
        or any(
            "opt.c" in item["file"]
            or "ARGON2_NO_THREADS" in item["command"]
            or "VOLATILE_ACCESSOR_LIB" not in item["command"]
            for item in compile_commands
        )
    ):
        raise ValueError("Actual source/flags do not match the candidate contract")
    results = {}
    for arm in ("reference", "candidate"):
        argv = [str(python), "-B", str(Path(__file__).resolve()), "--_functional"]
        if arm == "candidate":
            argv.append(str(package_root))
        owned(arm, argv)
        results[arm] = json.loads((output / f"{arm}.stdout.txt").read_text())
    after = reference_files(Path(reference["site"]))
    save(output / "reference-after.json", after)
    validate_functional(
        results["reference"], results["candidate"], reference["reference_files"], after
    )
    if results["reference"]["image_sha256"] != reference["image_sha256"]:
        raise ValueError("Reference image changed between probe and functional helper")
    image = package / "_ffi.pyd"
    if digest(image) != results["candidate"]["image_sha256"]:
        raise ValueError("Candidate image changed")
    return {
        "schema": 1,
        "status": "PASS_FUNCTIONAL_PACKAGE",
        "reference_image_sha256": reference["image_sha256"],
        "candidate_image_sha256": digest(image),
        "candidate_package_root": str(package_root),
        "sdk_version": selected,
        "compiler": str(clang),
        "target": "aarch64-pc-windows-msvc",
        "compiler_version": compiler_version,
        "binding_commit": BINDING_COMMIT,
        "vendor_commit": VENDOR_COMMIT,
        "reference_files_unchanged": len(after),
        "strict_natural_drain": True,
        "python_sabi": "3.10",
        "performance": "UNQUALIFIED",
        "compatibility": "Current-host private package only; no wheel/downlevel/HOBL/CI adoption.",
    }


def main(argv=None):
    args = parse_args(argv)
    output = None
    try:
        if os.name != "nt":
            raise RuntimeError("This builder supports Windows only")
        output = prepare_output(args.output, args.source, args.python)
        proof = build(args, output)
        save(output / "binding-proof.json", proof)
        print(json.dumps(proof))
        return 0
    except Exception as error:
        proof = {
            "schema": 1,
            "status": "UNQUALIFIED",
            "error": f"{type(error).__name__}: {error}",
        }
        if output:
            save(output / "binding-proof.json", proof)
        print(json.dumps(proof), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    if sys.argv[1:] == ["--_probe"]:
        probe()
    elif sys.argv[1:2] == ["--_functional"]:
        functional(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        raise SystemExit(main())
