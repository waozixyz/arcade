"""Exercise the real shared library and normal game titles and console navigation privately."""
import argparse
import contextlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from PIL import Image



LEVEL_UPDATES = 'Download new levels when they come out?'

def answer_library_question(driver):
    """Consent to the loopback library, keeping bundled game levels."""
    question = 'Allow fetching content and automatic app updates?'
    driver.wait(label=question, role='text')
    driver.wait(label='The app library, previews and the apps you’ve downloaded stay up to date automatically.', role='text')
    driver.wait(label='Stay offline', role='button')
    driver.press(label='Allow', role='button')
    driver.wait_gone(label=question, role='text')
    driver.wait(label='Shovey', role='button', timeout=60)
    if driver.find(label=LEVEL_UPDATES, role='text'):
        driver.press(label='Not now', role='button')
        driver.wait_gone(label=LEVEL_UPDATES, role='text')



def answer_level_updates(driver, timeout=20):
    """An installed Shovey first asks once whether to download new levels;
    tests keep the levels it ships with. Returns once a level takes input
    or asks how to move."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if driver.find(label=LEVEL_UPDATES, role='text'):
            driver.press(label='Not now', role='button')
            driver.wait_gone(label=LEVEL_UPDATES, role='text')
            return
        if driver.find(label='How do you want to move?', role='text') or driver.find(label='Restart', role='button'):
            return
        time.sleep(0.05)

def campaign_progress(data):
    # Keep unlocks/completions and the player/move state, allowing decorative
    # animals to animate independently while an installed game is open.
    value = data.decode()
    assert value[:2] in ("C2", "C3", "C4", "C5", "C6")
    start = value.index("P")
    state = value[start:]
    assert state[:2] in ("P1", "P2", "P3")
    return value[:start], state[:32]


def enter_shovey_play(driver):
    """Use the game's normal title and, where present, its world map."""
    driver.wait(label='Play', role='button', timeout=60)
    driver.press(label='Play', role='button')
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if driver.find(key=20105, visible=True):
            driver.press(key=33001, role='button')
            driver.press(key=20122, role='button')
            return
        if driver.find(label='Restart', role='button') or driver.find(label=LEVEL_UPDATES, role='text'):
            return
        if driver.find(label='Continue', role='button'):
            driver.press(label='Continue', role='button')
            return
        time.sleep(.05)
    raise driver._failure('Shovey did not enter its normal map or gameplay')


def enter_wurm_play(driver):
    """The title opens the stage chooser, whose Play starts the game."""
    driver.wait(label='Play', role='button', timeout=60)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if driver.find(label='Pause', role='button'):
            return
        if driver.find(label='How do you want to move?', role='text'):
            driver.press(label='Swipe', role='button')
        elif driver.find(label='Play', role='button'):
            driver.press(label='Play', role='button')
        elif driver.find(label='Start', role='button'):
            driver.press(label='Start', role='button')
        time.sleep(.05)
    raise driver._failure('Apfelwurm did not enter play through its title and stages')


@contextlib.contextmanager
def package_server(root):
    metadata = json.loads((root / 'build/arcade.json').read_text())
    by_digest = {entry['sha256']: entry for entry in metadata['children']}
    state = {'requests': [], 'corrupt_wurm': False, 'corrupt_shovey': False, 'offline': False, 'game_delay': 0}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            digest = self.path.removeprefix('/api/v2/packages/inbe.arcade/').removesuffix('.zx')
            state['requests'].append(digest)
            # Every published file: the games and the library art.
            published = root / 'build/node-apps/arcade.games' / (digest + '.zx')
            if state['offline'] or not published.is_file():
                self.send_error(503)
                return
            entry = by_digest.get(digest, {})
            data = published.read_bytes()
            if (state['corrupt_wurm'] and entry.get('expected_id') == 'wurm') or (state['corrupt_shovey'] and entry.get('expected_id') == 'shovey'):
                data = data[:-1] + bytes([data[-1] ^ 1])
            if entry and state['game_delay']:
                time.sleep(state['game_delay'])
            self.send_response(200)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:' + str(server.server_port), state
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--inbe-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Private test receipts and captures")
    args = parser.parse_args()
    assert int(os.environ["DISPLAY"].split(":")[-1].split(".")[0]) >= 400
    assert os.environ["YUE_DESKTOP_RECOVERY"] == "0"
    root = Path(__file__).resolve().parents[1]
    entries = json.loads((root / 'build/arcade.json').read_text())['children']
    by_name = {entry['expected_id']: entry for entry in entries}
    # The library art downloads with Arcade; games only after consent.
    games = {entry['sha256'] for entry in entries}
    def size_text(size):
        return f"{(size * 10 + 500000) // 1000000 / 10:.1f} MB"
    sizes = {name: size_text(entry['bytes']) for name, entry in by_name.items()}
    output = args.output or root / "work/collection-ui-test"
    # The Classic heading counts its levels, which Shovey's level file lists.
    shovey = Path(subprocess.check_output([str(root / "scripts/ziran.sh"), "pkg", "path", "shovey"], text=True).strip())
    classic = len(json.loads((shovey / "levels/approved.json").read_text())["levels"])
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(args.inbe_source / "tests"))
    from ui_driver import UiDriver
    driver = UiDriver(output / "driver")

    @contextlib.contextmanager
    def application(profile, name, *arguments):
        log_path = output / (name + ".log")
        with log_path.open("w") as log:
            child = subprocess.Popen([str(args.binary.resolve()), *arguments], cwd=root,
                                     env=os.environ | driver.environment() |
                                     {"ARCADE_DATA": str(profile), "ENTITY_DATA": str(profile / "entity"),
                                      "XDG_DATA_HOME": str(profile / "share"),
                                      "XDG_CONFIG_HOME": str(profile / "config"),
                                      "XDG_CACHE_HOME": str(profile / "cache"),
                                      "LANG": "en_US.UTF-8", "ARCADE_PACKAGE_ORIGIN": origin},
                                     stdout=log, stderr=subprocess.STDOUT)
            driver.attach(child, log_path)
            try:
                driver.tree()
                yield child
            except Exception:
                driver.tree()
                (output / (name + '-failure-tree.json')).write_text(json.dumps(driver.last, indent=2) + '\n')
                capture(child, name + '-failure')
                raise
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=10)

    def wait(predicate, message):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if value := predicate():
                return value
            time.sleep(.05)
        raise driver._failure(message)

    def capture(child, name):
        window = subprocess.check_output(
            ["xdotool", "search", "--onlyvisible", "--pid", str(child.pid)], text=True, timeout=10).splitlines()[0]
        assert int(subprocess.check_output(["xdotool", "getwindowpid", window], text=True, timeout=10)) == child.pid
        subprocess.run(["import", "-window", window, str(output / (name + ".png"))], check=True, timeout=10)

    def grid(child, name, phone=False):
        driver.wait_idle(frames=20)
        assert not driver.find(label="Arcade", role="text"), "Home has no app-name header"
        assert not driver.find(label="Chess"), "Chess is temporarily disabled"
        assert not driver.find(label="Monkey"), "Monkey does not belong in Arcade"
        covers = [node for node in driver.find(role="button", visible=True)
                  if node['height'] > 100 and node['selected']]
        assert len(covers) == 1
        cover = covers[0]
        ratio = cover['width'] / cover['height']
        assert abs(ratio - (2 / 3 if phone else 16 / 9)) < .02, (name, ratio)
        assert cover['width'] >= (250 if phone else 200)
        assert cover['selected'], "A console always has a focused game"
        assert not driver.find(label='Play', role='button')
        assert not driver.find(label='Open', role='button')
        for label in ('Shovey', 'Apfelwurm', 'Choano'):
            assert not driver.find(label=label, role='text'), "Artwork replaces cover captions"
            if not phone or label == cover['label']:
                assert driver.find(label=label, role='button'), "Names stay accessible in the shelf"
        assert not driver.find(label='Shovey Editor', role='button'), 'Editors open from inside their game'
        assert not driver.find(label='Apfelwurm Editor', role='button')
        assert len([node for node in driver.find(role='image', visible=True)
                    if node['width'] >= 150 and node['height'] >= 100]) >= 1
        capture(child, name)
        with Image.open(output / (name + ".png")) as image:
            assert len(image.convert("RGB").getcolors(1000000) or []) > 100, "Cover artwork was not painted"
            # Full viewport art must cover the former light host reservation.
            top = image.convert('RGB').crop((0, 0, image.width // 2, 88))
            pixels = list(top.resize((30, 10)).getdata())
            clear = sum(all(abs(a-b) <= 3 for a,b in zip(pixel, (248, 250, 252))) for pixel in pixels)
            assert clear < len(pixels) // 2, "Home leaves a light header band"
            assert len(set(pixels)) > 20, "Focused art must color the background"

    def open_game(label):
        order = ['Shovey', 'Apfelwurm', 'Choano']
        current = next(n for n in driver.tree() if n['kind']=='button' and n['selected'] and n['height']>100)
        while current['label'] != label:
            driver.key('right' if order.index(current['label']) < order.index(label) else 'left')
            driver.wait_idle(frames=20)
            current = next(n for n in driver.tree() if n['kind']=='button' and n['selected'] and n['height']>100)
        driver.press(key=current['key'],role='button')

    def finish_download(label):
        entry = next(e for e in by_name.values() if e['title']==label)
        wait(lambda: (profile/'resources/downloads'/(entry['sha256']+'.zx')).exists() and
             not driver.find(label='Downloading',role='text'), 'Download did not finish on shelf')
        assert driver.find(label=label,role='button'), 'Download left the shelf'
        open_game(label)

    def primary_download(label='Download'):
        driver.wait(label=label, role='button')
        actions = driver.find(label=label, role='button', visible=True)
        action = max(actions, key=lambda node: node['width'])
        driver.press(key=action['key'], role='button')

    with package_server(root) as (origin, server), tempfile.TemporaryDirectory(prefix="profile-", dir=output) as temporary:
        profile = Path(temporary)
        # Disabling an entry must leave a person's older Chess save untouched.
        chess = profile / "games/inbe.chess/records/computer"
        chess.parent.mkdir(parents=True)
        chess.write_bytes(b"existing private Chess save")
        # Active play stays on this device; account sync shares completions.
        record = profile / "games/arcade.shovey/records/local.campaign"


        with application(profile, "grid") as child:
            # A fresh profile asks for consent before it shows the library.
            answer_library_question(driver)
            window = subprocess.check_output(['xdotool', 'search', '--onlyvisible', '--pid', str(child.pid)], text=True).splitlines()[0]
            subprocess.run(['xdotool', 'windowsize', window, '480', '820'], check=True)
            grid(child, "apps-portrait", phone=True)
            driver.key('right')
            driver.wait_idle(frames=20)
            editor = [n for n in driver.find(label='Apfelwurm', role='button') if n['height'] > 100]
            assert editor and editor[0]['selected'], 'Right selects the next game'
            driver.key('left')
            driver.wait_idle(frames=20)
            subprocess.run(['xdotool', 'windowsize', window, '1120', '700'], check=True)
            grid(child, "apps-landscape")
            subprocess.run(['xdotool', 'windowsize', window, '900', '420'], check=True)
            grid(child, "apps-short-landscape")
            selected = [n for n in driver.find(role='button') if n['selected'] and n['height'] > 100][0]
            cx, cy = UiDriver.center(selected)
            driver.pointer(cx, cy, wheel=-1)
            driver.wait_idle(frames=20)
            assert any(n['selected'] and n['height'] > 100 for n in driver.find(label='Apfelwurm', role='button')), 'Wheel selects the next game'
            driver.drag((cx - 100, cy), (cx + 100, cy))
            driver.wait_idle(frames=20)
            assert any(n['selected'] and n['height'] > 100 for n in driver.find(label='Shovey', role='button')), 'Swipe returns to the previous game'
            assert not driver.find(role='modal'), 'A swipe selects without opening an install dialog'
            subprocess.run(['xdotool', 'windowsize', window, '480', '820'], check=True)
            grid(child, "apps-portrait-return", phone=True)
            assert not games & set(server['requests']), "Covers must not predownload games"
            # Covers show only the art; the download dialog names the size.
            cover_sizes = dict(sizes, **{'shovey-editor': size_text(by_name['shovey']['bytes'] + by_name['shovey-editor']['bytes'])})
            for text in cover_sizes.values():
                assert not driver.find(label=text, role='text'), "Covers must not show download sizes"
            (output / 'before-profile-tree.json').write_text(json.dumps(driver.tree(), indent=2))
            reply = driver.press(label='Profile', role='button')
            (output / 'profile-press.json').write_text(json.dumps(reply, indent=2))
            driver.wait(label='Account', role='text')
            capture(child, 'arcade-profile')
            driver.press(label='Back', role='button')
            driver.wait(label='Shovey', role='button')
            assert not [path for path in (profile / 'resources/downloads').glob('*.zx') if path.stem in games]
            server['game_delay'] = 3
            open_game('Shovey')
            driver.wait(label='Downloading',role='text')
            assert driver.find(label='Apfelwurm',role='button'), 'Download must keep the carousel available'
            assert not driver.find(role='modal'), 'Transfer progress must not capture modal focus'
            assert any(n['selected'] and n['height']>100 for n in driver.find(label='Shovey',role='button'))
            finish_download('Shovey')
            server['game_delay'] = 0
            driver.wait(label='Play',role='button',timeout=60)
            assert not driver.find(label="Restart", role="button"), "A game opens its own title"
            capture(child, "shovey-title")
            enter_shovey_play(driver)
            driver.wait(label=f"Level 1 / {classic}")
            answer_level_updates(driver)
            # Desktop input already chooses keyboard controls; touch hosts
            # still ask before the first level.
            if driver.find(label="How do you want to move?", role="text"):
                driver.press(label="Swipe and tap")
                driver.wait_gone(label="How do you want to move?", role="text")
            driver.wait(label='Restart', role='button')
            assert not driver.find(label="Play", role="button"), "Play enters gameplay from the game title"
            assert len(driver.find(label="Back", role="button", visible=True)) == 1
            home = driver.find(label='Arcade', role='button', visible=True)[0]
            back = driver.find(label='Back', role='button', visible=True)[0]
            assert back['y'] >= home['y'] + home['height'], 'Home must not overlap game navigation'
            capture(child, "classic-playing")
            for direction in ("left", "right", "up", "down"):
                driver.key(direction)
                driver.wait_idle(frames=5)
            driver.press(label="Back", role="button")
            driver.wait(label="Play", role="button")
            driver.key(290)
            driver.wait(key=50400,visible=True)
            saved = wait(lambda: record.read_bytes() if record.exists() else None, "Classic did not save")
            assert not driver.find(label=sizes["shovey"], role="text"), "Installed games must omit their download size"
            open_game('Shovey')
            driver.wait(label='Next',role='button')
            driver.press(label='Next',role='button')
            driver.wait_idle(frames=20)
            driver.press(label='Open',role='button')
            driver.wait(label='Download size: ' + sizes['shovey-editor'], role='text')
            primary_download()
            assert server['requests'].count(by_name['shovey']['sha256']) == 1, 'Installed dependencies must not download again'
            # The editor opens on a blank board.
            driver.wait(label="New level", role="text")
            driver.press(label="Levels", role="button")
            driver.wait(label="Your levels", role="text")
            back = driver.wait(label="Back", role="button", visible=True)
            assert back['width'] >= 64 and back['height'] >= 40
            driver.press(label="Back", role="button")
            driver.wait(label="New level", role="text")
            capture(child, "editor-open")
            driver.key("escape")
            driver.wait(label='Open',role='button')
            driver.press(label='Previous',role='button')
            driver.wait(label='Play',role='button')
            assert not driver.find(key=50400,visible=True), 'Editor Back returns to the game title'
            driver.key(290)
            driver.wait(key=50400,visible=True)
            window = subprocess.check_output(["xdotool", "search", "--onlyvisible", "--pid", str(child.pid)], text=True).splitlines()[0]
            subprocess.run(["xdotool", "windowsize", window, "900", "540"], check=True)
            grid(child, "apps-landscape")
            server['corrupt_wurm'] = True
            open_game('Apfelwurm')
            driver.wait(label='Download failed',role='text',timeout=60)
            assert not driver.find(label='Pause', role='button'), 'Unverified bytes must never run'
            server['corrupt_wurm'] = False
            open_game('Apfelwurm')
            finish_download('Apfelwurm')
            # Both the built-in editor and retained add-on open inside Wurm.
            driver.wait(label='Play', role='button', timeout=60)
            driver.press(label='Level editor', role='button')
            driver.wait(label='My levels', role='button')
            driver.press(label='Apfelwurm Editor', role='button')
            driver.wait(label='Cancel', role='button')
            primary_download()
            driver.wait(label='My levels', role='button', timeout=60)
            assert not driver.find(label='Apfelwurm Editor', role='button'), 'A legacy add-on must not link to itself'
            driver.key('escape')
            driver.wait(label='Apfelwurm Editor', role='button')
            driver.press(label='Back', role='button')
            driver.wait(label='Play', role='button')
            enter_wurm_play(driver)
            driver.wait(label='Pause', role='button')
            capture(child, 'wurm-playing')
            driver.press(label='Pause', role='button')
            driver.wait(label='Resume', role='button')
            driver.press(label='Back to title', role='button')
            driver.wait(label='Play', role='button')
            capture(child, 'wurm-title')
            driver.key(290)
            driver.wait(label='Shovey', role='button')
            open_game('Choano')
            finish_download('Choano')
            driver.wait(label='Play', role='button', timeout=60)
            assert not driver.find(label='Pause', role='button'), 'Choano keeps its own title screen'
            driver.press(label='Play', role='button')
            if driver.find(label='Swipe', role='button'):
                driver.press(label='Swipe', role='button')
            driver.wait(label='Pause', role='button', timeout=60)
            driver.key('right')
            driver.press(label='Pause', role='button')
            driver.press(label='Title screen', role='button')
            driver.wait(label='New game', role='button')
            capture(child, 'choano-title')
            subprocess.run(['xdotool', 'windowsize', window, '480', '820'], check=True)
            driver.wait_idle(frames=15)
            driver.press(label='Arcade', role='button')
            driver.wait(label='Shovey', role='button')
            exercised = [by_name[name] for name in ('shovey', 'shovey-editor', 'wurm', 'wurm-editor', 'choano')]
            expected_downloads = {entry['sha256'] for entry in exercised}
            actual_downloads = {path.stem for path in (profile / 'resources/downloads').glob('*.zx') if path.stem in games}
            assert actual_downloads == expected_downloads, 'Only the games opened with consent may download'
            for entry in exercised:
                path = profile / 'resources/downloads' / (entry['sha256'] + '.zx')
                assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256']
            requested = list(server['requests'])
            server['offline'] = True
        with application(profile, "restore", "--app", "arcade.shovey"):
            driver.wait(label="Play", role="button")
            assert not driver.find(label="Restart", role="button"), "Offline reopen retains normal title entry"
            assert campaign_progress(record.read_bytes()) == campaign_progress(saved), "Classic progress changed on restart"
        # Allowed automatic library refresh may retry its metadata while
        # offline. Cached game/art bytes must never be requested again.
        cached_payloads = games | {json.loads((root / 'build/arcade.json').read_text())['art']['sha256']}
        assert not cached_payloads & set(server['requests'][len(requested):]), 'A cached game must reopen offline without downloading'
        assert chess.read_bytes() == b"existing private Chess save"
        assert not (profile / "inbe.db").exists()
        refused = subprocess.run([str(args.binary.resolve()), "--app", "chess"], env=os.environ | {"ARCADE_DATA": str(profile)}, capture_output=True, timeout=10)
        assert refused.returncode == 1 and b"unknown game" in refused.stderr
    print("Arcade: console covers, selection and in-place downloads, digest failure/retry, all three game titles/play, in-game editors, Back, rotation, offline reopen and retained saves passed")


if __name__ == "__main__":
    main()
