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
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ZIRAN = str(ROOT / 'scripts/ziran.sh')


def package(name):
    flags = [] if (ROOT / 'ziran.local.toml').exists() else ['--locked']
    return Path(subprocess.check_output([ZIRAN, 'pkg', 'path', name, *flags], cwd=ROOT, text=True).strip())


def compress(path):
    """A gzip copy beside path, which the page fetches first: Cloudflare
    Pages does not compress binary files (apps.zx 1.9 MB -> 0.24 MB)."""
    with open(path.with_name(path.name + '.gz'), 'wb') as raw:
        with gzip.GzipFile(filename='', mode='wb', compresslevel=9, fileobj=raw, mtime=0) as packed:
            packed.write(path.read_bytes())


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
    print(f'{"Shovey" if args.shovey else "Arcade"} {args.version} for the browser in {output}')


if __name__ == '__main__':
    main()
