import hashlib
import http.server
import io
import importlib.util
import json
from pathlib import Path
import struct
import tarfile
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "wait_published_games", ROOT / "scripts/wait-published-games.py"
)
readiness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(readiness)


def bundle(files):
    def text(value):
        return struct.pack("<I", len(value)) + value

    data = b"ZX\0\0\x1a\0\0\0" + text(b"arcade") + text(b"Main")
    data += struct.pack("<IIII", 0, 0, 0, 0) + struct.pack("<I", len(files))
    for path in sorted(files):
        data += text(path.encode()) + text(files[path])
    return data


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Handler(http.server.BaseHTTPRequestHandler):
    responses = {}

    def do_GET(self):
        digest = self.path.rsplit("/", 1)[-1].removesuffix(".zx")
        response = self.responses.get(digest, "ready")
        if isinstance(response, list):
            response = response.pop(0)
        if response == "ready":
            game = getattr(self.server, "games", {})
            body = game.get(digest, b"")[:16]
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("ETag", f'"{digest}"')
            self.end_headers()
            self.wfile.write(body)
            return
        if isinstance(response, int):
            self.send_response(response)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")
            return
        body = response.get("body", b"ZX\0\0\x1a\0\0\0port")
        self.send_response(response.get("status", 200))
        self.send_header("Content-Type", response.get("type", "application/octet-stream"))
        if "etag" in response:
            self.send_header("ETag", response["etag"])
        if "range" in response:
            self.send_header("Content-Range", response["range"])
        self.send_header("Content-Length", str(response.get("length", len(body))))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *arguments):
        pass


class WaitPublishedGamesTests(unittest.TestCase):
    def setUp(self):
        work = ROOT / "build/scratch"
        work.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="published-games-", dir=work)
        self.root = Path(self.temporary.name)
        self.games = {
            hashlib.sha256(b"first game").hexdigest(): b"first game",
            hashlib.sha256(b"second game").hexdigest(): b"second game",
            hashlib.sha256(b"third game with bytes").hexdigest(): b"third game with bytes",
        }
        catalog = {
            "children": [
                {"sha256": digest, "bytes": len(data)} for digest, data in self.games.items()
            ]
        }
        self.bundle = self.root / "arcade.zx"
        self.bundle.write_bytes(bundle({"assets/apps/catalog.json": json.dumps(catalog).encode()}))
        self.archive = self.root / "arcade.games.tar"
        with tarfile.open(self.archive, "w") as content:
            for digest, data in self.games.items():
                member = tarfile.TarInfo(digest + ".zx")
                member.size = len(data)
                content.addfile(member, io.BytesIO(data))
        Handler.responses = {}
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.games = {digest: data for digest, data in self.games.items()}
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.api_root = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temporary.cleanup()

    def wait(self, deadline=1.0):
        games = readiness.expected_games(readiness.catalog_from_bundle(self.bundle))
        members = readiness.archive_members(self.archive, games)
        clock = Clock()
        readiness.wait_for_published_games(self.api_root, self.archive, games, members,
                                           deadline, poll_seconds=0.01,
                                           clock=clock, sleep=clock.sleep)

    def test_all_packages_ready(self):
        self.wait()

    def test_a_404_is_retried_until_the_package_is_ready(self):
        digest = next(iter(self.games))
        Handler.responses[digest] = [404, "ready"]
        self.wait(deadline=0.03)

    def test_a_permanent_404_fails_at_the_deadline(self):
        Handler.responses[next(iter(self.games))] = 404
        with self.assertRaisesRegex(TimeoutError, "still unavailable"):
            self.wait(deadline=0.01)

    def test_error_or_mismatched_responses_do_not_count_as_ready(self):
        digest = next(iter(self.games))
        for response in (
            {"etag": '"0" * 64'},
            {"type": "text/plain"},
            {"body": b"not the verified prefix"},
            {"body": b"0123456789abcdef", "etag": None},
            {"status": 206, "range": "bytes 0-15/1"},
            500,
        ):
            Handler.responses[digest] = response
            with self.subTest(response=response), self.assertRaises(TimeoutError):
                self.wait()

    def test_an_exact_partial_response_counts_as_ready(self):
        digest, game = next(item for item in self.games.items() if len(item[1]) > 16)
        Handler.responses[digest] = {
            "status": 206,
            "etag": f'"{digest}"',
            "range": f"bytes 0-{min(16, len(game)) - 1}/{len(game)}",
            "body": game[:16],
        }
        self.wait()

    def test_a_wrong_full_response_content_length_does_not_count_as_ready(self):
        digest, game = next(iter(self.games.items()))
        Handler.responses[digest] = {
            "etag": f'"{digest}"',
            "body": game,
            "length": len(game) + 1,
        }
        with self.assertRaisesRegex(TimeoutError, digest):
            self.wait(deadline=0.02)


if __name__ == "__main__":
    unittest.main()
