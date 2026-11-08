"""Verify native Arcade and standalone Shovey reuse the shared Entity profile."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from PIL import Image, ImageChops


def arcade_profile(binary, inbe_source, root):
    """Exercise the production Arcade entry without accounts or public services."""
    sys.path.insert(0, str(inbe_source / 'tests'))
    from ui_driver import UiDriver
    out = root / 'backup/entity-ui-test'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out) as temporary:
        data = Path(temporary)
        driver = UiDriver(data / 'driver')
        env = os.environ | driver.environment() | {
            'ARCADE_DATA': str(data / 'arcade'), 'ENTITY_DATA': str(data / 'entity'),
            'HOME': str(data), 'XDG_DATA_HOME': str(data / 'share'),
            'XDG_CONFIG_HOME': str(data / 'config'), 'XDG_CACHE_HOME': str(data / 'cache'),
            'LANG': 'en_US.UTF-8', 'APP_NO_TRAY': '1',
            'ARCADE_PACKAGE_ORIGIN': 'http://127.0.0.1:9'}
        log_path = out / 'app.log'
        with log_path.open('w') as log:
            child = subprocess.Popen([str(binary.resolve())], cwd=binary.resolve().parent,
                                     env=env, stdout=log, stderr=subprocess.STDOUT)
            driver.attach(child, log_path)
            try:
                driver.wait(label='Stay offline', role='button')
                driver.press(label='Stay offline', role='button')
                driver.wait(label='Profile', role='button')
                driver.press(label='Profile', role='button')
                driver.press(label='Sign in', role='button')
                # The native sign-in page includes file recovery before the
                # online password. Scroll only this test's private window.
                for _ in range(20):
                    if driver.find(label='Password', role='text_field', visible=True):
                        break
                    driver.pointer(500, 650, wheel=-3)
                field = driver.wait(label='Password', role='text_field')
                assert field['secure'] and field['value'] == '' and field['cursor'] == 0
                windows = subprocess.check_output(
                    ['xdotool', 'search', '--onlyvisible', '--pid', str(child.pid)],
                    env=env, text=True).split()
                assert len(windows) == 1
                window = windows[0]
                assert subprocess.check_output(['xdotool', 'getwindowpid', window],
                    env=env, text=True).strip() == str(child.pid)
                subprocess.run(['xdotool', 'windowfocus', '--sync', window], env=env, check=True)

                def keyboard(*keys):
                    subprocess.run(['xdotool', 'key', '--clearmodifiers', *keys], env=env, check=True)
                    driver.wait_idle(frames=3)

                def field_image(name):
                    driver.press(label='Username or public ID', role='text_field')
                    driver.wait_idle(frames=3)
                    node = driver.wait(label='Password', role='text_field')
                    path = out / (name + '.png')
                    subprocess.run(['import', '-window', window, str(path)], env=env, check=True)
                    with Image.open(path) as picture:
                        return picture.convert('RGB').crop((round(node['x'] + 14), round(node['y'] + 12),
                            round(node['x'] + node['width'] - 14), round(node['y'] + node['height'] - 12)))

                def star_count(image):
                    # Bright text stands above the muted placeholder. Each
                    # ASCII star occupies one separate run of pixel columns.
                    background = image.getpixel((image.width - 1, image.height // 2))
                    columns = [any(max(abs(a - b) for a, b in zip(image.getpixel((x, y)), background)) > 90
                                   for y in range(image.height)) for x in range(image.width)]
                    return sum(lit and (x == 0 or not columns[x - 1]) for x, lit in enumerate(columns))

                empty = field_image('empty')
                assert star_count(empty) == 0, 'An empty password must not prefill stars'
                counts = []
                for name, text in [('twelve', 'Ab3defghijkl'), ('thirty-two', 'Ab3' + 'x' * 29),
                                   ('unicode', 'Ab3é中🙂')]:
                    driver.press(label='Password', role='text_field')
                    assert driver.wait(label='Password', role='text_field')['focused'], 'Password must take focus'
                    keyboard('ctrl+a')
                    # Arcade forwards the physical SDL text/modifier path;
                    # its entry does not consume UiDriver's typed-text queue.
                    if text.isascii():
                        subprocess.run(['xdotool', 'type', '--clearmodifiers', '--delay', '20', text],
                                       env=env, check=True)
                    else:
                        # Xvfb has no Unicode keyboard layout. Exercise native
                        # clipboard paste rather than synthesizing unmapped keys.
                        subprocess.run(['xclip', '-selection', 'clipboard'], input=text.encode(), env=env, check=True)
                        keyboard('ctrl+v')
                    image = field_image(name)
                    groups = star_count(image)
                    assert groups == len(text), (name, groups, len(text))
                    counts.append(groups)
                    assert driver.wait(label='Password', role='text_field')['value'] == ''
                driver.press(label='Password', role='text_field')
                keyboard('BackSpace')
                assert star_count(field_image('backspace')) == 5, 'Backspace removes one Unicode symbol'
                driver.press(label='Password', role='text_field')
                keyboard('ctrl+a', 'BackSpace')
                cleared = field_image('cleared')
                assert ImageChops.difference(empty, cleared).getbbox() is None, 'Clearing must restore the empty field'
                driver.press(label='Password', role='text_field')
                subprocess.run(['xdotool', 'type', '--clearmodifiers', 'Ab3-not-retained'], env=env, check=True)
                driver.press(label='Back', role='button')
                driver.wait(label='Profile', role='button')
                driver.press(label='Profile', role='button')
                driver.press(label='Sign in', role='button')
                assert driver.wait(label='Password', role='text_field')['cursor'] == 0
                assert star_count(field_image('reopened')) == 0, 'Returning must not prefill the old password'
                driver.press(label='Back', role='button')
                driver.wait(label='Profile', role='button')
                # Escape goes back one page, then exits from the profile root.
                driver.press(label='Profile', role='button')
                driver.press(label='Sign in', role='button')
                driver.key('escape')
                driver.wait_gone(label='Password', role='text_field')
                assert not driver.find(label='Profile', role='button'), 'Back must stay inside Profile first'
                driver.key('escape')
                driver.wait(label='Profile', role='button')
                (out / 'result.json').write_text(json.dumps({'rendered_stars': counts,
                    'empty_initially': True, 'empty_after_clear': True,
                    'empty_after_reopen': True, 'returned_to_library': True}) + '\n')
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=10)
    print('Arcade native Profile: empty password, 12/32/Unicode stars, editing and direct close from sign-in passed')

parser = argparse.ArgumentParser()
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--inbe-source', type=Path, required=True)
parser.add_argument('--product', choices=('arcade', 'shovey'), default='shovey')
args = parser.parse_args()
assert int(os.environ['DISPLAY'].split(':')[-1].split('.')[0]) >= 400
assert os.environ['YUE_DESKTOP_RECOVERY'] == '0'
root = Path(__file__).resolve().parents[1]
if args.product == 'arcade':
    arcade_profile(args.binary, args.inbe_source, root)
    sys.exit(0)
out = root / 'work/entity-ui-test-shovey'
out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(args.inbe_source / 'tests'))
from ui_driver import UiDriver
with tempfile.TemporaryDirectory(dir=out) as temporary:
    data = Path(temporary)
    driver = UiDriver(out / 'driver')
    env = os.environ | driver.environment() | {'ARCADE_DATA': str(data), 'ENTITY_DATA': str(data / 'shared'),
        'XDG_DATA_HOME': str(data / 'share'), 'XDG_CONFIG_HOME': str(data / 'config'),
        'XDG_CACHE_HOME': str(data / 'cache'), 'LANG': 'en_US.UTF-8'}
    log_path = out / 'app.log'
    with log_path.open('w') as log:
        child = subprocess.Popen([str(args.binary.resolve())], cwd=args.binary.resolve().parent,
                                 env=env, stdout=log, stderr=subprocess.STDOUT)
        driver.attach(child, log_path)
        try:
            startup = driver.tree()
            (out / 'startup-tree.json').write_text(json.dumps(driver.last, indent=2) + '\n')
            assert driver.last['frame'] <= 3, 'Loading artwork must precede collection startup'
            assert not any(node['label'] == 'Play' for node in startup)
            images = [node for node in startup if node['kind'] == 'image' and node['label'] == 'Shovey']
            assert len(images) == 2, 'Loading must show both the full title artwork and logo'
            assert max(node['height'] for node in images) >= 800, 'Loading artwork must fill the window'
            windows = subprocess.check_output(['xdotool', 'search', '--onlyvisible', '--pid', str(child.pid)], env=env, text=True).split()
            assert len(windows) == 1
            assert subprocess.check_output(['xdotool', 'getwindowpid', windows[0]], env=env, text=True).strip() == str(child.pid)
            subprocess.run(['import', '-window', windows[0], str(out / 'loading.png')], env=env, check=True)
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
            driver.wait(label='Sign in', role='button')
            driver.wait(label='Profile', role='text')
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
            driver.wait(label='Sign in', role='button')
            driver.press(label='Back', role='button')
            driver.wait(label='Play', role='button')
            assert (record.read_bytes() if record.exists() else b'') == before
            assert not (data / 'games/arcade.shovey/entity').exists()
        finally:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=10)
print('Standalone Entity profile, return navigation and retained campaign passed')
