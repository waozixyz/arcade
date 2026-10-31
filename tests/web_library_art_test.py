"""The website serves small verified copies of the collection's library art."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_web', ROOT / 'scripts/build-web.py')
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)


def bundle(files):
    """A minimal ZX v27 bundle: empty program sections, then its files."""
    def text(value):
        return struct.pack('<I', len(value)) + value
    data = b'ZX\0\0\x1b\0\0\0' + text(b'art') + text(b'Main') + struct.pack('<IIII', 0, 0, 0, 0)
    data += struct.pack('<I', len(files))
    for path in sorted(files):
        data += text(path.encode()) + text(files[path])
    return data


def png(image):
    output = io.BytesIO()
    image.save(output, 'PNG', optimize=True)
    return output.getvalue()


def jpeg(image):
    output = io.BytesIO()
    image.save(output, 'JPEG', quality=85)
    return output.getvalue()


def gradient(width, height):
    image = Image.new('RGB', (width, height))
    image.putdata([(x * 255 // width, y * 255 // height, (x * y) % 256)
                   for y in range(height) for x in range(width)])
    return image


def decoded(data):
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


class WebLibraryArtTests(unittest.TestCase):
    def setUp(self):
        work = ROOT / 'build/scratch'
        work.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='web-art-', dir=work)
        self.root = Path(self.temporary.name)
        self.published = self.root / 'published'
        self.published.mkdir()
        self.site = self.root / 'site'
        self.site.mkdir()
        # A photographic cover, larger than any library copy should be.
        self.portrait = jpeg(gradient(800, 1200))
        self.landscape = jpeg(gradient(640, 427))
        logo = gradient(512, 180).convert('RGBA')
        logo.putalpha(Image.new('L', logo.size, 0))
        logo.paste(gradient(300, 100), (100, 40))
        self.logo = png(logo)
        # Pixel art with a palette, which must stay exact.
        pixels = Image.new('P', (48, 32))
        pixels.putpalette([value for index in range(16) for value in (index * 16, 255 - index * 16, index * 8)])
        pixels.putdata([(x // 4 + y // 4) % 16 for y in range(32) for x in range(48)])
        self.preview = png(pixels)
        self.art = bundle({
            'assets/arcade/covers/wurm-portrait.jpg': self.portrait,
            'assets/arcade/covers/wurm-landscape.jpg': self.landscape,
            'assets/arcade/covers/wurm-logo.png': self.logo,
            'assets/arcade/previews/wurm.png': self.preview,
        })

    def tearDown(self):
        self.temporary.cleanup()

    def collection(self, art=None, archive=True):
        art = self.art if art is None else art
        catalog = dict(schema=1, id='inbe.arcade', title='Arcade', harness='assets/apps/apps.zx',
                       art=dict(sha256=hashlib.sha256(self.art).hexdigest(), bytes=len(self.art)),
                       children=[dict(id='xyz.waozi.wurm', title='Apfelwurm',
                                      preview='assets/arcade/previews/wurm.png',
                                      icon='assets/arcade/previews/wurm.png',
                                      cover=dict(portrait='assets/arcade/covers/wurm-portrait.jpg',
                                                 landscape='assets/arcade/covers/wurm-landscape.jpg',
                                                 logo='assets/arcade/covers/wurm-logo.png',
                                                 caption='Play'))])
        path = self.published / 'arcade.zx'
        path.write_bytes(bundle({'assets/apps/catalog.json': json.dumps(catalog).encode()}))
        digest = catalog['art']['sha256']
        if archive:
            # The release's game archive, as the website workflow downloads it.
            with tarfile.open(self.published / 'arcade.games.tar', 'w') as games:
                for name, data in ((f'{digest}.zx', art), ('0' * 64 + '.zx', b'ZX\0\0game')):
                    entry = tarfile.TarInfo(name)
                    entry.size = len(data)
                    games.addfile(entry, io.BytesIO(data))
        else:
            (self.published / 'arcade.games').mkdir()
            (self.published / 'arcade.games' / f'{digest}.zx').write_bytes(art)
        return path, digest

    def test_small_webp_copies_keep_alpha_pixels_and_the_exact_art(self):
        path, digest = self.collection()
        listing = web.stage_web_library_art(path, self.site)
        self.assertEqual(listing['art'], digest)
        self.assertEqual(json.loads((self.site / 'library.json').read_text()), listing)
        # The exact signed bundle stays beside the copies, for the fallback.
        self.assertEqual((self.site / 'library' / f'{digest}.zx').read_bytes(), self.art)
        pictures = listing['pictures']
        self.assertEqual(set(pictures), {'assets/arcade/covers/wurm-portrait.jpg',
                                         'assets/arcade/covers/wurm-landscape.jpg',
                                         'assets/arcade/covers/wurm-logo.png',
                                         'assets/arcade/previews/wurm.png'})
        copies = {}
        for name, picture in pictures.items():
            data = (self.site / picture['file']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), picture['sha256'])
            self.assertEqual(len(data), picture['bytes'])
            self.assertEqual(picture['file'], f'library/{picture["sha256"]}' + Path(picture['file']).suffix)
            copies[name] = data
        portrait = decoded(copies['assets/arcade/covers/wurm-portrait.jpg'])
        self.assertEqual(portrait.format, 'WEBP')
        self.assertEqual(portrait.size, (427, 640))
        landscape = copies['assets/arcade/covers/wurm-landscape.jpg']
        self.assertEqual(decoded(landscape).format, 'WEBP')
        self.assertLess(len(landscape), len(self.landscape))
        logo = decoded(copies['assets/arcade/covers/wurm-logo.png'])
        self.assertEqual((logo.format, logo.mode, logo.size), ('WEBP', 'RGBA', (512, 180)))
        self.assertEqual(logo.getpixel((5, 5))[3], 0)
        self.assertEqual(logo.getpixel((200, 80))[3], 255)
        preview = copies['assets/arcade/previews/wurm.png']
        if decoded(preview).format == 'WEBP':
            self.assertLess(len(preview), len(self.preview))
            self.assertEqual(decoded(preview).convert('RGB').tobytes(),
                             decoded(self.preview).convert('RGB').tobytes())
        else:
            # WebP is no smaller: the verified original goes as it is.
            self.assertEqual(preview, self.preview)

    def test_a_local_build_folder_also_supplies_the_art(self):
        path, digest = self.collection(archive=False)
        self.assertEqual(web.stage_web_library_art(path, self.site)['art'], digest)

    def test_corrupt_or_resized_art_is_refused_before_anything_is_written(self):
        corrupt = bytearray(self.art)
        corrupt[-1] ^= 1
        for art in (bytes(corrupt), self.art + b'\0'):
            path, _ = self.collection(art)
            with self.assertRaisesRegex(ValueError, 'differs from the collection catalog'):
                web.stage_web_library_art(path, self.site)
            self.assertFalse((self.site / 'library.json').exists())
            self.assertFalse((self.site / 'library').exists())

    def test_missing_art_or_pictures_are_refused(self):
        path, _ = self.collection()
        (self.published / 'arcade.games.tar').unlink()
        with self.assertRaisesRegex(ValueError, 'not beside it'):
            web.stage_web_library_art(path, self.site)
        self.art = bundle({'assets/arcade/previews/wurm.png': self.preview})
        path, _ = self.collection()
        with self.assertRaisesRegex(ValueError, 'lacks assets/arcade/covers'):
            web.stage_web_library_art(path, self.site)
        self.assertFalse((self.site / 'library.json').exists())

    def test_a_collection_that_packs_its_art_needs_no_copies(self):
        catalog = dict(schema=1, id='inbe.arcade', children=[])
        path = self.published / 'arcade.zx'
        path.write_bytes(bundle({'assets/apps/catalog.json': json.dumps(catalog).encode()}))
        self.assertIsNone(web.stage_web_library_art(path, self.site))
        self.assertEqual(list(self.site.iterdir()), [])

    def test_truncated_or_trailing_bundles_are_refused(self):
        for data in (self.art[:-3], self.art + b'x', b'PK' + self.art[2:]):
            with self.assertRaises(ValueError):
                web.bundle_assets(data)


if __name__ == '__main__':
    unittest.main()
