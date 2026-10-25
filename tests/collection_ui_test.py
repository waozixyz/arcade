"""Exercise the real shared library and both unchanged games privately."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from PIL import Image



LEVEL_UPDATES = 'Download new levels when they come out?'

def answer_library_question(driver):
    """Keep the test's bundled levels when the library asks about updates."""
    driver.wait(label='Shovey', role='button', timeout=60)
    if driver.find(label=LEVEL_UPDATES, role='text'):
        driver.press(label='Not now', role='button')
        driver.wait_gone(label=LEVEL_UPDATES, role='text')



def answer_level_updates(driver, timeout=20):
    """An installed Shovey first asks once whether to download new levels;
    tests keep the levels it ships with. Returns once a level takes input
    or asks how to move."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if driver.find(label=LEVEL_UPDATES, role='text'):
            driver.press(label='Not now', role='button')
            driver.wait_gone(label=LEVEL_UPDATES, role='text')
            return
        if driver.find(label='How do you want to move?', role='text') or driver.find(label='Restart', role='button'):
            return
        time.sleep(0.05)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--inbe-source", type=Path, required=True)
    args = parser.parse_args()
    assert int(os.environ["DISPLAY"].split(":")[-1].split(".")[0]) >= 400
    assert os.environ["YUE_DESKTOP_RECOVERY"] == "0"
    root = Path(__file__).resolve().parents[1]
    output = root / "build/collection-ui-test"
    # The Classic heading counts its levels, which Shovey's level file lists.
    shovey = Path(subprocess.check_output([str(root / "scripts/ziran.sh"), "pkg", "path", "shovey"], text=True).strip())
    classic = len(json.loads((shovey / "levels/approved.json").read_text())["levels"])
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(args.inbe_source / "tests"))
    from ui_driver import UiDriver
    driver = UiDriver(output / "driver")

    @contextlib.contextmanager
    def application(profile, name, *arguments):
        log_path = output / (name + ".log")
        with log_path.open("w") as log:
            child = subprocess.Popen([str(args.binary.resolve()), *arguments], cwd=root,
                                     env=os.environ | driver.environment() |
                                     {"ARCADE_DATA": str(profile), "ENTITY_DATA": str(profile / "entity"),
                                      "LANG": "en_US.UTF-8"},
                                     stdout=log, stderr=subprocess.STDOUT)
            driver.attach(child, log_path)
            try:
                driver.tree()
                yield child
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=10)

    def wait(predicate, message):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if value := predicate():
                return value
            time.sleep(.05)
        raise driver._failure(message)

    def capture(child, name):
        window = subprocess.check_output(
            ["xdotool", "search", "--onlyvisible", "--pid", str(child.pid)], text=True, timeout=10).splitlines()[0]
        assert int(subprocess.check_output(["xdotool", "getwindowpid", window], text=True, timeout=10)) == child.pid
        subprocess.run(["import", "-window", window, str(output / (name + ".png"))], check=True, timeout=10)

    def grid(child, name):
        driver.wait_idle(frames=20)
        driver.wait(label="Arcade", role="text")
        assert not driver.find(label="Chess"), "Chess is temporarily disabled"
        assert not driver.find(label="Monkey"), "Monkey does not belong in Arcade"
        assert not driver.find(label="Next", role="button"), "Arcade must open on its app grid"
        classic_card = driver.wait(label="Shovey", role="button")
        editor_card = driver.wait(label="Shovey Editor", role="button")
        assert classic_card['y'] == editor_card['y'], "Apps must share a grid row"
        assert classic_card['x'] != editor_card['x']
        capture(child, name)
        with Image.open(output / (name + ".png")) as image:
            assert len(image.convert("RGB").getcolors(1000000) or []) > 100, "App icons were not painted"

    with tempfile.TemporaryDirectory(prefix="profile-", dir=output) as temporary:
        profile = Path(temporary)
        # Disabling an entry must leave a person's older Chess save untouched.
        chess = profile / "games/inbe.chess/records/computer"
        chess.parent.mkdir(parents=True)
        chess.write_bytes(b"existing private Chess save")
        # Active play stays on this device; account sync shares completions.
        record = profile / "games/arcade.shovey/records/local.campaign"

        def progress(data):
            # Unlocks, completion marks and the board in play.
            value = data.decode()
            assert value[:2] in ("C2", "C3", "C4", "C5")
            start = value.index("P")
            state = value[start:]
            assert state[:2] in ("P1", "P2", "P3")
            return value[:start], state[:32]

        with application(profile, "grid") as child:
            driver.wait(label="Shovey", role="button")
            answer_library_question(driver)
            grid(child, "apps-portrait")
            driver.press(label="Shovey", role="button")
            driver.wait(label=f"Level 1 / {classic}")
            answer_level_updates(driver)
            driver.wait(label="How do you want to move?", role="text")
            driver.press(label="Swipe and tap")
            driver.wait_gone(label="How do you want to move?", role="text")
            assert not driver.find(label="Play", role="button"), "Arcade must skip the second title screen"
            assert len(driver.find(label="Back", role="button", visible=True)) == 1
            capture(child, "classic-playing")
            for direction in ("left", "right", "up", "down"):
                driver.key(direction)
                driver.wait_idle(frames=5)
            saved = wait(lambda: record.read_bytes() if record.exists() else None, "Classic did not save")
            driver.press(label="Back", role="button")
            driver.wait(label="Shovey Editor", role="button")
            driver.press(label="Shovey Editor", role="button")
            # The editor opens on a blank board.
            driver.wait(label="New level", role="text")
            capture(child, "editor-open")
            driver.key("escape")
            driver.wait(label="Shovey Editor", role="button")
            window = subprocess.check_output(["xdotool", "search", "--onlyvisible", "--pid", str(child.pid)], text=True).splitlines()[0]
            subprocess.run(["xdotool", "windowsize", window, "900", "540"], check=True)
            grid(child, "apps-landscape")
        with application(profile, "restore", "--app", "arcade.shovey"):
            driver.wait(label=f"Level 1 / {classic}")
            assert progress(record.read_bytes()) == progress(saved), "Classic progress changed on restart"
        assert chess.read_bytes() == b"existing private Chess save"
        assert not (profile / "inbe.db").exists()
        refused = subprocess.run([str(args.binary.resolve()), "--app", "chess"], env=os.environ | {"ARCADE_DATA": str(profile)}, capture_output=True, timeout=10)
        assert refused.returncode == 1 and b"unknown game" in refused.stderr
    print("Arcade: app grid and icons, direct play/editor, Back, rotation and retained saves passed")


if __name__ == "__main__":
    main()
