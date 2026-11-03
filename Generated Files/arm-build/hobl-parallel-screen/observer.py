"""Read-only evidence for stock pytest scheduling and native coverage."""

import json
import os
import sys
from pathlib import Path

import pytest
from native import native_machine

OUT = Path(os.environ["CORRECTNESS_OUTPUT"])
SOURCE = Path(os.environ["CORRECTNESS_SOURCE"])
WORKER = "controller"
OWNED = {}


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def pytest_configure(config):
    global WORKER
    WORKER = (
        config.workerinput["workerid"]
        if hasattr(config, "workerinput")
        else "controller"
    )


def pytest_sessionstart(session):
    if os.environ.get("CHECK_COVERAGE") != "1":
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


def pytest_collection_finish(session):
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


def pytest_runtest_logreport(report):
    with (OUT / ("phases-" + WORKER + ".jsonl")).open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                {
                    "nodeid": report.nodeid,
                    "when": report.when,
                    "outcome": report.outcome,
                    "worker": WORKER,
                }
            )
            + "\n"
        )


@pytest.hookimpl(hookwrapper=True)
def pytest_fixture_setup(fixturedef, request):
    observe = (
        os.environ.get("CHECK_FIXTURE") == "1"
        and fixturedef.argname == "client"
        and "test_custom_docs_ui" in request.node.nodeid
    )
    before = Path.cwd()
    yield
    if observe:
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
