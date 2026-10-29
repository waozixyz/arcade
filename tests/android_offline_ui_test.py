"""Check that the APK's collection opens Arcade's whole library offline.

The collection make android packs (build/android-assets) is opened by the
desktop host from a private folder, as the Android host opens it from the
APK's assets: no controller beside it and no reachable download origin, so
every game and the art must come from the collection itself."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

LEVEL_UPDATES = 'Download new levels when they come out?'

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--inbe-source', type=Path, required=True)
args = parser.parse_args()
assert int(os.environ['DISPLAY'].split(':')[-1].split('.')[0]) >= 400
assert os.environ['YUE_DESKTOP_RECOVERY'] == '0'
root = Path(__file__).resolve().parents[1]
assets = root / 'build/android-assets'
receipt = json.loads((assets / 'arcade.json').read_text())
assert receipt['id'] == 'inbe.arcade' and receipt['games'] == 'packed' and 'art' not in receipt
assert receipt['sha256'] == hashlib.sha256((assets / 'arcade.zx').read_bytes()).hexdigest()
sys.path.insert(0, str(args.inbe_source / 'tests'))
from ui_driver import UiDriver
output = root / 'build/android-offline-ui-test'
output.mkdir(parents=True, exist_ok=True)
driver = UiDriver(output / 'driver')

with tempfile.TemporaryDirectory(prefix='arcade-offline-') as temporary:
    install = Path(temporary) / 'app'
    install.mkdir()
    shutil.copy2(args.binary, install / 'arcade')
    for name in ('arcade.zx', 'arcade.json'):
        shutil.copyfile(assets / name, install / name)
    # The shared profile, which the APK also carries.
    shutil.copyfile(root / 'build/entity.zx', install / 'entity.zx')
    profile = Path(temporary) / 'profile'
    log_path = output / 'arcade.log'
    with log_path.open('w') as log:
        # Port 9 (discard) refuses connections: any download would fail.
        child = subprocess.Popen([str(install / 'arcade')], cwd=install,
                                 env=os.environ | driver.environment() |
                                 {'ARCADE_DATA': str(profile), 'ENTITY_DATA': str(profile / 'entity'),
                                  'LANG': 'en_US.UTF-8', 'ARCADE_PACKAGE_ORIGIN': 'http://127.0.0.1:9'},
                                 stdout=log, stderr=subprocess.STDOUT)
        driver.attach(child, log_path)
        try:
            for title in ('Shovey', 'Shovey Editor', 'Apfelwurm'):
                driver.wait(label=title, role='button', timeout=60)
            covers = [node for node in driver.find(role='image', visible=True)
                      if node['width'] >= 100 and node['height'] >= 140]
            assert len(covers) >= 2, 'The packed library art must draw without a download'
            if driver.find(label=LEVEL_UPDATES, role='text'):
                driver.press(label='Not now', role='button')
                driver.wait_gone(label=LEVEL_UPDATES, role='text')
            driver.press(label='Shovey', role='button')
            deadline = time.monotonic() + 30
            while True:
                assert not driver.find(label='Download', role='button'), 'A packed game must not ask to download'
                assert not driver.find(label='Try again', role='button'), 'A packed game must not download'
                if driver.find(label=LEVEL_UPDATES, role='text'):
                    driver.press(label='Not now', role='button')
                    driver.wait_gone(label=LEVEL_UPDATES, role='text')
                if [node for node in driver.tree() if str(node.get('label', '')).startswith('Level 1 / ')]:
                    break
                assert time.monotonic() < deadline, 'Shovey did not start from the packed collection'
                time.sleep(0.05)
            assert not list((profile / 'resources').rglob('*.zx')), 'Nothing may be downloaded'
        finally:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=10)
print('The Android collection opens every game and its art offline')
