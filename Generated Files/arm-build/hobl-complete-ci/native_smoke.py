"""Tiny untimed three-arm semantic oracle; no timing instrumentation."""

import json
import os
import sys
import warnings
from pathlib import Path

import coverage
import coverage.tracer
import native_fixture

mode = sys.argv[1]
if os.environ.get("HOBL_NATIVE_EXPECT"):
    if (
        Path(coverage.__file__).resolve()
        != Path(os.environ["HOBL_NATIVE_EXPECT"]).resolve()
    ):
        raise RuntimeError("semantic probe coverage origin")
events = []


def audit(event, args):
    if event == "object.__getattr__" and args[1] == "f_code":
        frame = args[0]
        if frame.f_globals.get("__name__") == "native_fixture":
            events.append(frame.f_lineno)
            if mode == "audit":
                raise RuntimeError("native-audit-block")


sys.addaudithook(audit)
cov = coverage.Coverage(
    data_file=None, config_file=False, include=[str(Path(native_fixture.__file__))]
)
cov.set_option("run:dynamic_context", "test_function")
error = None
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    cov.start()
    tracer = cov._collector.tracers[0]
    if type(tracer).__name__ != "CTracer":
        raise RuntimeError("native CTracer required")
    if mode == "mutation":
        tracer.should_start_context = lambda frame: (
            "custom" if frame.f_code.co_name == "ordinary" else None
        )
    try:
        native_fixture.exercise()
    except RuntimeError as exc:
        error = [type(exc).__name__, str(exc)]
    finally:
        cov.stop()
    data = cov.get_data()
    result = {
        "files": {
            name: {
                str(line): sorted(contexts)
                for line, contexts in data.contexts_by_lineno(name).items()
            }
            for name in sorted(data.measured_files())
        },
        "contexts": sorted(data.measured_contexts()),
        "error": error,
        "audit": events,
        "warnings": [str(w.message) for w in caught],
    }
print(json.dumps(result, ensure_ascii=True, sort_keys=True))
