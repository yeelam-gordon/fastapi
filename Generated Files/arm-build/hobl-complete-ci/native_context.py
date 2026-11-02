"""Owned, untimed preparation of matched normal-GIL coverage extensions."""

import dataclasses
import importlib.metadata
import json
import os
import shutil
import struct
import sys
import sysconfig
import tarfile
import urllib.request
from pathlib import Path

import native_context_inputs as inputs
import owned_process
import runtime_pair

HERE = Path(__file__).resolve().parent
GUARD_SHA = "45d6db4f6452c4f7116ca23c6e2aa74cda90a15548bd5c9bb3b3574973ef458e"
require = runtime_pair.require
save = runtime_pair.save
sha = inputs.sha


def files(root):
    return {
        p.relative_to(root).as_posix(): sha(p.read_bytes())
        for p in sorted(root.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }


def run(command, root, name, cwd=None, env=None, timeout=180):
    receipt = owned_process.run_owned(
        list(map(str, command)),
        cwd=str(cwd or root),
        env=env or os.environ.copy(),
        stdout_path=root / f"{name}.stdout",
        stderr_path=root / f"{name}.stderr",
        timeout=timeout,
    )
    save(root / f"{name}.receipt.json", dataclasses.asdict(receipt))
    require(receipt.succeeded, f"owned preparation failed: {name}")
    require(
        not (root / f"{name}.stderr").read_bytes(),
        f"preparation diagnostics retained: {name}",
    )
    return (root / f"{name}.stdout").read_text(encoding="utf-8", errors="replace")


def windows_sdk(vs, kits, target="arm64"):
    require(target == "arm64", "only ARM64 SDK target supported")

    def versions(folder):
        return (
            sorted(
                (
                    p
                    for p in folder.iterdir()
                    if p.is_dir() and all(s.isdigit() for s in p.name.split("."))
                ),
                key=lambda p: tuple(map(int, p.name.split("."))),
                reverse=True,
            )
            if folder.is_dir()
            else []
        )

    for vc in versions(vs / "VC" / "Tools" / "MSVC"):
        if not (vc / "include").is_dir() or not (vc / "lib" / target).is_dir():
            continue
        for kit in kits:
            for version in versions(kit / "Include"):
                include = [
                    vc / "include",
                    *[version / n for n in ("ucrt", "shared", "um")],
                ]
                libraries = [
                    vc / "lib" / target,
                    *[kit / "Lib" / version.name / n / target for n in ("ucrt", "um")],
                ]
                if all(p.is_dir() for p in include + libraries):
                    return (
                        include,
                        libraries,
                        {"vc_tools_version": vc.name, "sdk_version": version.name},
                    )
    raise RuntimeError(
        "no coherent installed SDK include/ucrt/shared/um + same-version ARM64 libraries and VC tools"
    )


def toolchain(root):
    env = os.environ.copy()
    if sys.platform == "win32":
        roots = [Path(env["VSINSTALLDIR"])] if env.get("VSINSTALLDIR") else []
        for base in (Path(r"C:\Program Files"), Path(r"C:\Program Files (x86)")):
            roots.extend((base / "Microsoft Visual Studio").glob(r"*\*"))
        kits = [Path(env["WindowsSdkDir"])] if env.get("WindowsSdkDir") else []
        kits.append(Path(r"C:\Program Files (x86)\Windows Kits\10"))
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows Kits\Installed Roots",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_32KEY,
            ) as key:
                kits.append(Path(winreg.QueryValueEx(key, "KitsRoot10")[0]))
        except OSError:
            pass
        for suffix in (("ARM64", "bin"), ("x64", "bin"), ("bin",)):
            for vs in roots:
                compiler = vs / "VC" / "Tools" / "Llvm" / Path(*suffix)
                clang, linker = compiler / "clang-cl.exe", compiler / "lld-link.exe"
                if not (clang.is_file() and linker.is_file()):
                    continue
                include, libraries, identity = windows_sdk(vs, kits)
                env["INCLUDE"] = ""
                env["LIB"] = ""
                env["HOBL_SDK_INCLUDE"] = os.pathsep.join(map(str, include))
                env["HOBL_SDK_LIB"] = os.pathsep.join(map(str, libraries))
                host = pe_machine(clang)
                require(
                    host in {0xAA64, 0x8664}, "supported LLVM compiler host required"
                )
                return (
                    clang,
                    linker,
                    env,
                    {
                        "compiler_host_machine": hex(host),
                        **identity,
                        "include_paths": list(map(str, include)),
                        "library_paths": list(map(str, libraries)),
                    },
                )
        raise RuntimeError("installed VS LLVM clang-cl/lld-link and ARM64 SDK missing")
    require(sys.platform == "darwin", "native experiment requires Windows/macOS")
    clang = run(["/usr/bin/xcrun", "--find", "clang"], root, "xcrun").strip()
    require(Path(clang).is_file(), "installed Xcode clang missing")
    return Path(clang), None, env, {"compiler_host_machine": "native arm64"}


def pe_machine(path):
    raw = path.read_bytes()
    require(raw[:2] == b"MZ", "PE DOS header")
    offset = struct.unpack_from("<I", raw, 60)[0]
    require(raw[offset : offset + 4] == b"PE\0\0", "PE signature")
    return struct.unpack_from("<H", raw, offset + 4)[0]


def pe_abi(path):
    raw = path.read_bytes()
    header = struct.unpack_from("<I", raw, 60)[0]
    optional = header + 24
    require(struct.unpack_from("<H", raw, optional)[0] == 0x20B, "PE32+ required")
    sections = optional + struct.unpack_from("<H", raw, header + 20)[0]

    def offset(rva):
        for i in range(struct.unpack_from("<H", raw, header + 6)[0]):
            size, address, count, start = struct.unpack_from(
                "<IIII", raw, sections + i * 40 + 8
            )
            if address <= rva < address + max(size, count):
                return start + rva - address
        raise RuntimeError("unmapped PE RVA")

    def text(rva):
        start = offset(rva)
        return raw[start : raw.index(0, start)].decode("ascii")

    export = offset(struct.unpack_from("<I", raw, optional + 112)[0])
    names = offset(struct.unpack_from("<I", raw, export + 32)[0])
    exports = [
        text(struct.unpack_from("<I", raw, names + 4 * i)[0])
        for i in range(struct.unpack_from("<I", raw, export + 24)[0])
    ]
    descriptor = offset(struct.unpack_from("<I", raw, optional + 120)[0])
    imports = []
    while any(raw[descriptor : descriptor + 20]):
        imports.append(text(struct.unpack_from("<I", raw, descriptor + 12)[0]))
        descriptor += 20
    require(exports == ["PyInit_tracer"], "native export")
    require("python313.dll" in [n.lower() for n in imports], "normal cp313 import")
    return {
        "machine": hex(pe_machine(path)),
        "exports": exports,
        "imports": imports,
        "sha256": sha(raw),
    }


def commands(clang, linker, include, library, suffix, env):
    sources = [
        Path("coverage") / "ctracer" / f"{name}.c"
        for name in ("datastack", "filedisp", "module", "tracer")
    ]
    output = Path("coverage") / ("tracer" + suffix)
    if linker:
        objects = [Path("objects") / (p.stem + ".obj") for p in sources]
        return [
            [
                str(clang),
                "--target=aarch64-pc-windows-msvc",
                "/c",
                "/nologo",
                "/O2",
                "/W3",
                "/DNDEBUG",
                "/MD",
                "/std:c11",
                "/I" + str(include),
                *[
                    "/imsvc" + p
                    for p in env.get("HOBL_SDK_INCLUDE", "").split(os.pathsep)
                    if p
                ],
                "/Tc" + str(source),
                "/Fo" + str(obj),
            ]
            for source, obj in zip(sources, objects, strict=True)
        ] + [
            [
                str(linker),
                "/nologo",
                "/INCREMENTAL:NO",
                "/DLL",
                "/MACHINE:ARM64",
                "/MANIFEST:EMBED,ID=2",
                "/MANIFESTUAC:NO",
                "/EXPORT:PyInit_tracer",
                "/LIBPATH:" + str(library.parent),
                *[
                    "/LIBPATH:" + p
                    for p in env.get("HOBL_SDK_LIB", env.get("LIB", "")).split(
                        os.pathsep
                    )
                    if p
                ],
                *map(str, objects),
                str(library),
                "/OUT:" + str(output),
                "/IMPLIB:objects/tracer.lib",
            ]
        ]
    return [
        [
            str(clang),
            "-O2",
            "-DNDEBUG",
            "-std=c11",
            "-fPIC",
            "-shared",
            "-undefined",
            "dynamic_lookup",
            "-arch",
            "arm64",
            "-I" + str(include),
            *map(str, sources),
            "-o",
            str(output),
        ]
    ]


def fetch(root):
    manifest = inputs.load_inputs()
    archive = root / "official-source.tar.gz"
    url = f"https://codeload.github.com/coveragepy/coveragepy/tar.gz/{inputs.REVISION}"
    with urllib.request.urlopen(url, timeout=30) as response:
        require(response.geturl() == url, "unexpected source redirect")
        with archive.open("wb") as stream:
            shutil.copyfileobj(response, stream)
    source = root / "official-source"
    source.mkdir()
    with tarfile.open(archive, "r:gz") as tar:
        for name in manifest["stock"]:
            member = tar.getmember(f"coveragepy-{inputs.REVISION}/{name}")
            require(member.isfile() and not member.issym(), "nonregular owner input")
            raw = tar.extractfile(member).read()
            require(sha(raw) == manifest["stock"][name], f"official input hash: {name}")
            target = source.joinpath(*name.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
    save(
        root / "source-download.json", {"url": url, "sha256": sha(archive.read_bytes())}
    )
    return source


def prepare(root, source, candidate):
    build_packages(root, source, candidate, runtime_pair.identity(source, "3.13.15"))


def build_packages(root, source, candidate, identity):
    require(
        sys.version_info[:3] == (3, 13, 15)
        and not sysconfig.get_config_var("Py_GIL_DISABLED")
        and getattr(sys, "_is_gil_enabled", lambda: True)()
        and not sysconfig.get_config_var("PYTHON_JIT")
        and not getattr(getattr(sys, "_jit", None), "is_enabled", lambda: False)(),
        "normal cp313/no-JIT build interpreter required",
    )
    require(not os.environ.get("COVERAGE_CORE"), "default CTracer required")
    require(
        not any(
            os.environ.get(k)
            for k in ("CL", "_CL_", "LINK", "_LINK_", "CFLAGS", "CPPFLAGS", "LDFLAGS")
        ),
        "ambient compiler flags are not allowed",
    )
    save(
        root / "helper-inputs.json",
        {
            name: sha((HERE / name).read_bytes())
            for name in (
                "native_context.py",
                "native_context_inputs.py",
                "native-context.patch",
                "native-context-inputs.json",
                "native_smoke.py",
                "native_fixture.py",
                "runtime_pair.py",
                "run_payload.py",
                "owned_process.py",
            )
        },
    )
    save(root / "official-runtime-identity.json", identity)
    import coverage

    installed = Path(coverage.__file__).parent
    require(
        installed.resolve()
        == Path(
            importlib.metadata.distribution("coverage").locate_file("coverage")
        ).resolve()
        and installed.resolve().is_relative_to(Path(sys.prefix).resolve()),
        "official wheel must come from the lexical payload venv",
    )
    before = files(installed)
    clean = os.environ.copy()
    clean.pop("PYTHONPATH", None)
    clean["PYTHONNOUSERSITE"] = "1"
    other = Path(
        run(
            [candidate, "-B", "-c", "import coverage;print(coverage.__file__)"],
            root,
            "candidate-installed-origin",
            env=clean,
        ).strip()
    ).parent
    require(
        other.resolve().is_relative_to(Path(candidate).parent.parent.resolve()),
        "candidate official wheel must remain in its venv",
    )
    originals = [{"path": str(p), "files": files(p)} for p in (installed, other)]
    require(len(before) == 54, "official installed package member count")
    trees = root / "sources"
    inputs.stage(fetch(root), trees)
    clang, linker, env, host = toolchain(root)
    version = run([clang, "--version"], root, "compiler-version")
    if linker:
        run([linker, "--version"], root, "linker-version")
    include = Path(sysconfig.get_config_var("INCLUDEPY"))
    suffix = sysconfig.get_config_var("EXT_SUFFIX")
    require((include / "Python.h").is_file() and suffix, "native Python headers/suffix")
    library = Path(
        sysconfig.get_config_var("LIBDIR") or (Path(sys.base_prefix) / "libs")
    )
    library /= sysconfig.get_config_var("LIBRARY") or "python313.lib"
    if linker:
        library = library.with_suffix(".lib")
        require(library.is_file(), "normal cp313 ARM64 import library missing")
    recipe = commands(clang, linker, include, library, suffix, env)
    save(
        root / "build-spec.json",
        {
            "commands_both_arms": recipe,
            "compiler_sha256": sha(clang.read_bytes()),
            "compiler_version": version,
            "host": host,
            "sysconfig": {
                key: sysconfig.get_config_var(key)
                for key in ("INCLUDEPY", "LIBDIR", "LIBRARY", "LDLIBRARY", "EXT_SUFFIX")
            },
            "headers": files(include),
            "import_library_sha256": sha(library.read_bytes()) if linker else None,
            "linker_sha256": sha(linker.read_bytes()) if linker else None,
            "no_lto_pgo": True,
        },
    )
    overlays = root / "overlays"
    for arm in ("stock", "candidate"):
        tree = trees / arm
        (tree / "objects").mkdir()
        for number, command in enumerate(recipe):
            run(command, root, f"{arm}-compile-{number}", cwd=tree, env=env)
        binary = tree / "coverage" / ("tracer" + suffix)
        if linker:
            require(pe_machine(binary) == 0xAA64, "extension must be ARM64 PE")
            save(root / f"{arm}-native-abi.json", pe_abi(binary))
        else:
            slices = run(["/usr/bin/lipo", "-archs", binary], root, f"{arm}-slices")
            require(slices.split() == ["arm64"], "extension must be thin ARM64")
            exports = run(["/usr/bin/nm", "-g", binary], root, f"{arm}-exports")
            require("_PyInit_tracer" in exports, "native Python module export")
            run(["/usr/bin/otool", "-L", binary], root, f"{arm}-imports")
        package = overlays / arm / "coverage"
        shutil.copytree(
            installed, package, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
        )
        for old in package.glob("tracer.*"):
            if old.suffix in {".pyd", ".so"}:
                old.unlink()
        for name in ("collector.py", "tracer.pyi"):
            shutil.copyfile(tree / "coverage" / name, package / name)
        shutil.copyfile(binary, package / binary.name)
    payloads = {arm: files(overlays / arm) for arm in ("stock", "candidate")}
    require(payloads["stock"].keys() == payloads["candidate"].keys(), "overlay members")
    require(
        {
            name
            for name in payloads["stock"]
            if payloads["stock"][name] != payloads["candidate"][name]
        }
        == {"coverage/collector.py", "coverage/tracer.pyi", "coverage/tracer" + suffix},
        "overlay treatment scope",
    )
    save(root / "payloads.json", payloads)
    for mode in ("default", "mutation", "audit"):
        baseline = None
        for arm in ("official", "stock", "candidate"):
            smoke_env = env.copy()
            smoke_env.pop("PYTHONPATH", None)
            smoke_env["PYTHONNOUSERSITE"] = "1"
            smoke_env["PYTHONDONTWRITEBYTECODE"] = "1"
            if arm != "official":
                smoke_env["PYTHONPATH"] = str(overlays / arm)
            smoke_env["HOBL_NATIVE_EXPECT"] = str(
                (installed if arm == "official" else overlays / arm / "coverage")
                / "__init__.py"
            )
            text = run(
                [sys.executable, "-B", HERE / "native_smoke.py", mode],
                root,
                f"smoke-{mode}-{arm}",
                env=smoke_env,
            )
            require(
                not (root / f"smoke-{mode}-{arm}.stderr").read_bytes(),
                "semantic probe stderr",
            )
            result = json.loads(text)
            baseline = result if baseline is None else baseline
            require(result == baseline, f"public semantic mismatch: {mode}/{arm}")
    require(files(installed) == before, "installed wheel changed")
    save(root / "installed-package.json", originals)


def verify(root, arm):
    for name, digest in json.loads((root / "helper-inputs.json").read_bytes()).items():
        require(sha((HERE / name).read_bytes()) == digest, "native helper changed")
    inputs.inspect(root / "sources" / arm, arm, inputs.load_inputs())
    require(
        files(root / "overlays" / arm)
        == json.loads((root / "payloads.json").read_bytes())[arm],
        "native overlay changed",
    )
    for package in json.loads((root / "installed-package.json").read_bytes()):
        require(
            files(Path(package["path"])) == package["files"], "installed wheel changed"
        )
    receipt = json.loads((root / "ownership.json").read_bytes())
    require(owned_process.Receipt(**receipt).succeeded, "native preparation lifecycle")


if __name__ == "__main__":
    action, root, source, candidate = sys.argv[1:]
    root, source = Path(root), Path(source)
    require(
        sha((HERE / "owned_process.py").read_bytes()) == GUARD_SHA, "guardian identity"
    )
    if action == "worker":
        prepare(root, source, candidate)
    else:
        require(action == "prepare" and not root.exists(), "fresh native prep required")
        root.mkdir()
        run(
            [
                sys.executable,
                "-B",
                HERE / "native_context.py",
                "worker",
                root,
                source,
                candidate,
            ],
            root,
            "preparation",
            timeout=90,
        )
        shutil.copyfile(root / "preparation.receipt.json", root / "ownership.json")
