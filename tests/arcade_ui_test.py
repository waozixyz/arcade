"""Play the real Chess bundle in Arcade on a private display and restore its game."""
import contextlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
assert int(os.environ["DISPLAY"].split(":")[-1].split(".")[0]) >= 400
assert os.environ["YUE_DESKTOP_RECOVERY"] == "0"
inbe = Path(subprocess.check_output(["ziran", "pkg", "path", "inbe"], cwd=ROOT, text=True).strip())
sys.path.insert(0, str(inbe / "tests"))
from ui_driver import UiDriver

OUTPUT = ROOT / "build/ui-test"
OUTPUT.mkdir(parents=True, exist_ok=True)
BINARY = ROOT / "build/arcade"
driver = UiDriver(OUTPUT / "driver")


def command(*args):
    return subprocess.check_output(args, text=True, timeout=10).strip()


def wait(predicate, message):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.05)
    raise driver._failure(message)


@contextlib.contextmanager
def application(profile, name, *arguments):
    log_path = OUTPUT / (name + ".log")
    env = os.environ | driver.environment() | {"ARCADE_DATA": str(profile), "LANG": "en_US.UTF-8"}
    with log_path.open("w") as log:
        child = subprocess.Popen([str(BINARY), *arguments], cwd=ROOT, env=env,
                                 stdout=log, stderr=subprocess.STDOUT)
        driver.attach(child, log_path)
        try:
            driver.tree()
            yield child
        finally:
            if child.poll() is None:
                child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)


def square(name):
    return 8010 + (8 - int(name[1])) * 8 + ord(name[0]) - ord("a")


def board():
    return {node["key"]: node["label"] for node in driver.tree()
            if node["kind"] == "image" and node["visible"] and 8400 <= node["key"] < 8464}


def capture(child, name):
    window = command("xdotool", "search", "--onlyvisible", "--pid", str(child.pid)).splitlines()[0]
    assert int(command("xdotool", "getwindowpid", window)) == child.pid
    path = OUTPUT / (name + ".png")
    command("import", "-window", window, str(path))
    return path


with tempfile.TemporaryDirectory(prefix="profile-", dir=OUTPUT) as directory:
    profile = Path(directory)
    record = profile / "games/inbe.chess/records/computer"
    with application(profile, "play") as child:
        driver.wait(label="Arcade", role="text")
        capture(child, "library")
        driver.press(label="Chess", role="button")
        driver.wait(label="Easy", role="button")
        driver.press(label="Easy", role="button")
        driver.press(label="Play White", role="button")
        driver.press(label="Start", role="button")
        driver.wait(label="Your move")
        assert len(board()) == 32, "Initial pieces are missing"
        driver.press(key=square("e2"))
        driver.press(key=square("e4"))
        def two_moves():
            if not record.exists():
                return None
            text = record.read_text()
            if "moves=" not in text:
                return None
            moves = text.split("moves=", 1)[1].split()
            return moves if len(moves) == 2 else None
        moves = wait(two_moves, "Computer did not reply to e2e4")
        assert moves[0] == "e2e4", moves
        driver.wait(label="Your move")
        driver.wait_idle(frames=3)
        position = board()
        assert 8400 + square("e4") - 8010 in position
        assert 8400 + square("e2") - 8010 not in position
        image_path = capture(child, "after-e4")
        pawn = driver.find(key=8400 + square("e4") - 8010)[0]
        with Image.open(image_path).convert("RGB") as image:
            x, y = UiDriver.center(pawn)
            pixels = [image.getpixel((int(x) + dx, int(y) + dy))
                      for dx in range(-8, 9) for dy in range(-8, 9)]
            assert any(all(abs(channel - target) < 15 for channel, target in zip(pixel, (246, 241, 231)))
                       for pixel in pixels), "The pawn's image did not render"
        saved = record.read_bytes()
        driver.press(label="Arcade", role="button")
        driver.wait(label="Chess", role="button")
        driver.press(label="Chess", role="button")
        driver.wait(label="Your move")
        assert board() == position, "Returning from the library reset the game"
        assert record.stat().st_mode & 0o777 == 0o600
    with application(profile, "restore", "--app", "chess") as child:
        driver.wait(label="Your move")
        assert board() == position, "Restart did not restore the game"
        assert record.read_bytes() == saved
        driver.press(label="Friends", role="button")
        driver.wait(contains="Sign in")
        capture(child, "friends-offline")
    # The profile's lock rejects a second writer without affecting the game.
    with application(profile, "lock-owner", "--app", "chess"):
        driver.wait(label="Your move")
        second = subprocess.run([str(BINARY), "--app", "chess"], cwd=ROOT,
                                env=os.environ | {"ARCADE_DATA": str(profile)},
                                capture_output=True, timeout=10)
        assert second.returncode == 1, "Two processes were allowed to write the same game"
        assert record.read_bytes() == saved

print("Arcade: Chess catalog, rendered board, legal move and computer reply, library return, restart persistence and private single-writer storage passed")
