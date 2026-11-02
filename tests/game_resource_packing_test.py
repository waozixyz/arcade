#!/usr/bin/env python3
"""Lossless resource packing keeps color, transparency and dependency copies."""
import hashlib
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image, PngImagePlugin

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from game_resources import pack_opaque_pngs


class PackingTest(unittest.TestCase):
    def test_only_redundant_alpha_is_removed(self):
        scratch = Path(__file__).resolve().parents[1] / 'work/resource-packing-tests'
        scratch.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder)
            rng = random.Random(1)
            image = Image.new('RGBA', (64, 64))
            image.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256), 255)
                           for _ in range(64 * 64)])
            opaque = root / 'opaque.png'
            image.save(opaque, compress_level=0)
            inventory = root / 'art.json'
            inventory.write_text(json.dumps({'files': [{'path': 'opaque.png', 'sha256': hashlib.sha256(opaque.read_bytes()).hexdigest()}]}))
            expected = image.tobytes()
            old_size = opaque.stat().st_size
            transparent = root / 'transparent.png'
            image.putpixel((0, 0), (1, 2, 3, 127))
            image.save(transparent)
            before_transparent = transparent.read_bytes()
            tagged = root / 'tagged.png'
            info = PngImagePlugin.PngInfo()
            info.add_text('source', 'fixture')
            image.putpixel((0, 0), (1, 2, 3, 255))
            image.save(tagged, pnginfo=info)
            before_tagged = tagged.read_bytes()
            pack_opaque_pngs(root)
            self.assertLess(opaque.stat().st_size, old_size)
            with Image.open(opaque) as actual:
                self.assertEqual(actual.convert('RGBA').tobytes(), expected)
            self.assertEqual(json.loads(inventory.read_text())['files'][0]['sha256'], hashlib.sha256(opaque.read_bytes()).hexdigest())
            self.assertEqual(transparent.read_bytes(), before_transparent)
            self.assertEqual(tagged.read_bytes(), before_tagged)
            once = opaque.read_bytes()
            pack_opaque_pngs(root)
            self.assertEqual(opaque.read_bytes(), once)


if __name__ == '__main__':
    unittest.main()
