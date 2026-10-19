"""Run the standalone Pushy app privately: the edition chooser, both
editions opening straight on their newest level with picture sprites,
independent saves, and the same level after a restart."""
import argparse
import contextlib
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
    output = root / 'build/pushy-standalone-ui-test'
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(args.inbe_source / 'tests'))
    from ui_driver import UiDriver
    driver = UiDriver(output / 'driver')

    @contextlib.contextmanager
    def application(profile, name):
        log_path = output / (name + '.log')
        with log_path.open('w') as log:
            child = subprocess.Popen([str(args.binary.resolve())], cwd=args.binary.resolve().parent,
                                     env=os.environ | driver.environment() |
                                     {'ARCADE_DATA': str(profile), 'LANG': 'en_US.UTF-8'},
                                     stdout=log, stderr=subprocess.STDOUT)
            driver.attach(child, log_path)
            try:
                driver.wait(label='Pushy Classic', role='button')
                driver.wait(label='Pushy Island', role='button')
                yield child
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=10)

    def move_until_saved(record):
        before = record.read_bytes() if record.exists() else b''
        for key in ('left', 'up', 'right', 'down'):
            driver.key(key)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if record.exists() and record.read_bytes() != before:
                    return record.read_bytes()
                time.sleep(.05)
        raise AssertionError(f'No move was saved to {record}')

    with tempfile.TemporaryDirectory(prefix='profile-', dir=output) as temporary:
        profile = Path(temporary)
        classic = profile / 'games/arcade.pushy/records/campaign'
        island = profile / 'games/arcade.pushy-island/records/campaign'
        with application(profile, 'play'):
            assert not driver.find(label='Arcade', role='text')
            driver.press(label='Pushy Classic', role='button')
            driver.wait(label='Level 1 / 175')
            assert not driver.find(label='Continue', role='button'), 'Classic must open straight on a level'
            assert driver.find(label='Pushy', role='image', visible=True), 'Pushy must be drawn as a picture'
            classic_saved = move_until_saved(classic)
            driver.press(label='Back', role='button')
            driver.press(label='Pushy Island', role='button')
            driver.wait(label='Island 1 / 175')
            assert not driver.find(label='Continue', role='button'), 'Island must open straight on a level'
            assert driver.find(label='Pushy', role='image', visible=True)
            island_saved = move_until_saved(island)
            assert classic.read_bytes() == classic_saved, 'Island changed the Classic save'
        with application(profile, 'restore'):
            driver.press(label='Pushy Island', role='button')
            driver.wait(label='Island 1 / 175')
            assert island.read_bytes() == island_saved, 'Reopening the newest island must keep its position'
            driver.press(label='Back', role='button')
            driver.press(label='Pushy Classic', role='button')
            driver.wait(label='Level 1 / 175')
            assert classic.read_bytes() == classic_saved
    print('Standalone Pushy: chooser, both editions opening on their newest level with sprites, and independent saves passed')


if __name__ == '__main__':
    main()
