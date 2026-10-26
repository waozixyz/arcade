"""Startup previews keep full colour and alpha while the originals stay intact."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_desktop', ROOT / 'scripts/build-desktop.py')
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)


class StartupArtTests(unittest.TestCase):
    def test_previews_keep_colour_alpha_and_aspect_ratio(self):
        work = ROOT / 'build/scratch'
        work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='startup-art-', dir=work) as temporary:
            root = Path(temporary)
            source = root / 'source/assets/shovey'
            source.mkdir(parents=True)
            # A continuous RGB gradient needs more than a 256-colour palette.
            gradient = Image.new('RGB', (900, 1200))
            gradient.putdata([(x % 256, y % 256, (x + y) % 256)
                              for y in range(1200) for x in range(900)])
            gradient.save(source / 'title-portrait.png')
            gradient.transpose(Image.Transpose.ROTATE_90).save(source / 'title-landscape.png')
            logo = gradient.resize((1200, 400)).convert('RGBA')
            alpha = Image.new('L', logo.size, 0)
            alpha.paste(255, (100, 50, 1100, 350))
            logo.putalpha(alpha)
            logo.save(source / 'logo.png')
            originals = {path.name: path.read_bytes() for path in source.iterdir()}
            output = root / 'output'
            desktop.stage_startup_art(root / 'source', output)
            expected = {'title-portrait.png': (480, 640),
                        'title-landscape.png': (640, 480), 'logo.png': (512, 171)}
            for name, size in expected.items():
                with self.subTest(image=name), Image.open(output / 'startup/shovey' / name) as preview:
                    self.assertEqual(preview.size, size)
                    self.assertEqual(preview.mode, 'RGBA' if name == 'logo.png' else 'RGB')
                    self.assertIsNone(preview.getcolors(256), 'Title previews must not use a 256-colour palette')
                    if name == 'logo.png':
                        self.assertEqual(preview.getpixel((0, 0))[3], 0)
                        self.assertEqual(preview.getpixel((256, 85))[3], 255)
                    self.assertEqual((source / name).read_bytes(), originals[name])


if __name__ == '__main__':
    unittest.main()
