#!/usr/bin/env python3
"""Stage bounded thumbnails for every game's library covers and previews.

Library covers retain full colour and transparency at thumbnail resolution:
opaque art uses quality-80 WebP, while transparent art uses lossless WebP.
Games keep their own original title artwork. Arcade downloads this small art
bundle separately from its launcher and caches it by its content digest.

The copies and sources.json, which records the SHA-256 of the art each copy
was made from, are committed. The collection build uses them as they are,
so its bytes never depend on the local image library, and it stops when a
game's art changes until this script makes fresh copies.
"""
import hashlib
import io
import json
from pathlib import Path
from PIL import Image
from game_packages import declared_packages

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / 'assets/arcade/library'
# The shared cover grid starts at 104 logical pixels wide on phones
# (156 high), and 200 wide on desktop. These deliberately small thumbnails
# cover the phone cards without carrying the original full-screen artwork.
PREVIEW_LONGEST = 256
COVER_LONGEST = 256
LOGO_LONGEST = 256


COVER_QUALITY = 80
SUFFIXES = ('.webp', '.png', '.jpg')


def copy_path(name):
    """The committed copy for name, whichever format it was made in."""
    for suffix in SUFFIXES:
        if (LIBRARY / (name + suffix)).is_file():
            return LIBRARY / (name + suffix)
    raise FileNotFoundError(f'{name} has no library copy; run scripts/library-art.py')


def small_copy(data, key):
    """(bytes, suffix) of the library's copy of one picture."""
    image = Image.open(io.BytesIO(data))
    image.load()
    # The shared library cards are 2:3. Keep the top of taller paintings,
    # where their title lives, rather than letting the card centre-crop it.
    # Originals remain untouched; this framing belongs to the thumbnail.
    if key == 'portrait' and image.height > image.width * 1.5:
        image = image.crop((0, 0, image.width, round(image.width * 1.5)))
    longest = PREVIEW_LONGEST if key == 'preview' else LOGO_LONGEST if key == 'logo' else COVER_LONGEST
    scale = min(1.0, longest / max(image.size))
    alpha = 'A' in image.getbands() or 'transparency' in image.info
    image = image.convert('RGBA' if alpha else 'RGB')
    if scale < 1.0:
        size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        image = image.resize(size, Image.Resampling.LANCZOS)
    output = io.BytesIO()
    # Lossless WebP preserves every resized alpha value and logo colour.
    image.save(output, 'WEBP', quality=COVER_QUALITY, lossless=alpha, method=6, exact=True)
    return output.getvalue(), '.webp'


def art(root=ROOT):
    """(copy name, key, source bytes) for every enabled game's library art."""
    for package in declared_packages(root)[1:]:
        for app in package['apps']:
            if not app['enabled']:
                continue
            name = app['descriptor']['name']
            yield name, 'preview', (app['art_source'] / app['descriptor']['preview']).read_bytes()
            for key in ('portrait', 'landscape', 'logo'):
                if app['cover'] and key in app['cover']:
                    yield name, key, (app['art_source'] / app['cover'][key]).read_bytes()


def main():
    LIBRARY.mkdir(parents=True, exist_ok=True)
    sources = {}
    written = set()
    for name, key, data in art():
        copy = f'{name}-{key}'
        contents, suffix = small_copy(data, key)
        (LIBRARY / (copy + suffix)).write_bytes(contents)
        written.add(copy + suffix)
        sources[copy] = {'source_sha256': hashlib.sha256(data).hexdigest()}
    for suffix in SUFFIXES:
        for stale in LIBRARY.glob('*' + suffix):
            if stale.name not in written:
                stale.unlink()
    (LIBRARY / 'sources.json').write_text(json.dumps(dict(sorted(sources.items())), indent=2) + '\n')
    total = sum((LIBRARY / name).stat().st_size for name in written)
    print(f'{len(sources)} library images, {total / 1048576:.1f} MiB')


if __name__ == '__main__':
    main()
