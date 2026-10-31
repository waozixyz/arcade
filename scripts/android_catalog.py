"""Strict content boundary for the thin Android Arcade launcher."""
import hashlib
import io
import json
import struct
import subprocess
from functools import lru_cache
from pathlib import Path
from node_config import node_source

ROOT = Path(__file__).resolve().parents[1]
ESSENTIALS = {'arcade.zx', 'arcade.json', 'apps.zx', 'entity.zx', 'kryon-font.ttf'}


@lru_cache(maxsize=1)
def profile_asset_hashes():
    flags = [] if (ROOT / 'ziran.local.toml').is_file() else ['--locked']
    package = Path(subprocess.check_output(
        [str(ROOT / 'scripts/ziran.sh'), 'pkg', 'path', 'entity', *flags],
        cwd=ROOT, text=True).strip())
    paths = json.loads((package / 'asset-groups.json').read_text())['profile']
    result = {}
    for path in paths:
        with (package / path).open('rb') as source:
            result[path] = hashlib.file_digest(source, 'sha256').hexdigest()
    return result


def profile_assets():
    return set(profile_asset_hashes())


def bundle_assets(payload, limit):
    # The catalog is tiny. Reject packed collections before allocating/reading
    # their contents, then inspect every actual asset rather than path strings
    # in the JSON (which intentionally names remote game and art resources).
    assert len(payload) <= limit, 'Bundle exceeds its asset policy budget'
    stream = io.BytesIO(payload)
    def take(size):
        assert 0 <= size <= len(payload), 'Invalid bundle field'
        data = stream.read(size)
        assert len(data) == size, 'Truncated bundle'
        return data
    def number():
        return struct.unpack('<I', take(4))[0]
    def text():
        return take(number())
    # ZX 26 and 27 share this layout; 27 only marks composed library modules.
    assert take(8) in (b'ZX\0\0\x1a\0\0\0', b'ZX\0\0\x1b\0\0\0'), 'Unsupported catalog bundle'
    text(); text()
    for _ in range(number()):
        text(); text()
    for _ in range(number()):
        for _ in range(7):
            text()
        take(8); text(); take(4)
    for _ in range(number()):
        text(); text(); text()
    take(number())
    assets = {}
    for _ in range(number()):
        name = text().decode()
        assert name not in assets, 'Duplicate bundle asset'
        assets[name] = take(number())
    assert not stream.read(1), 'Trailing bundle bytes'
    return assets


def catalog_assets(payload):
    assets = bundle_assets(payload, 256 * 1024)
    assert set(assets) == {'assets/apps/catalog.json', 'assets/arcade/sidebar.shape'}, 'Game payload or art bundled in Arcade'
    return json.loads(assets['assets/apps/catalog.json'])


def verify_assets(assets, essentials=True, edition='direct'):
    expected = ESSENTIALS if essentials else ESSENTIALS - {'entity.zx', 'kryon-font.ttf'}
    if essentials and edition == 'gplay':
        # AndroidX's generated ART startup profiles accompany Play Billing.
        expected = expected | {'dexopt/baseline.prof', 'dexopt/baseline.profm'}
    assert set(assets) == expected, 'Unexpected or missing Android asset: ' + str(set(assets) ^ expected)
    metadata = json.loads(assets['arcade.json'])
    assert metadata['id'] == 'inbe.arcade' and metadata.get('games') != 'packed'
    assert metadata.get('node') == node_source(ROOT), 'Node publisher binding differs from the reviewed host configuration'
    assert hashlib.sha256(assets['arcade.zx']).hexdigest() == metadata['sha256']
    trusted = (ROOT / 'apps-controller.sha256').read_text().strip()
    assert hashlib.sha256(assets['apps.zx']).hexdigest() == metadata['apps_sha256'] == trusted
    if essentials:
        pictures = bundle_assets(assets['entity.zx'], 16 * 1024 * 1024)
        assert set(pictures) == profile_assets(), 'Entity contains undeclared or game artwork'
        assert {name: hashlib.sha256(data).hexdigest() for name, data in pictures.items()} == profile_asset_hashes(), 'Entity profile artwork differs from its pinned declaration'
        assert not bundle_assets(assets['apps.zx'], 2 * 1024 * 1024), 'Apps controller must contain no art or game payloads'
    catalog = catalog_assets(assets['arcade.zx'])
    assert catalog['children'] == metadata['children'] and catalog['art'] == metadata['art']
    assert catalog['harness'] == 'assets/apps/apps.zx'
    return metadata
