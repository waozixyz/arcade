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

    def cover(child, name):
        driver.wait_idle(frames=20)
        assert not driver.find(label="Arcade", role="text"), "Library must have no heading"
        assert not driver.find(label="Chess"), "Chess is temporarily disabled"
        images = driver.find(role="image", visible=True)
        screen = driver.tree()[0]
        assert max(n["visible_width"] * n["visible_height"] for n in images) >= screen["width"] * screen["height"] * .95
        capture(child, name)
        with Image.open(output / (name + ".png")) as image:
            assert len(image.convert("RGB").getcolors(1000000) or []) > 1000, "Cover artwork was not painted"

    with tempfile.TemporaryDirectory(prefix="profile-", dir=output) as temporary:
        profile = Path(temporary)
        # Disabling an entry must leave a person's older Chess save untouched.
        chess = profile / "games/inbe.chess/records/computer"
        chess.parent.mkdir(parents=True)
        chess.write_bytes(b"existing private Chess save")
        record = profile / "games/arcade.shovey/records/campaign"
        with application(profile, "carousel") as child:
            driver.wait(label="Play", role="button")
            cover(child, "classic-portrait")
            driver.press(label="Next", role="button")
            driver.wait(label="Open", role="button")
            driver.wait(label="Editor", role="text")
            cover(child, "editor-portrait")
            driver.press(label="Previous", role="button")
            driver.key("right")
            driver.wait(label="Open", role="button")
            driver.key("left")
            driver.wait(label="Play", role="button")
            driver.drag((350, 400), (100, 400))
            driver.wait(label="Open", role="button")
            driver.pointer(240, 400, wheel=1)
            driver.wait(label="Play", role="button")
            driver.key("enter")
            driver.wait(label=f"Level 1 / {classic}")
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
            driver.wait(label="Play", role="button")
            driver.press(label="Next", role="button")
            driver.press(label="Open", role="button")
            driver.wait(label="Explore", role="button")
            capture(child, "editor-open")
            driver.key("escape")
            driver.wait(label="Open", role="button")
            # Keep the selected editor when returning from its screen.
            driver.wait(label="Editor", role="text")
            window = subprocess.check_output(["xdotool", "search", "--onlyvisible", "--pid", str(child.pid)], text=True).splitlines()[0]
            subprocess.run(["xdotool", "windowsize", window, "900", "540"], check=True)
            cover(child, "editor-landscape")
            driver.press(label="Previous", role="button")
            driver.wait(label="Play", role="button")
            cover(child, "classic-landscape")
        with application(profile, "restore", "--app", "arcade.shovey"):
            driver.wait(label=f"Level 1 / {classic}")
            assert record.read_bytes()[:210] == saved[:210], "Classic progress changed on restart"
        assert chess.read_bytes() == b"existing private Chess save"
        assert not (profile / "inbe.db").exists()
        refused = subprocess.run([str(args.binary.resolve()), "--app", "chess"], env=os.environ | {"ARCADE_DATA": str(profile)}, capture_output=True, timeout=10)
        assert refused.returncode == 1 and b"unknown game" in refused.stderr
    print("Arcade: full covers, arrows/swipe/wheel/Enter, direct play/editor, Back, rotation and retained saves passed")


if __name__ == "__main__":
    main()
