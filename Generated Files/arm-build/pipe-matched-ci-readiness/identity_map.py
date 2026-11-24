"""Verify exact public xdist suffixes; retain every raw identity unchanged."""

SHARED = {"tests/test_application.py", "tests/test_path.py", "tests/test_query.py"}
WORKDIR = {
    "tests/test_tutorial/test_additional_responses/test_tutorial002.py",
    "tests/test_tutorial/test_additional_responses/test_tutorial004.py",
    "tests/test_tutorial/test_background_tasks/test_tutorial001.py",
    "tests/test_tutorial/test_background_tasks/test_tutorial002.py",
    "tests/test_tutorial/test_events/test_tutorial002.py",
}


def group_for(nodeid):
    filename = nodeid.split("::", 1)[0]
    if filename in SHARED:
        return "shared-main-app"
    if filename in WORKDIR:
        return "workdir_lock"
    return filename


def exact_mapping(expected, raw, parallel):
    assert len(expected) == len(set(expected)), "Canonical nodes are not unique"
    forward = {
        node + ("@" + group_for(node) if parallel else ""): node for node in expected
    }
    assert len(forward) == len(expected)
    assert len(raw) == len(set(raw)) == len(expected), "Missing or repeated raw nodes"
    assert set(raw) == set(forward), "Unexpected/missing exact xdist group suffix"
    return forward
