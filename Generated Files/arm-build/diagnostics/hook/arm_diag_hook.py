"""No backend/runtime patches: use CPython's public per-code monitoring API."""

import os
import sys
import time

ROLES = {
    "get_requires_for_build_sdist": "get-requires-sdist",
    "build_sdist": "build-sdist",
    "get_requires_for_build_wheel": "get-requires-wheel",
    "build_wheel": "build-wheel",
}


def classify(command):
    # Longest first: build_sdist is also a suffix of get_requires_for_build_sdist.
    for symbol in sorted(ROLES, key=len, reverse=True):
        start = 0
        while (position := command.find(symbol, start)) >= 0:
            before = command[position - 1] if position else ""
            after = command[position + len(symbol) : position + len(symbol) + 1]
            if not (before.isalnum() or before == "_") and not (
                after.isalnum() or after == "_"
            ):
                return ROLES[symbol]
            start = position + len(symbol)
    return "additional-unknown"


def install():
    bootstrap_start = time.monotonic_ns()
    argv = sys.orig_argv
    if "-c" not in argv or argv.index("-c") + 1 >= len(argv):
        return
    command = argv[argv.index("-c") + 1]
    expected_code = compile(
        command, "<string>", "exec", dont_inherit=True, optimize=sys.flags.optimize
    )
    role = classify(command)
    mode = os.environ["ARM_DIAG_PASS"]
    directory = os.environ["ARM_DIAG_RECEIPTS"]
    identity = os.environ["ARM_DIAG_ID"]
    pid, ppid = os.getpid(), os.getppid()
    prefix = os.path.join(directory, str(pid))
    preloaded = sorted(sys.modules)
    state = {"started": False, "ended": False}
    operations = {}
    if mode == "resource":

        def audit(event, args):
            if (
                state["started"]
                and not state["ended"]
                and event
                in (
                    "open",
                    "os.listdir",
                    "os.scandir",
                    "os.remove",
                    "os.rename",
                    "os.mkdir",
                )
            ):
                operations[event] = operations.get(event, 0) + 1

        sys.addaudithook(audit)
    profile = memory = platform = None
    errors = []
    try:
        import arm_diag_platform as platform
    except Exception as error:
        errors.append("platform:" + type(error).__name__)
    if mode == "cprofile":
        import cProfile

        profile = cProfile.Profile()
    elif mode == "memory":
        import tracemalloc

        memory = tracemalloc
    stderr_copy = descriptor = None
    if mode == "importtime":
        stderr_copy = os.dup(2)
        descriptor = os.open(
            prefix + ".imports.raw.log", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
    monitoring = sys.monitoring
    tool = next(
        (value for value in range(6) if monitoring.get_tool(value) is None), None
    )
    if tool is None:
        raise RuntimeError("No free CPython monitoring tool ID")
    monitoring.use_tool_id(tool, "arm-build-analysis")

    def snapshot():
        if platform is None:
            return {"status": "unavailable", "reason": "arm_diag_platform missing"}
        try:
            return platform.process_snapshot()
        except Exception as error:
            return {"status": "unavailable", "reason": type(error).__name__}

    # Prewarm platform's lazy counter adapters outside the observed command.
    snapshot()
    bootstrap_end = time.monotonic_ns()

    def finish(code, offset, *args, failed=False):
        if state["ended"] or not state["started"] or state.get("code") is not code:
            return
        end = time.monotonic_ns()
        state["ended"] = True
        if profile is not None:
            profile.disable()
        allocation = None
        if memory is not None:
            current, peak = memory.get_traced_memory()
            allocation = {
                "status": "measured",
                "current": current,
                "peak": peak,
                "unit": "bytes",
                "scope": "self_python_allocations_after_command_entry",
                "aggregation": "current_and_window_peak",
            }
            allocation["end_live_top"] = [
                {
                    "bytes": item.size,
                    "count": item.count,
                    "traceback": [
                        {"file": frame.filename, "line": frame.lineno}
                        for frame in item.traceback
                    ],
                }
                for item in memory.take_snapshot().statistics("traceback")[:50]
            ]
            allocation["top_scope"] = (
                "live allocations at window end, not peak allocation attribution"
            )
            memory.stop()
        end_snapshot = snapshot()
        monitoring.set_events(tool, 0)
        monitoring.set_local_events(tool, code, 0)
        if stderr_copy is not None:
            os.dup2(stderr_copy, 2)
            os.close(stderr_copy)
        export_start = time.monotonic_ns()
        import hashlib
        import json
        import sysconfig
        from importlib.metadata import PackageNotFoundError, version

        try:
            backend_version = version("pdm-backend")
        except PackageNotFoundError:
            backend_version = None

        if profile is not None:
            profile.dump_stats(prefix + ".pstats")
        record = {
            "schema": 1,
            "identity": identity,
            "mode": mode,
            "role": role,
            "pid": pid,
            "ppid": ppid,
            "status": "failed" if failed else "measured",
            "start_ns": state["start"],
            "end_ns": end,
            "wall_seconds": (end - state["start"]) / 1e9,
            "clock": "monotonic_ns",
            "scope": "actual_uv_generated_command_PY_START_to_PY_RETURN_or_UNWIND",
            "performance_eligible": False,
            "bootstrap_start_ns": bootstrap_start,
            "bootstrap_end_ns": bootstrap_end,
            "bootstrap_scope": "after sitecustomize/helper os/sys/time imports; earlier startup unassigned",
            "preloaded_modules_at_bootstrap": preloaded,
            "preloaded_modules_at_window": state["preloaded"],
            "export_start_ns": export_start,
            "snapshots": {"start": state["snapshot"], "end": end_snapshot},
            "cpu_scope": "self_all_threads; enclosing counter reads, not process tree",
            "allocation": allocation,
            "python_operations": {
                "requested": True,
                "status": "measured" if mode == "resource" else "unavailable",
                "value": operations if mode == "resource" else None,
                "scope": "self Python audit events only; no arguments retained",
                "reason": "Not kernel I/O, stat coverage, physical reads, latency or scanner events",
            },
            "generated_command_sha256": hashlib.sha256(command.encode()).hexdigest(),
            "python": sys.version,
            "runtime": {
                "executable": sys.executable,
                "prefix": sys.prefix,
                "base_prefix": sys.base_prefix,
                "platform": sysconfig.get_platform(),
                "compiler": sys.version,
                "backend_version": backend_version,
                "backend_file": getattr(
                    sys.modules.get("pdm.backend"), "__file__", None
                ),
            },
            "cwd": os.getcwd(),
            "argv_shape": [
                "<isolated-python>",
                "-c",
                "<generated-command-sha256-only>",
            ],
            "isolated": bool(sys.flags.isolated),
            "ignore_environment": bool(sys.flags.ignore_environment),
            "errors": errors,
        }
        record["export_prewrite_end_ns"] = time.monotonic_ns()
        with open(prefix + ".end.json", "x", encoding="utf-8") as stream:
            json.dump(record, stream, indent=2)
        monitoring.free_tool_id(tool)

    def start(code, offset):
        if (
            code.co_filename != "<string>"
            or state["started"]
            or code.co_code != expected_code.co_code
            or code.co_names != expected_code.co_names
            or code.co_consts != expected_code.co_consts
        ):
            return
        monitoring.set_events(tool, 0)
        state["preloaded"] = sorted(sys.modules)
        state["snapshot"] = snapshot()
        if descriptor is not None:
            os.dup2(descriptor, 2)
            os.close(descriptor)
        if memory is not None:
            memory.start()
        if profile is not None:
            profile.enable()
        state["start"] = time.monotonic_ns()
        state["started"] = True
        state["code"] = code
        # Durable minimal start receipt; JSON and export modules stay deferred.
        with open(prefix + ".start.tsv", "x", encoding="utf-8") as stream:
            stream.write(
                f"{identity}\t{mode}\t{role}\t{pid}\t{ppid}\t{state['start']}\n"
            )
        monitoring.set_local_events(tool, code, monitoring.events.PY_RETURN)
        # UNWIND is global-only; unlike call tracing it fires only on unwind.
        monitoring.set_events(tool, monitoring.events.PY_UNWIND)

    monitoring.register_callback(tool, monitoring.events.PY_START, start)
    monitoring.register_callback(tool, monitoring.events.PY_RETURN, finish)
    monitoring.register_callback(
        tool,
        monitoring.events.PY_UNWIND,
        lambda code, offset, *args: finish(code, offset, *args, failed=True),
    )
    monitoring.set_events(tool, monitoring.events.PY_START)
