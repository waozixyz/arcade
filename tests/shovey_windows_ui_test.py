"""Run the unpacked Windows download of standalone Shovey under Wine on a
private display: the title screen, Classic, sound, a saved move, Back, and the
saved game after a restart."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time



def wait_level_one(driver, classic_levels):
    """Level 1 of the campaign. The live campaign on the server may already
    hold levels published after this checkout, so it is never shorter."""
    label = driver.wait(contains='Level 1 / ', role='text')['label']
    assert label.startswith('Level 1 / ') and int(label.rsplit(' ', 1)[1]) >= classic_levels, label

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--program', type=Path, required=True, help='shovey.exe in the unpacked download')
    parser.add_argument('--inbe-source', type=Path, required=True)
    args = parser.parse_args()
    assert int(os.environ['DISPLAY'].split(':')[-1].split('.')[0]) >= 400
    root = Path(__file__).resolve().parents[1]
    output = root / 'build/shovey-windows-ui-test'
    shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True)
    shovey = Path(subprocess.check_output([str(root / 'scripts/ziran.sh'), 'pkg', 'path', 'shovey'], text=True).strip())
    classic_levels = len(json.loads((shovey / 'levels/approved.json').read_text())['levels'])
    sys.path.insert(0, str(args.inbe_source / 'tests'))
    from ui_driver import UiDriver
    driver = UiDriver(output / 'driver')
    environment = {**os.environ, 'WINEDEBUG': '-all', 'LANG': 'en_US.UTF-8'}
    prefix = Path(environment.setdefault('WINEPREFIX', str(output / 'prefix')))
    subprocess.run(['wineboot', '--init'], env=environment, check=True)
    # Wine reports Unix mount points as reparse points, which private storage
    # refuses as links, so saves live on the prefix's own drive C:. The
    # driver's files cross through Z:, Wine's view of the Unix root.
    saves = prefix / 'drive_c/shovey-windows-ui-test'
    shutil.rmtree(saves, ignore_errors=True)
    profile = saves / 'profile'
    profile.mkdir(parents=True)
    environment.update(ARCADE_DATA='C:/shovey-windows-ui-test/profile', ENTITY_DATA='C:/shovey-windows-ui-test/entity',
                       KRYON_TEST_DRIVER='Z:' + str(driver.directory.resolve()))
    program = args.program.resolve()

    @contextlib.contextmanager
    def application(name):
        log_path = output / (name + '.log')
        with log_path.open('w') as log:
            child = subprocess.Popen(['wine', str(program)], cwd=program.parent, env=environment,
                                     stdout=log, stderr=subprocess.STDOUT)
            driver.attach(child, log_path)
            try:
                # A new Wine prefix takes a while before the first frame, so
                # the first reply may come long after the usual 15 seconds.
                driver.send('status', timeout=180)
                driver.wait(timeout=180, label='Play', role='button')
                yield child
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=30)
                subprocess.run(['wineserver', '-k'], env=environment, check=False)

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

    classic = profile / 'games/arcade.shovey/records/campaign'
    with application('play'):
        driver.press(label='Play', role='button')
        wait_level_one(driver, classic_levels)
        # The first level asks how to move; until then it takes every key.
        driver.press(label='Swipe and tap')
        driver.wait_gone(label='How do you want to move?', role='text')
        # Entering play saves the untouched campaign.
        deadline = time.monotonic() + 10
        while not classic.exists() and time.monotonic() < deadline:
            time.sleep(.05)
        fresh = classic.read_bytes()
        driver.press(label='Mute', role='button')
        driver.wait(label='Unmute', role='button')
        assert (profile / 'games/arcade.shovey-player/records/sound').read_text() == 'muted'
        driver.press(label='Unmute', role='button')
        driver.wait(label='Mute', role='button')
        assert move_until_saved(classic) != fresh
        driver.key('escape')
        driver.wait(label='Play', role='button')
    with application('restart'):
        driver.press(label='Play', role='button')
        wait_level_one(driver, classic_levels)
        assert classic.read_bytes() != fresh, 'The move was lost across a restart'
    print('Windows Shovey under Wine: title, Classic, sound, saved move, Back and restart passed')


if __name__ == '__main__':
    main()
