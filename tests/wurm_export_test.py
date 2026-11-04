"""Wurm releases are imported unchanged, with the exact source/release identity."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


exports = load('wurm_exports', 'scripts/fetch-wurm-export.py')
importer = load('game_importer', 'scripts/build-games.py')


class WurmExports(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / 'work/console-redesign'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def archive(self, bad=None):
        archive = self.root / 'exports.tar.gz'
        with tarfile.open(archive, 'w:gz') as output:
            for name in sorted(exports.EXPORT_FILES):
                member = tarfile.TarInfo(name)
                data = name.encode()
                member.size = len(data)
                if name == 'wurm.zx' and bad:
                    if bad == 'link':
                        member.type, member.linkname = tarfile.SYMTYPE, 'private'
                    else:
                        member.name = '../wurm.zx'
                output.addfile(member, io.BytesIO(data))
        return archive

    def test_complete_archive_is_copied_unchanged(self):
        exports.unpack(self.archive(), self.root)
        for name in exports.EXPORT_FILES:
            self.assertEqual((self.root / 'build/games' / name).read_bytes(), name.encode())

    def test_invalid_members_preserve_previous_export(self):
        target = self.root / 'build/games/wurm.zx'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'previous export')
        for bad in ('link', 'traversal'):
            with self.assertRaises(ValueError):
                exports.unpack(self.archive(bad), self.root)
            self.assertEqual(target.read_bytes(), b'previous export')

    def test_wrong_release_commit_is_rejected_before_download(self):
        (self.root / 'version.json').write_text('{"version":"0.2.32"}')
        with patch.object(exports.subprocess, 'check_output', return_value='1' * 40), \
                patch.object(exports.subprocess, 'run') as download:
            with self.assertRaisesRegex(ValueError, 'pinned commit'):
                exports.fetch(self.root, '2' * 40)
            download.assert_not_called()

    @unittest.skipUnless(os.environ.get('WURM_EXPORT_ARCHIVE'), 'set WURM_EXPORT_ARCHIVE and WURM_SOURCE for real bundle test')
    def test_real_release_passes_arcade_import_contract(self):
        source = Path(os.environ['WURM_SOURCE'])
        archive = Path(os.environ['WURM_EXPORT_ARCHIVE'])
        exports.unpack(archive, self.root)
        apps, records = [], {}
        for declaration in json.loads((source / 'apps.json').read_text())['apps']:
            descriptor = json.loads((source / declaration['manifest']).read_text())
            name = descriptor['name']
            apps.append(dict(descriptor=descriptor, requires=declaration.get('requires', []),
                             enabled=True, source=source, package='wurm'))
            records[descriptor['id']] = {
                kind: str(self.root / 'build/games' / (name + suffix))
                for kind, suffix in [('bundle', '.zx'), ('resources', '-resources.json'), ('preview', '-preview.png')]}
        manifest = self.root / 'exports.json'
        manifest.write_text(json.dumps({'apps': records}))
        before = {path.name: importer.digest(path) for path in (self.root / 'build/games').iterdir()}
        with patch.object(importer, 'ROOT', self.root), patch.object(importer, 'declared_apps', return_value=apps):
            importer.build('unused', [], manifest)
        for name, digest in before.items():
            if '-catalog.json' not in name:
                self.assertEqual(importer.digest(self.root / 'build/games' / name), digest)


if __name__ == '__main__':
    unittest.main()
