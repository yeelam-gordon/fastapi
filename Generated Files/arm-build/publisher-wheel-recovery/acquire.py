"""Acquire only manifest-bound publisher bytes; never load acquired packages."""

import hashlib
import http.client
import json
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "publisher-manifest.json"
OUTPUT = ROOT / "verified-publisher-wheels"
MANIFEST_SHA256 = "cc9bf397aeaeba8a68fceffb94135b8a39c1d7fe6dc88d2b6a6dc17ad04b5c70"
COUNT = 14
TOTAL = 2266989
HOST = "files.pythonhosted.org"
RECEIPT = "receipt.json"
STAGES = {"manifest", "tls", "transfer", "verify", "write", "membership"}
CATEGORIES = {
    "manifest",
    "url",
    "redirect",
    "tls",
    "http",
    "transport",
    "size",
    "sha256",
    "filesystem",
    "membership",
    "internal",
}


class Rejected(Exception):
    def __init__(self, category):
        self.category = category


def check_url(url, filename):
    if not isinstance(url, str) or not url.isascii():
        raise Rejected("url")
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != HOST
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(
            r"/packages/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{60}/" + re.escape(filename),
            parsed.path,
        )
        or url != urllib.parse.urlunsplit(parsed)
    ):
        raise Rejected("url")


def validate_manifest(raw):
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise Rejected("manifest")
    manifest = json.loads(raw)
    if (
        manifest.get("schema") != 1
        or type(manifest.get("count")) is not int
        or manifest["count"] != COUNT
        or type(manifest.get("total_bytes")) is not int
        or manifest["total_bytes"] != TOTAL
        or not isinstance(manifest.get("files"), list)
        or len(manifest["files"]) != COUNT
    ):
        raise Rejected("manifest")
    names = set()
    total = 0
    for item in manifest["files"]:
        filename = item.get("filename")
        if (
            not isinstance(filename, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+-]*\.whl", filename)
            or ".." in filename
            or filename.casefold() in names
            or not isinstance(item.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
            or type(item.get("size")) is not int
            or not 0 < item["size"] <= TOTAL
        ):
            raise Rejected("manifest")
        check_url(item.get("url"), filename)
        names.add(filename.casefold())
        total += item["size"]
    if total != TOTAL:
        raise Rejected("manifest")
    return manifest["files"]


class PublisherRedirect(urllib.request.HTTPRedirectHandler):
    max_redirections = 3
    max_repeats = 1

    def redirect_request(self, request, response, code, message, headers, newurl):
        filename = urllib.parse.urlsplit(request.full_url).path.rsplit("/", 1)[-1]
        try:
            check_url(newurl, filename)
        except (Rejected, ValueError):
            raise Rejected("redirect") from None
        return super().redirect_request(
            request, response, code, message, headers, newurl
        )


def publisher_opener():
    context = ssl.create_default_context()
    if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
        raise Rejected("tls")
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=context),
        PublisherRedirect(),
    )


def verify_payload(data, item):
    if len(data) != item["size"]:
        raise Rejected("size")
    if hashlib.sha256(data).hexdigest() != item["sha256"]:
        raise Rejected("sha256")


def verified_entry(item):
    return {key: item[key] for key in ("filename", "size", "sha256")}


def check_membership(verified):
    expected = {RECEIPT} | {item["filename"] for item in verified}
    if {path.name for path in OUTPUT.iterdir()} != expected:
        raise Rejected("membership")
    if any(path.is_symlink() or not path.is_file() for path in OUTPUT.iterdir()):
        raise Rejected("membership")


def acquire():
    # Neither a caller-supplied path nor an existing directory can become an artifact.
    if OUTPUT.parent.resolve() != ROOT or OUTPUT.is_symlink():
        print("FAILED output filesystem")
        return 1
    try:
        OUTPUT.mkdir(exist_ok=False)
    except OSError:
        print("FAILED output filesystem")
        return 1
    result = {
        "schema": 1,
        "manifest_sha256": MANIFEST_SHA256,
        "status": "FAILED",
        "verified": [],
        "failure": {"stage": "manifest", "file": None, "category": "internal"},
    }
    stage = "manifest"
    filename = None
    try:
        files = validate_manifest(MANIFEST.read_bytes())
        stage = "tls"
        opener = publisher_opener()
        for item in files:
            filename = item["filename"]
            stage = "transfer"
            request = urllib.request.Request(
                item["url"], headers={"Accept-Encoding": "identity"}
            )
            with opener.open(request, timeout=15) as response:
                if response.status != 200:
                    raise Rejected("http")
                check_url(response.geturl(), filename)
                data = response.read(item["size"] + 1)
            stage = "verify"
            verify_payload(data, item)
            stage = "write"
            target = OUTPUT / filename
            try:
                with target.open("xb") as stream:
                    if stream.write(data) != len(data):
                        raise OSError("short write")
            except OSError:
                target.unlink(missing_ok=True)
                raise
            result["verified"].append(verified_entry(item))
        result.update(status="VERIFIED", failure=None)
    except (
        Rejected,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        RuntimeError,
        http.client.HTTPException,
    ) as error:
        if isinstance(error, Rejected):
            category = error.category
        elif isinstance(error, ssl.SSLError):
            category = "tls"
        elif isinstance(error, urllib.error.HTTPError):
            category = "http"
        elif isinstance(error, urllib.error.URLError):
            category = "transport"
        elif isinstance(error, OSError):
            category = "filesystem" if stage in {"manifest", "write"} else "transport"
        else:
            category = "internal"
        result["failure"] = {"stage": stage, "file": filename, "category": category}
    try:
        (OUTPUT / RECEIPT).write_text(
            json.dumps(result, indent=2) + "\n", encoding="ascii"
        )
        check_membership(result["verified"])
    except (Rejected, OSError, ValueError, TypeError):
        result.update(
            status="FAILED",
            failure={"stage": "membership", "file": None, "category": "membership"},
        )
        try:
            (OUTPUT / RECEIPT).write_text(
                json.dumps(result, indent=2) + "\n", encoding="ascii"
            )
        except OSError:
            pass
        print("FAILED membership filesystem")
        return 1
    print(result["status"])
    return 0 if result["status"] == "VERIFIED" else 1


def check_output():
    """Revalidate exact artifact membership, safe receipt and every retained byte."""
    try:
        if OUTPUT.is_symlink() or OUTPUT.parent.resolve() != ROOT:
            raise Rejected("membership")
        files = validate_manifest(MANIFEST.read_bytes())
        result = json.loads((OUTPUT / RECEIPT).read_text(encoding="ascii"))
        verified = result["verified"]
        if (
            type(verified) is not list
            or len(verified) > len(files)
            or verified != [verified_entry(item) for item in files[: len(verified)]]
            or result["schema"] != 1
            or result["manifest_sha256"] != MANIFEST_SHA256
            or set(result)
            != {"schema", "manifest_sha256", "status", "verified", "failure"}
        ):
            raise Rejected("membership")
        if result["status"] == "VERIFIED":
            if len(verified) != COUNT or result["failure"] is not None:
                raise Rejected("membership")
        elif result["status"] == "FAILED":
            failure = result["failure"]
            if (
                set(failure) != {"stage", "file", "category"}
                or failure["stage"] not in STAGES
                or failure["category"] not in CATEGORIES
                or failure["file"] not in {None} | {item["filename"] for item in files}
                or len(verified) == COUNT
            ):
                raise Rejected("membership")
        else:
            raise Rejected("membership")
        check_membership(verified)
        for item in verified:
            with (OUTPUT / item["filename"]).open("rb") as stream:
                verify_payload(stream.read(item["size"] + 1), item)
    except (Rejected, OSError, ValueError, TypeError, KeyError, AttributeError):
        print("FAILED artifact membership")
        return 1
    print("VERIFIED artifact membership")
    return 0


def main():
    if sys.argv[1:] == ["--check-output"]:
        return check_output()
    if sys.argv[1:]:
        print("FAILED arguments")
        return 1
    return acquire()


if __name__ == "__main__":
    raise SystemExit(main())
