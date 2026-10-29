"""Opt-in instrumentation of stock uv's actual isolated ``python -c`` children."""

import os

if os.environ.get("ARM_DIAG_PASS"):
    from arm_diag_hook import install

    install()
