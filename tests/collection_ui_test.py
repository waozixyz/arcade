"""Exercise the real shared library and both unchanged games privately."""
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
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if driver.find(label='Connect', role='button', visible=True):
            driver.press(label='Connect', role='button')
            break
        if driver.find(label='Shovey', role='button', visible=True):
            break
        driver.wait_idle(frames=3)
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

@contextlib.contextmanager
def package_server(root):
    metadata = json.loads((root / 'build/arcade.json').read_text())
    by_digest = {entry['sha256']: entry for entry in metadata['children']}
    state = {'requests': [], 'corrupt_wurm': False, 'corrupt_shovey': False, 'offline': False}
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
    output = root / "build/collection-ui-test"
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
                                      "LANG": "en_US.UTF-8", "ARCADE_PACKAGE_ORIGIN": origin},
                                     stdout=log, stderr=subprocess.STDOUT)
            driver.attach(child, log_path)
            try:
                driver.tree()
                yield child
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
        driver.wait(label="Arcade", role="text")
        assert not driver.find(label="Chess"), "Chess is temporarily disabled"
        assert not driver.find(label="Monkey"), "Monkey does not belong in Arcade"
        assert not driver.find(label="Next", role="button"), "Arcade must open on its app grid"
        classic_card = driver.wait(label="Shovey", role="button")
        editor_card = driver.wait(label="Shovey Editor", role="button")
        assert classic_card['y'] == editor_card['y'], "Apps must share a grid row"
        assert classic_card['x'] != editor_card['x']
        if phone:
            # Phones show small covers, two or three a row.
            wurm_card = driver.wait(label='Apfelwurm', role='button')
            assert wurm_card['y'] == classic_card['y'], 'A phone row holds all three covers'
            assert 100 <= classic_card['width'] < 200, 'Phone covers must be small cards'
        else:
            assert classic_card['width'] >= 200 and classic_card['height'] >= 350
        assert not driver.find(label='Play', role='button')
        assert not driver.find(label='Open', role='button')
        for label in ('Shovey', 'Shovey Editor', 'Apfelwurm'):
            assert driver.find(label=label, role='text'), 'Every library cover shows its declared title'
        driver.wait(label='Apfelwurm', role='button', visible=False)
        smallest = (100, 140) if phone else (180, 200)
        covers = [node for node in driver.find(role='image', visible=True)
                  if node['width'] >= smallest[0] and node['height'] >= smallest[1]]
        assert len(covers) >= 2, "Apps must use large title-screen artwork"
        capture(child, name)
        with Image.open(output / (name + ".png")) as image:
            assert len(image.convert("RGB").getcolors(1000000) or []) > 100, "App icons were not painted"

    def primary_download(label='Download'):
        driver.wait(label=label, role='button')
        actions = driver.find(label=label, role='button', visible=True)
        action = max(actions, key=lambda node: node['width'])
        driver.press(key=action['key'], role='button')

    with package_server(root) as (origin, server), tempfile.TemporaryDirectory(prefix="profile-", dir=output) as temporary:
        profile = Path(temporary)
        dependency_profile = profile / 'editor-first'
        with application(dependency_profile, 'editor-dependencies') as child:
            answer_library_question(driver)
            driver.press(label='Shovey Editor', role='button')
            driver.wait(label='Shovey (required) · ' + sizes['shovey'], role='text')
            driver.wait(label='Shovey Editor · ' + sizes['shovey-editor'], role='text')
            total = size_text(by_name['shovey']['bytes'] + by_name['shovey-editor']['bytes'])
            driver.wait(label='Download size: ' + total, role='text')
            capture(child, 'editor-download-plan')
            driver.press(label='Cancel', role='button')
            assert not games & set(server['requests']), 'Dependency consent must precede every download'
            driver.press(label='Shovey Editor', role='button')
            server['corrupt_shovey'] = True
            primary_download()
            driver.wait(label='Try again', role='button', timeout=60)
            assert not driver.find(label='New level', role='text'), 'An editor must not open with a corrupt dependency'
            server['corrupt_shovey'] = False
            primary_download('Try again')
            driver.wait(label='New level', role='text', timeout=60)
            capture(child, 'editor-shared-assets')
            assert server['requests'].count(by_name['shovey']['sha256']) == 2
            assert server['requests'].count(by_name['shovey-editor']['sha256']) == 1
            assert len([digest for digest in server['requests'] if digest in games]) == 3, 'Retry must reuse the already downloaded editor'
            assert by_name['shovey-editor']['bytes'] < by_name['shovey']['bytes'], 'The editor must carry only its additions'
        server['requests'].clear()
        # Disabling an entry must leave a person's older Chess save untouched.
        chess = profile / "games/inbe.chess/records/computer"
        chess.parent.mkdir(parents=True)
        chess.write_bytes(b"existing private Chess save")
        # Active play stays on this device; account sync shares completions.
        record = profile / "games/arcade.shovey/records/local.campaign"

        def progress(data):
            # Unlocks, completion marks and the board in play.
            value = data.decode()
            assert value[:2] in ("C2", "C3", "C4", "C5")
            start = value.index("P")
            state = value[start:]
            assert state[:2] in ("P1", "P2", "P3")
            return value[:start], state[:32]

        with application(profile, "grid") as child:
            # A fresh profile asks for consent before it shows the library.
            answer_library_question(driver)
            window = subprocess.check_output(['xdotool', 'search', '--onlyvisible', '--pid', str(child.pid)], text=True).splitlines()[0]
            subprocess.run(['xdotool', 'windowsize', window, '480', '820'], check=True)
            grid(child, "apps-portrait", phone=True)
            assert not games & set(server['requests']), "Covers must not predownload games"
            # Covers show only the art; the download dialog names the size.
            cover_sizes = dict(sizes, **{'shovey-editor': size_text(by_name['shovey']['bytes'] + by_name['shovey-editor']['bytes'])})
            for text in cover_sizes.values():
                assert not driver.find(label=text, role='text'), "Covers must not show download sizes"
            driver.press(label='Profile', role='button')
            driver.wait(label='Account', role='text')
            capture(child, 'arcade-profile')
            driver.press(label='Leaderboard', role='button')
            driver.wait(label='Leaderboard', role='text')
            driver.wait(label='No leaderboard data yet.', role='text')
            capture(child, 'leaderboard-empty')
            driver.press(label='Back', role='button')
            driver.wait(label='Account', role='text')
            driver.press(label="Back", role="button")
            driver.wait(label='Shovey', role='button')
            assert not [path for path in (profile / 'resources/downloads').glob('*.zx') if path.stem in games]
            driver.press(label="Shovey", role="button")
            driver.wait(label='Cancel', role='button')
            driver.press(label='Cancel', role='button')
            assert not games & set(server['requests']), 'Cancel must download nothing'
            driver.press(label="Shovey", role="button")
            primary_download()
            driver.wait(label=f"Level 1 / {classic}")
            answer_level_updates(driver)
            driver.wait(label="How do you want to move?", role="text")
            driver.press(label="Swipe and tap")
            driver.wait_gone(label="How do you want to move?", role="text")
            assert not driver.find(label="Play", role="button"), "Arcade must skip the second title screen"
            assert len(driver.find(label="Back", role="button", visible=True)) == 1
            driver.press(label="Levels", role="button")
            driver.wait(label="Continue", role="button")
            back = driver.wait(label="Back", role="button", visible=True)
            assert back['width'] >= 100 and back['height'] >= 48
            scroll = driver.wait(role="scroll")
            driver.pointer(*UiDriver.center(scroll), wheel=-200)
            driver.wait_idle(frames=20)
            assert driver.find(label="Back", role="button", visible=True)[0]['y'] == back['y']
            driver.press(label="Back", role="button")
            driver.wait(label="Restart", role="button")
            driver.press(label="Levels", role="button")
            driver.wait(label="Continue", role="button")
            driver.key("escape")
            driver.wait(label="Restart", role="button")
            capture(child, "classic-playing")
            for direction in ("left", "right", "up", "down"):
                driver.key(direction)
                driver.wait_idle(frames=5)
            saved = wait(lambda: record.read_bytes() if record.exists() else None, "Classic did not save")
            driver.press(label="Back", role="button")
            driver.wait(label="Shovey Editor", role="button")
            driver.press(label='Profile', role='button')
            driver.press(label='Leaderboard', role='button')
            driver.wait(label='Shovey', role='button')
            assert not driver.find(label='Apfelwurm', role='button'), 'An undownloaded game has a board'
            assert not driver.find(label='Shovey Editor', role='button'), 'An unranked editor has a board'
            capture(child, 'leaderboard-installed')
            state = profile / 'resources/state/arcade.shovey.json'
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text('{"v":1,"installed":0,"favorite":0}')
            driver.wait(label='No leaderboard data yet.', role='text')
            assert not driver.find(label='Shovey', role='button'), 'A retained score kept an uninstalled board visible'
            state.write_text('{"v":1,"installed":1,"favorite":0}')
            driver.wait(label='Shovey', role='button')
            driver.press(label='Back', role='button')
            driver.wait(label='Account', role='text')
            driver.press(label='Back', role='button')
            driver.wait(label='Shovey Editor', role='button')
            assert not driver.find(label=sizes["shovey"], role="text"), "Installed games must omit their download size"
            driver.press(label="Shovey Editor", role="button")
            driver.wait(label='Download size: ' + sizes['shovey-editor'], role='text')
            primary_download()
            assert server['requests'].count(by_name['shovey']['sha256']) == 1, 'Installed dependencies must not download again'
            # The editor opens on a blank board.
            driver.wait(label="New level", role="text")
            driver.press(label="Levels", role="button")
            driver.wait(label="Story levels", role="text")
            back = driver.wait(label="Back", role="button", visible=True)
            assert back['width'] >= 100 and back['height'] >= 48
            driver.press(label="Back", role="button")
            driver.wait(label="New level", role="text")
            capture(child, "editor-open")
            driver.key("escape")
            driver.wait(label="Shovey Editor", role="button")
            window = subprocess.check_output(["xdotool", "search", "--onlyvisible", "--pid", str(child.pid)], text=True).splitlines()[0]
            subprocess.run(["xdotool", "windowsize", window, "900", "540"], check=True)
            grid(child, "apps-landscape")
            server['corrupt_wurm'] = True
            driver.press(label='Apfelwurm', role='button')
            primary_download()
            driver.wait(label='Try again', role='button', timeout=60)
            assert not driver.find(label='Pause', role='button'), 'Unverified bytes must never run'
            server['corrupt_wurm'] = False
            primary_download('Try again')
            # The hosted player opens its title before its first steering choice.
            driver.wait(label='Play', role='button', timeout=60)
            driver.press(label='Play', role='button')
            driver.wait(label='How do you want to move?', role='text')
            driver.press(label='Swipe', role='button')
            driver.wait(label='Pause', role='button')
            capture(child, 'wurm-playing')
            driver.press(label='Pause', role='button')
            driver.wait(label='Resume', role='button')
            driver.press(label='Back to title', role='button')
            driver.wait(label='Play', role='button')
            capture(child, 'wurm-title')
            driver.key('escape')
            driver.wait(label='Shovey', role='button')
            for entry in json.loads((root / 'build/arcade.json').read_text())['children']:
                path = profile / 'resources/downloads' / (entry['sha256'] + '.zx')
                assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256']
            requested = list(server['requests'])
            server['offline'] = True
        with application(profile, "restore", "--app", "arcade.shovey"):
            driver.wait(label=f"Level 1 / {classic}")
            assert progress(record.read_bytes()) == progress(saved), "Classic progress changed on restart"
        assert server['requests'] == requested, 'A cached game must reopen offline without downloading'
        assert chess.read_bytes() == b"existing private Chess save"
        assert not (profile / "inbe.db").exists()
        refused = subprocess.run([str(args.binary.resolve()), "--app", "chess"], env=os.environ | {"ARCADE_DATA": str(profile)}, capture_output=True, timeout=10)
        assert refused.returncode == 1 and b"unknown game" in refused.stderr
    print("Arcade: rounded covers, download consent/cancel, digest failure/retry, Shovey and Apfelwurm play, Back, rotation, offline reopen and retained saves passed")


if __name__ == "__main__":
    main()
