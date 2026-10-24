"""Check native Profile and cover navigation without touching owner data."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, action='append', required=True)
parser.add_argument('--inbe-source', type=Path, required=True)
args = parser.parse_args()
assert int(os.environ['DISPLAY'].split(':')[-1].split('.')[0]) >= 400
assert os.environ['YUE_DESKTOP_RECOVERY'] == '0'
sys.path.insert(0, str(args.inbe_source / 'tests'))
from ui_driver import UiDriver
LEVEL_UPDATES = 'Download new levels when they come out?'


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

output = Path(__file__).resolve().parents[1] / 'build/standalone-navigation-ui-test'
output.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='native-navigation-') as temporary:
    for binary in args.binary:
        profile_root = Path(temporary) / binary.name
        driver = UiDriver(output / binary.name / 'driver')
        log_path = output / (binary.name + '.log')
        with log_path.open('w') as log:
            child = subprocess.Popen([str(binary.resolve())], cwd=binary.resolve().parent,
                                     env=os.environ | driver.environment() |
                                     {'ARCADE_DATA': str(profile_root), 'LANG': 'en_US.UTF-8'},
                                     stdout=log, stderr=subprocess.STDOUT)
            driver.attach(child, log_path)
            try:
                driver.wait(label='Play', role='button')

                def toolbar():
                    screen = driver.tree()[0]
                    buttons = driver.find(label='Profile', role='button', visible=True)
                    assert len(buttons) == 1, buttons
                    button = buttons[0]
                    assert button['y'] <= 12 and button['width'] >= 44 and button['height'] >= 44
                    assert button['x'] >= screen['width'] - 112, 'Profile is not at the top right'
                    assert not driver.find(label='Settings', role='button', visible=True)

                def capture(name):
                    windows = subprocess.check_output(['xdotool', 'search', '--onlyvisible', '--pid', str(child.pid)], text=True).split()
                    assert len(windows) == 1
                    assert int(subprocess.check_output(['xdotool', 'getwindowpid', windows[0]], text=True)) == child.pid
                    subprocess.run(['import', '-window', windows[0], str(output / (binary.name + '-' + name + '.png'))], check=True)

                def profile():
                    toolbar()
                    driver.press(label='Profile', role='button')
                    driver.wait(label='Profile', role='text')
                    driver.wait(label='Account', role='text')
                    capture('profile')
                    driver.press(key=49001)
                    driver.wait(label='Play', role='button')

                # The library's covers carry Profile at the top right.
                toolbar()
                capture('home')
                profile()
                driver.press(label='Play', role='button')
                driver.wait(label='Restart', role='button')
                answer_level_updates(driver)
                if driver.find(label='How do you want to move?', role='text'):
                    driver.press(label='Swipe and tap')
                    driver.wait_gone(label='How do you want to move?', role='text')
                for direction in ('left', 'up', 'right', 'down'):
                    driver.key(direction)
                record = profile_root / 'games/arcade.shovey/records/campaign'
                driver.wait_idle(frames=5)
                before = record.read_bytes()
                # Play fills the screen; its one Back returns to the covers.
                assert not driver.find(label='Profile', role='button', visible=True)
                assert len(driver.find(label='Back', role='button', visible=True)) == 1
                capture('playing')
                driver.press(label='Back', role='button')
                driver.wait(label='Play', role='button')
                profile()
                assert record.read_bytes() == before, 'Native pages changed game progress'
                driver.press(label='Play', role='button')
                driver.wait(label='Restart', role='button')
                print(f'PASS: {binary.name}: top-right Profile on the covers, full-screen play, return navigation, retained save')
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=10)
