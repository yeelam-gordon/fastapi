import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

THREAD = threading.get_ident()
EVENTS = []
STACK = []
REPORTS = []
COLLECTED = []


@contextmanager
def span(kind, nodeid=None, **metadata):
    if threading.get_ident() != THREAD:
        raise RuntimeError("pytest phase observer invoked off its caller thread")
    event = {
        "id": len(EVENTS),
        "parent": STACK[-1] if STACK else None,
        "kind": kind,
        "nodeid": nodeid,
        "thread_id": THREAD,
        **metadata,
    }
    EVENTS.append(event)
    STACK.append(event["id"])
    event["start_ns"] = time.perf_counter_ns()
    event["cpu_start_ns"] = time.thread_time_ns()
    try:
        yield
    finally:
        event["cpu_end_ns"] = time.thread_time_ns()
        event["end_ns"] = time.perf_counter_ns()
        if threading.get_ident() != THREAD or STACK.pop() != event["id"]:
            raise RuntimeError("pytest phase thread/stack changed")
        event["elapsed_ns"] = event["end_ns"] - event["start_ns"]
        event["cpu_elapsed_ns"] = event["cpu_end_ns"] - event["cpu_start_ns"]


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_cmdline_main(config):
    try:
        with span("pytest_command"):
            return (yield)
    finally:
        output = Path(os.environ["HOBL_BOUNDARY_OUTPUT"])
        if STACK:
            raise RuntimeError("unclosed pytest observer spans")
        (output / "raw-boundaries.json").write_text(
            json.dumps(
                {
                    "events": EVENTS,
                    "reports": REPORTS,
                    "collected_nodeids": COLLECTED,
                    "caller_thread_id": THREAD,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_sessionstart(session):
    with span("session_start"):
        return (yield)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_collection(session):
    with span("collection"):
        return (yield)


def pytest_collection_finish(session):
    COLLECTED.extend(item.nodeid for item in session.items)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtestloop(session):
    with span("test_loop"):
        return (yield)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_protocol(item, nextitem):
    with span("protocol", item.nodeid):
        return (yield)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_setup(item):
    with span("setup", item.nodeid):
        return (yield)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_call(item):
    with span("call", item.nodeid):
        return (yield)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_teardown(item, nextitem):
    with span("teardown", item.nodeid):
        return (yield)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_fixture_setup(fixturedef, request):
    function = fixturedef.func
    code = getattr(function, "__code__", None)
    with span(
        "fixture_setup",
        request.node.nodeid,
        fixture=fixturedef.argname,
        fixture_scope=fixturedef.scope,
        file=code.co_filename if code is not None else None,
        line=code.co_firstlineno if code is not None else None,
    ):
        return (yield)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    with span("make_report", item.nodeid, report_when=call.when):
        return (yield)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_logreport(report):
    with span("log_report", report.nodeid, report_when=report.when):
        result = yield
    REPORTS.append(
        {
            "nodeid": report.nodeid,
            "when": report.when,
            "outcome": report.outcome,
            "wasxfail": getattr(report, "wasxfail", None),
            "duration_s": report.duration,
        }
    )
    return result


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    with span("session_finish"):
        return (yield)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_terminal_summary(terminalreporter, exitstatus, config):
    with span("terminal_summary"):
        return (yield)
