"""Public coverage configurer: record live identity without preloading the CLI."""

import json
import os
import sys
from pathlib import Path

from cli_identity import native_identity
from coverage import CoveragePlugin


class IdentityConfigurer(CoveragePlugin):
    def configure(self, config):
        output = Path(os.environ["CORRECTNESS_OUTPUT"])
        record = {
            **native_identity(),
            "namespace": str(output),
            "orig_argv": sys.orig_argv,
        }
        path = output / f"cli-native-identity-{os.getpid()}.json"
        if path.exists():
            if json.loads(path.read_text()) != record:
                raise RuntimeError(
                    "Native identity changed during coverage configuration"
                )
        else:
            with path.open("x", encoding="utf-8") as stream:
                json.dump(record, stream)


def coverage_init(reg, options):
    reg.add_configurer(IdentityConfigurer())
