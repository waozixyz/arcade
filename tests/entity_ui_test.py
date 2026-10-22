"""Verify standalone Shovey reuses Entity without losing the game."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from PIL import Image

parser = argparse.ArgumentParser()
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--inbe-source', type=Path, required=True)
args = parser.parse_args()
assert int(os.environ['DISPLAY'].split(':')[-1].split('.')[0]) >= 400
assert os.environ['YUE_DESKTOP_RECOVERY'] == '0'
root = Path(__file__).resolve().parents[1]
out = root / 'build/entity-ui-test'
out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(args.inbe_source / 'tests'))
from ui_driver import UiDriver
with tempfile.TemporaryDirectory(dir=out) as temporary:
    data = Path(temporary)
    driver = UiDriver(out / 'driver')
    env = os.environ | driver.environment() | {'ARCADE_DATA': str(data), 'ENTITY_DATA': str(data / 'shared'), 'LANG': 'en_US.UTF-8'}
    log_path = out / 'app.log'
    with log_path.open('w') as log:
        child = subprocess.Popen([str(args.binary.resolve())], cwd=args.binary.resolve().parent,
                                 env=env, stdout=log, stderr=subprocess.STDOUT)
        driver.attach(child, log_path)
        try:
            driver.wait(label='Play', role='button')
            profile_button = driver.wait(label='Profile', role='button')
            windows = subprocess.check_output(['xdotool', 'search', '--onlyvisible', '--pid', str(child.pid)], env=env, text=True).split()
            assert len(windows) == 1
            window = windows[0]
            assert subprocess.check_output(['xdotool', 'getwindowpid', window], env=env, text=True).strip() == str(child.pid)
            subprocess.run(['import', '-window', window, str(out / 'title.png')], env=env, check=True)
            title = Image.open(out / 'title.png')
            title.crop((round(profile_button['x']), round(profile_button['y']),
                        round(profile_button['x'] + profile_button['width']), round(profile_button['y'] + profile_button['height']))).save(out / 'profile-icon.png')
            driver.press(label='Profile', role='button')
            driver.wait(label='Connect an account', role='button')
            driver.wait(label='Entity', role='text')
            driver.wait_idle(frames=3)
            subprocess.run(['import', '-window', window, str(out / 'profile.png')], env=env, check=True)
            profile = Image.open(out / 'profile.png').convert('RGB')
            assert profile.getpixel((5, 85)) == (42, 46, 45), 'Profile canvas must use Shovey slate'
            assert profile.getpixel((profile.width // 2, 92)) == (59, 64, 63), 'Profile surface must use the host palette'

            assert not driver.find(label='Play', role='button', visible=True)
            driver.press(label='Back', role='button')
            driver.wait(label='Play', role='button')
            driver.press(label='Play', role='button')
            driver.wait(label='Restart', role='button')
            record = data / 'games/arcade.shovey/records/campaign'
            for direction in ('left', 'up', 'right', 'down'):
                driver.key(direction)
            driver.key('escape')
            driver.wait(label='Profile', role='button')
            before = record.read_bytes() if record.exists() else b''
            driver.press(label='Profile', role='button')
            driver.wait(label='Connect an account', role='button')
            driver.press(label='Back', role='button')
            driver.wait(label='Play', role='button')
            assert (record.read_bytes() if record.exists() else b'') == before
            assert not (data / 'games/arcade.shovey/entity').exists()
        finally:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=10)
print('Standalone Entity profile, return navigation and retained campaign passed')
