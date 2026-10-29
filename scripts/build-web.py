#!/usr/bin/env python3
"""Build Arcade's browser edition into build/web-site.

The page runs a collection, by default this checkout's build/node-apps/arcade.zx;
the website passes the published one Inner Breeze downloads. Arcade's own host
is compiled to WebAssembly with the account Profile. The receipt names the
collection's digest and the Apps library it trusts. Arcade's own copy of that
library goes beside it for collections that do not pack one.

With --shovey the page is shovey.waozi.xyz: the same host runs a released
Shovey download's own shovey.zx, shovey.json and entity.zx, unchanged, on the
page files --site names. Their programs, and the game and Apps controller
packed in shovey.zx, are compiled into the page, so they run as fast as a
native build of them; the page still opens those exact bytes.

The library's pictures come from the site too (stage_web_library_art), so
the covers never wait for the art bundle from api.waozi.xyz.
"""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
ZIRAN = str(ROOT / 'scripts/ziran.sh')
ART_LIMIT = 64 * 1024 * 1024
# The committed library copies are at most this large (scripts/library-art.py).
PICTURE_LONGEST = 640
COVER_QUALITY = 80


def bundle_assets(data):
    """The files embedded in a ZX v26 bundle by path; never runs it."""
    if data[:8] != b'ZX\0\0\x1a\0\0\0' or len(data) > ART_LIMIT:
        raise ValueError('unsupported bundle')
    at = 8

    def take(size):
        nonlocal at
        if at + size > len(data):
            raise ValueError('truncated bundle')
        value = data[at:at + size]
        at += size
        return value

    def number():
        return struct.unpack('<I', take(4))[0]

    def text():
        return take(number())

    text(); text()
    for _ in range(number()):
        text(); text()
    for _ in range(number()):
        for _ in range(7):
            text()
        take(8); text(); take(4)
    for _ in range(number()):
        for _ in range(3):
            text()
    take(number())
    assets = {}
    for _ in range(number()):
        path = text().decode()
        if path in assets:
            raise ValueError('duplicate bundle file')
        assets[path] = take(number())
    if at != len(data):
        raise ValueError('trailing bundle bytes')
    return assets


def published_art(folder, digest):
    """The art bundle a collection names, from the release's game archive
    beside it or a local build's arcade.games folder."""
    built = folder / 'arcade.games' / f'{digest}.zx'
    if built.is_file():
        return built.read_bytes()
    archive = folder / 'arcade.games.tar'
    if archive.is_file():
        with tarfile.open(archive) as games:
            member = next((entry for entry in games if entry.name == f'{digest}.zx'), None)
            if member is not None and member.isfile() and member.size <= ART_LIMIT:
                return games.extractfile(member).read()
    raise ValueError('The collection\'s art bundle is not beside it')


def web_picture(data, exact):
    """(bytes, suffix) of the page's copy of one verified library picture: a
    WebP, lossless when exact (pixel-art previews), unless the original is
    smaller. Transparency is kept; nothing is larger than PICTURE_LONGEST."""
    from PIL import Image
    image = Image.open(io.BytesIO(data))
    image.load()
    original = '.' + image.format.lower().replace('jpeg', 'jpg')
    alpha = 'A' in image.getbands() or 'transparency' in image.info
    image = image.convert('RGBA' if alpha else 'RGB')
    scale = min(1.0, PICTURE_LONGEST / max(image.size))
    if scale < 1.0:
        size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        image = image.resize(size, Image.Resampling.LANCZOS)
    output = io.BytesIO()
    if exact:
        image.save(output, 'WEBP', lossless=True, method=6)
    else:
        image.save(output, 'WEBP', quality=COVER_QUALITY, method=6)
    if scale == 1.0 and len(data) <= output.tell():
        return data, original
    return output.getvalue(), '.webp'


def stage_web_library_art(bundle, output):
    """Serve the collection's separate library art from the site.

    The art bundle must have the exact digest and size the collection's
    signed catalog names. Its pictures go to output/library as small WebP
    copies, named by content and listed in library.json under that digest;
    the exact bundle goes beside them for browsers that cannot draw WebP.
    Returns the listing, or None when the collection packs its own art.
    """
    assets = bundle_assets(bundle.read_bytes())
    catalog = json.loads(assets['assets/apps/catalog.json'])
    art = catalog.get('art')
    if art is None:
        return None
    digest, size = art.get('sha256', ''), art.get('bytes')
    if not re.fullmatch(r'[0-9a-f]{64}', digest) or not isinstance(size, int):
        raise ValueError('Invalid art in the collection catalog')
    data = published_art(bundle.parent, digest)
    if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('The art bundle differs from the collection catalog')
    pictures = bundle_assets(data)
    previews = {child[key] for child in catalog['children'] for key in ('preview', 'icon') if child.get(key)}
    covers = {path for child in catalog['children'] for key, path in child.get('cover', {}).items()
              if key in ('portrait', 'landscape', 'logo')}
    copies = {}
    for path in sorted(previews | covers):
        if path not in pictures:
            raise ValueError(f'The art bundle lacks {path}')
        copies[path] = web_picture(pictures[path], path in previews)
    library = output / 'library'
    if library.exists():
        shutil.rmtree(library)
    library.mkdir(parents=True)
    (library / f'{digest}.zx').write_bytes(data)
    listed = {}
    for path, (contents, suffix) in copies.items():
        name = hashlib.sha256(contents).hexdigest()
        (library / (name + suffix)).write_bytes(contents)
        listed[path] = dict(file=f'library/{name}{suffix}', sha256=name, bytes=len(contents))
    manifest = dict(art=digest, bytes=size, pictures=listed)
    (output / 'library.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def package(name):
    flags = [] if (ROOT / 'ziran.local.toml').exists() else ['--locked']
    return Path(subprocess.check_output([ZIRAN, 'pkg', 'path', name, *flags], cwd=ROOT, text=True).strip())


def compress(path):
    """A gzip copy beside path, which the page fetches first: Cloudflare
    Pages does not compress binary files (apps.zx 1.9 MB -> 0.24 MB)."""
    with open(path.with_name(path.name + '.gz'), 'wb') as raw:
        with gzip.GzipFile(filename='', mode='wb', compresslevel=9, fileobj=raw, mtime=0) as packed:
            packed.write(path.read_bytes())


def version_assets(output, receipt):
    """Keep the runtime, its data and the verified collection on one cache key."""
    page = output / 'index.html'
    html = page.read_text()
    if '__ARCADE_ASSET_REVISION__' not in html:
        return
    digest = hashlib.sha256()
    for name in ('runtime.js', 'runtime.wasm', 'runtime.data', 'arcade.json', 'apps.zx', 'library.json'):
        path = output / name
        if path.is_file():
            digest.update(name.encode() + b'\0')
            digest.update(path.read_bytes())
    revision = digest.hexdigest()
    page.write_text(html.replace('__ARCADE_ASSET_REVISION__', revision))
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    (output / 'build.json').write_text(json.dumps({
        'source_revision': source, 'version': receipt['version'],
        'assets_sha256': revision,
    }, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=ROOT / 'build/node-apps/arcade.zx')
    parser.add_argument('--controller-sha256', default=(ROOT / 'apps-controller.sha256').read_text().strip())
    parser.add_argument('--version', default=(ROOT / 'VERSION').read_text().strip())
    parser.add_argument('--profile', type=Path, default=ROOT / 'build/entity.zx')
    parser.add_argument('--controller', type=Path, default=ROOT / 'build/apps-ui/apps.zx')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/web-site')
    parser.add_argument('--shovey', type=Path, help='a released Shovey download folder')
    parser.add_argument('--site', type=Path, default=ROOT / 'site')
    args = parser.parse_args()
    if args.shovey:
        bundle = (args.shovey / 'shovey.zx').resolve()
        receipt = json.loads((args.shovey / 'shovey.json').read_text())
        if receipt.get('id') != 'arcade.shovey-player' or \
                hashlib.sha256(bundle.read_bytes()).hexdigest() != receipt.get('sha256'):
            raise SystemExit('The Shovey download does not match its shovey.json')
        args.profile = args.shovey / 'entity.zx'
        args.controller_sha256 = receipt['apps_sha256']
        args.version = receipt['version']
    else:
        bundle = args.bundle.resolve()
        receipt = dict(id='inbe.arcade', version=args.version,
                       sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),
                       apps_sha256=args.controller_sha256)
    # The host reads the receipt into a 4 KiB buffer.
    text = json.dumps(receipt, separators=(',', ':')) if args.shovey else json.dumps(receipt, indent=2) + '\n'
    if len(text.encode()) >= 4096:
        raise SystemExit('The receipt exceeds the host buffer')
    work = ROOT / 'build/web'
    work.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, 'ZIRAN': str(package('ziran') / 'build/bin/ziran')}
    linked = [item for path in (bundle, args.profile.resolve()) for item in ('--linked', str(path))] \
        if args.shovey else []
    subprocess.run([sys.executable, str(package('entity') / 'scripts/build-web.py'),
                    '--bundle', str(bundle), '--profile', str(args.profile.resolve()),
                    '--output', str(work / 'runtime.html'), *linked,
                    '--entry', 'runtime:main', '--source', 'src/web/runtime.zi'], cwd=ROOT, env=env, check=True)
    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(args.site, output)
    for name in ('runtime.js', 'runtime.wasm', 'runtime.data'):
        shutil.copyfile(work / name, output / name)
    compress(output / 'runtime.data')
    (output / 'arcade.json').write_text(text)
    # Only the library the receipt trusts; the host refuses any other.
    controller = args.controller.read_bytes() if args.controller.is_file() else b''
    if hashlib.sha256(controller).hexdigest() == args.controller_sha256:
        (output / 'apps.zx').write_bytes(controller)
        compress(output / 'apps.zx')
    else:
        print('No matching Apps controller beside the collection; it must pack its own')
    if not args.shovey and stage_web_library_art(bundle, output) is None:
        print('The collection packs its own library art')
    version_assets(output, receipt)
    print(f'{"Shovey" if args.shovey else "Arcade"} {args.version} for the browser in {output}')


if __name__ == '__main__':
    main()
