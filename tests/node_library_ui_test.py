"""Private host test: consent, signed node membership, art and offline cache."""
import argparse
import contextlib
import hashlib
import http.server
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
from PIL import Image

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]


def capture_window(child, path):
    window = subprocess.check_output(['xdotool', 'search', '--onlyvisible', '--pid', str(child.pid)],
        text=True, timeout=10).splitlines()[0]
    assert int(subprocess.check_output(['xdotool', 'getwindowpid', window], text=True, timeout=10)) == child.pid
    subprocess.run(['import', '-window', window, str(path)], check=True, timeout=10)
    return path


def live_library(binary, driver, work):
    """Use a disposable profile against the real public node; download no game."""
    import time
    from android_catalog import catalog_assets
    with tempfile.TemporaryDirectory(dir=work) as temporary:
        profile = Path(temporary)
        log_path = work / 'live-node.log'
        with log_path.open('w') as log:
            child = subprocess.Popen([str(binary.resolve())], cwd=ROOT,
                env=os.environ | driver.environment() | {'ARCADE_DATA': str(profile),
                    'ENTITY_DATA': str(profile / 'entity'), 'LANG': 'en_US.UTF-8'},
                stdout=log, stderr=subprocess.STDOUT)
            driver.attach(child, log_path)
            try:
                driver.wait(label='Connect', role='button', timeout=60)
                driver.press(label='Connect', role='button')
                driver.wait(label='Apfelwurm Editor', role='button', timeout=60)
                driver.wait(label='Choano', role='button', timeout=60)
                metadata = json.loads((profile / 'node/current.json').read_text())
                assert metadata['app_id'] == 'inbe.arcade'
                source = json.loads((ROOT / 'build/arcade.json').read_text())['node']
                assert metadata['sequence'] >= source['minimum_sequence']
                digest = next(item['sha256'] for item in metadata['artifacts'] if item['variant'] == 'module')
                catalog = catalog_assets((profile / 'node' / (digest + '.zx')).read_bytes())
                art = profile / 'resources/downloads' / (catalog['art']['sha256'] + '.zx')
                deadline = time.monotonic() + 60
                while (not art.exists() or art.stat().st_size != catalog['art']['bytes']) and time.monotonic() < deadline:
                    driver.wait_idle(frames=5)
                assert art.stat().st_size == catalog['art']['bytes']
                with art.open('rb') as stream:
                    assert hashlib.file_digest(stream, 'sha256').hexdigest() == catalog['art']['sha256']
                driver.wait_idle(frames=40)
                card = driver.wait(label='Shovey', role='button')
                with Image.open(capture_window(child, work / 'live-node-library.png')) as image:
                    crop = image.crop((card['x'], card['y'], card['x'] + card['width'], card['y'] + card['height']))
                    assert len(crop.convert('RGB').getcolors(1000000) or []) > 500
                cached = {path.stem for path in (profile / 'resources/downloads').glob('*.zx')}
                assert cached == {catalog['art']['sha256']}, 'No game payload may download during library browsing'
                print('Live node signed catalog and verified thumbnail pixels passed:', metadata['version'])
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=10)


def with_catalog(payload, catalog):
    """Keep the real root program and replace only its fixture catalog asset."""
    assert len(payload) <= 262144
    source = io.BytesIO(payload)
    def number():
        return struct.unpack('<I', source.read(4))[0]
    def text():
        return source.read(number())
    assert source.read(8) == b'ZX\0\0\x1b\0\0\0'
    text(); text()
    for _ in range(number()):
        text(); text()
    for _ in range(number()):
        for _ in range(7):
            text()
        source.read(8); text(); source.read(4)
    for _ in range(number()):
        text(); text(); text()
    source.read(number())
    prefix = payload[:source.tell()]
    assets = {text(): text() for _ in range(number())}
    assert not source.read(1)
    assets[b'assets/apps/catalog.json'] = json.dumps(catalog).encode()
    def packed(value):
        return struct.pack('<I', len(value)) + value
    return prefix + struct.pack('<I', len(assets)) + b''.join(
        packed(name) + packed(value) for name, value in assets.items())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--inbe-source', type=Path, required=True)
    parser.add_argument('--apps-source', type=Path, required=True)
    parser.add_argument('--live', action='store_true', help='Verify the real public node using a disposable profile')
    args = parser.parse_args()
    assert int(os.environ['DISPLAY'].split(':')[-1].split('.')[0]) >= 400
    assert os.environ['YUE_DESKTOP_RECOVERY'] == '0'
    subprocess.run(['git', 'check-ignore', 'work/node-library-ui/data'], cwd=ROOT, check=True)
    sys.path[:0] = [str(args.inbe_source / 'tests'), str(args.apps_source / 'tests'), str(ROOT / 'scripts')]
    from ui_driver import UiDriver
    from remote_catalog_test import descriptor
    from android_catalog import catalog_assets
    work = ROOT / 'work/node-library-ui'
    work.mkdir(parents=True, exist_ok=True)
    driver = UiDriver(work / 'driver')
    if args.live:
        live_library(args.binary, driver, work)
        return
    key = Ed25519PrivateKey.generate()
    seed = (ROOT / 'build/arcade.zx').read_bytes()
    catalog = catalog_assets(seed)
    entry = next(child for child in catalog['children'] if child['expected_id'] == 'shovey')
    first_entry = dict(entry, title='Node Shovey')
    if 'cover' in entry:
        first_entry['cover'] = dict(entry['cover'], caption='Node Shovey')
    first = dict(catalog, children=[first_entry])
    payloads = [with_catalog(seed, first), with_catalog(seed, catalog)]
    digests = [hashlib.sha256(data).hexdigest() for data in payloads]
    state = {'revision': 0, 'requests': []}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            state['requests'].append(self.path)
            relative = self.path.removeprefix('/api/v2/packages/inbe.arcade/')
            if relative.startswith('latest?'):
                index = state['revision']
                data = json.dumps(descriptor(key, payloads[index], 196 + index, module_api=2)).encode()
            elif relative.removesuffix('.zx') in digests:
                data = payloads[digests.index(relative.removesuffix('.zx'))]
            else:
                package = ROOT / 'build/node-apps/arcade.games' / relative
                if not package.is_file():
                    self.send_error(404)
                    return
                data = package.read_bytes()
            self.send_response(200)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    origin = f'http://127.0.0.1:{server.server_port}'
    try:
        with tempfile.TemporaryDirectory(dir=work) as temporary:
            folder = Path(temporary)
            app = folder / 'app'
            app.mkdir()
            shutil.copy2(args.binary, app / 'arcade')
            for name in ('arcade.zx', 'apps.zx', 'entity.zx'):
                shutil.copyfile(ROOT / 'build' / name, app / name)
            receipt = json.loads((ROOT / 'build/arcade.json').read_text())
            receipt['node'] = dict(origin=origin, app_id='inbe.arcade', key_id='fixture-2026', minimum_sequence=195,
                public_key=key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex())
            (app / 'arcade.json').write_text(json.dumps(receipt))
            profile = folder / 'data'
            save = profile / 'games/inbe.chess/records/computer'
            save.parent.mkdir(parents=True)
            save.write_bytes(b'prior saved game')

            @contextlib.contextmanager
            def application(name):
                log_path = work / (name + '.log')
                with log_path.open('w') as log:
                    child = subprocess.Popen([str(app / 'arcade')], cwd=app,
                        env=os.environ | driver.environment() | {'ARCADE_DATA': str(profile),
                            'ENTITY_DATA': str(profile / 'entity'), 'LANG': 'en_US.UTF-8'},
                        stdout=log, stderr=subprocess.STDOUT)
                    driver.attach(child, log_path)
                    try:
                        yield child
                    finally:
                        if child.poll() is None:
                            child.terminate()
                        child.wait(timeout=10)

            def capture(child, name):
                return capture_window(child, work / (name + '.png'))

            def resize(child, width, height):
                window = subprocess.check_output(['xdotool', 'search', '--onlyvisible', '--pid', str(child.pid)],
                    text=True, timeout=10).splitlines()[0]
                subprocess.run(['xdotool', 'windowsize', window, str(width), str(height)], check=True, timeout=10)
                # The previous tree may already be stable while X11's resize
                # event is still queued. Wait for the accepted viewport first.
                import time
                deadline = time.monotonic() + 10
                while max(node['width'] for node in driver.tree()) != width:
                    assert time.monotonic() < deadline, 'The host did not accept the new viewport'
                    time.sleep(0.05)
                driver.wait_idle(frames=20)

            with application('consent-refresh') as child:
                driver.wait(label='Connect', role='button')
                driver.wait_idle(frames=20)
                assert not state['requests'], 'No node traffic before consent'
                capture(child, 'consent')
                resize(child, 360, 740)
                capture(child, 'phone-consent')
                resize(child, 1000, 820)
                driver.press(label='Stay offline', role='button')
                driver.wait(label='Shovey', role='button')
                driver.wait_idle(frames=20)
                assert not state['requests'], 'Offline choice must prevent preview downloads'
                driver.press(label='Node connection', role='button')
                driver.wait(label='Connect', role='button')
                driver.press(label='Connect', role='button')
                driver.wait(label='Node Shovey', role='button', timeout=60)
                assert not driver.find(label='Choano', role='button'), 'Membership must come from the signed node catalog'
                driver.wait_idle(frames=60)
                assert any(path.endswith(catalog['art']['sha256'] + '.zx') for path in state['requests']), 'Node previews must be fetched'
                assert driver.find(role='image', visible=True), 'Verified previews must draw'
                card = driver.wait(label='Node Shovey', role='button')
                assert card['y'] >= 88, 'The library must leave room for its connection controls'
                with Image.open(capture(child, 'node-library')) as image:
                    crop = image.crop((card['x'], card['y'], card['x'] + card['width'], card['y'] + card['height']))
                    assert len(crop.convert('RGB').getcolors(1000000) or []) > 500, 'The preview must paint actual image pixels'
                game_hashes = {entry['sha256'] for entry in catalog['children']}
                assert not any(any(digest in path for digest in game_hashes) for path in state['requests']), 'No game payload before Download'
                state['revision'] = 1
                driver.press(label='Refresh library', role='button')
                driver.wait(label='Choano', role='button', timeout=60)
                driver.wait(label='Apfelwurm Editor', role='button')
                driver.wait_idle(frames=20)
                capture(child, 'refreshed-library')
                resize(child, 360, 740)
                capture(child, 'phone-library')
                resize(child, 1000, 820)
                assert save.read_bytes() == b'prior saved game'
                driver.press(label='Node connection', role='button')
                driver.wait(label='Stay offline', role='button')
                driver.press(label='Stay offline', role='button')
                driver.wait(label='Choano', role='button')
                driver.wait_idle(frames=10)
                count = len(state['requests'])
                driver.wait_idle(frames=40)
                assert len(state['requests']) == count, 'Revocation must stop node traffic'
            with application('cached-offline'):
                driver.wait(label='Choano', role='button', timeout=60)
                driver.wait(label='Apfelwurm Editor', role='button')
                driver.wait_idle(frames=40)
                assert len(state['requests']) == count, 'Saved offline choice and signed catalog must survive restart'
                assert save.read_bytes() == b'prior saved game'
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    print('Arcade node consent, signed membership refresh, preview rendering, game download consent and offline restart passed')


if __name__ == '__main__':
    main()
