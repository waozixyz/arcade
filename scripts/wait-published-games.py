#!/usr/bin/env python3
"""Wait for the game packages a published Arcade catalog advertises.

The site still tests the real Inbe API before its browser gate. The publisher
can follow a GitHub release by several minutes, so readiness is conditional and
has a hard deadline; no package is extracted or executed.
"""
import argparse
import hashlib
import json
import re
import struct
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

API_ROOT = "https://api.waozi.xyz"
CATALOG_PATH = "assets/apps/catalog.json"
BUNDLE_LIMIT = 64 * 1024 * 1024
CATALOG_LIMIT = 1024 * 1024
READ_CHUNK = 1024 * 1024
PREFIX_BYTES = 16
REQUEST_TIMEOUT_SECONDS = 15


class Reader:
    def __init__(self, path):
        self.size = path.stat().st_size
        if self.size > BUNDLE_LIMIT:
            raise ValueError("published Arcade bundle is too large")
        self.remaining = self.size
        self.file = path.open("rb")

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        self.file.close()

    def take(self, size):
        if size < 0 or size > self.remaining:
            raise ValueError("truncated bundle")
        data = self.file.read(size)
        if len(data) != size:
            raise ValueError("truncated bundle")
        self.remaining -= size
        return data

    def skip(self, size):
        if size < 0 or size > self.remaining:
            raise ValueError("truncated bundle")
        self.file.seek(size, 1)
        self.remaining -= size

    def number(self):
        return struct.unpack("<I", self.take(4))[0]

    def text(self, limit=BUNDLE_LIMIT):
        size = self.number()
        if size > limit or size > self.remaining:
            raise ValueError("oversized bundle field")
        return self.take(size)

    def finish(self):
        if self.file.read(1):
            raise ValueError("trailing bundle bytes")
        self.file.close()


def catalog_from_bundle(path):
    with Reader(path) as reader:
        if reader.take(8) not in (b"ZX\0\0\x1a\0\0\0", b"ZX\0\0\x1b\0\0\0"):
            raise ValueError("unsupported bundle")
        reader.text()
        reader.text()
        for _ in range(reader.number()):
            reader.text()
            reader.text()
        for _ in range(reader.number()):
            for _ in range(7):
                reader.text()
            reader.take(8)
            reader.text()
            reader.take(4)
        for _ in range(reader.number()):
            for _ in range(3):
                reader.text()
        reader.skip(reader.number())
        assets = reader.number()
        catalog = None
        seen = set()
        for _ in range(assets):
            name = reader.text().decode()
            if name in seen:
                raise ValueError("duplicate bundle file")
            seen.add(name)
            size = reader.number()
            if name == CATALOG_PATH:
                if catalog is not None or size > CATALOG_LIMIT:
                    raise ValueError("invalid collection catalog")
                catalog = reader.take(size)
            else:
                reader.skip(size)
        reader.finish()
    if catalog is None:
        raise ValueError("the collection lacks a catalog")
    return json.loads(catalog)


def expected_games(catalog):
    children = catalog.get("children")
    if not isinstance(children, list):
        raise ValueError("invalid collection catalog")
    games = {}
    for child in children:
        digest, size = child.get("sha256", ""), child.get("bytes")
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or not isinstance(size, int) \
                or not 0 < size <= BUNDLE_LIMIT:
            raise ValueError("invalid game in the collection catalog")
        games[digest] = size
    return games


def archive_members(archive, games):
    members = {}
    with tarfile.open(archive, "r:") as content:
        for entry in content:
            digest = entry.name.removesuffix(".zx")
            if digest not in games:
                continue
            if not entry.isfile() or digest in members or entry.size != games[digest]:
                raise ValueError("the release game archive differs from the catalog")
            source = content.extractfile(entry)
            source_digest = hashlib.sha256()
            prefix = bytearray()
            read = 0
            while chunk := source.read(min(READ_CHUNK, games[digest] - read)):
                source_digest.update(chunk)
                if len(prefix) < PREFIX_BYTES:
                    prefix.extend(chunk[:PREFIX_BYTES - len(prefix)])
                read += len(chunk)
            if read != games[digest] or source_digest.hexdigest() != digest:
                raise ValueError("the release game archive differs from the catalog")
            members[digest] = (source_digest.hexdigest(), bytes(prefix))
    if set(members) != set(games):
        raise ValueError("the release game archive lacks a catalog game")
    return members


def package_ready(api_root, digest, size, prefix, timeout_seconds=REQUEST_TIMEOUT_SECONDS):
    url = f"{api_root.rstrip('/')}/api/v2/packages/inbe.arcade/{digest}.zx"
    request = urllib.request.Request(
        url,
        headers={"Range": f"bytes=0-{PREFIX_BYTES - 1}", "User-Agent": "arcade-site-readiness"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status = response.status
            content_type = response.headers.get_content_type()
            etag = response.headers.get("ETag")
            content_range = response.headers.get("Content-Range")
            content_length = response.headers.get("Content-Length")
            body = response.read(PREFIX_BYTES)
    except urllib.error.HTTPError as error:
        error.close()
        return False
    except (TimeoutError, urllib.error.URLError):
        return False
    if etag != f'"{digest}"':
        return False
    expected_length = size if status == 200 else min(PREFIX_BYTES, size)
    if content_length is not None:
        try:
            length = int(content_length)
        except ValueError:
            return False
        if length != expected_length:
            return False
    if status == 206:
        match = re.fullmatch(r"bytes 0-(\d+)/(\d+)", content_range or "")
        if not match or int(match[1]) != min(PREFIX_BYTES, size) - 1 or int(match[2]) != size:
            return False
    elif status != 200:
        return False
    return content_type == "application/octet-stream" and body == prefix


def wait_for_published_games(api_root, archive, games, members, deadline_seconds,
                             poll_seconds=30, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + deadline_seconds
    pending = set(games)
    while True:
        for digest in list(pending):
            remaining = deadline - clock()
            if remaining <= 0:
                raise TimeoutError(
                    f"published game packages still unavailable: {', '.join(sorted(pending))}"
                )
            ready = package_ready(
                api_root, digest, games[digest], members[digest][1],
                timeout_seconds=min(REQUEST_TIMEOUT_SECONDS, remaining),
            )
            if not ready:
                continue
            pending.remove(digest)
        if not pending:
            return
        now = clock()
        remaining = deadline - now
        if remaining <= 0:
            raise TimeoutError(f"published game packages still unavailable: {', '.join(pending)}")
        sleep(min(poll_seconds, remaining))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-root", default=API_ROOT)
    parser.add_argument("--deadline-seconds", type=int, default=900)
    parser.add_argument("--poll-seconds", type=float, default=30)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("archive", type=Path)
    arguments = parser.parse_args()
    catalog = catalog_from_bundle(arguments.bundle)
    games = expected_games(catalog)
    members = archive_members(arguments.archive, games)
    wait_for_published_games(arguments.api_root, arguments.archive, games, members,
                             arguments.deadline_seconds, arguments.poll_seconds)
    print(f"all {len(games)} catalog game packages are published and ready")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TimeoutError, tarfile.TarError) as error:
        raise SystemExit(str(error))
