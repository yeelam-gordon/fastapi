"""Public early pytest-only policy selection with buffered captured-object proof."""

import asyncio
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from portable_lifetime import capture, certificate

ORIGINAL_POLICY = None
INSTALLED_POLICY = None
STREAM = None
CREATED = []
CLOSED = []
MAIN = []
FAILURES = []
LOCK = threading.RLock()
ORIGINAL_UNRAISABLE = None


def emit(kind, **values):
    with LOCK:
        STREAM.write(
            json.dumps(
                {
                    "kind": kind,
                    "pid": os.getpid(),
                    "arm": os.environ["OWNER_ARM"],
                    "namespace": os.environ["CORRECTNESS_OUTPUT"],
                    **values,
                }
            )
            + "\n"
        )


class CloseObserver:
    def close(self):
        if self.is_closed():
            return super().close()
        try:
            value = self._owned_lifetime
            super().close()
            value.close_returned = True
            proof = certificate(value, mac_source_qualified=sys.platform == "darwin")
            CLOSED.append(id(self))
            emit("first_close", loop_id=id(self), certificate=proof)
        except BaseException as error:
            FAILURES.append(repr(error))
            emit("close_failure", error=repr(error))
            raise


def unraisable(arguments):
    FAILURES.append(repr(arguments.exc_value))
    ORIGINAL_UNRAISABLE(arguments)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    if item.nodeid.split("@", 1)[0] != "tests/test_fastapi_cli.py::test_fastapi_cli":
        yield
        return
    original = subprocess.Popen
    actual = []

    def observe(*args, **kwargs):
        process = original(*args, **kwargs)
        actual.append(process)
        emit(
            "actual_cli_popen",
            child_pid=process.pid,
            argv=process.args,
            native_popen_object_id=id(process),
        )
        return process

    try:
        with patch.object(subprocess, "Popen", side_effect=observe):
            yield
    finally:
        for process in actual:
            emit(
                "actual_cli_waited",
                child_pid=process.pid,
                returncode=process.returncode,
                native_popen_object_id=id(process),
            )


@pytest.hookimpl(tryfirst=True)
def pytest_load_initial_conftests(early_config, parser, args):
    global ORIGINAL_POLICY, INSTALLED_POLICY, STREAM, ORIGINAL_UNRAISABLE
    arm = os.environ.get("OWNER_ARM")
    if arm not in ("A", "B") or sys.platform not in ("darwin", "win32"):
        raise RuntimeError("Explicit owned A/B arm and native platform required")
    readiness = json.loads(Path(os.environ["MATCHED_READINESS"]).read_text())
    if not readiness["accepted"] or (
        sys.platform == "darwin" and not readiness["mac_runtime_accepted"]
    ):
        raise RuntimeError("Pre-payload runtime readiness required")
    if sys.dont_write_bytecode or sys.pycache_prefix is not None:
        raise RuntimeError("Workload must use normal source caches")
    if "fastapi" in sys.modules:
        raise RuntimeError("Application was preloaded before owned pytest hook")
    if sys.platform == "win32":
        from prototype import WorkerProactorEventLoop

        base_policy = asyncio.WindowsProactorEventLoopPolicy
        stock = asyncio.ProactorEventLoop
        candidate = WorkerProactorEventLoop
    else:
        base_policy = asyncio.DefaultEventLoopPolicy
        stock = candidate = asyncio.SelectorEventLoop

    class StockLoop(CloseObserver, stock):
        pass

    class CandidateLoop(CloseObserver, candidate):
        pass

    class OwnedPolicy(base_policy):
        def new_event_loop(self):
            if threading.current_thread() is threading.main_thread():
                loop = super().new_event_loop()
                MAIN.append(loop)
                return loop
            loop = (StockLoop if arm == "A" else CandidateLoop)()
            loop._owned_lifetime = capture(loop)
            CREATED.append(loop)
            emit("worker_loop", loop_id=id(loop), creator=loop._owned_lifetime.identity)
            return loop

    ORIGINAL_POLICY = asyncio.get_event_loop_policy()
    if type(ORIGINAL_POLICY) is not base_policy:
        raise RuntimeError("Stock default policy required")
    STREAM = (
        Path(os.environ["CORRECTNESS_OUTPUT"]) / f"events-{os.getpid()}.jsonl"
    ).open(
        "x",
        encoding="utf-8",
        buffering=65536,
    )
    ORIGINAL_UNRAISABLE = sys.unraisablehook
    sys.unraisablehook = unraisable
    INSTALLED_POLICY = OwnedPolicy()
    asyncio.set_event_loop_policy(INSTALLED_POLICY)
    import coverage

    active = coverage.Coverage.current()
    if active is None or active._data is None:
        raise RuntimeError("Stock native coverage must already be active")
    emit(
        "policy_install",
        policy_id=id(INSTALLED_POLICY),
        data_filename=active._data.data_filename(),
        native_cache=True,
        process_binding="actual Popen-owned payload namespace and native PID; no Mac birth claim",
    )


def pytest_unconfigure(config):
    if INSTALLED_POLICY is None:
        return
    try:
        if asyncio.get_event_loop_policy() is not INSTALLED_POLICY:
            raise RuntimeError("Owned policy replaced")
        if (
            FAILURES
            or len(CLOSED) != len(CREATED)
            or set(CLOSED) != {id(loop) for loop in CREATED}
        ):
            raise RuntimeError("Missing or failed close certificates")
        if not all(loop.is_closed() for loop in CREATED + MAIN):
            raise RuntimeError("Unclosed owned loops")
        if any(value._owned_lifetime.creator.is_alive() for value in CREATED):
            raise RuntimeError("Owned creator thread remains alive")
        emit(
            "policy_restore",
            created=len(CREATED),
            closed=len(CLOSED),
            main_closed=True,
            failures=FAILURES,
            global_resource_counts="UNKNOWN",
        )
    finally:
        asyncio.set_event_loop_policy(ORIGINAL_POLICY)
        sys.unraisablehook = ORIGINAL_UNRAISABLE
        STREAM.close()
