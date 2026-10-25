"""Resume one shared progress fixture on the USB Moto in an isolated APK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--apk', type=Path, required=True)
parser.add_argument('--breeze', type=Path, required=True)
args = parser.parse_args()
sys.path.insert(0, str(args.breeze.resolve() / 'tests'))
import android_library_device as transport

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
transport.OUTPUT = root / 'backup/shared-progress-moto'
transport.PACKAGE = 'xyz.waozi.shovey.verification'
transport.ACTIVITY = transport.PACKAGE + '/xyz.waozi.arcade.ArcadeActivity'
transport.TRANSFER = '/data/local/tmp/shovey-progress-test'
transport.OUTPUT.mkdir(parents=True, exist_ok=True)

class Phone(transport.Device):
    def start(self):
        result = self.shell('am', 'start', '-W', '-n', transport.ACTIVITY)
        assert 'Error:' not in result, result
        self.owns_foreground()

    def write(self, name, text, destination):
        local = transport.OUTPUT / name
        local.write_text(text)
        self.put_private(local, destination)
        self.private('chmod', '600', destination)

    def restore(self):
        if not self.state.get('isolated'):
            return
        self.stop()
        assert self.exists('files/.progress-test'), 'Refusing to remove unmarked data'
        self.private('rm', '-rf', 'files')
        if self.state.get('preserved'):
            self.private('mv', 'files.progress-preserved', 'files')
        self.shell('rm', '-rf', transport.TRANSFER)
        self.state.update(isolated=False, restored=True)
        self.save()

phone = Phone()
apk = args.apk.resolve(strict=True)
sdk = Path(os.environ.get('ANDROID_HOME') or Path.home() / 'Android/Sdk')
aapt = sorted(sdk.glob('build-tools/*/aapt'))[-1]
manifest = subprocess.check_output([str(aapt), 'dump', 'badging', str(apk)], text=True)
assert re.search(r"^package: name='([^']+)'", manifest, re.M)[1] == transport.PACKAGE
assert 'application-debuggable' in manifest
assert not phone.state.get('isolated'), 'Restore the previous test first'
assert not phone.exists('files.progress-preserved'), 'Preserved data already exists'
foreground = phone.foreground()
assert ' xyz.waozi.shovey/' not in foreground, 'The regular Shovey app is foreground'
phone.stop()
phone.adb('install', '-r', '-t', apk, timeout=180)
phone.state = dict(originating_chat='-1000000002', task='codex-projects-library-bookshelf',
                   foreground_before=foreground, apk_sha256=hashlib.sha256(apk.read_bytes()).hexdigest(),
                   isolated=True, preserved=False)
phone.save()
try:
    if phone.exists('files'):
        phone.private('mv', 'files', 'files.progress-preserved')
        phone.state['preserved'] = True
        phone.save()
    identifier = 'fd65a3d7ac3d5ceb2d4d96cc5224a740'
    records = 'files/entity/records/local'
    game = records + '/game-progress/' + identifier + '.json'
    phone.private('mkdir', '-p', 'files/kryon-test-driver', records + '/game-progress')
    phone.private('touch', 'files/.progress-test')
    stamp = int(time.time())
    phone.write('state', 'game-progress\nsince 0\n', records + '/state')
    phone.write('game-progress.index', f'{identifier} {stamp} {stamp * 1000} -- entity.game-progress.v1\n', records + '/game-progress.index')
    phone.write('campaign.json', json.dumps(dict(game='shovey.classic', unlocked=40,
                completed='1' * 39, state='', updated_at=stamp)), game)
    for attempt in ('first', 'restart'):
        phone.start()
        driver = transport.AndroidDriver(phone)
        driver.wait(label='Play', role='button', timeout=60)
        answer_cover_question(driver)
        driver.press(label='Play', role='button', timeout=60)
        deadline = time.monotonic() + 60
        while not driver.find(contains='Level 40 / ', role='text'):
            if driver.find(label='Download new levels when they come out?', role='text'):
                driver.press(label='Not now', role='button')
            assert time.monotonic() < deadline, driver.text()
        driver.wait_idle(frames=5)
        record = json.loads(phone.private('cat', game))
        assert record['unlocked'] == 40 and record['completed'] == '1' * 39, record
        assert record['state'].startswith('M1'), record
        assert not phone.exists('files/games/arcade.shovey/records/campaign'), 'Duplicate wrapper campaign'
        assert len(phone.private('ls', records + '/game-progress').splitlines()) == 1
        phone.capture('level-40-' + attempt)
        phone.stop()
    phone.state['result'] = 'passed'
    phone.save()
    print('Moto standalone Shovey resumes level 40 from one canonical provider record, keeps completion marks and survives a cold restart')
finally:
    phone.restore()
