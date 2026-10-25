"""Dependencies reuse only the exact prepared assets they declare."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from game_resources import dependency_order, share_resources


class GameResourcesTest(unittest.TestCase):
    def test_dependency_order_rejects_missing_disabled_and_cyclic_games(self):
        base = dict(enabled=True, descriptor=dict(id='game'), requires=[])
        editor = dict(enabled=True, descriptor=dict(id='editor'), requires=['game'])
        self.assertEqual(dependency_order([editor, base]), [base, editor])
        for candidates in [[editor], [editor, base | dict(enabled=False)],
                           [editor, base | dict(requires=['editor'])]]:
            with self.assertRaises(ValueError):
                dependency_order(candidates)

    def test_shared_bytes_are_removed_and_changed_bytes_remain_private(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = root / 'editor/catalog.json'
            manifest.parent.mkdir()
            manifest.with_name('shared_assets.json').write_text(json.dumps(dict(copies=[
                dict(**{'from': 'assets/game/sprites'}, to='classic/sprites'),
                dict(**{'from': 'assets/game/sound.ogg'}, to='classic/sound.ogg')])))
            base = dict(source=root, manifest=root / 'catalog.json',
                        descriptor=dict(id='game', name='game', assets='assets/game'))
            editor = dict(source=root, manifest=manifest, requires=['game'],
                          descriptor=dict(id='editor', name='editor'))
            original = root / 'staged/game/assets/game'
            (original / 'sprites').mkdir(parents=True)
            (original / 'sprites/player.png').write_bytes(b'original image')
            (original / 'sound.ogg').write_bytes(b'original audio')
            resources = root / 'editor-assets'
            (resources / 'classic/sprites').mkdir(parents=True)
            (resources / 'classic/sprites/player.png').write_bytes(b'original image')
            (resources / 'classic/sound.ogg').write_bytes(b'changed editor audio')
            result = share_resources(editor, [base, editor], resources, root / 'staged')
            self.assertEqual(result, dict(dependencies=['game'], resources=[dict(
                dependency='game', path='assets/editor/classic/sprites/', source='assets/game/sprites/')]))
            self.assertFalse((resources / 'classic/sprites').exists())
            self.assertEqual((resources / 'classic/sound.ogg').read_bytes(), b'changed editor audio')
            self.assertEqual((original / 'sprites/player.png').read_bytes(), b'original image')


if __name__ == '__main__':
    unittest.main(verbosity=2)
