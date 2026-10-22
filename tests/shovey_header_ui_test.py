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
                    for label in ('Levels', 'Help', 'Mute', 'Profile'):
                        control = driver.wait(label=label, role='button')
                        assert control['y'] < 16 and control['height'] >= 44, (label, control)
                    assert not driver.find(label='Settings', role='button')
                    assert not driver.find(key=49202), 'The native header must not cover the artwork'
                    covers = driver.find(role='image', visible=True)
                    assert any(image['y'] == 0 and image['height'] == height for image in covers), covers
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
                    driver.press(label='Back', role='button')
                    driver.wait(label='Play', role='button')
                driver.press(label='Levels', role='button')
                assert driver.wait(label='Back', role='button')['y'] < 16
                driver.press(label='Back', role='button')
                driver.wait(label='Play', role='button')
                driver.press(label='Profile', role='button')
                driver.wait(label='Intention', role='text')
                driver.press(label='Connect an account', role='button')
                driver.press(label='Create account', role='button')
                driver.wait(contains='Account connected on this device', timeout=30)
                driver.press(key=49001)
                driver.press(key=49001)
                driver.wait(label='Play', role='button')
                assert driver.wait(label='Dew', role='button')['y'] < 16
                driver.press(label='Dew', role='button')
                driver.wait(label='Add Dew with Monero', role='button')
                assert len(driver.find(label='Back', role='button', visible=True)) == 1
                assert not driver.find(label='Settings', role='button')
                driver.press(key=49001)
                driver.wait(label='Profile', role='text')
                driver.press(key=49001)
                driver.wait(label='Play', role='button')
                (output / 'receipt.json').write_text(json.dumps({
                    'passed': True, 'sizes': [[390, 844], [480, 820], [960, 600]],
                    'guide_pieces': 137, 'shared_entity_intention': True, 'shared_dew_route': True,
                    'screenshots': False, 'network': False,
                }, indent=2) + '\n')
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=10)
    print('Shovey: full-cover top controls, one Help row, 137 guide entries, shared Profile and Dew passed')


if __name__ == '__main__':
    main()
