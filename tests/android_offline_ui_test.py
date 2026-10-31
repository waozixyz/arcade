"""Exercise APK assets through generic Apps install, open and offline cache."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'scripts'))
from android_catalog import verify_assets
from collection_ui_test import package_server, answer_library_question, answer_level_updates

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--inbe-source', type=Path, required=True)
args = parser.parse_args()
assert int(os.environ['DISPLAY'].split(':')[-1].split('.')[0]) >= 400
assert os.environ['YUE_DESKTOP_RECOVERY'] == '0'
assets = root / 'build/android-assets'
metadata = verify_assets({p.name: p.read_bytes() for p in assets.iterdir() if p.is_file()} |
                         {'entity.zx': (root / 'build/entity.zx').read_bytes()})
entries = {entry['expected_id']: entry for entry in metadata['children']}
sys.path.insert(0, str(args.inbe_source / 'tests'))
from ui_driver import UiDriver
output = root / 'work/android-offline-ui-test'
output.mkdir(parents=True, exist_ok=True)
driver = UiDriver(output / 'driver')

with tempfile.TemporaryDirectory(prefix='host-', dir=output) as temporary, package_server(root) as (origin, server):
    install = Path(temporary) / 'app'
    install.mkdir()
    shutil.copy2(args.binary, install / 'arcade')
    for name in ('arcade.zx', 'arcade.json', 'apps.zx'):
        shutil.copyfile(assets / name, install / name)
    shutil.copyfile(root / 'build/entity.zx', install / 'entity.zx')
    profile = Path(temporary) / 'profile'
    retained = profile / 'games/inbe.chess/records/computer'
    retained.parent.mkdir(parents=True)
    retained.write_bytes(b'existing private save')
    record = profile / 'games/arcade.shovey/records/local.campaign'

    @contextlib.contextmanager
    def application(name):
        log_path = output / (name + '.log')
        with log_path.open('w') as log:
            child = subprocess.Popen([str(install / 'arcade')], cwd=install,
                env=os.environ | driver.environment() |
                {'ARCADE_DATA': str(profile), 'ENTITY_DATA': str(profile / 'entity'),
                 'LANG': 'en_US.UTF-8', 'ARCADE_PACKAGE_ORIGIN': origin},
                stdout=log, stderr=subprocess.STDOUT)
            driver.attach(child, log_path)
            try:
                yield child
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=10)

    def download(label='Download'):
        driver.wait(label=label, role='button', timeout=60)
        action = max(driver.find(label=label, role='button', visible=True), key=lambda node: node['width'])
        driver.press(key=action['key'], role='button')

    def play():
        answer_level_updates(driver)
        if driver.find(label='How do you want to move?', role='text'):
            driver.press(label='Swipe and tap')
        driver.wait(label='Restart', role='button', timeout=60)
        assert not driver.find(label='Download', role='button')

    with application('install'):
        answer_library_question(driver)
        games = {entry['sha256'] for entry in metadata['children']}
        assert not games & set(server['requests']), 'No game before download consent'
        driver.press(label='Shovey Editor', role='button')
        driver.wait(label='Cancel', role='button')
        driver.press(label='Cancel', role='button')
        assert not games & set(server['requests']), 'Cancel must download nothing'
        driver.press(label='Shovey Editor', role='button')
        server['corrupt_shovey'] = True
        download()
        driver.wait(label='Try again', role='button', timeout=60)
        assert not driver.find(label='New level', role='text'), 'Corrupt dependency must not open'
        server['corrupt_shovey'] = False
        download('Try again')
        driver.wait(label='New level', role='text', timeout=60)
        assert server['requests'].count(entries['shovey']['sha256']) == 2
        assert server['requests'].count(entries['shovey-editor']['sha256']) == 1
        driver.key('escape')
        driver.wait(label='Shovey', role='button')
        driver.press(label='Shovey', role='button')
        play()
        driver.key('right')
        deadline = time.monotonic() + 20
        while not record.exists() and time.monotonic() < deadline:
            driver.wait_idle(frames=5)
        assert record.exists(), 'Game must persist progress'
        driver.press(label='Back', role='button')
        driver.wait(label='Shovey', role='button')
        driver.press(label='Apfelwurm', role='button')
        download()
        driver.wait(label='Play', role='button', timeout=60)
        driver.key('escape')
        driver.wait(label='Shovey', role='button')
        driver.press(label='Profile', role='button')
        driver.wait(label='Account', role='text')
        driver.press(label='Leaderboard', role='button')
        driver.wait(label='Apfelwurm', role='button')
        driver.press(label='Apfelwurm', role='button')
        # The profile stays usable with its optional game sheets omitted.
        driver.wait(label='Back', role='button')
        driver.press(label='Back', role='button')
        driver.wait(label='Account', role='text')
        driver.press(label='Back', role='button')
        driver.key('escape')
        driver.wait(label='Node connection', role='button')
        driver.press(label='Node connection', role='button')
        driver.wait(label='Stay offline', role='button')
        driver.press(label='Stay offline', role='button')
        driver.wait(label='Shovey', role='button')
    saved = record.read_bytes()
    for name in ('shovey', 'shovey-editor', 'wurm'):
        entry = entries[name]
        cached = profile / 'resources/downloads' / (entry['sha256'] + '.zx')
        assert hashlib.sha256(cached.read_bytes()).hexdigest() == entry['sha256']
    assert metadata['art']['sha256'] in server['requests'], 'Art must download separately'
    requested = list(server['requests'])
    server['offline'] = True
    with application('offline'):
        answer_library_question(driver)
        driver.press(label='Shovey', role='button')
        play()
        driver.press(label='Back', role='button')
        driver.wait(label='Shovey Editor', role='button')
        driver.press(label='Shovey Editor', role='button')
        driver.wait(label='New level', role='text', timeout=60)
        driver.key('escape')
        driver.wait(label='Apfelwurm', role='button')
        driver.press(label='Apfelwurm', role='button')
        driver.wait(label='Play', role='button', timeout=60)
    assert server['requests'] == requested, 'Installed apps/art must reopen offline without requests'
    assert record.read_bytes() == saved, 'Offline restart must preserve saved progress'
    assert retained.read_bytes() == b'existing private save'
print('Android catalog: consent, dependency verification/retry, install/open, cached offline and retained saves passed')
