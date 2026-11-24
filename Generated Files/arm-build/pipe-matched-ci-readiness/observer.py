"""Read-only evidence for stock pytest scheduling and native coverage."""

import json
import os
import sys
import time
from pathlib import Path
from typing import TextIO

import pytest
from native import native_machine

OUT = Path(os.environ["CORRECTNESS_OUTPUT"])
SOURCE = Path(os.environ["CORRECTNESS_SOURCE"])
WORKER = "controller"
OWNED = {}
PHASE_STREAM: TextIO | None = None
_EARLY_FLAG = os.environ.get("ARM_BUILD_EARLY_BOUNDARIES", "0")
if _EARLY_FLAG not in ("0", "1"):
    raise RuntimeError("FATAL: invalid ARM_BUILD_EARLY_BOUNDARIES opt-in")
_EARLY_ENABLED = _EARLY_FLAG == "1"
_EARLY_EVENTS = []
_EARLY_CAPTURE_PENDING = False
_EARLY_FIRST_REPORT = False


def _early_mark(name):
    global _EARLY_CAPTURE_PENDING
    if not _EARLY_ENABLED:
        return
    if _EARLY_CAPTURE_PENDING:
        raise RuntimeError("FATAL: early boundary capture failed; unqualified")
    _EARLY_CAPTURE_PENDING = True
    cpu = os.times()
    user, system = cpu.user, cpu.system
    if not all(
        isinstance(value, float) and 0 <= value < float("inf")
        for value in (user, system)
    ):
        raise RuntimeError("FATAL: invalid current-process CPU snapshot; unqualified")
    _EARLY_EVENTS.append(
        {
            "name": name,
            "cpu_user_seconds": user,
            "cpu_system_seconds": system,
            "monotonic_ns": time.monotonic_ns(),
        }
    )
    _EARLY_CAPTURE_PENDING = False


def _early_save():
    if not _EARLY_ENABLED:
        return
    if _EARLY_CAPTURE_PENDING:
        raise RuntimeError("FATAL: early boundary capture failed; unqualified")
    with (OUT / ("early-boundaries-" + WORKER + ".json")).open(
        "x", encoding="utf-8"
    ) as stream:
        json.dump(
            {
                "schema_version": 2,
                "pid": os.getpid(),
                "worker": WORKER,
                "clock": "time.monotonic_ns",
                "clock_scope": "same-host-only",
                "cpu_scope": "current-process-all-threads/no-children",
                "sample_order": "CPU-then-wall/non-atomic",
                "events": _EARLY_EVENTS,
            },
            stream,
            indent=2,
        )
        stream.write("\n")


@pytest.hookimpl(hookwrapper=True)
def pytest_collection(session):
    _early_mark("pytest_collection.entry")
    yield
    _early_mark("pytest_collection.exit")


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def pytest_configure(config):
    _early_mark("pytest_configure.entry")
    global WORKER
    WORKER = (
        config.workerinput["workerid"]
        if hasattr(config, "workerinput")
        else "controller"
    )
    _early_mark("pytest_configure.exit")


def pytest_sessionstart(session):
    _early_mark("pytest_sessionstart.entry")
    global PHASE_STREAM
    PHASE_STREAM = (OUT / ("phases-" + WORKER + ".jsonl")).open("w", encoding="utf-8")
    if os.environ.get("CHECK_COVERAGE") != "1":
        _early_mark("pytest_sessionstart.exit")
        return
    import coverage

    cov = coverage.Coverage.current()
    assert cov is not None and type(sys.gettrace()).__name__ == "CTracer"
    tracer = Path(sys.modules["coverage.tracer"].__file__)
    machine = native_machine(tracer)
    options = {
        key: cov.get_option("run:" + key)
        for key in (
            "source",
            "branch",
            "dynamic_context",
            "patch",
            "parallel",
            "omit",
            "context",
        )
    }
    assert options["branch"] is False
    assert options["dynamic_context"] == "test_function"
    assert options["patch"] == ["subprocess", "_exit"] and options["parallel"] is True
    assert options["context"] == ""
    assert coverage.__version__ == "7.17.0"
    assert options["omit"] == [
        "docs_src/response_model/tutorial003_04.py",
        "docs_src/response_model/tutorial003_04_py310.py",
    ]
    assert (cov.get_option("run:include") or []) == []
    expected = (
        ["smoke_sut"]
        if os.environ.get("SMOKE") == "1"
        else ["docs_src", "tests", "fastapi"]
    )
    assert [Path(p).name for p in options["source"]] == expected
    save(
        "identity-" + WORKER + ".json",
        {
            "pid": os.getpid(),
            "worker": WORKER,
            "trace_type": type(sys.gettrace()).__name__,
            "native_machine": machine,
            "options": options,
            "coverage_version": coverage.__version__,
            "tracer": str(tracer),
        },
    )
    _early_mark("pytest_sessionstart.exit")


def pytest_collection_finish(session):
    _early_mark("pytest_collection_finish.entry")
    ids = [item.nodeid for item in session.items]
    if ids:
        assert len(ids) == len(set(ids))
        if os.environ.get("FULL_SUITE") == "1":
            assert len(ids) == 2643
            import fastapi

            assert fastapi.__version__ == "0.119.1"
            assert (
                Path(fastapi.__file__).resolve() == SOURCE / "fastapi" / "__init__.py"
            )
        save("collection-" + WORKER + ".json", ids)
    _early_mark("pytest_collection_finish.exit")


def pytest_runtest_logreport(report):
    global _EARLY_FIRST_REPORT
    if _EARLY_ENABLED and not _EARLY_FIRST_REPORT:
        _early_mark("pytest_runtest_logreport.first_entry")
        _EARLY_FIRST_REPORT = True
    assert PHASE_STREAM is not None
    PHASE_STREAM.write(
        json.dumps(
            {
                "nodeid": report.nodeid,
                "when": report.when,
                "outcome": report.outcome,
                "worker": WORKER,
                "duration_seconds": report.duration,
                "completion_monotonic_ns": time.monotonic_ns(),
                "pid": os.getpid(),
                "source_root": str(SOURCE),
            }
        )
        + "\n"
    )


def pytest_sessionfinish(session, exitstatus):
    _early_mark("pytest_sessionfinish.entry")
    global PHASE_STREAM
    assert PHASE_STREAM is not None
    PHASE_STREAM.close()
    PHASE_STREAM = None
    _early_mark("pytest_sessionfinish.exit")
    _early_save()


@pytest.hookimpl(hookwrapper=True)
def pytest_fixture_setup(fixturedef, request):
    observe = (
        os.environ.get("CHECK_FIXTURE") == "1"
        and fixturedef.argname == "client"
        and "test_custom_docs_ui" in request.node.nodeid
    )
    if not observe:
        yield
        return
    before = Path.cwd()
    yield
    owned = Path.cwd()
    base = request.getfixturevalue("tmp_path_factory").getbasetemp()
    assert owned.is_relative_to(base) and owned != before
    assert (owned / "static").is_dir()
    key = request.node.nodeid
    OWNED[key] = {"before": str(before), "owned": str(owned), "base": str(base)}
    save("fixture-setup-" + WORKER + "-" + owned.name + ".json", OWNED[key])


def pytest_fixture_post_finalizer(fixturedef, request):
    key = request.node.nodeid
    if fixturedef.argname == "client" and key in OWNED:
        value = OWNED.pop(key)
        assert Path.cwd() == Path(value["before"])
        assert not (Path(value["owned"]) / "static").exists()
        save(
            "fixture-final-" + WORKER + "-" + Path(value["owned"]).name + ".json",
            {
                **value,
                "cwd_restored": True,
                "static_removed": True,
            },
        )
