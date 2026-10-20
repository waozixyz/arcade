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
    classic = len(json.loads((shovey / "levels/classic.json").read_text())["levels"])
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
                                     {"ARCADE_DATA": str(profile), "LANG": "en_US.UTF-8"},
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

    def open_card(name, index):
        cards = driver.find(label=name, role="button", visible=True)
        if cards:
            driver.press(key=cards[0]["key"])
        else:
            # The controller's card actions carry distinct stable widget keys.
            driver.press(key=103 + index * 16)

    with tempfile.TemporaryDirectory(prefix="profile-", dir=output) as temporary:
        profile = Path(temporary)
        record = profile / "games/inbe.chess/records/computer"
        with application(profile, "library") as child:
            driver.wait(label="Arcade", role="text")
            driver.wait(label="Chess", role="image")
            options = driver.find(label="App options", role="button", visible=True)
            assert len(options) == 2 and all(item['visible_height'] <= 38 for item in options)
            assert not driver.find(label="App actions"), 'Old dropdown must not return'
            driver.press(key=options[0]['key'])
            driver.wait(label="Pin")
            capture(child, "library-menu")
            driver.press(label="Pin")
            driver.press(key=options[0]['key'])
            driver.wait(label="Unpin")
            driver.key('escape')
            assert not driver.find(label="Updated"), 'Applied actions must not leave a status banner'
            capture(child, "library")
            open_card("Chess", 0)
            driver.wait(label="Easy", role="button")
            driver.press(label="Easy", role="button")
            driver.press(label="Play White", role="button")
            driver.press(label="Start", role="button")
            driver.wait(label="Your move")
            driver.press(key=8062)  # e2
            driver.press(key=8046)  # e4
            saved = wait(lambda: record.read_bytes() if record.exists() and
                         len(record.read_text().split("moves=", 1)[-1].split()) == 2 else None,
                         "Nested Chess did not save a move and computer reply")
            capture(child, "chess")
            driver.press(label="Back", role="button")
            driver.wait(label="Arcade", role="text")
            driver.press(key=options[0]['key'])
            driver.press(label="Uninstall")
            assert record.read_bytes() == saved
            driver.press(key=options[0]['key'])
            driver.press(label="Install")
            assert record.read_bytes() == saved
            open_card("Chess", 0)
            driver.wait(label="Your move")
            assert record.read_bytes() == saved, "Returning through the collection changed the game"
        with application(profile, "chess-restore", "--app", "inbe.chess"):
            driver.wait(label="Your move")
            assert record.read_bytes() == saved, "The unchanged Chess record did not survive restart"
        with application(profile, "shovey", "--app", "arcade.shovey") as child:
            driver.wait(label=f"Level 1 / {classic}")
            driver.wait(label="Shovey", role="image")
            assert not driver.find(label="Back", role="button"), "Shovey must own all of its chrome"
            capture(child, "shovey")
            driver.key("escape")
            driver.wait(label="Shovey Classic", role="button")
            driver.wait(label="Shovey Island", role="button")
            driver.wait(label="Shovey Editor", role="button")
            driver.key("escape")
            driver.wait(label="Arcade", role="text")
        assert not (profile / "inbe.db").exists(), "standalone Arcade opened an Inbe profile"
        assert record.exists(), "standalone Arcade lost its private game profile"
    print("Shared Arcade library: previews, Chess play/save/Back/restart and nested Shovey passed")


if __name__ == "__main__":
    main()
