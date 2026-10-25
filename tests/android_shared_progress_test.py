"""Verify completion-only progress on the USB Moto in an isolated APK.

The default full case covers real swipe motion, device-local board persistence,
read-only account progress across movement/restart, earned completion and logout
isolation. Startup/account cases are diagnostics, not substitutes for the full
case. Supply the exact approved campaign and an offline throwaway account folder;
never supply owner keys. Existing verification-profile files are preserved.
"""
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
parser.add_argument('--campaign', type=Path, required=True)
parser.add_argument('--test-account', type=Path, required=True)
parser.add_argument('--output', type=Path)
parser.add_argument('--case', choices=('all', 'startup', 'account'), default='all')
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
transport.OUTPUT = args.output or root / 'backup/shared-progress-moto'
transport.PACKAGE = 'xyz.waozi.shovey.verification'
transport.ACTIVITY = transport.PACKAGE + '/xyz.waozi.arcade.ArcadeActivity'
transport.TRANSFER = '/data/local/tmp/shovey-progress-test'
transport.OUTPUT.mkdir(parents=True, exist_ok=True)

class Phone(transport.Device):
    def owns_foreground(self):
        # Test-driver file input does not count as Android user activity.
        # Wake only the USB test device; keep its timeout setting intact.
        if time.monotonic() - getattr(self, '_last_wake', 0) > 10:
            self.shell('input', 'keyevent', 'KEYCODE_WAKEUP')
            self._last_wake = time.monotonic()
        super().owns_foreground()

    def start(self):
        self.shell('input', 'keyevent', 'KEYCODE_WAKEUP')
        self.shell('wm', 'dismiss-keyguard', check=False)
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
phone.state = dict(originating_chat='361338016', task='78530008ff5f508081150dec7522f477464f',
                   foreground_before=foreground, apk_sha256=hashlib.sha256(apk.read_bytes()).hexdigest(),
                   isolated=True, preserved=False)
phone.save()
try:
    if phone.exists('files'):
        phone.private('mv', 'files', 'files.progress-preserved')
        phone.state['preserved'] = True
        phone.save()
    identifier = 'fd65a3d7ac3d5ceb2d4d96cc5224a740'
    local_campaign = None
    route = json.loads(args.campaign.read_text())['levels'][0]['solution']
    timings = []

    def seed(unlocked, completed, account=False):
        phone.stop()
        assert phone.exists('files/.progress-test') or not phone.exists('files')
        if phone.exists('files'):
            phone.private('rm', '-rf', 'files')
        phone.private('mkdir', '-p', 'files/kryon-test-driver', 'files/entity')
        phone.private('touch', 'files/.progress-test')
        owner = 'local'
        if account:
            profile = json.loads((args.test_account / 'entity.json').read_text())
            owner = profile['owner_id']
            for name in ('account.key', 'entity.json'):
                phone.put_private(args.test_account / name, 'files/entity/' + name)
        records = 'files/entity/records/' + owner
        phone.private('mkdir', '-p', records + '/game-progress')
        stamp = int(time.time())
        phone.write('state', 'game-progress\nsince 0\n', records + '/state')
        phone.write('game-progress.index', f'{identifier} {stamp} {stamp * 1000} -- entity.game-progress.v1\n', records + '/game-progress.index')
        game = records + '/game-progress/' + identifier + '.json'
        phone.write('campaign.json', json.dumps(dict(game='shovey.classic', unlocked=unlocked,
                    completed=completed, updated_at=stamp)), game)
        return game

    def enter(level):
        phone.start()
        driver = transport.AndroidDriver(phone)
        answer_cover_question(driver)
        driver.press(label='Play', role='button', timeout=60)
        driver.wait(contains=f'Level {level} / ', role='text', timeout=60)
        if driver.find(label='How do you want to move?', role='text'):
            driver.press(label='Swipe and tap', role='button')
        driver.wait(label='Restart', role='button')
        return driver

    def campaign_path():
        paths = phone.private('find', 'files/games', '-name', 'local.campaign').splitlines()
        assert len(paths) == 1, paths
        return paths[0]

    def player(driver):
        node = driver.wait(label='Shovey', role='image')
        return tuple(node[field] for field in ('x', 'y', 'width'))

    def step(driver, direction):
        before = phone.private('cat', campaign_path())
        driver.key(('left', 'up', 'right', 'down')[int(direction)])
        # Input is handled by the real frame and commits its local campaign.
        deadline = time.monotonic() + 10
        while phone.private('cat', campaign_path()) == before:
            assert time.monotonic() < deadline, 'Direction did not update the device-local campaign'
            time.sleep(.05)

    if args.case in ('all', 'startup'):
        game = seed(40, '1' * 39)
        driver = enter(40)
        provider_before = phone.private('cat', game)
        local_campaign = campaign_path()
        first_local = phone.private('cat', local_campaign)
        phone.capture('level-40-initial')
        # Android's actual input path, independently of the widget driver.
        before = player(driver)
        x, y, cell = before
        start = time.monotonic()
        phone.shell('input', 'swipe', round(x + cell / 2), round(y + cell / 2),
                    round(x + cell / 2 - cell * 2), round(y + cell / 2), 150)
        deadline = time.monotonic() + 10
        while player(driver) == before:
            assert time.monotonic() < deadline, 'Real Android swipe did not move the player'
        timings.append(dict(input='Android swipe left', observed_ms=round((time.monotonic()-start)*1000, 1)))
        assert phone.private('cat', local_campaign) != first_local
        assert phone.private('cat', game) == provider_before, 'Movement modified the account progress record'
        saved = phone.private('cat', local_campaign)
        position = player(driver)
        phone.capture('level-40-moved')
        # The app's own frame metrics retain recent frame times; no global reset.
        layers = phone.shell('dumpsys', 'SurfaceFlinger', '--list')
        owned = [line for line in layers.splitlines() if transport.PACKAGE in line]
        for index, layer in enumerate(owned):
            (transport.OUTPUT / f'frame-latency-{index}.txt').write_text(phone.shell('dumpsys', 'SurfaceFlinger', '--latency', layer))
        phone.stop()
        driver = enter(40)
        assert phone.private('cat', local_campaign) == saved, 'Cold restart changed the saved board'
        assert player(driver) == position, 'Cold restart changed the player position'
        after_restart = phone.private('cat', game)
        (transport.OUTPUT / 'provider-before-restart.json').write_text(provider_before + '\n')
        (transport.OUTPUT / 'provider-after-restart.json').write_text(after_restart + '\n')
        assert after_restart == provider_before, 'Cold restart rewrote identical earned account progress'
        restarted = json.loads(after_restart)
        assert restarted['unlocked'] == 40 and restarted['completed'].startswith('1' * 39), restarted
        assert 'state' not in restarted
        phone.state['level40_restart_record'] = restarted
        phone.save()
        phone.capture('level-40-restarted')

        print('Level40 real swipe/local save/cold restart passed', flush=True)
        if args.case == 'all':
            game = seed(1, '')
            driver = enter(1)
            provider_before = phone.private('cat', game)
            for direction in route[:-1]:
                step(driver, direction)
                assert phone.private('cat', game) == provider_before, 'Active puzzle wrote account progress'
            step(driver, route[-1])
            deadline = time.monotonic() + 30
            while True:
                record = json.loads(phone.private('cat', game))
                if record['unlocked'] == 2 and record['completed'].startswith('1'):
                    break
                assert time.monotonic() < deadline, record
            assert 'state' not in record, 'Account record contains player state'
            phone.state['completion_record'] = record
            phone.save()
            phone.stop()
            driver = enter(2)
            assert json.loads(phone.private('cat', game))['unlocked'] == 2
            phone.capture('completion-restarted')
            print('Completion-only unlock and restart passed', flush=True)

    continued = None
    if args.case in ('all', 'account'):
        # Start as an entirely artificial account, with a different local owner.
        # No owner key, app or profile is read or altered.
        game = seed(40, '', account=True)
        driver = enter(40)
        driver.press(label='Levels', role='button')
        driver.press(key=33001)
        driver.wait(contains='Level 1 / ', role='text')
        step(driver, route[0])
        before_logout = player(driver)
        (transport.OUTPUT / 'old-owner-active-campaign.txt').write_text(phone.private('cat', campaign_path()))
        old_account = phone.private('cat', game)
        driver.press(label='Back', role='button')
        driver.wait(label='Play', role='button')
        driver.press(label='Profile', role='button')
        if not driver.find(label='Log out', role='button', visible=True):
            driver.press(label='Account', role='button')
        driver.press(label='Log out', role='button')
        driver.press(key=807)
        driver.wait(label='Not signed in', role='text', timeout=30)
        for depth in range(8):
            if driver.find(label='Play', role='button', visible=True):
                break
            driver.press(label='Back', role='button')
        driver.wait(label='Play', role='button')
        driver.press(label='Play', role='button')
        driver.wait(contains='Level 1 / ', role='text')
        continued = player(driver) == before_logout
        assert not phone.exists('files/entity/account.key'), 'Logout did not finish'
        phone.state['account_switch_kept_active_board'] = continued
        local_owner_record = 'files/entity/records/local/game-progress/' + identifier + '.json'
        if phone.exists(local_owner_record):
            text = phone.private('cat', local_owner_record)
            (transport.OUTPUT / 'new-owner-before-completion.json').write_text(text + '\n')
            phone.state['new_owner_before_completion'] = json.loads(text)
        phone.save()
        for direction in (route[1:] if continued else route):
            step(driver, direction)
        # Owner isolation is independent of whether the host retained the
        # device-local board or reopened it. Neither path may publish old unlocks.
        deadline = time.monotonic() + 30
        while not (driver.find(contains='Level 1 / ', role='text') or
                   driver.find(contains='Level 2 / ', role='text')):
            assert time.monotonic() < deadline, driver.text()
        phone.state['account_switch_final_header'] = [node['label'] for node in driver.find(key=20001)]
        assert phone.private('cat', game) == old_account, 'Signed-out account was modified'
        new_record = 'files/entity/records/local/game-progress/' + identifier + '.json'
        if phone.exists(new_record):
            record = json.loads(phone.private('cat', new_record))
            (transport.OUTPUT / 'new-owner-completion.json').write_text(json.dumps(record, indent=2) + '\n')
            phone.state['account_switch_new_record'] = record
            phone.state['account_switch_kept_active_board'] = continued
            phone.save()
            assert record['unlocked'] <= 2 and 'state' not in record, 'Old account progress leaked into new owner: ' + json.dumps(record)
    phone.state.update(result='passed', case=args.case,
                       movement_saved_locally=args.case in ('all', 'startup'),
                       provider_unchanged_during_moves=args.case in ('all', 'startup'),
                       completion_only=args.case == 'all', cold_restart=args.case in ('all', 'startup'), account_switch=args.case in ('all', 'account'),
                       account_switch_kept_active_board=continued, motion_observations=timings,
                       timing_limitation='ADB-to-widget observation includes transport/poll latency; SurfaceFlinger samples saved separately, no before/after baseline')
    phone.save()
    print('USB Moto local test passed: ' + args.case)
finally:
    phone.restore()
