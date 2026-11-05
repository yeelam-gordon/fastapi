"""Separate local83 native correctness preflight; never a CI admission path."""

import argparse
import concurrent.futures
import importlib.metadata
import marshal
import os
import sys
import types
from pathlib import Path

from execution import owned, runtime_snapshot
from matched import HERE, static_check, verify_sourcepins
from screen import digest, load, save


def local_metadata():
    if sys.platform != "win32" or sys.version_info[:3] != (3, 13, 15):
        raise ValueError("Qualified Windows CPython 3.13.15 required")
    if (
        not sys.dont_write_bytecode
        or sys.pycache_prefix is not None
        or sys.flags.optimize != 0
    ):
        raise ValueError(
            "Local administrative preflight requires -B and no cache prefix"
        )
    if (
        not sys._is_gil_enabled()
        or (hasattr(sys, "_jit") and sys._jit.is_enabled())
        or sys.getprofile() is not None
    ):
        raise ValueError("Normal-GIL, non-JIT, unprofiled qualified runtime required")
    baseline = load(HERE / "qualified-local83.json")
    actual = {
        dist.metadata["Name"].lower().replace("_", "-").replace(".", "-"): dist.version
        for dist in importlib.metadata.distributions()
    }
    if actual != baseline["packages"] or len(actual) != 83:
        raise ValueError(
            "Exact qualified local83 baseline required; no arbitrary extras"
        )
    common = dict(
        line.split("==")
        for line in (HERE / "requirements.txt").read_text().splitlines()
    )
    common = {
        name.lower().replace("_", "-").replace(".", "-"): version
        for name, version in common.items()
    }
    if {
        name: value for name, value in actual.items() if name != "fastapi"
    } != common or actual["fastapi"] != "0.119.1":
        raise ValueError(
            "Only the specifically qualified FastAPI 0.119.1 extra is allowed locally"
        )
    for relative, expected in baseline["runtime_sources"].items():
        if digest(Path(sys.base_prefix) / "Lib" / relative) != expected:
            raise ValueError(f"Qualified runtime source changed: {relative}")
    import asyncio.proactor_events
    import asyncio.windows_events
    import asyncio.windows_utils
    import socket

    targets = {
        "socket.py": [
            socket.socket.close,
            socket.socket._real_close,
            socket.socket._decref_socketios,
        ],
        "asyncio/proactor_events.py": [
            asyncio.proactor_events.BaseProactorEventLoop.close,
            asyncio.proactor_events.BaseProactorEventLoop._close_self_pipe,
        ],
        "asyncio/windows_events.py": [asyncio.windows_events.IocpProactor.close],
        "asyncio/windows_utils.py": [asyncio.windows_utils.PipeHandle.close],
    }

    def nested_codes(code):
        yield code
        for value in code.co_consts:
            if isinstance(value, types.CodeType):
                yield from nested_codes(value)

    for relative, functions in targets.items():
        path = Path(sys.base_prefix) / "Lib" / relative
        compiled = list(
            nested_codes(
                compile(path.read_bytes(), str(path), "exec", dont_inherit=True)
            )
        )
        for function in functions:
            matches = [
                code
                for code in compiled
                if code.co_qualname == function.__code__.co_qualname
            ]
            if len(matches) != 1 or marshal.dumps(matches[0]) != marshal.dumps(
                function.__code__
            ):
                raise ValueError(
                    f"Loaded runtime code differs from qualified source: {relative}"
                )
    import coverage.tracer
    from native import native_machine

    native = Path(coverage.tracer.__file__)
    if digest(native) != baseline["coverage_native_sha256"]:
        raise ValueError("Qualified native CTracer changed")
    static_check()
    return {
        "packages": actual,
        "native_machine": native_machine(native),
        "native_sha256": digest(native),
        "source_provenance": baseline["runtime_sources"],
    }


def child(output):
    import asyncio

    import coverage
    from portable_lifetime import capture, certificate
    from prototype import WorkerProactorEventLoop

    metadata = local_metadata()
    trace = sys.gettrace()
    if (
        coverage.Coverage.current() is None
        or type(trace) is not sys.modules["coverage.tracer"].CTracer
    ):
        raise ValueError(
            "Actual active native CTracer required, not extension metadata only"
        )

    def close_case(label, factory, pipe):
        loop = factory()
        try:
            if bool(getattr(loop, "_use_pipe", False)) != pipe:
                raise ValueError("Worker-only pipe selection changed")
            value = capture(loop)
        finally:
            loop.close()
        value.close_returned = True
        return {"role": label, "pipe": pipe, "certificate": certificate(value)}

    records = [
        close_case("main-stock", asyncio.ProactorEventLoop, False),
        close_case("main-candidate-stock-fallback", WorkerProactorEventLoop, False),
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        records.append(
            pool.submit(
                close_case, "worker-stock", asyncio.ProactorEventLoop, False
            ).result(timeout=5)
        )
        records.append(
            pool.submit(
                close_case, "worker-pipe", WorkerProactorEventLoop, True
            ).result(timeout=5)
        )
    save(
        output / "native-child.json",
        {
            "metadata": metadata,
            "close_cases": records,
            "native_trace": type(trace).__name__,
            "scope": "four construction/close cases; no ASGI, wakeups or HOBL",
        },
    )


def run(output, *, worker=False):
    verify_sourcepins()
    output = output.resolve()
    if not output.is_relative_to(
        HERE.parents[4] / "arm-build" / "pipe-matched-ci-readiness"
    ):
        raise ValueError("Output must be under the new owned root research directory")
    if not worker:
        output.mkdir(exist_ok=False)
        return owned(
            [
                sys.executable,
                "-B",
                str(Path(__file__)),
                "--worker",
                "--output",
                str(output),
            ],
            HERE,
            os.environ.copy(),
            output,
            "local-controller",
            75,
        )
    before = runtime_snapshot(Path(sys.prefix))
    result = {
        "status": "ERROR",
        "native_scope": "four loops; one stock coverage CLI; no full HOBL",
        "native_child_cap_seconds": 45,
        "overall_guard_cap_seconds": 75,
        "ci_admission": False,
    }
    try:
        result["metadata"] = local_metadata()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith(("PYTHON", "COVERAGE_", "COV_CORE_")):
                env.pop(key)
        env["PYTHONPATH"] = str(HERE)
        command = [
            sys.executable,
            "-B",
            "-m",
            "coverage",
            "run",
            "--rcfile",
            str(HERE / "local-coverage.toml"),
            "--data-file",
            str(output / ".coverage"),
            str(Path(__file__)),
            "--child",
            "--output",
            str(output),
        ]
        receipt = owned(command, HERE, env, output, "local-native", 45, native=True)
        import coverage

        data = coverage.CoverageData(basename=str(output / ".coverage"))
        data.read()
        if not data.measured_files() or not (output / "native-child.json").is_file():
            raise ValueError("Stock native CLI did not flush coverage and child proof")
        result.update(
            status="PASS_LOCAL_PREFLIGHT_NOT_CI_ADMISSION",
            native_seconds=(receipt.native_end_ns - receipt.native_start_ns) / 1e9,
        )
    finally:
        try:
            if runtime_snapshot(Path(sys.prefix)) != before:
                raise ValueError(
                    "Original local runtime/cache inventory or bytes changed"
                )
            result["original_runtime_and_caches_unchanged"] = True
        except BaseException:
            result["status"] = "ERROR"
            raise
        finally:
            save(output / "result.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        child(args.output)
    else:
        run(args.output, worker=args.worker)
