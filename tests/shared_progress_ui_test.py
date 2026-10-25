"""The real standalone game resumes its canonical account-provider record."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--breeze', type=Path, required=True)
args = parser.parse_args()
assert int(os.environ['DISPLAY'].split(':')[-1].split('.')[0]) >= 400
assert os.environ['YUE_DESKTOP_RECOVERY'] == '0'
sys.path.insert(0, str(args.breeze / 'tests'))
from ui_driver import UiDriver

LEVEL_UPDATES = 'Download new levels when they come out?'

def answer_cover_question(driver):
    """Standalone Arcade and Shovey ask once on their covers whether games
    download new levels; tests keep the levels they ship with. The question
    shows in the covers' first frame."""
    driver.wait(label='Play', role='button', timeout=60)
    if driver.find(label=LEVEL_UPDATES, role='text'):
        driver.press(label='Not now', role='button')
        driver.wait_gone(label=LEVEL_UPDATES, role='text')


root = Path(__file__).resolve().parents[1]
output = root / 'build/shared-progress-ui-test'
output.mkdir(parents=True, exist_ok=True)
identifier = 'fd65a3d7ac3d5ceb2d4d96cc5224a740'
driver = UiDriver(output / 'driver')
with tempfile.TemporaryDirectory(prefix='shovey-account-progress-') as directory:
    profile = Path(directory)
    records = profile / 'entity/records/local'
    game = records / 'game-progress' / (identifier + '.json')
    game.parent.mkdir(parents=True)
    document = dict(game='shovey.classic', unlocked=40, completed='1' * 39, state='', updated_at=int(time.time()))
    game.write_text(json.dumps(document))
    (records / 'state').write_text('game-progress\nsince 0\n')
    (records / 'game-progress.index').write_text(f'{identifier} {document["updated_at"]} {document["updated_at"] * 1000} -- entity.game-progress.v1\n')
    for path in [profile / 'entity', *(profile / 'entity').rglob('*')]:
        path.chmod(0o700 if path.is_dir() else 0o600)

    for attempt in ('first', 'restart'):
        with (output / (attempt + '.log')).open('w') as log:
            child = subprocess.Popen([str(args.binary.resolve())], cwd=args.binary.resolve().parent,
                                     env=os.environ | driver.environment() | {'ARCADE_DATA': str(profile), 'LANG': 'en_US.UTF-8'},
                                     stdout=log, stderr=subprocess.STDOUT)
            driver.attach(child, output / (attempt + '.log'))
            try:
                answer_cover_question(driver)
                driver.press(label='Play', role='button')
                end = time.monotonic() + 30
                while True:
                    if driver.find(contains='Level 40 / ', role='text'):
                        break
                    if driver.find(label='Download new levels when they come out?', role='text'):
                        driver.press(label='Not now', role='button')
                    assert time.monotonic() < end, driver.text()
                    time.sleep(.05)
                driver.wait_idle(frames=5)
                stored = json.loads(game.read_text())
                assert stored['unlocked'] == 40 and stored['completed'] == '1' * 39, stored
                assert stored['state'].startswith('M1'), stored
                assert len(list(game.parent.glob('*.json'))) == 1
                assert not (profile / 'games/arcade.shovey/records/campaign').exists(), 'Duplicate wrapper campaign created'
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=10)
print('Standalone Shovey resumes level 40 from one shared account-provider record, preserves completion marks and survives a cold restart')
