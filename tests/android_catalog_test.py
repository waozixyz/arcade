"""Assert the actual staged/packaged Android assets contain no games or art."""
import json
import importlib.util
from pathlib import Path
import sys
import struct
import hashlib
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from android_catalog import verify_assets


class AndroidCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('android_builder', ROOT / 'scripts/build-android.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        builder.stage_arcade()

    def setUp(self):
        self.assets = {name: (ROOT / 'build' / name).read_bytes()
                       for name in ('arcade.zx', 'arcade.json', 'apps.zx', 'entity.zx')}
        self.assets['kryon-font.ttf'] = b'font'  # Content boundary, not a font renderer.

    def test_standard_catalog(self):
        verify_assets(self.assets)

    def test_reject_game_or_thumbnail_beside_catalog(self):
        for name in ('games/shovey.zx', 'covers/shovey.png'):
            with self.subTest(name=name), self.assertRaises(AssertionError):
                verify_assets(self.assets | {name: b'payload'})

    def test_reject_packed_collection(self):
        with self.assertRaises(AssertionError):
            verify_assets(self.assets | {'arcade.zx': b'packed' * 100000})

    def test_reject_game_or_art_inside_bundle(self):
        def number(n):
            return struct.pack('<I', n)
        def text(data):
            return number(len(data)) + data
        # Structurally valid ZX with a catalog and an extra embedded asset.
        for path in (b'assets/arcade/games/test.zx', b'assets/arcade/covers/test.png'):
            payload = b'ZX\0\0\x1b\0\0\0' + text(b'') * 2 + number(0) * 4
            payload += number(2) + text(b'assets/apps/catalog.json') + text(b'{}')
            payload += text(path) + text(b'payload')
            metadata = json.loads(self.assets['arcade.json'])
            metadata['sha256'] = hashlib.sha256(payload).hexdigest()
            with self.subTest(path=path), self.assertRaisesRegex(AssertionError, 'Game payload or art'):
                verify_assets(self.assets | {'arcade.zx': payload, 'arcade.json': json.dumps(metadata).encode()})

    def test_reject_game_art_nested_in_entity(self):
        from android_catalog import profile_assets
        def text(data):
            return struct.pack('<I', len(data)) + data
        names = sorted(profile_assets() | {'assets/entity/game-art.png'})
        payload = b'ZX\0\0\x1b\0\0\0' + text(b'') * 2 + struct.pack('<IIII', 0, 0, 0, 0)
        payload += struct.pack('<I', len(names))
        payload += b''.join(text(name.encode()) + text(b'image') for name in names)
        with self.assertRaisesRegex(AssertionError, 'Entity contains'):
            verify_assets(self.assets | {'entity.zx': payload})

    def test_reject_modified_profile_art(self):
        from android_catalog import profile_assets
        def text(data):
            return struct.pack('<I', len(data)) + data
        names = sorted(profile_assets())
        payload = b'ZX\0\0\x1b\0\0\0' + text(b'') * 2 + struct.pack('<IIII', 0, 0, 0, 0)
        payload += struct.pack('<I', len(names))
        payload += b''.join(text(name.encode()) + text(b'changed image') for name in names)
        with self.assertRaisesRegex(AssertionError, 'profile artwork differs'):
            verify_assets(self.assets | {'entity.zx': payload})

    def test_reject_packed_policy(self):
        metadata = json.loads(self.assets['arcade.json']) | {'games': 'packed'}
        with self.assertRaises(AssertionError):
            verify_assets(self.assets | {'arcade.json': json.dumps(metadata).encode()})

    def test_reject_unreviewed_controller(self):
        with self.assertRaises(AssertionError):
            verify_assets(self.assets | {'apps.zx': b'altered'})

    def test_staged_android_assets(self):
        folder = ROOT / 'build/android-assets'
        if not folder.exists():
            self.skipTest('Run make android to stage Android assets')
        verify_assets({str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob('*') if p.is_file()} |
                      {'entity.zx': (ROOT / 'build/entity.zx').read_bytes()})


if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1].endswith('.apk'):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('apk')
        parser.add_argument('--edition', choices=('direct', 'fdroid', 'gplay'), default='direct')
        args = parser.parse_args()
        with zipfile.ZipFile(args.apk) as apk:
            verify_assets({name[7:]: apk.read(name) for name in apk.namelist()
                           if name.startswith('assets/') and not name.endswith('/')}, edition=args.edition)
        print('APK contains only the thin catalog and host essentials')
    else:
        unittest.main()
