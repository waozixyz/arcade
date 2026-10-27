#!/usr/bin/env python3
"""Stage bounded thumbnails for every game's library covers and previews.

Library covers retain full colour and transparency at thumbnail resolution:
opaque cover art is a JPEG, a sixth of its PNG size, while logos keep their
transparency and previews their pixel art as PNG. Games keep their own
original title artwork. Arcade downloads this small art
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
PREVIEW_LONGEST = 480
COVER_LONGEST = 640
LOGO_LONGEST = 512


COVER_QUALITY = 85
SUFFIXES = ('.png', '.jpg')


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
    longest = PREVIEW_LONGEST if key == 'preview' else LOGO_LONGEST if key == 'logo' else COVER_LONGEST
    scale = min(1.0, longest / max(image.size))
    alpha = 'A' in image.getbands() or 'transparency' in image.info
    photo = key in ('portrait', 'landscape') and not alpha
    if scale == 1.0 and key != 'preview' and not photo:
        return data, '.png'
    image = image.convert('RGBA' if alpha else 'RGB')
    if scale < 1.0:
        size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        image = image.resize(size, Image.Resampling.LANCZOS)
    if key == 'preview':
        if alpha:
            image = image.quantize(256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG)
        else:
            image = image.quantize(256, dither=Image.Dither.FLOYDSTEINBERG)
    output = io.BytesIO()
    if photo:
        image.save(output, 'JPEG', quality=COVER_QUALITY, optimize=True, progressive=True)
        return output.getvalue(), '.jpg'
    image.save(output, 'PNG', optimize=True)
    return output.getvalue(), '.png'


def art(root=ROOT):
    """(copy name, key, source bytes) for every enabled game's library art."""
    for package in declared_packages(root)[1:]:
        for app in package['apps']:
            if not app['enabled']:
                continue
            name = app['descriptor']['name']
            yield name, 'preview', (app['source'] / app['descriptor']['preview']).read_bytes()
            for key in ('portrait', 'landscape', 'logo'):
                if app['cover'] and key in app['cover']:
                    yield name, key, (app['source'] / app['cover'][key]).read_bytes()


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
