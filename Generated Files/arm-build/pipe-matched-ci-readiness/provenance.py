"""Pinned public CPython source contract and in-allocation runtime readiness."""

import ast
import hashlib
import inspect
import json
import sys
import textwrap
from pathlib import Path

from matched import HERE


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def method(source, owner, name):
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == owner:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == name:
                    return ast.dump(item, include_attributes=False)
    raise RuntimeError(f"Missing pinned method: {owner}.{name}")


def source_contract():
    folder = HERE / "cpython-3.13.15"
    pins = json.loads((folder / "SOURCE.json").read_text())
    for name, pin in pins.items():
        if digest(folder / name) != pin["sha256"]:
            raise RuntimeError(f"Pinned CPython source changed: {name}")
    native = (folder / "selectmodule.c").read_text()
    for text in (
        "kqueue_queue_internal_close(kqueue_queue_Object *self)",
        "self->kqfd = -1;",
        "if (close(kqfd) < 0)",
        "kqueue_queue_get_closed(kqueue_queue_Object *self",
        "if (self->kqfd < 0)",
        '{"closed", (getter)kqueue_queue_get_closed',
    ):
        if text not in native:
            raise RuntimeError("Pinned native kqueue close contract differs")
    return pins


def mac_runtime():
    """Only invoked by the bounded readiness command, never static validation."""
    import asyncio
    import asyncio.selector_events
    import selectors

    from portable_lifetime import capture, certificate

    if sys.platform != "darwin" or sys.version_info[:3] != (3, 13, 15):
        raise RuntimeError("Exact Mac CPython runtime required")
    source_contract()
    folder = HERE / "cpython-3.13.15"
    for owner, name, filename in (
        (selectors.KqueueSelector, "close", "selectors.py"),
        (selectors._BaseSelectorImpl, "close", "selectors.py"),
        (asyncio.selector_events.BaseSelectorEventLoop, "close", "selector_events.py"),
        (
            asyncio.selector_events.BaseSelectorEventLoop,
            "_close_self_pipe",
            "selector_events.py",
        ),
    ):
        actual = ast.dump(
            ast.parse(textwrap.dedent(inspect.getsource(getattr(owner, name)))).body[0]
        )
        expected = method((folder / filename).read_bytes(), owner.__name__, name)
        if actual != expected:
            raise RuntimeError(f"Installed Mac stdlib differs: {owner.__name__}.{name}")
    loop = asyncio.SelectorEventLoop()
    value = capture(loop)
    loop.close()
    value.close_returned = True
    return certificate(value, mac_source_qualified=True)
