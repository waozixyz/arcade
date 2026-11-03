"""Real console home, artwork pixels, rotation, input and profile roundtrip privately."""
import argparse, contextlib, json, os, subprocess, sys, tempfile, time
from pathlib import Path
from PIL import Image, ImageOps, ImageChops, ImageStat
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
out = root / 'backup/console-fixes/results'
out.mkdir(parents=True, exist_ok=True)
driver = UiDriver(out / 'driver')
metadata = json.loads((root / 'build/arcade.json').read_text())
approved = json.loads((root / 'tests/library_art_sources.json').read_text())
sources = json.loads((root / 'assets/arcade/library/sources.json').read_text())
for name, digest in approved.items():
    assert sources[name]['source_sha256'] == digest, 'Cover replaced the original painted artwork: ' + name
assert metadata['art']['bytes'] <= 2 * 1024 * 1024

def selected_cover():
    return next(n for n in driver.tree() if n['kind'] == 'button' and n['selected'] and n['height'] > 100)

def viewport_width():
    # Scenery shapes may extend past the window; the window-sized background starts at its origin.
    return max(n['width'] for n in driver.tree() if n['x'] == 0 and n['y'] == 0)

def tap_cover(label, mouse):
    cover = next(n for n in driver.find(label=label, role='button') if n['height'] > 100 and n['visible'])
    width = viewport_width()
    x = max(4, min(width - 4, cover['x'] + cover['width'] / 2))
    y = cover['y'] + cover['height'] / 2
    if mouse:
        # A real X11 click held like a person's: SDL sees the move, press and release.
        subprocess.run(['xdotool', 'mousemove', '--window', window, str(int(x)), str(int(y))], check=True)
        time.sleep(.25)
        subprocess.run(['xdotool', 'mousedown', '1'], check=True)
        time.sleep(.15)
        subprocess.run(['xdotool', 'mouseup', '1'], check=True)
        time.sleep(.3)
    else:
        driver.pointer(x, y)
        driver.pointer(x, y, down=True)
        driver.wait_idle(frames=2)
        driver.pointer(x, y, down=False)
        driver.release_pointer()
    driver.wait_idle(frames=20)

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
            # Keep the whole window on the private screen so captures are never clipped.
            subprocess.run(['xdotool', 'windowmove', window, '0', '0'], check=True)
            deadline = time.monotonic() + 10
            while viewport_width() != width:
                assert time.monotonic() < deadline
                time.sleep(.05)
            driver.wait_idle(frames=30)
            nodes = driver.tree()
            assert not driver.find(label='Arcade', role='text'), 'No app-name header'
            assert not [n for n in nodes if n['kind'] in ('button', 'text') and 'Editor' in n['label']], 'Games only'
            for title in ('Shovey', 'Apfelwurm', 'Choano'):
                assert driver.find(label=title, role='button'), 'Accessible game name missing'
                assert not driver.find(label=title, role='text'), 'No captions under artwork'
            # Both orientations draw the same scenic pattern, never game art behind the covers.
            scenery = next(n for n in nodes if n['key'] == 50400)
            assert (scenery['x'], scenery['y'], scenery['width'], scenery['height']) == (0, 0, width, height)
            assert not any(n['key'] == 50021 for n in nodes), 'No full-screen game artwork behind the covers'
            assert not [n for n in nodes if n['role'] == 'image' and n['width'] >= width * .9 and n['height'] >= height * .9], 'No hero image'
            selected = [n for n in nodes if n['kind'] == 'button' and n['selected'] and n['height'] > 100]
            (out / 'latest-debug-tree.json').write_text(json.dumps(nodes,indent=2))
            assert len(selected) == 1, [(n['label'],n['selected'],n['width'],n['height']) for n in nodes if n['kind']=='button']
            selected = selected[0]
            assert abs(selected['width'] / selected['height'] - (16/9 if width > height else 2/3)) < .02
            covers = [n for n in nodes if n['role'] == 'image' and n['label'] in ('Shovey','Apfelwurm','Choano') and n['visible']]
            assert len(covers) >= 2, 'Real neighbouring covers must be visible'
            # The portrait carousel layout in landscape too: one large centred cover,
            # neighbours cut by the screen edges and the small cover markers below.
            assert abs(selected['x'] + selected['width'] / 2 - width / 2) < 2, 'Selected cover is centred'
            assert selected['width'] >= width * (.55 if width > height else .65)
            assert height * .15 < selected['y'] and selected['y'] + selected['height'] < height * .9
            neighbours = [n for n in covers if n['label'] != selected['label']]
            assert neighbours and all(n['x'] <= 0 or n['x'] + n['width'] >= width for n in neighbours), 'Neighbours peek in from the sides'
            assert all(abs(n['y'] + n['height'] / 2 - (selected['y'] + selected['height'] / 2)) < 2 for n in neighbours)
            markers = [n for n in nodes if 50300 <= n['key'] <= 50302 and n['role'] == 'image']
            assert len(markers) == 3 and all(n['y'] > selected['y'] + selected['height'] for n in markers)
            assert all(n['detail'].endswith(('landscape.webp' if width > height else 'portrait.webp')) for n in markers)
            for icon in ('profile', 'dew'):
                assert any(n['role'] == 'image' and n['detail'].endswith('/assets/hud/' + icon + '.webp') for n in nodes), 'Painted startup icon missing'
            subprocess.run(['import', '-window', window, str(out / (name + '.png'))], check=True)
            (out / (name + '-tree.json')).write_text(json.dumps(driver.tree(), indent=2))
            with Image.open(out / (name + '.png')) as im:
                rgb = im.convert('RGB')
                # The sky above the covers is the dusk scenic pattern, not a white band or game art.
                sky = ImageStat.Stat(rgb.crop((0, 0, width - 260, 80))).mean
                assert sky[2] > sky[0] + 15 and max(sky) < 170 and min(sky) > 12, ('Scenic sky must fill the top', sky)
                hills = ImageStat.Stat(rgb.crop((0, int(height * .93), width, height))).mean
                assert hills[1] > hills[0] and max(hills) < 140, ('Scenic hills must fill the bottom', hills)
                for cover in covers:
                    x,y,w,h = (cover[k] for k in ('x','y','width','height'))
                    crop = rgb.crop((max(0,x),max(0,y),min(width,x+w),min(height,y+h)))
                    assert len(crop.getcolors(1000000) or []) > 100, 'A neighbour became a blank grey block'
                # Compare the rendered focused cover to the approved painted asset.
                view = 'landscape' if width > height else 'portrait'
                game = {'Shovey':'shovey', 'Apfelwurm':'wurm', 'Choano':'choano'}[selected['label']]
                asset = root / 'assets/arcade/library' / (game + '-' + view + '.webp')
                with Image.open(asset) as painting:
                    expected = ImageOps.fit(painting.convert('RGB'), (round(selected['width']), round(selected['height'])))
                actual = rgb.crop(tuple(round(v) for v in (selected['x'],selected['y'],selected['x']+selected['width'],selected['y']+selected['height'])))
                # Ignore the rounded corners and lower action icon.
                region = (20,20,expected.width-20,expected.height-50)
                error = ImageStat.Stat(ImageChops.difference(actual.crop(region),expected.crop(region))).mean
                assert sum(error)/3 < 12, ('Rendered cover must show the original painting',game,error)
                mint = rgb.getpixel((int(selected['x'])-2,int(selected['y']+selected['height']/2)))
                assert mint[0] > 160 and mint[1] > 200 and mint[2] > 180, ('Missing focus glow',mint)
            before = selected['label']
            driver.key('right')
            driver.wait_idle(frames=20)
            changed = selected_cover()['label']
            assert changed != before, 'Keyboard selection moves to the next cover'
            assert not any(n['key'] == 50021 for n in driver.tree()), 'Selection never adds a game background'
            # Physical mouse and the held pointer/touch path both select only.
            requests = list(server['requests'])
            for mouse in (True, False):
                tap_cover('Shovey', mouse)
                assert selected_cover()['label'] == 'Shovey'
                tap_cover('Apfelwurm', mouse)
                assert selected_cover()['label'] == 'Apfelwurm'
                assert any(n['key'] == 50400 for n in driver.tree()), 'A side-cover tap stays on the carousel'
                assert server['requests'] == requests, 'Side-cover tap launched/downloaded a game'
                assert not driver.find(label='Cancel',role='button')
            tap_cover('Shovey', False)
            driver.wait_idle(frames=20)
            driver.press(label='Profile', role='button')
            driver.wait(label='Account', role='text')
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
        assert not any(entry['sha256'] in server['requests'] for entry in metadata['children']), 'Browsing does not predownload games'
        # Each orientation starts a missing game on the same shelf, immediately.
        for label, width, height in [('Apfelwurm',1200,720),('Shovey',480,820)]:
            subprocess.run(['xdotool','windowsize',window,str(width),str(height)],check=True)
            driver.wait_idle(frames=30)
            if selected_cover()['label'] != label: tap_cover(label, False)
            entry = next(e for e in metadata['children'] if e['title'] == label)
            server['game_delay'] = 3
            tap_cover(label, width > height)
            driver.wait(label='Downloading',role='text',timeout=10)
            nodes = driver.tree()
            assert any(n['key']==50400 for n in nodes), 'Download left the carousel'
            assert selected_cover()['label'] == label, 'Download moved selection'
            assert not driver.find(role='modal') and not driver.find(label='Cancel',role='button')
            cover = selected_cover()
            track = next(n for n in nodes if n['key']==cover['key']+14)
            assert track['width'] > 40 and cover['y'] < track['y'] < cover['y']+cover['height'], 'Progress bar must be on the downloading cover'
            other = 'Shovey' if label=='Apfelwurm' else 'Apfelwurm'
            tap_cover(other,False)
            assert selected_cover()['label']==other, 'Download blocked browsing'
            deadline = time.monotonic()+60
            while driver.find(label='Downloading',role='text') or not (profile/'resources/downloads'/(entry['sha256']+'.zx')).exists():
                assert time.monotonic()<deadline,'Background installation did not finish'
                time.sleep(.1)
            assert any(n['key']==50400 for n in driver.tree()), 'Finishing download interrupted browsing'
            assert server['requests'].count(entry['sha256'])==1,'Repeated activation queued duplicate transfers'
            server['game_delay']=0
        # A fresh activation now opens the installed game through its real title.
        tap_cover('Shovey',False)
        tap_cover('Shovey',False)
        driver.wait(label='Play',role='button',timeout=60)
        assert not any(n['key']==50400 for n in driver.tree()), 'Centred installed cover did not launch'
        print('PASS console home: original painted cover pixels, scenic pattern with no game-art backdrop, same centred carousel in landscape and portrait, no title/captions/editors, focus glow, keyboard, side-cover mouse/touch selection only, immediate inline download and browsing, installed title, Profile roundtrip')
        print('Captured only owned private-Xvfb window:', child.pid)
        for name in ('home-landscape.png', 'home-portrait.png', 'dew-profile-closeup.png'):
            print(out / name)
    finally:
        if child.poll() is None: child.terminate()
        child.wait(timeout=10)
