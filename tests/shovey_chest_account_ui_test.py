"""The real Shovey host opens its account provider from the hidden chest."""
import argparse
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
assert int(os.environ['DISPLAY'].split(':')[-1].split('.')[0]) >= 400
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--campaign', type=Path, required=True)
args = parser.parse_args()
sys.path.insert(0, str(ROOT.parent / 'breeze/tests'))
from ui_driver import UiDriver
output = ROOT / 'build/scratch/chest-account-ui'
output.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(dir=output, prefix='profile-') as temporary:
    profile = Path(temporary)
    records = profile / 'games/arcade.shovey/records'
    records.mkdir(parents=True)
    records.joinpath('local.campaign').write_text(args.campaign.read_text().splitlines()[0])
    settings = profile / 'games/arcade.shovey-player/records'
    settings.mkdir(parents=True)
    settings.joinpath('controls').write_text('off')
    settings.joinpath('updates').write_text('off')
    driver = UiDriver(profile / 'driver')
    env = os.environ | driver.environment() | dict(ARCADE_DATA=str(profile), XDG_DATA_HOME=str(profile / 'xdg'),
        YUE_DESKTOP_RECOVERY='0', SDL_AUDIODRIVER='dummy', LANG='en_US.UTF-8')
    for key in ('WAYLAND_DISPLAY', 'DBUS_SESSION_BUS_ADDRESS', 'SESSION_MANAGER', 'GDK_DISPLAY'):
        env.pop(key, None)
    with (output / 'game.log').open('w') as log:
        child = subprocess.Popen([str(args.binary.resolve()), '--app', 'shovey'], env=env,
                                 stdout=log, stderr=subprocess.STDOUT)
        driver.attach(child, output / 'game.log')
        try:
            driver.wait(label='Restart', role='button', timeout=60)
            window = subprocess.check_output(['xdotool', 'search', '--onlyvisible', '--pid', str(child.pid)], text=True).split()[0]
            subprocess.run(['xdotool', 'windowsize', window, '1280', '800'], check=True)
            time.sleep(.5)
            driver.key('down')
            driver.wait(contains='29a', role='text')
            time.sleep(.75)
            driver.press(label='Levels', role='button')
            driver.wait(label='Continue', role='button')
            labels = [node.get('label', '') for node in driver.tree()]
            assert '29' in labels and '30' in labels
            assert not any(re.fullmatch(r'[0-9]+[ab]', label) for label in labels), labels
            driver.press(label='Continue', role='button')
            for key in ('down', 'right', *(['down'] * 6)):
                driver.key(key)
                time.sleep(.18)
            driver.wait(label='Connect account', role='button')
            campaign_before = records.joinpath('local.campaign').read_bytes()
            driver.press(label='Connect account', role='button')
            driver.wait(label='Create account', role='button')
            driver.wait(label='Import key', role='button')
            driver.wait(label='Link from another device', role='button')
            tree = driver.tree()
            assert not any('offline preview' in node.get('label', '').lower() for node in tree)
            subprocess.run(['import', '-window', window, str(output / 'account-modal.png')], check=True)
            with Image.open(output / 'account-modal.png') as image:
                pixel = image.convert('RGB').getpixel((372, 52))
            assert max(pixel) < 130, f'The account modal ignored the dark game palette: {pixel}'
            driver.key('down')
            driver.press(label='Back', role='button')
            driver.wait(label='Connect account', role='button')
            driver.wait(contains='29a', role='text')
            assert records.joinpath('local.campaign').read_bytes() == campaign_before
            assert not list(profile.rglob('account.key')), 'This test created an account'
            (output / 'result.json').write_text(json.dumps(dict(actual_host=True, real_beach_entry=True,
                normal_account_provider=True, signin_actions=['Create account', 'Import key', 'Link from another device'],
                palette_sample=pixel, game_restored=True, account_created=False, live_claim=False), indent=2) + '\n')
            print('Actual Shovey: beach29 -> hidden29a -> chest -> normal themed account modal; sign-in choices present; game restored; no account created')
        finally:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=15)
