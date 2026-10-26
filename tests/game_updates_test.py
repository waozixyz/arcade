"""Release metadata must not prevent Arcade from following the actual game source."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('follow_game_releases', ROOT / 'scripts/follow-game-releases.py')
follower = importlib.util.module_from_spec(spec)
spec.loader.exec_module(follower)


class GameUpdates(unittest.TestCase):
    def follow(self, comparison, same_commit=False):
        with tempfile.TemporaryDirectory(prefix='arcade-release-metadata-') as temporary:
            root = Path(temporary)
            (root / 'apps').mkdir()
            old = '1' * 40
            new = old if same_commit else '2' * 40
            url = 'https://github.com/waozixyz/wurm.git'
            identifier = follower.package_id(url, old)
            lock = {'format': 1, 'toolchain': {}, 'root': {'dependencies': {'wurm': identifier}},
                    'packages': [{'id': identifier, 'name': 'Apfelwurm', 'url': url,
                                  'commit': old, 'ref': 'master', 'dependencies': {}}]}
            (root / 'ziran.lock').write_text(follower.write_lock(lock))
            (root / 'games.json').write_text(json.dumps({'packages': ['wurm']}))
            # This is the normal release order: metadata first, game release next.
            (root / 'apps/versions.json').write_text(json.dumps({'node_apps': {'wurm': {'version': '0.1.8'}}}))

            def gh(*arguments):
                if arguments[0] == 'release':
                    return 'v0.1.8'
                return comparison if '/compare/' in arguments[1] else new

            updates = root / 'updates.json'
            with patch.object(follower, 'ROOT', root), patch.object(follower, 'UPDATES', updates), patch.object(follower, 'gh', gh):
                follower.pin()
            return json.loads((root / 'ziran.lock').read_text()), json.loads(updates.read_text()), old, new

    def test_metadata_already_names_the_release(self):
        lock, updates, old, new = self.follow('ahead')
        self.assertEqual(lock['packages'][0]['commit'], new)
        self.assertEqual(lock['root']['dependencies']['wurm'], lock['packages'][0]['id'])
        self.assertEqual(len(updates), 1)

    def test_same_source_is_unchanged(self):
        lock, updates, old, new = self.follow('identical', same_commit=True)
        self.assertEqual(lock['packages'][0]['commit'], old)
        self.assertEqual(updates, [])

    def test_older_release_never_moves_the_pin_back(self):
        lock, updates, old, new = self.follow('behind')
        self.assertEqual(lock['packages'][0]['commit'], old)
        self.assertEqual(updates, [])


if __name__ == '__main__':
    unittest.main()
