"""Import portable exports without compiling, executing or transforming games."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from game_packages import portable_artifacts, declared_apps
spec = importlib.util.spec_from_file_location('game_importer', ROOT / 'scripts/build-games.py')
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


def zx(descriptor, requirements=None, extra=(), version=27):
    def number(value):
        return struct.pack('<I', value)

    def text(value):
        value = value.encode() if isinstance(value, str) else value
        return number(len(value)) + value

    public = {k: v for k, v in descriptor.items() if k not in ('build_defines', 'prepare_assets')}
    name = descriptor['name']
    assets = [(f'assets/{name}/catalog.json', json.dumps(public).encode()),
              (f'assets/{name}/picture.png', b'unchanged resource'), *extra]
    if requirements is not None:
        assets.append((f'assets/{name}/requirements.json', json.dumps(requirements).encode()))
    return (b'ZX\0\0' + number(version) + text('portable') + text('Main') + number(0) * 4
            + number(len(assets)) + b''.join(text(k) + text(v) for k, v in assets))


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / 'work/console-redesign'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='import-test-', dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'owner'
        self.source.mkdir()
        self.apps = []
        for name, requires in [('base', []), ('base-editor', ['test.base'])]:
            descriptor = dict(id='test.' + name, name=name, title=name, kind='game',
                              harnesses=['arcade'], entry='portable:Main', host_api=42,
                              contract_version=1, module_api=2, save_schema=1,
                              preview='preview.png', build_defines=['OWNER_ONLY'])
            self.apps.append(dict(descriptor=descriptor, requires=requires, enabled=True,
                                  source=self.source, package='fixture'))
        self.resources = [dict(dependencies=[], resources=[]), dict(dependencies=['test.base'], resources=[
            dict(dependency='test.base', path='assets/base-editor/shared.png', source='assets/base/picture.png')])]
        self.manifest = self.root / 'exports.json'
        self.write_exports()
        (self.root / 'src').mkdir()
        (self.root / 'build/games').mkdir(parents=True)
        (self.root / 'build/games/previous.zx').write_bytes(b'previous payload')
        (self.root / 'src/catalog.zi').write_text('previous source catalog')
        (self.root / 'build/catalog.json').write_text('previous catalog')
        self.before = self.snapshot()

    def write_exports(self):
        records = {}
        for index, app in enumerate(self.apps):
            name = app['descriptor']['name']
            required = None if index == 0 else self.resources[index] | {'sha256': {
                'test.base': hashlib.sha256((self.source / 'base.zx').read_bytes()).hexdigest()}}
            (self.source / (name + '.zx')).write_bytes(zx(app['descriptor'], required))
            (self.source / (name + '-resources.json')).write_text(json.dumps(self.resources[index]))
            (self.source / (name + '.png')).write_bytes(b'unchanged preview')
            records[app['descriptor']['id']] = dict(bundle=f'owner/{name}.zx',
                resources=f'owner/{name}-resources.json', preview=f'owner/{name}.png')
        self.manifest.write_text(json.dumps(dict(apps=records)))

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for folder in ('src', 'build') for p in (self.root / folder).rglob('*') if p.is_file()}

    def run_import(self):
        with patch.object(importer, 'ROOT', self.root), patch.object(importer, 'declared_apps', return_value=self.apps), \
                patch('subprocess.run', side_effect=AssertionError('No game subprocess')), \
                patch('subprocess.check_output', side_effect=AssertionError('No compiler/resolver needed with fixtures')):
            importer.build('must-not-run', [], self.manifest)

    def reject(self, message):
        with self.assertRaisesRegex(ValueError, message):
            self.run_import()
        self.assertEqual(self.snapshot(), self.before)

    def test_byte_identical_exports_catalog_and_legacy_editor_id(self):
        self.run_import()
        for app in self.apps:
            name = app['descriptor']['name']
            for suffix in ('.zx', '-resources.json'):
                self.assertEqual((self.root / 'build/games' / (name + suffix)).read_bytes(),
                                 (self.source / (name + suffix)).read_bytes())
            self.assertEqual((self.root / 'build/games' / (name + '-preview.png')).read_bytes(),
                             (self.source / (name + '.png')).read_bytes())
        self.assertFalse((self.root / 'build/games/previous.zx').exists())
        catalog = json.loads((self.root / 'build/catalog.json').read_text())
        self.assertEqual([g['id'] for g in catalog['games']], ['test.base', 'test.base-editor'])
        self.assertIn('test.base-editor', (self.root / 'src/catalog.zi').read_text())

    def test_missing_export_preserves_all_previous_outputs(self):
        (self.source / 'base-editor.zx').unlink()
        self.reject('missing bundle export.*Arcade never compiles')

    def test_native_packaging_manifest_cannot_escape_game_namespace(self):
        (self.source / 'base.zx').write_bytes(zx(self.apps[0]['descriptor'],
            extra=[('assets/manifest.json', b'{}')]))
        self.reject('assets escape the game namespace')

    def test_asset_cannot_use_another_games_namespace(self):
        (self.source / 'base.zx').write_bytes(zx(self.apps[0]['descriptor'],
            extra=[('assets/other/private.png', b'not a declared dependency')]))
        self.reject('assets escape the game namespace')

    def test_individual_asset_host_limit(self):
        (self.source / 'base.zx').write_bytes(zx(self.apps[0]['descriptor'],
            extra=[('assets/base/large.bin', b'x' * (importer.MAX_ASSET_BYTES + 1))]))
        self.reject('asset exceeds the host asset limit')

    def test_wrong_embedded_identity(self):
        wrong = self.apps[1]['descriptor'] | {'id': 'other.game'}
        (self.source / 'base-editor.zx').write_bytes(zx(wrong))
        self.reject('embedded catalog/entry mismatch')

    def test_missing_catalog(self):
        data = zx(self.apps[1]['descriptor']).replace(b'catalog.json', b'ignored.json')
        (self.source / 'base-editor.zx').write_bytes(data)
        self.reject('embedded catalog/entry mismatch')

    def test_wrong_dependency_id(self):
        (self.source / 'base-editor-resources.json').write_text(json.dumps(dict(dependencies=['other.game'], resources=[])))
        self.reject('dependency identities mismatch')

    def test_wrong_dependency_hash(self):
        requirement = self.resources[1] | {'sha256': {'test.base': '0' * 64}}
        (self.source / 'base-editor.zx').write_bytes(zx(self.apps[1]['descriptor'], requirement))
        self.reject('requirements/hash mismatch')

    def test_wrong_resource_source(self):
        self.resources[1]['resources'][0]['source'] = 'assets/base/missing.png'
        self.write_exports()
        self.reject('missing dependency resource')

    def test_traversal_resource(self):
        self.resources[1]['resources'][0]['path'] = 'assets/base-editor/../outside'
        self.write_exports()
        self.reject('unsafe resource link')

    def test_over_budget(self):
        with patch.object(importer, 'MAX_PAYLOAD_BYTES', 32):
            self.reject('payload limit')

    def test_truncated_and_duplicate_zx(self):
        for data in (zx(self.apps[0]['descriptor'])[:-1],
                     zx(self.apps[0]['descriptor'], extra=[('assets/base/picture.png', b'duplicate')])):
            with self.subTest(length=len(data)):
                (self.source / 'base.zx').write_bytes(data)
                self.reject('truncated|duplicate')

    def test_manifest_rejects_external_private_id(self):
        manifest = json.loads(self.manifest.read_text())
        manifest['apps']['private.island'] = dict(bundle='island.zx', preview='island.png')
        self.manifest.write_text(json.dumps(manifest))
        self.reject('exactly the enabled public app IDs')

    def test_disabled_metadata_needs_no_artifact(self):
        self.apps.append(dict(descriptor=self.apps[0]['descriptor'] | {'id': 'test.disabled', 'name': 'disabled'},
                              requires=[], enabled=False, source=self.source, package='self'))
        self.run_import()
        catalog = json.loads((self.root / 'build/catalog.json').read_text())
        self.assertFalse(catalog['games'][-1]['enabled'])
        self.assertFalse((self.root / 'build/games/disabled.zx').exists())

    def test_duplicate_ids_and_cycles(self):
        self.apps[1]['descriptor']['id'] = 'test.base'
        self.reject('distinct games')
        self.apps[1]['descriptor']['id'] = 'test.base-editor'
        self.apps[0]['requires'] = ['test.base-editor']
        self.reject('Cyclic')

    def test_promotion_failure_rolls_back_every_output(self):
        original = importer.os.replace
        calls = 0
        def fail_once(source, target):
            nonlocal calls
            calls += 1
            if calls == 6:
                raise OSError('simulated promotion failure')
            return original(source, target)
        with patch.object(importer.os, 'replace', side_effect=fail_once), self.assertRaisesRegex(OSError, 'promotion failure'):
            self.run_import()
        self.assertEqual(self.snapshot(), self.before)

    def test_canonical_game_owned_paths_and_missing_guidance(self):
        expected = {'shovey': 'build/player/games/base.zx', 'wurm': 'build/games/base.zx', 'choano': 'build/base.zx'}
        for package, path in expected.items():
            app = self.apps[0] | {'package': package}
            locations, guidance = portable_artifacts(app)
            self.assertEqual(locations['bundle'], self.source / path)
            self.assertIn('build-queue --', guidance)

    def test_zx26_supported_without_running_payload(self):
        bundle = self.source / 'v26.zx'
        bundle.write_bytes(zx(self.apps[0]['descriptor'], version=26))
        self.assertEqual(importer.bundle_metadata(bundle, 'base')[0], 'portable:Main')

    def test_base_app_can_omit_resource_sidecar(self):
        manifest = json.loads(self.manifest.read_text())
        del manifest['apps']['test.base']['resources']
        self.manifest.write_text(json.dumps(manifest))
        self.run_import()
        resources = json.loads((self.root / 'build/games/base-resources.json').read_text())
        self.assertEqual(resources, dict(dependencies=[], resources=[]))

    def test_addon_cannot_omit_resource_sidecar(self):
        manifest = json.loads(self.manifest.read_text())
        del manifest['apps']['test.base-editor']['resources']
        self.manifest.write_text(json.dumps(manifest))
        self.reject('dependencies require exported resources metadata')

    def test_invalid_metadata_type_rejected_atomically(self):
        (self.source / 'base-editor-resources.json').write_text('[]')
        self.reject('dependency identities mismatch')

    def test_external_declaration_filtered_before_manifest_read(self):
        (self.root / 'games.json').write_text('{"packages": []}')
        (self.root / 'apps.json').write_text(json.dumps(dict(id='test', title='test', apps=[
            dict(manifest='private/not-readable.json', external=True, standalone_bundle='private/island.zx')])))
        self.assertEqual(declared_apps(self.root), [])


if __name__ == '__main__':
    unittest.main()
