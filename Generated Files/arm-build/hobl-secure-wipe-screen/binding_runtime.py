"""Observe binding provenance and normal runtime without importing crypto."""

import hashlib
import importlib.metadata
import json
import os
import sys
import sysconfig
from pathlib import Path

import pytest
from native import native_machine


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    worker = (
        session.config.workerinput["workerid"]
        if hasattr(session.config, "workerinput")
        else "controller"
    )
    module = sys.modules.get("_argon2_cffi_bindings._ffi")
    evidence = {
        "worker": worker,
        "status": "NOT_IMPORTED",
        "image_sha256": None,
        "image_path": None,
        "dont_write_bytecode": sys.dont_write_bytecode,
        "pycache_prefix": sys.pycache_prefix,
        "switch_interval": sys.getswitchinterval(),
        "gil": sys._is_gil_enabled(),
        "version": list(sys.version_info[:3]),
        "jit_enabled": getattr(
            getattr(sys, "_jit", None), "is_enabled", lambda: False
        )(),
        "free_threaded": bool(sysconfig.get_config_var("Py_GIL_DISABLED")),
        "debug": hasattr(sys, "gettotalrefcount"),
        "plugins": sorted(
            name
            for name, plugin in session.config.pluginmanager.list_name_plugin()
            if plugin is not None
        ),
    }
    if (
        evidence["dont_write_bytecode"]
        or evidence["pycache_prefix"] is not None
        or evidence["switch_interval"] != 0.005
        or not evidence["gil"]
        or evidence["version"] != [3, 13, 15]
        or evidence["jit_enabled"]
        or evidence["free_threaded"]
        or evidence["debug"]
    ):
        raise ValueError("nondefault_runtime")
    if module is not None:
        image = Path(module.__file__).resolve()
        data = image.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        machine = native_machine(image)
        if digest != os.environ["HOBL_BINDING_SHA256"]:
            raise ValueError("binding_image_mismatch")
        if (
            importlib.metadata.version("argon2-cffi-bindings") != "26.1.0"
            or importlib.metadata.version("pwdlib") != "0.3.1"
        ):
            raise ValueError("binding_version_mismatch")
        evidence.update(
            status="OBSERVED",
            image_sha256=digest,
            image_path=str(image),
            native_machine=machine,
        )
    (Path(os.environ["CORRECTNESS_OUTPUT"]) / f"binding-{worker}.json").write_text(
        json.dumps(evidence, indent=2), encoding="utf-8"
    )
