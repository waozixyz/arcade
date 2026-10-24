#!/usr/bin/env python3
"""Build Entity once for the outer native host; never pack it into a game."""
from pathlib import Path
import argparse
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ZIRAN = str(ROOT / 'scripts/ziran.sh')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--locked', action='store_true')
args = parser.parse_args()
flags = ['--locked'] if args.locked or not (ROOT / 'ziran.local.toml').exists() else []
def package(name):
    return Path(subprocess.check_output([ZIRAN, 'pkg', 'path', name, *flags], cwd=ROOT, text=True).strip())
entity, kryon, toolchain, qrcode = map(package, ('entity', 'kryon', 'ziran', 'qrcode'))
subprocess.run([ZIRAN, 'bundle', '--root', str(entity),
                '--module-path', str(entity / 'src'),
                '--module-path', str(kryon / 'src/ui'),
                '--module-path', 'kryon=' + str(kryon / 'src/ui'),
                '--module-path', 'kryon=' + str(kryon / 'src/backend'),
                '--module-path', 'qrcode=' + str(qrcode / 'src'),
                '--module-path', str(toolchain / 'std'),
                '--define', 'KRYON_HOSTED_UI', '--asset-dir', 'assets=' + str(entity / 'assets'),
                '--entry', 'entity:Main', '-o', str(ROOT / 'build/entity.zx'), str(entity / 'src/entity.zi')],
               cwd=entity, check=True)

assets = ROOT / 'build/entity-assets'
assets.mkdir(parents=True, exist_ok=True)
shutil.copyfile(ROOT / 'build/entity.zx', assets / 'entity.zx')
