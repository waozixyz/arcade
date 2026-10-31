"""Catalog releases advance independently; native APK verification stays strict."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import android_catalog


def load(name, script):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load('collection_versions', 'build-collection.py')
release = load('android_release_versions', 'android-release.py')


class Fixture(unittest.TestCase):
    def setUp(self):
        work = ROOT / 'work'
        work.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix='catalog-versions-', dir=work)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for directory in ('scripts', 'apps', 'catalog'):
            (self.root / directory).mkdir()


class SynchronizerTests(Fixture):
    def setUp(self):
        super().setUp()
        shutil.copyfile(ROOT / 'update_version.sh', self.root / 'update_version.sh')
        (self.root / 'scripts/game_packages.py').write_text(
            "from pathlib import Path\n"
            "def declared_apps(root):\n"
            "    return [dict(descriptor=dict(name='game', id='inbe.game', title='Game', host_api=41),\n"
            "                 manifest=Path('apps/catalog.json'))]\n")
        (self.root / 'CHANGELOG.md').write_text('## [Unreleased]\n\n- Later host.\n\n## 0.7.117\n')
        (self.root / 'VERSION').write_text('0.7.116\n')
        (self.root / 'catalog/CHANGELOG.md').write_text('## 0.7.118\n\n- New games.\n')
        (self.root / 'catalog/VERSION').write_text('0.7.116\n')
        (self.root / 'apps/CHANGELOG.md').write_text('## [1.0.0] - 2026-10-31\n')
        self.original = {'node_apps': {
            'arcade': {'id': 'inbe.arcade', 'version': '0.7.116', 'sequence': 120},
            'game': {'id': 'inbe.game', 'version': '1.0.0', 'sequence': 7}}}
        self.write_ledger(self.original)

    def write_ledger(self, value):
        (self.root / 'apps/versions.json').write_text(json.dumps(value))

    def sync(self, *args, success=True):
        result = subprocess.run(['sh', str(self.root / 'update_version.sh'), *args],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return json.loads((self.root / 'apps/versions.json').read_text())['node_apps']

    def test_catalog_release_never_bumps_host_and_is_idempotent(self):
        ledger = self.sync('--catalog')
        self.assertEqual((self.root / 'VERSION').read_text(), '0.7.116\n')
        self.assertEqual((self.root / 'catalog/VERSION').read_text(), '0.7.118\n')
        self.assertEqual((ledger['arcade']['version'], ledger['arcade']['sequence']), ('0.7.118', 121))
        self.assertEqual(ledger['game'], self.original['node_apps']['game'])
        self.assertEqual(self.sync('--catalog'), ledger)

    def test_host_release_never_advances_catalog_sequence(self):
        (self.root / 'catalog/CHANGELOG.md').write_text('## 0.7.116\n')
        ledger = self.sync()
        self.assertEqual((self.root / 'VERSION').read_text(), '0.7.117\n')
        self.assertEqual(ledger, self.original['node_apps'])
        self.assertEqual(builder.catalog_version(self.root), '0.7.116')

    def test_catalog_release_updates_game_ledger_from_its_own_changelog(self):
        (self.root / 'apps/CHANGELOG.md').write_text('## [1.0.1] - 2026-10-31\n')
        ledger = self.sync('--catalog')
        self.assertEqual((ledger['game']['version'], ledger['game']['sequence']), ('1.0.1', 8))

    def test_catalog_version_cannot_go_back_and_failure_preserves_files(self):
        (self.root / 'catalog/CHANGELOG.md').write_text('## 0.7.115\n')
        ledger = self.sync('--catalog', success=False)
        self.assertEqual(ledger, self.original['node_apps'])
        self.assertEqual((self.root / 'VERSION').read_text(), '0.7.116\n')
        self.assertEqual((self.root / 'catalog/VERSION').read_text(), '0.7.116\n')

    def test_collection_rejects_stale_catalog_ledger(self):
        (self.root / 'catalog/VERSION').write_text('0.7.118\n')
        with self.assertRaisesRegex(ValueError, 'signed release ledger'):
            builder.catalog_version(self.root)

    def test_unknown_switch_does_not_change_versions(self):
        self.sync('--wrong', success=False)
        self.assertEqual((self.root / 'VERSION').read_text(), '0.7.116\n')


def bundle(assets):
    def number(value):
        return struct.pack('<I', value)
    def text(value):
        return number(len(value)) + value
    return (b'ZX\0\0\x1b\0\0\0' + text(b'') * 2 + number(0) * 4 + number(len(assets))
            + b''.join(text(name.encode()) + text(value) for name, value in assets.items()))


class AndroidVerifierTests(Fixture):
    def setUp(self):
        super().setUp()
        (self.root / 'CHANGELOG.md').write_text('## 0.7.117\n')
        (self.root / 'catalog/VERSION').write_text('0.7.116\n')
        controller = bundle({})
        self.controller_digest = hashlib.sha256(controller).hexdigest()
        (self.root / 'apps-controller.sha256').write_text(self.controller_digest)
        catalog = {'children': [], 'art': {'sha256': 'a' * 64, 'bytes': 123},
                   'harness': 'assets/apps/apps.zx'}
        payload = bundle({'assets/apps/catalog.json': json.dumps(catalog).encode(),
                          'assets/arcade/sidebar.shape': b'shape'})
        self.metadata = {'id': 'inbe.arcade', 'version': '0.7.116',
                         'sha256': hashlib.sha256(payload).hexdigest(),
                         'apps_sha256': self.controller_digest, 'children': [], 'art': catalog['art']}
        self.assets = {'assets/arcade.zx': payload, 'assets/apps.zx': controller,
                       'assets/entity.zx': bundle({}), 'assets/kryon-font.ttf': b'font',
                       'res/icon.png': b'icon', 'lib/arm64-v8a/libmain.so': b'arm64',
                       'lib/armeabi-v7a/libmain.so': b'arm', 'classes.dex': b'normal'}
        self.badging = ("package: name='xyz.waozi.arcade' versionCode='121' versionName='0.7.117'\n"
                        "application-label:'Arcade'\napplication: label='Arcade' icon='res/icon.png'\n")
        self.signer = hashlib.sha256(b'certificate').hexdigest()

    def verify(self, edition='direct'):
        apk = self.root / 'fixture.apk'
        with zipfile.ZipFile(apk, 'w') as output:
            for name, data in self.assets.items():
                output.writestr(name, data)
            output.writestr('assets/arcade.json', json.dumps(self.metadata))

        def command(args, **kwargs):
            if args[0] == 'openssl':
                return b'certificate'
            if 'apksigner' in args[0]:
                return 'Number of signers: 1\nSigner #1 certificate SHA-256 digest: ' + self.signer + '\n'
            self.assertIn('badging', args)
            return self.badging

        with patch.object(release, 'ROOT', self.root), patch.object(android_catalog, 'ROOT', self.root), \
                patch.object(android_catalog, 'profile_asset_hashes', return_value={}), \
                patch.object(release, 'verify_launcher'), \
                patch.object(release.subprocess, 'check_output', side_effect=command), \
                patch.object(release.subprocess, 'run'):
            return release.verify(apk, '0.7.117', self.root / 'tools', edition)

    def test_host_and_embedded_catalog_versions_may_differ(self):
        for edition in ('direct', 'fdroid'):
            result = self.verify(edition)
            self.assertEqual((result['version'], result['catalog_version']), ('0.7.117', '0.7.116'))

    def test_wrong_native_identity_or_version_rejected(self):
        for old, new in (('xyz.waozi.arcade', 'xyz.waozi.other'), ('0.7.117', '0.7.116')):
            original = self.badging
            self.badging = original.replace(old, new)
            with self.assertRaisesRegex(AssertionError, 'APK identity or version'):
                self.verify()
            self.badging = original

    def test_wrong_catalog_identity_or_source_version_rejected(self):
        for key, value in (('id', 'inbe.other'), ('version', '0.7.117')):
            original = self.metadata[key]
            self.metadata[key] = value
            with self.assertRaisesRegex(AssertionError, 'catalog (identity|version)'):
                self.verify()
            self.metadata[key] = original

    def test_payload_hash_stays_required(self):
        self.assets['assets/arcade.zx'] += b'changed'
        with self.assertRaisesRegex(AssertionError, 'differs from its receipt'):
            self.verify()

    def test_controller_digest_stays_required(self):
        self.assets['assets/apps.zx'] += b'changed'
        with self.assertRaises(AssertionError):
            self.verify()

    def test_extra_assets_and_oversized_catalog_rejected(self):
        self.assets['assets/game.zx'] = b'game'
        with self.assertRaisesRegex(AssertionError, 'Unexpected or missing'):
            self.verify()
        del self.assets['assets/game.zx']
        self.assets['assets/arcade.zx'] = b'x' * (256 * 1024 + 1)
        self.metadata['sha256'] = hashlib.sha256(self.assets['assets/arcade.zx']).hexdigest()
        with self.assertRaisesRegex(AssertionError, 'asset policy budget'):
            self.verify()

    def test_google_edition_gates_stay_required(self):
        self.badging += "uses-permission: name='com.android.vending.BILLING'\n"
        with self.assertRaisesRegex(AssertionError, 'Only the Google Play edition'):
            self.verify()
        self.assets['assets/dexopt/baseline.prof'] = b'profile'
        self.assets['assets/dexopt/baseline.profm'] = b'metadata'
        with self.assertRaisesRegex(AssertionError, 'Only the Google Play edition'):
            self.verify('gplay')
        self.assets['classes.dex'] = b'Lorg/kryonlabs/play/PlayBilling; Lcom/android/billingclient/'
        self.assertEqual(self.verify('gplay')['edition'], 'gplay')
        self.badging = self.badging.split('uses-permission:')[0]
        del self.assets['assets/dexopt/baseline.prof']
        del self.assets['assets/dexopt/baseline.profm']
        with self.assertRaisesRegex(AssertionError, 'Only the Google Play edition'):
            self.verify()

    def test_signer_and_native_architectures_stay_required(self):
        self.signer = '0' * 64
        with self.assertRaisesRegex(AssertionError, 'APK signer differs'):
            self.verify()
        self.signer = hashlib.sha256(b'certificate').hexdigest()
        del self.assets['lib/armeabi-v7a/libmain.so']
        with self.assertRaisesRegex(AssertionError, 'Both supported ARM architectures'):
            self.verify()


class WorkflowTests(unittest.TestCase):
    def test_catalog_publication_never_dispatches_android(self):
        for name in ('game-updates.yml', 'node-release.yml'):
            text = (ROOT / '.github/workflows' / name).read_text()
            self.assertNotIn('gh workflow run android.yml', text)
            self.assertNotIn('cat VERSION', text)
            self.assertIn('cat catalog/VERSION', text)
        follower = (ROOT / '.github/workflows/game-updates.yml').read_text()
        self.assertIn('sh update_version.sh --catalog', follower)
        self.assertNotIn('ziran.lock CHANGELOG.md VERSION', follower)

    def test_native_release_is_created_after_all_editions_verify(self):
        text = (ROOT / '.github/workflows/android.yml').read_text()
        publish = text[text.index('  publish:'):]
        self.assertIn('edition: [direct, fdroid, gplay]', text)
        self.assertIn('needs: [release, build]', publish)
        self.assertIn('for edition in direct fdroid gplay', publish)
        self.assertLess(publish.index('scripts/android-release.py verify'), publish.index('gh release create'))
        self.assertIn('tag="arcade-$VERSION"', publish)
        self.assertIn('--target "$GITHUB_SHA"', publish)
        self.assertNotIn('"node-arcade-', text)
        self.assertIn("expect-google: 'true'", text)


if __name__ == '__main__':
    unittest.main()
