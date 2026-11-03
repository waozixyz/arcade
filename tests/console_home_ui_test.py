"""Real console home, artwork pixels, rotation, input and profile roundtrip privately."""
import argparse, contextlib, json, os, subprocess, sys, tempfile, time
from pathlib import Path
from PIL import Image
root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, default=root / 'build/arcade')
parser.add_argument('--inbe-source', type=Path, required=True)
args = parser.parse_args()
assert int(os.environ['DISPLAY'].split(':')[-1].split('.')[0]) >= 400
assert os.environ['YUE_DESKTOP_RECOVERY'] == '0'
sys.path.insert(0, str(root / 'tests'))
sys.path.insert(0, str(args.inbe_source / 'tests'))
from collection_ui_test import package_server, answer_library_question
from ui_driver import UiDriver
out = root / 'work/console-redesign/results'
out.mkdir(parents=True, exist_ok=True)
driver = UiDriver(out / 'driver')
with package_server(root) as (origin, server), tempfile.TemporaryDirectory(dir=out) as temporary, (out / 'capture.log').open('w') as log:
    profile = Path(temporary)
    child = subprocess.Popen([str(args.binary.resolve())], cwd=root, env=os.environ | driver.environment() | {
        'ARCADE_DATA': str(profile), 'ENTITY_DATA': str(profile / 'entity'), 'XDG_DATA_HOME': str(profile / 'share'),
        'XDG_CONFIG_HOME': str(profile / 'config'), 'XDG_CACHE_HOME': str(profile / 'cache'),
        'LANG': 'en_US.UTF-8', 'ARCADE_PACKAGE_ORIGIN': origin}, stdout=log, stderr=subprocess.STDOUT)
    driver.attach(child, out / 'capture.log')
    try:
        answer_library_question(driver)
        art = json.loads((root / 'build/arcade.json').read_text())['art']['sha256']
        deadline = time.monotonic() + 60
        while not (profile / 'resources/downloads' / (art + '.zx')).exists():
            assert time.monotonic() < deadline, 'Library art did not download'
            time.sleep(.1)
        window = subprocess.check_output(['xdotool', 'search', '--onlyvisible', '--pid', str(child.pid)], text=True).splitlines()[0]
        assert int(subprocess.check_output(['xdotool', 'getwindowpid', window], text=True)) == child.pid
        for name, width, height in [('home-landscape', 1200, 720), ('home-portrait', 480, 820)]:
            subprocess.run(['xdotool', 'windowsize', window, str(width), str(height)], check=True)
            deadline = time.monotonic() + 10
            while max(n['width'] for n in driver.tree()) != width:
                assert time.monotonic() < deadline
                time.sleep(.05)
            driver.wait_idle(frames=30)
            nodes = driver.tree()
            assert not driver.find(label='Arcade', role='text'), 'No app-name header'
            assert not [n for n in nodes if n['kind'] in ('button', 'text') and 'Editor' in n['label']], 'Games only'
            for title in ('Shovey', 'Apfelwurm', 'Choano'):
                assert driver.find(label=title, role='button'), 'Accessible game name missing'
                assert not driver.find(label=title, role='text'), 'No captions under artwork'
            background = next(n for n in nodes if n['key'] == 50021)
            assert (background['x'], background['y'], background['width'], background['height']) == (0, 0, width, height)
            assert background['detail'].endswith(('landscape.webp' if width > height else 'portrait.webp'))
            selected = [n for n in nodes if n['kind'] == 'button' and n['selected'] and n['height'] > 100]
            (out / 'latest-debug-tree.json').write_text(json.dumps(nodes,indent=2))
            assert len(selected) == 1, [(n['label'],n['selected'],n['width'],n['height']) for n in nodes if n['kind']=='button']
            selected = selected[0]
            assert abs(selected['width'] / selected['height'] - (16/9 if width > height else 2/3)) < .02
            covers = [n for n in nodes if n['role'] == 'image' and n['label'] in ('Shovey','Apfelwurm','Choano') and n['visible']]
            assert len(covers) >= 2, 'Real neighbouring covers must be visible'
            if width > height:
                assert len(covers) == 3 and max(n['y'] for n in covers) - min(n['y'] for n in covers) < 1
                assert selected['y'] > height * .65, 'Single shelf belongs at bottom'
            else:
                assert selected['width'] >= width * .65 and selected['height'] > height * .55
                assert len([n for n in nodes if 50300 <= n['key'] <= 50302 and n['role'] == 'image']) == 3
            for icon in ('profile', 'dew'):
                assert any(n['role'] == 'image' and n['detail'].endswith('/assets/hud/' + icon + '.webp') for n in nodes), 'Painted startup icon missing'
            subprocess.run(['import', '-window', window, str(out / (name + '.png'))], check=True)
            (out / (name + '-tree.json')).write_text(json.dumps(driver.tree(), indent=2))
            with Image.open(out / (name + '.png')) as im:
                rgb = im.convert('RGB')
                top = list(rgb.crop((0,0,width//2,88)).resize((30,10)).getdata())
                clear = sum(all(abs(a-b) <= 3 for a,b in zip(pixel,(248,250,252))) for pixel in top)
                assert clear < len(top)//2 and len(set(top)) > 20, 'Former white band must paint full game artwork'
                for cover in covers:
                    x,y,w,h = (cover[k] for k in ('x','y','width','height'))
                    crop = rgb.crop((max(0,x),max(0,y),min(width,x+w),min(height,y+h)))
                    assert len(crop.getcolors(1000000) or []) > 100, 'A neighbour became a blank grey block'
                mint = rgb.getpixel((int(selected['x'])-2,int(selected['y']+selected['height']/2)))
                assert mint[0] > 160 and mint[1] > 200 and mint[2] > 180, ('Missing focus glow',mint)
            before = background['detail']
            driver.key('right')
            driver.wait_idle(frames=20)
            changed = next(n for n in driver.tree() if n['key'] == 50021)
            assert changed['detail'] != before, 'Selection changes the full-screen game background'
            driver.key('enter')
            driver.wait(label='Cancel', role='button')
            dialog_nodes = driver.tree()
            (out / 'install-dialog-tree.json').write_text(json.dumps(dialog_nodes,indent=2))
            subprocess.run(['import','-window',window,str(out/'install-dialog.png')],check=True)
            assert not any(n['kind'] == 'modal' for n in dialog_nodes), 'Launch progress must not create a modal'
            assert any(n['label'] == 'Apfelwurm' and n['kind'] == 'text' for n in dialog_nodes), 'Launch screen must name the game'
            driver.press(label='Cancel', role='button')
            driver.key('left')
            driver.wait_idle(frames=20)
            driver.press(label='Profile', role='button')
            driver.wait(label='Account', role='text')
            if width < height:
                driver.press(label='Library connection', role='button')
                driver.wait(label='Allow fetching content and automatic app updates?', role='text')
                driver.press(label='Stay offline', role='button')
            else:
                driver.press(label='Back', role='button')
            driver.wait(label='Shovey', role='button')
            driver.wait_idle(frames=20)

        # Native keyboard focus reaches the HUD without opening a game too.
        for _ in range(16):
            driver.key('tab')
            driver.wait_idle(frames=3)
            if any(n['label']=='Profile' and n['focused'] for n in driver.tree()):
                break
        else:
            raise AssertionError('Tab cannot reach Profile')
        driver.key('enter')
        driver.wait(label='Account', role='text')
        driver.press(label='Back', role='button')
        driver.wait(label='Shovey', role='button')
        assert not driver.find(role='modal'), 'HUD keyboard activation also opened a game dialog'

        with Image.open(out / 'home-landscape.png') as im:
            im.crop((im.width - 240, 0, im.width, 90)).resize((960, 360), Image.Resampling.LANCZOS).save(out / 'dew-profile-closeup.png')
        assert not any(entry['sha256'] in server['requests'] for entry in json.loads((root / 'build/arcade.json').read_text())['children']), 'Browsing does not predownload games'
        print('PASS console home: real art/background pixels, no white band/title/captions/editors, orientation, focus glow, keyboard, named install consent, Profile roundtrip')
        print('Captured only owned private-Xvfb window:', child.pid)
        for name in ('home-landscape.png', 'home-portrait.png', 'dew-profile-closeup.png'):
            print(out / name)
    finally:
        if child.poll() is None: child.terminate()
        child.wait(timeout=10)
