"""Private PDM 2.5 experiment: bounded reads, unchanged stdlib archive writer."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
import tarfile

from pdm.backend.sdist import SdistBuilder, clean_tarinfo
from pdm.backend.utils import safe_version, to_filename
from pdm.backend._vendor.packaging.utils import canonicalize_name


def payloads(files, threaded):
    if not threaded:
        for relative, path in files:
            yield relative, path, path.read_bytes()
        return
    iterator = iter(files)
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="sdist-read") as pool:
        pending = deque()

        def submit():
            item = next(iterator, None)
            if item is not None:
                relative, path = item
                pending.append((relative, path, pool.submit(path.read_bytes)))

        try:
            for _ in range(3):
                submit()
            while pending:
                relative, path, future = pending.popleft()
                yield relative, path, future.result()
                del future
                submit()
        finally:
            for _, _, future in pending:
                future.cancel()


class BufferedSdistBuilder(SdistBuilder):
    threaded = False
    modes = {}

    def build_artifact(self, context, files):
        version = to_filename(safe_version(context.config.metadata["version"]))
        name = to_filename(canonicalize_name(context.config.metadata["name"]))
        root = f"{name}-{version}"
        target = context.dist_dir / f"{root}.tar.gz"
        with tarfile.open(target, "w:gz", format=tarfile.PAX_FORMAT,
                          compresslevel=9) as archive:
            for relative, path, data in payloads(files, self.threaded):
                info = clean_tarinfo(archive.gettarinfo(path, f"{root}/{relative}"))
                if not info.isreg() or info.size != len(data):
                    raise ValueError(f"Nonregular or changed payload: {relative}")
                if relative in self.modes:
                    info.mode = 0o755 if self.modes[relative]["mode"] & 0o111 else 0o644
                archive.addfile(info, BytesIO(data))
                self._show_add_file(relative, path)
            info = clean_tarinfo(tarfile.TarInfo(f"{root}/PKG-INFO"))
            data = str(self._package_metadata.as_rfc822()).encode("utf-8")
            info.size = len(data)
            archive.addfile(info, BytesIO(data))
            self._show_add_file("PKG-INFO", Path("PKG-INFO"))
        return target


def extract_selected(archive, destination, selected, attrs):
    members = [archive.getmember(name) for name in selected]
    if not attrs and any(not m.isfile() or m.mode != 0o644 for m in members):
        raise ValueError("Attribute skipping requires exclusively public nonexecutable 0644 inputs")
    for member in members:
        archive.extract(member, destination, set_attrs=attrs, filter="data")
