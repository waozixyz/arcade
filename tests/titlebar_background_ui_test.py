"""Verify Arcade's host bar pixels on a private display, including repaint."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--inbe-source', type=Path, required=True)
    args = parser.parse_args()
    assert int(os.environ['DISPLAY'].split(':')[-1].split('.')[0]) >= 400
    assert os.environ['YUE_DESKTOP_RECOVERY'] == '0'
    root = Path(__file__).resolve().parents[1]
    subprocess.run(['git', 'check-ignore', 'work/titlebar-background-ui'], cwd=root, check=True)
    output = root / 'work/titlebar-background-ui'
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(args.inbe_source / 'tests'))
    from ui_driver import UiDriver
    driver = UiDriver(output / 'driver')
    with tempfile.TemporaryDirectory(dir=output) as temporary, (output / 'app.log').open('w') as log:
        profile = Path(temporary)
        child = subprocess.Popen([str(args.binary.resolve())], cwd=root,
            env=os.environ | driver.environment() | {
                'ARCADE_DATA': str(profile), 'ENTITY_DATA': str(profile / 'entity'),
                'XDG_DATA_HOME': str(profile / 'share'), 'XDG_CONFIG_HOME': str(profile / 'config'),
                'XDG_CACHE_HOME': str(profile / 'cache'), 'LANG': 'en_US.UTF-8'},
            stdout=log, stderr=subprocess.STDOUT)
        driver.attach(child, output / 'app.log')
        try:
            driver.wait(label='Stay offline', role='button', timeout=60)
            driver.press(label='Stay offline', role='button')
            driver.wait(label='Profile', role='button', timeout=60)
            window = subprocess.check_output(['xdotool', 'search', '--onlyvisible', '--pid', str(child.pid)],
                text=True, timeout=10).splitlines()[0]
            assert int(subprocess.check_output(['xdotool', 'getwindowpid', window], text=True)) == child.pid

            def capture(name, size=None):
                driver.wait_idle(frames=15)
                path = output / (name + '.png')
                subprocess.run(['import', '-window', window, str(path)], check=True, timeout=10)
                with Image.open(path) as source:
                    image = source.convert('RGB')
                    if size is not None:
                        assert image.size == size, (name, image.size, size)
                    # Sample both edges of the former reserved area, away
                    # from controls and cards. The full-canvas library may
                    # have a subtle gradient, but must never expose the host's
                    # light clear color after resizing or changing screens.
                    expected = (17, 18, 35)
                    for x, y in [(2, 2), (2, 54), (2, 80), (image.width - 8, 80)]:
                        pixel = image.getpixel((x, y))
                        assert max(pixel) < 72, (name, (x, y), pixel, 'opaque dark home')

            capture('library')
            for width, height in [(480, 820), (1200, 900)]:
                subprocess.run(['xdotool', 'windowsize', window, str(width), str(height)], check=True)
                capture(f'resized-{width}', (width, height))
            driver.press(label='Profile', role='button')
            driver.wait(label='Back', role='button')
            driver.press(label='Back', role='button')
            driver.wait_gone(label='Back', role='button')
            capture('returned-from-profile')
            print('Local titlebar pixel test passed: library, narrow/wide resize, profile return')
        finally:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=10)


if __name__ == '__main__':
    main()
