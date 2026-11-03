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
import subprocess
from pathlib import Path
from PIL import Image, ImageOps
from game_packages import declared_packages

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / 'assets/arcade/library'
# Previews stay at 256 px. Separately fetched painted covers are sized for
# full-screen landscape and focused portrait art, with a total 2 MiB budget.
PREVIEW_LONGEST = 256
LANDSCAPE_LONGEST = 1600
PORTRAIT_LONGEST = 1080
COVER_LONGEST = 256
ART_BUDGET = 2 * 1024 * 1024
LOGO_LONGEST = 256


COVER_QUALITY = 80
SUFFIXES = ('.webp', '.png', '.jpg')


def copy_path(name):
    """The committed copy for name, whichever format it was made in."""
    for suffix in SUFFIXES:
        if (LIBRARY / (name + suffix)).is_file():
            return LIBRARY / (name + suffix)
    raise FileNotFoundError(f'{name} has no library copy; run scripts/library-art.py')


def small_copy(data, key, crop_top=0):
    """(bytes, suffix) of the library's copy of one picture."""
    image = Image.open(io.BytesIO(data))
    image.load()
    if not 0 <= crop_top < image.height:
        raise ValueError('Gameplay crop exceeds screenshot')
    if crop_top:
        image = image.crop((0, crop_top, image.width, image.height))
    # Frame the original painted artwork for the shelf, never gameplay captures.
    # Portrait paintings keep their title near the top; landscape art is centred.
    if key in ('portrait', 'landscape'):
        ratio = 2 / 3 if key == 'portrait' else 16 / 9
        width = min(image.width, round(image.height * ratio))
        height = min(image.height, round(image.width / ratio))
        image = ImageOps.fit(image, (width, height), Image.Resampling.LANCZOS,
                             centering=(0.5, 0.0 if key == 'portrait' else 0.5))
    longest = {'preview': PREVIEW_LONGEST, 'logo': LOGO_LONGEST, 'landscape': LANDSCAPE_LONGEST, 'portrait': PORTRAIT_LONGEST}.get(key, COVER_LONGEST)
    scale = min(1.0, longest / max(image.size))
    alpha = ('A' in image.getbands() or 'transparency' in image.info) and key not in ('landscape', 'portrait')
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
    flags = [] if (root / 'ziran.local.toml').exists() else ['--locked']
    apps = Path(subprocess.check_output([str(root / 'scripts/ziran.sh'), 'pkg', 'path', 'apps', *flags], cwd=root, text=True).strip())
    for icon in ('profile', 'dew'):
        yield 'hud', icon, (apps / 'assets/hud' / (icon + '.webp')).read_bytes(), 0
    for package in declared_packages(root)[1:]:
        for app in package['apps']:
            if not app['enabled']:
                continue
            name = app['descriptor']['name']
            yield name, 'preview', (app['art_source'] / app['descriptor']['preview']).read_bytes(), 0
            for key in ('portrait', 'landscape', 'logo'):
                if app['cover'] and key in app['cover']:
                    yield name, key, (app['art_source'] / app['cover'][key]).read_bytes(), app.get('cover_crops', {}).get(key, 0)


def main():
    LIBRARY.mkdir(parents=True, exist_ok=True)
    sources = {}
    written = set()
    for name, key, data, crop_top in art():
        copy = f'{name}-{key}'
        contents, suffix = small_copy(data, 'preview' if name.endswith('-editor') else key, crop_top)
        (LIBRARY / (copy + suffix)).write_bytes(contents)
        written.add(copy + suffix)
        sources[copy] = {'source_sha256': hashlib.sha256(data).hexdigest(), 'crop_top': crop_top}
    for suffix in SUFFIXES:
        for stale in LIBRARY.glob('*' + suffix):
            if stale.name not in written:
                stale.unlink()
    (LIBRARY / 'sources.json').write_text(json.dumps(dict(sorted(sources.items())), indent=2) + '\n')
    total = sum((LIBRARY / name).stat().st_size for name in written)
    if total > ART_BUDGET:
        raise ValueError(f'Library art exceeds {ART_BUDGET} bytes: {total}')
    print(f'{len(sources)} library images, {total / 1048576:.1f} MiB (budget 2 MiB)')


if __name__ == '__main__':
    main()
