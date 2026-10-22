"""Check native Profile/Settings navigation without touching owner data."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, action='append', required=True)
parser.add_argument('--inbe-source', type=Path, required=True)
args = parser.parse_args()
assert int(os.environ['DISPLAY'].split(':')[-1].split('.')[0]) >= 400
assert os.environ['YUE_DESKTOP_RECOVERY'] == '0'
sys.path.insert(0, str(args.inbe_source / 'tests'))
from ui_driver import UiDriver
output = Path(__file__).resolve().parents[1] / 'build/standalone-navigation-ui-test'
output.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='native-navigation-') as temporary:
    for binary in args.binary:
        profile = Path(temporary) / binary.name
        driver = UiDriver(output / binary.name / 'driver')
        log_path = output / (binary.name + '.log')
        with log_path.open('w') as log:
            child = subprocess.Popen([str(binary.resolve())], cwd=binary.resolve().parent,
                                     env=os.environ | driver.environment() |
                                     {'ARCADE_DATA': str(profile), 'LANG': 'en_US.UTF-8'},
                                     stdout=log, stderr=subprocess.STDOUT)
            driver.attach(child, log_path)
            try:
                driver.wait(label='Play', role='button')

                def toolbar():
                    screen = driver.tree()[0]
                    for label in ('Profile', 'Settings'):
                        buttons = driver.find(label=label, role='button', visible=True)
                        assert len(buttons) == 1, (label, buttons)
                        button = buttons[0]
                        assert button['y'] <= 12 and button['width'] >= 44 and button['height'] >= 44
                        assert button['x'] >= screen['width'] - 112, 'Action is not at the top right'

                def capture(name):
                    windows = subprocess.check_output(['xdotool', 'search', '--onlyvisible', '--pid', str(child.pid)], text=True).split()
                    assert len(windows) == 1
                    assert int(subprocess.check_output(['xdotool', 'getwindowpid', windows[0]], text=True)) == child.pid
                    subprocess.run(['import', '-window', windows[0], str(output / (binary.name + '-' + name + '.png'))], check=True)

                def profile_and_settings(return_label):
                    toolbar()
                    driver.press(label='Profile', role='button')
                    driver.wait(label='Profile', role='text')
                    driver.wait(label='Change picture', role='button')
                    toolbar()
                    driver.press(label='Settings', role='button')
                    driver.wait(label='Settings', role='text')
                    driver.wait(label='Nodes', role='text', visible=False)
                    toolbar()
                    capture('settings')
                    driver.press(label='Back', role='button')
                    driver.wait(label=return_label, role='button')

                toolbar()
                capture('home')
                profile_and_settings('Play')
                driver.press(label='Play', role='button')
                driver.wait(label='Restart', role='button')
                for direction in ('left', 'up', 'right', 'down'):
                    driver.key(direction)
                record = profile / 'games/arcade.shovey/records/campaign'
                before = record.read_bytes()
                profile_and_settings('Restart')
                assert record.read_bytes() == before, 'Native pages changed game progress'
                toolbar()
                assert len(driver.find(label='Back', role='button', visible=True)) == 1
                capture('playing')
                print(f'PASS: {binary.name}: top-right Profile/Settings, shared pages, return navigation, retained save')
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=10)
