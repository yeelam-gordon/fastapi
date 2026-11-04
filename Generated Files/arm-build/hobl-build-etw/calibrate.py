"""Short known root+child CPU and file activity; no capture APIs here."""
import pathlib
import json
import os
import subprocess
import sys
import time


def work():
    directory = pathlib.Path(str(os.getpid()))
    directory.mkdir()
    p = directory / "calibration-data.bin"
    deadline = time.perf_counter() + .5
    while time.perf_counter() < deadline:
        p.write_bytes(b"x" * 65536)
        assert len(p.read_bytes()) == 65536
        sum(i * i for i in range(15000))
    time.sleep(.1)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.path.insert(0, str(pathlib.Path(__file__).parent))
        from launch import spawn, qpc
        child, anchor = spawn([sys.executable, "-I", "-B", __file__, "child"])
        try:
            if os.environ.get("HOBL_PRIVATE_WAIT_CALIBRATION") == "1":
                from native_calibration import controlled_wait
                pathlib.Path("wait-handshake.json").write_text(
                    json.dumps(controlled_wait()), encoding="utf-8")
            work()
        finally:
            code = child.wait(timeout=3)
        anchor["qpc_end"] = qpc()
        pathlib.Path("child-anchor.json").write_text(json.dumps(anchor), encoding="utf-8")
        sys.exit(code)
    work()
