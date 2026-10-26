#!/usr/bin/env python3
"""Make Arcade's small copies of each game's cover and preview art.

Game packages keep their full-size art for their own players and stores.
Arcade only shows that art in its library, so it packs copies sized for the
screen with a 256-colour palette: about a fifth of the bytes, with no visible
change. Arcade stays a small launcher; the games download separately.

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
# Longest side: covers fill the library's screen, logos sit on them and
# previews are small tiles and icons.
LONGEST = {'portrait': 1280, 'landscape': 1280, 'logo': 800, 'preview': 480}


def small_copy(data, key):
    image = Image.open(io.BytesIO(data))
    image.load()
    scale = min(1.0, LONGEST[key] / max(image.size))
    if scale < 1.0:
        size = (round(image.width * scale), round(image.height * scale))
        image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB').resize(size, Image.Resampling.LANCZOS)
    if 'A' in image.getbands():
        image = image.convert('RGBA').quantize(256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG)
    else:
        image = image.convert('RGB').quantize(256, dither=Image.Dither.FLOYDSTEINBERG)
    output = io.BytesIO()
    image.save(output, 'PNG', optimize=True)
    return output.getvalue()


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
    for name, key, data in art():
        copy = f'{name}-{key}'
        (LIBRARY / f'{copy}.png').write_bytes(small_copy(data, key))
        sources[copy] = {'source_sha256': hashlib.sha256(data).hexdigest()}
    for stale in LIBRARY.glob('*.png'):
        if stale.stem not in sources:
            stale.unlink()
    (LIBRARY / 'sources.json').write_text(json.dumps(dict(sorted(sources.items())), indent=2) + '\n')
    total = sum((LIBRARY / f'{copy}.png').stat().st_size for copy in sources)
    print(f'{len(sources)} library images, {total / 1048576:.1f} MiB')


if __name__ == '__main__':
    main()
