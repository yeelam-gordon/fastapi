"""Reuse native/phase evidence; append public marker identities without rewriting."""

import observer as base
from observer import (
    pytest_configure as pytest_configure,
)
from observer import (
    pytest_fixture_post_finalizer as pytest_fixture_post_finalizer,
)
from observer import (
    pytest_fixture_setup as pytest_fixture_setup,
)
from observer import (
    pytest_runtest_logreport as pytest_runtest_logreport,
)
from observer import (
    pytest_sessionstart as pytest_sessionstart,
)


def pytest_collection_finish(session):
    base.pytest_collection_finish(session)
    if session.items:
        base.save(
            "groups-" + base.WORKER + ".json",
            [
                {
                    "raw_nodeid": item.nodeid,
                    "xdist_group_marks": [
                        mark.args[0]
                        if mark.args
                        else mark.kwargs.get("name", "default")
                        for mark in item.iter_markers("xdist_group")
                    ],
                }
                for item in session.items
            ],
        )
