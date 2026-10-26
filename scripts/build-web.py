#!/usr/bin/env python3
"""Build Arcade's browser edition into build/web-site.

The page runs a collection, by default this checkout's build/node-apps/arcade.zx;
the website passes the published one Inner Breeze downloads. Arcade's own host
is compiled to WebAssembly with the account Profile. The receipt names the
collection's digest and the Apps library it trusts.
"""
import argparse
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=ROOT / 'build/node-apps/arcade.zx')
    parser.add_argument('--controller-sha256', default=(ROOT / 'apps-controller.sha256').read_text().strip())
    parser.add_argument('--version', default=(ROOT / 'VERSION').read_text().strip())
    parser.add_argument('--profile', type=Path, default=ROOT / 'build/entity.zx')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/web-site')
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    receipt = dict(id='inbe.arcade', version=args.version,
                   sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),
                   apps_sha256=args.controller_sha256)
    work = ROOT / 'build/web'
    work.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, 'ZIRAN': str(package('ziran') / 'build/bin/ziran')}
    subprocess.run([sys.executable, str(package('entity') / 'scripts/build-web.py'),
                    '--bundle', str(bundle), '--profile', str(args.profile.resolve()),
                    '--output', str(work / 'runtime.html'),
                    '--entry', 'runtime:main', '--source', 'src/web/runtime.zi'], cwd=ROOT, env=env, check=True)
    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(ROOT / 'site', output)
    for name in ('runtime.js', 'runtime.wasm', 'runtime.data'):
        shutil.copyfile(work / name, output / name)
    (output / 'arcade.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(f'Arcade {args.version} for the browser in {output}')


if __name__ == '__main__':
    main()
