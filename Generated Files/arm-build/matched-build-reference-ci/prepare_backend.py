"""Acquire one publisher-pinned pure backend wheel outside build measurements."""

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

FILENAME = "pdm_backend-2.5.0-py3-none-any.whl"
WHEEL_SHA256 = "5b8746b567a16a1fd506ce66ee28e89d46374526f52238aa1b96cc2c08245c63"
METADATA_URL = "https://pypi.org/pypi/pdm-backend/2.5.0/json"


def fetch(url, maximum):
    with urllib.request.urlopen(url, timeout=20) as response:
        final = urlsplit(response.geturl())
        expected = urlsplit(url)
        if final.scheme != "https" or final.hostname != expected.hostname:
            raise ValueError("Unexpected publisher redirect")
        raw = response.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError("Publisher response exceeds acquisition limit")
    return raw


def prepare(output):
    output = Path(output)
    if output.exists():
        raise FileExistsError("Fresh backend wheel directory required")
    metadata = json.loads(fetch(METADATA_URL, 2 * 1024 * 1024))
    wheels = [row for row in metadata["urls"] if row["filename"] == FILENAME]
    if len(wheels) != 1 or wheels[0]["digests"]["sha256"] != WHEEL_SHA256:
        raise ValueError("Pinned backend publisher identity differs")
    wheel = wheels[0]
    url = urlsplit(wheel["url"])
    if (
        url.scheme != "https"
        or url.hostname != "files.pythonhosted.org"
        or url.username is not None
        or url.password is not None
        or url.port not in (None, 443)
    ):
        raise ValueError("Unexpected backend publisher URL")
    raw = fetch(wheel["url"], 8 * 1024 * 1024)
    if len(raw) != wheel["size"] or hashlib.sha256(raw).hexdigest() != WHEEL_SHA256:
        raise ValueError("Backend wheel bytes differ from pinned publisher")
    output.mkdir()
    with (output / FILENAME).open("xb") as stream:
        stream.write(raw)
    return {"filename": FILENAME, "sha256": WHEEL_SHA256, "bytes": len(raw)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(prepare(parser.parse_args().output)))
