"""Play the real Chess bundle in Arcade on a private display and restore its game."""
import contextlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from PIL import Image
from chess_import_flow import check_import

ROOT = Path(__file__).resolve().parents[1]
assert int(os.environ["DISPLAY"].split(":")[-1].split(".")[0]) >= 400
assert os.environ["YUE_DESKTOP_RECOVERY"] == "0"
inbe = Path(subprocess.check_output(["ziran", "pkg", "path", "inbe"], cwd=ROOT, text=True).strip())
sys.path.insert(0, str(inbe / "tests"))
from ui_driver import UiDriver

OUTPUT = Path(os.environ.get('ARCADE_UI_TEST_DIR', ROOT / 'build/ui-test'))
OUTPUT.mkdir(parents=True, exist_ok=True)
BINARY = Path(os.environ.get('ARCADE_TEST_BINARY', ROOT / 'build/arcade'))
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
def application(profile, name, *arguments, language="en_US.UTF-8"):
    log_path = OUTPUT / (name + ".log")
    env = os.environ | driver.environment() | {"ARCADE_DATA": str(profile), "LANG": language}
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
        card = driver.find(label="Chess", role="button", visible=True)[0]
        preview = driver.find(key=300, role="image", visible=True)[0]
        assert card['visible_width'] > 150 and card['visible_height'] > 180
        assert preview['visible_width'] > 150 and preview['visible_height'] > 100
        capture(child, "library")
        driver.press(label="Chess", role="button")
        driver.wait(label="Easy", role="button")
        back = driver.find(label="Back", role="button", visible=True)[0]
        assert UiDriver.center(back)[1] < 56, "Back must stay in the top navigation"
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
        driver.press(label="Hint", role="button")
        driver.wait(contains="Suggested move:", timeout=60)
        assert board() == position and record.read_bytes() == saved, "A hint changed the game"
        capture(child, "hint")
        driver.press(label="Review", role="button")
        driver.wait(label="First", role="button")
        driver.press(label="First", role="button")
        assert len(board()) == 32
        assert 8400 + square("e2") - 8010 in board()
        driver.press(label="Next", role="button")
        assert 8400 + square("e4") - 8010 in board()
        # Try an alternative Black reply. The saved computer game must stay
        # byte-for-byte intact, including after returning from the study.
        driver.press(key=square("e7"))
        driver.press(key=square("e5"))
        driver.wait(label="Latest", role="button")
        driver.press(label="Analysis", role="button")
        driver.wait(contains="Depth", timeout=90)
        assert driver.find(key=8922, visible=True), "The evaluation bar did not render"
        capture(child, "analysis")
        driver.press(label="Notation", role="button")
        driver.wait(label="Copy", role="button")
        pgn = driver.find(key=8963)[0]['value']
        assert '[Result "*"]' in pgn and '1. e4 e5' in pgn, pgn
        driver.press(label="Copy", role="button")
        # Read the real native clipboard on this private display.
        def copied(expected):
            result = subprocess.run(['xclip', '-selection', 'clipboard', '-target', 'UTF8_STRING', '-o'],
                                    capture_output=True, text=True, timeout=3)
            return result.returncode == 0 and result.stdout.strip() == expected
        wait(lambda: copied(pgn), 'PGN did not reach the native clipboard')
        driver.press(label="FEN", role="button")
        wait(lambda: driver.find(label='FEN', role='button')[0]['selected'], 'FEN format did not become selected')
        fen = driver.find(key=8963)[0]['value']
        assert fen == 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2', fen
        driver.press(label='Copy', role='button')
        wait(lambda: copied(fen), 'FEN did not reach the native clipboard')
        driver.wait_idle(frames=3)
        capture(child, "notation")
        driver.press(label="Back to board", role="button")
        # A selected piece's highlight must not replace the navigation tab.
        driver.press(key=square('b1'))
        driver.press(key=square('c3'))
        driver.press(key=square('c3'))
        driver.wait(label='Study', role='button')
        driver.press(label="Computer", role="button")
        driver.wait(label="Your move")
        assert board() == position and record.read_bytes() == saved, "Study overwrote the live game"
        driver.press(label="Flip board", role="button")
        assert board() != position, "Flip did not rotate the board"
        driver.press(label="Flip board", role="button")
        assert board() == position
        driver.press(label="Take back", role="button")
        driver.wait(label="Your move")
        assert record.read_text().endswith("moves="), "Take back did not undo the complete turn"
        assert 8400 + square("e2") - 8010 in board()
        driver.press(key=square("e2"))
        driver.press(key=square("e4"))
        wait(two_moves, "Computer did not reply after a takeback")
        driver.wait(label="Your move")
        position = board()
        saved = record.read_bytes()
        driver.press(label="Back", role="button")
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

    with application(profile, 'import', '--app', 'chess') as child:
        driver.wait(label='Your move')
        check_import(driver, record.read_bytes, lambda name: capture(child, name))

    # Black keeps the computer's opening move when taking back a turn.
    black_profile = profile / 'black'
    black_record = black_profile / 'games/inbe.chess/records/computer'
    with application(black_profile, 'black', '--app', 'chess'):
        driver.press(label='Easy', role='button')
        driver.press(label='Play Black', role='button')
        driver.press(label='Start', role='button')
        driver.wait(label='Your move')
        opening = black_record.read_bytes()
        opening_board = board()
        assert not driver.find(label='Take back', role='button')[0]['enabled']
        # Black's board is rotated: e7 is drawn on d2 and e5 on d4.
        driver.press(key=square('d2'))
        driver.press(key=square('d4'))
        driver.wait(label='Your move')
        wait(lambda: len(black_record.read_text().split('moves=', 1)[1].split()) == 3,
             'The computer did not answer Black')
        driver.press(label='Take back', role='button')
        driver.wait(label='Your move')
        assert black_record.read_bytes() == opening and board() == opening_board
        driver.press(label='New game', role='button')
        driver.press(label='Expert', role='button')
        driver.press(label='Play White', role='button')
        driver.press(label='Start', role='button')
        assert 'level=3;color=w;' in black_record.read_text()
        driver.press(key=square('e2'))
        driver.press(key=square('e4'))
        driver.wait(label='Your move', timeout=75)
        wait(lambda: len(black_record.read_text().split('moves=', 1)[1].split()) == 2,
             'Expert did not produce a legal reply')

    # New labels come from the game even when a legacy host has no such text.
    with application(profile / 'spanish', 'spanish', '--app', 'chess', language='es_ES.UTF-8') as child:
        driver.wait(label='Experto', role='button')
        driver.press(label='Estudio', role='button')
        driver.wait(label='Inicio', role='button')
        driver.press(label='Notación', role='button')
        driver.wait(label='Copiar', role='button')
        driver.wait(label='Copiar exporta la partida en PGN o esta posición en FEN.')
        capture(child, 'spanish-notation')

print("Arcade: Chess preview, moves, hints, study variations, analysis, PGN/FEN clipboard, flip, full-turn takebacks, PGN/FEN import and recovery, Black opening, Expert reply, persistence and private storage passed")
