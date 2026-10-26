"""Verify coloured startup previews, original covers and title transitions privately."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from PIL import Image

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--driver-source', type=Path, required=True)
args = parser.parse_args()
assert int(os.environ['DISPLAY'].split(':')[-1].split('.')[0]) >= 400
assert os.environ['YUE_DESKTOP_RECOVERY'] == '0'
sys.path.insert(0, str(args.driver_source / 'tests'))
from ui_driver import UiDriver

root = Path(__file__).resolve().parents[1]
output = root / 'build/scratch/title-progressive/ui'
output.mkdir(parents=True, exist_ok=True)
binary = args.binary.resolve()
driver = UiDriver(output / 'driver')

with tempfile.TemporaryDirectory(prefix='profile-', dir=output) as temporary:
    profile = Path(temporary)
    records = profile / 'games/arcade.shovey-player/records'
    records.mkdir(parents=True)
    (records / 'level-updates').write_text('off')
    log_path = output / 'game.log'
    with log_path.open('w') as log:
        child = subprocess.Popen([str(binary)], cwd=binary.parent,
                                 env=os.environ | driver.environment() |
                                 {'ARCADE_DATA': str(profile), 'ENTITY_DATA': str(profile / 'entity'),
                                  'LANG': 'en_US.UTF-8', 'SDL_AUDIODRIVER': 'dummy'},
                                 stdout=log, stderr=subprocess.STDOUT)
        driver.attach(child, log_path)
        try:
            startup = driver.tree()
            assert driver.last['frame'] <= 3, 'Preview must precede collection loading'
            images = [node for node in startup if node['kind'] == 'image' and node['label'] == 'Shovey']
            assert len(images) == 2, 'Startup must show the artwork and coloured logo together'
            for node in images:
                assert 'startup/shovey/' in node['detail']
                with Image.open(node['detail']) as picture:
                    assert picture.mode in ('RGB', 'RGBA'), 'Startup art must retain full colour'
                    assert max(picture.size) <= 640, 'Startup must use a small preview'
            (output / 'startup-tree.json').write_text(json.dumps(driver.last, indent=2) + '\n')
            driver.wait(label='Play', role='button', timeout=60)
            full = [node for node in driver.tree() if node['kind'] == 'image' and
                    'arcade/covers/shovey-' in node.get('detail', '')]
            assert len(full) >= 2
            assert any(max(Image.open(node['detail']).size) >= 1200 for node in full), \
                'Ready cover must replace the preview with the original artwork'
            windows = subprocess.check_output(['xdotool', 'search', '--onlyvisible', '--pid', str(child.pid)], text=True).split()
            assert len(windows) == 1
            window = windows[0]
            assert subprocess.check_output(['xdotool', 'getwindowpid', window], text=True).strip() == str(child.pid)
            subprocess.run(['xdotool', 'windowmove', window, '0', '0'], check=True)
            subprocess.run(['import', '-window', window, str(output / 'classic-ready.png')], check=True)
            driver.key('right')
            subprocess.run(['import', '-window', window, str(output / 'logo-fading.png')], check=True)
            driver.wait(label='Editor', role='text')
            driver.wait(label='Open', role='button')
            driver.wait_idle(frames=5)
            subprocess.run(['import', '-window', window, str(output / 'editor-ready.png')], check=True)
            driver.key('left')
            driver.wait(label='Classic', role='text')
            driver.wait(label='Play', role='button')
            assert child.poll() is None
        finally:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=10)
print('Local title UI test: full-colour previews precede original covers; Classic/Editor transitions work')
