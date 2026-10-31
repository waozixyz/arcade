"""Released games must bring new dependency edges without moving backwards."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('follow_game_releases', ROOT / 'scripts/follow-game-releases.py')
follower = importlib.util.module_from_spec(spec)
spec.loader.exec_module(follower)


class GameUpdates(unittest.TestCase):
    def follow(self, comparison, same_commit=False, failure=False, wrong_commit=False):
        with tempfile.TemporaryDirectory(prefix='arcade-release-metadata-') as temporary:
            root = Path(temporary)
            (root / 'apps').mkdir()
            old = '1' * 40
            new = old if same_commit else '2' * 40
            lock = {'format': 1, 'toolchain': {'commit': 'compiler'},
                    'root': {'dependencies': {'wurm': 'old', 'other': 'unrelated'}},
                    'packages': [{'id': 'old', 'name': 'Apfelwurm',
                                  'url': 'https://github.com/waozixyz/wurm.git',
                                  'commit': old, 'ref': 'master', 'dependencies': {}},
                                 {'id': 'unrelated', 'commit': 'unchanged', 'dependencies': {}}]}
            original_lock = json.dumps(lock)
            (root / 'ziran.lock').write_text(original_lock)
            original_manifest = ('[package]\nname = "Arcade"\n\n[dependencies.wurm]\n'
                                 'git = "https://github.com/waozixyz/wurm.git"\nref = "master"\n\n'
                                 '[dependencies.other]\nref = "stable"\n')
            (root / 'ziran.toml').write_text(original_manifest)
            (root / 'games.json').write_text(json.dumps({'packages': ['wurm']}))
            # Release metadata may name a release before its source is pinned.
            (root / 'apps/versions.json').write_text(json.dumps({'node_apps': {'wurm': {'version': '0.2.0'}}}))

            def gh(*arguments):
                if arguments[0] == 'release':
                    return 'v0.2.0'
                return comparison if '/compare/' in arguments[1] else new

            def resolve(command, **kwargs):
                self.assertEqual(command, ['verified-ziran', 'update', 'wurm'])
                self.assertEqual(kwargs, {'cwd': root, 'check': True})
                self.assertIn(f'ref = "{new}"', (root / 'ziran.toml').read_text())
                declaration = tomllib.loads((root / 'ziran.toml').read_text())
                self.assertEqual(declaration['dependencies']['wurm']['ref'], new)
                self.assertEqual(declaration['dependencies']['other']['ref'], 'stable')
                if failure:
                    (root / 'ziran.lock').write_text('partial resolver output')
                    raise subprocess.CalledProcessError(1, command)
                # A package-manager result with a newly introduced Entity import.
                # The follower must retain this graph verbatim, rather than
                # replacing the game id while preserving its old empty edges.
                lock['root']['dependencies']['wurm'] = 'released'
                lock['packages'][0].update(id='released', commit=old if wrong_commit else new,
                                          ref=new, dependencies={'entity': 'accounts'})
                lock['packages'].append({'id': 'accounts', 'commit': 'new-entity', 'dependencies': {}})
                (root / 'ziran.lock').write_text(json.dumps(lock))

            updates = root / 'updates.json'
            with patch.object(follower, 'ROOT', root), patch.object(follower, 'UPDATES', updates), \
                    patch.object(follower, 'gh', gh), patch.object(follower.subprocess, 'run', side_effect=resolve) as run:
                # Discovery must not require a compiler or modify either input.
                follower.record_updates(follower.released_updates())
                self.assertEqual((root / 'ziran.lock').read_text(), original_lock)
                self.assertEqual((root / 'ziran.toml').read_text(), original_manifest)
                run.assert_not_called()
                if failure or wrong_commit:
                    with self.assertRaises((subprocess.CalledProcessError, ValueError)):
                        follower.pin('verified-ziran')
                    self.assertEqual((root / 'ziran.lock').read_text(), original_lock)
                    self.assertEqual((root / 'ziran.toml').read_text(), original_manifest)
                else:
                    follower.pin('verified-ziran')
                calls = run.call_count
            return json.loads((root / 'ziran.lock').read_text()), json.loads(updates.read_text()), old, new, calls

    def test_new_release_refreshes_transitive_graph(self):
        lock, updates, old, new, calls = self.follow('ahead')
        self.assertEqual(lock['packages'][0]['commit'], new)
        self.assertEqual(lock['root']['dependencies']['wurm'], lock['packages'][0]['id'])
        self.assertEqual(lock['packages'][0]['dependencies'], {'entity': 'accounts'})
        self.assertEqual(lock['packages'][1]['commit'], 'unchanged')
        self.assertEqual(lock['toolchain']['commit'], 'compiler')
        self.assertEqual((len(updates), calls), (1, 1))

    def test_same_source_is_unchanged(self):
        lock, updates, old, new, calls = self.follow('identical', same_commit=True)
        self.assertEqual(lock['packages'][0]['commit'], old)
        self.assertEqual((updates, calls), ([], 0))

    def test_older_release_never_moves_the_pin_back(self):
        lock, updates, old, new, calls = self.follow('behind')
        self.assertEqual(lock['packages'][0]['commit'], old)
        self.assertEqual((updates, calls), ([], 0))

    def test_failed_resolution_restores_manifest_and_lock(self):
        self.follow('ahead', failure=True)

    def test_local_override_cannot_publish_wrong_game(self):
        self.follow('ahead', wrong_commit=True)

    def test_release_ships_unreleased_notes(self):
        with tempfile.TemporaryDirectory(prefix='arcade-release-notes-') as temporary:
            root = Path(temporary)
            game = root / 'game'
            game.mkdir()
            (game / 'apps.json').write_text(json.dumps({'title': 'Apfelwurm', 'apps': [{'manifest': 'catalog.json'}]}))
            (game / 'CHANGELOG.md').write_text('## [Unreleased]\n\n- Later.\n\n## [0.2.1] - 2026-10-29\n\n- Faster.\n')
            (root / 'catalog').mkdir()
            (root / 'CHANGELOG.md').write_text('## 9.0.0\n\n- Host changes stay here.\n')
            (root / 'catalog/CHANGELOG.md').write_text('# Arcade changelog\n\n## [Unreleased]\n\n- Keyboard first.\n\n'
                                               '## 0.7.1\n\n- Older.\n')
            updates = root / 'updates.json'
            updates.write_text(json.dumps([{'name': 'wurm'}]))
            with patch.object(follower, 'ROOT', root), patch.object(follower, 'UPDATES', updates), \
                    patch.object(follower.subprocess, 'check_output', return_value=str(game) + '\n'):
                follower.changelog('ziran')
            self.assertEqual((root / 'CHANGELOG.md').read_text(), '## 9.0.0\n\n- Host changes stay here.\n')
            self.assertEqual((root / 'catalog/CHANGELOG.md').read_text(),
                             '# Arcade changelog\n\n## 0.7.2\n\n- Keyboard first.\n'
                             '- Apfelwurm 0.2.1: Faster.\n\n## 0.7.1\n\n- Older.\n')


if __name__ == '__main__':
    unittest.main()
