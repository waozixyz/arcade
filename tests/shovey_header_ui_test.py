"""Check Shovey's shared header, complete guide and native Entity routes.

Runs only on a private display with disposable account and game data. Uses
the widget tree, never screenshots. No network or account purchase is needed.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time



LEVEL_UPDATES = 'Download new levels when they come out?'

def answer_cover_question(driver):
    """Standalone Arcade and Shovey ask once on their covers whether games
    download new levels; tests keep the levels they ship with. The question
    shows in the covers' first frame."""
    driver.wait(label='Play', role='button', timeout=60)
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
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--inbe-source', type=Path, required=True)
    args = parser.parse_args()
    assert int(os.environ['DISPLAY'].split(':')[-1].split('.')[0]) >= 400
    assert os.environ['YUE_DESKTOP_RECOVERY'] == '0'
    root = Path(__file__).resolve().parents[1]
    output = root / 'build/shovey-header-ui-test'
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(args.inbe_source / 'tests'))
    from ui_driver import UiDriver

    with tempfile.TemporaryDirectory(dir=output) as temporary:
        data = Path(temporary)
        driver = UiDriver(data / 'driver')
        # Block network transport for the disposable account's balance read.
        env = os.environ | driver.environment() | {
            'ARCADE_DATA': str(data / 'profile'), 'LANG': 'en_US.UTF-8',
            'XDG_DATA_HOME': str(data / 'shared'),
            'http_proxy': 'http://127.0.0.1:9', 'https_proxy': 'http://127.0.0.1:9',
            'ALL_PROXY': 'http://127.0.0.1:9', 'NO_PROXY': '', 'no_proxy': '',
        }
        log_path = output / 'app.log'
        with log_path.open('w') as log:
            child = subprocess.Popen([str(args.binary.resolve())], cwd=args.binary.resolve().parent,
                                     env=env, stdout=log, stderr=subprocess.STDOUT)
            driver.attach(child, log_path)
            try:
                driver.wait(label='Play', role='button')
                windows = subprocess.check_output(
                    ['xdotool', 'search', '--onlyvisible', '--pid', str(child.pid)], text=True).split()
                assert len(windows) == 1
                window = windows[0]
                assert subprocess.check_output(['xdotool', 'getwindowpid', window], text=True).strip() == str(child.pid)
                for width, height in ((390, 844), (480, 820), (960, 600)):
                    subprocess.run(['xdotool', 'windowsize', '--sync', window, str(width), str(height)], check=True)
                    deadline = time.monotonic() + 5
                    while driver.tree()[0]['width'] != width:
                        assert time.monotonic() < deadline
                        time.sleep(.03)
                    # The covers keep only Profile over the full artwork.
                    profile = driver.wait(label='Profile', role='button')
                    assert profile['y'] < 16 and profile['height'] >= 44, profile
                    assert not driver.find(label='Settings', role='button')
                    assert not driver.find(key=49202), 'The native header must not cover the artwork'
                    covers = driver.find(role='image', visible=True)
                    assert any(image['y'] == 0 and image['height'] == height for image in covers), covers
                    # Play opens the level directly, with the game's own header.
                    answer_cover_question(driver)
                    driver.press(label='Play', role='button')
                    driver.wait(label='Restart', role='button')
                    answer_level_updates(driver)
                    if driver.find(label='How do you want to move?', role='text'):
                        driver.press(label='Swipe and tap')
                        driver.wait_gone(label='How do you want to move?', role='text')
                    for label in ('Back', 'Levels', 'Help', 'Mute'):
                        control = driver.wait(label=label, role='button')
                        assert control['y'] < 16 and control['height'] >= 44, (label, control)
                    assert not driver.find(label='Profile', role='button', visible=True), 'Play fills the screen'
                    driver.press(label='Help', role='button')
                    header = driver.wait(label='Help', role='text')
                    back = driver.wait(label='Back', role='button')
                    assert header['y'] < 16 and back['y'] < 16
                    assert len(driver.find(label='Back', role='button', visible=True)) == 1
                    for label in ('Profile', 'Restart', 'Levels', 'Mute', 'Settings'):
                        assert not driver.find(label=label, role='button', visible=True), label
                    captions = [node for node in driver.tree() if node['kind'] == 'text' and 45000 <= node['key'] < 45200]
                    assert len(captions) == 137, len(captions)
                    labels = {node['label'] for node in captions}
                    assert {'Abyss', 'Duck', 'Turtle', 'Crab', 'Goldfish', 'Koi', 'Minnow',
                            'Cherry', 'Orange portal', 'Bomb crate', 'Tree stump', 'Mossy timber wall'} <= labels, labels
                    for _ in range(12):
                        driver.pointer(width / 2, height / 2, wheel=-200)
                        if driver.find(label='Tree stump', role='text', visible=True):
                            break
                    driver.wait(label='Tree stump', role='text')
                    # Back closes the guide, then returns from the level to the covers.
                    driver.press(label='Back', role='button')
                    driver.wait(label='Restart', role='button')
                    driver.press(label='Back', role='button')
                    driver.wait(label='Play', role='button')
                answer_cover_question(driver)
                driver.press(label='Play', role='button')
                driver.press(label='Levels', role='button')
                assert driver.wait(label='Back', role='button')['y'] < 16
                driver.press(label='Back', role='button')
                driver.wait(label='Restart', role='button')
                driver.press(label='Back', role='button')
                driver.wait(label='Play', role='button')
                driver.press(label='Profile', role='button')
                driver.wait(label='Not signed in', role='text')
                assert not driver.find(label='Intention', role='text')
                assert not driver.find(label='Name', role='text')
                driver.press(label='Create account', role='button')
                driver.wait(label='Account connected', role='text', timeout=30)
                driver.wait(label='Dew balance', role='text')
                driver.press(key=49001)
                driver.wait(label='Play', role='button')
                assert not driver.find(label='Dew', role='button')
                driver.press(label='Profile', role='button')
                driver.wait(label='Dew balance', role='text')
                assert not driver.find(label='Intention', role='text')
                assert not driver.find(label='Name', role='text')
                assert not driver.find(label='Settings', role='button')
                driver.press(key=49001)
                driver.wait(label='Play', role='button')
                (output / 'receipt.json').write_text(json.dumps({
                    'passed': True, 'sizes': [[390, 844], [480, 820], [960, 600]],
                    'guide_pieces': 137, 'game_identity_fields_hidden': True, 'inline_dew_balance': True,
                    'screenshots': False, 'network': False,
                }, indent=2) + '\n')
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=10)
    print('Shovey: Profile over the covers, game header in play, one Help row, 137 guide entries, shared Profile and inline Dew passed')


if __name__ == '__main__':
    main()
