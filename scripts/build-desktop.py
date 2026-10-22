#!/usr/bin/env python3
"""Build native Arcade, or standalone Shovey, from the project's locked packages."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ZIRAN = str(ROOT / 'scripts/ziran.sh')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/arcade')
    parser.add_argument('--standalone-shovey', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    lock = [] if (ROOT / 'ziran.local.toml').exists() else ['--locked']
    toolchain = Path(subprocess.check_output([ZIRAN, 'pkg', 'path', 'ziran', *lock],
                                             cwd=ROOT, text=True).strip())
    generated = ROOT / ('build/shovey-native' if args.standalone_shovey else 'build/arcade-native') / 'c'
    # Only this build purpose owns generated C. Never replace an installed
    # binary in place: link separately, then atomically replace the path.
    if generated.exists():
        shutil.rmtree(generated)
    subprocess.run([ZIRAN, 'build', '--project', *lock, '--target=c', '--define', 'PLATFORM_DESKTOP',
                    *(['--define', 'SHOVEY_STANDALONE'] if args.standalone_shovey else []),
                    '--entry', 'desktop:main', '-o', str(generated), 'src/desktop.zi'], cwd=ROOT, check=True)
    libraries = subprocess.check_output(['pkg-config', '--libs', 'sdl2', 'cairo', 'freetype2',
                                         'fontconfig', 'pangocairo'], text=True).split()
    temporary = output.with_suffix('.new')
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-O2', '-ffunction-sections',
                    '-fdata-sections', '-I' + str(toolchain / 'include'), '-iquote', str(generated),
                    *[item for path in generated.rglob('*') if path.is_dir()
                      for item in ('-iquote', str(path))],
                    *map(str, generated.rglob('*.c')), str(ROOT / 'build/ziran/libziran.a'),
                    '-Wl,--gc-sections', *libraries, '-lm', '-lpthread', '-o', str(temporary)], check=True)
    temporary.replace(output)
    if args.standalone_shovey:
        from PIL import Image
        source = Path(subprocess.check_output([ZIRAN, 'pkg', 'path', 'shovey', *lock], cwd=ROOT, text=True).strip())
        Image.open(source / 'assets/branding/shovey-icon.png').resize((256, 256), Image.Resampling.LANCZOS).save(output.parent / 'shovey-icon.png')
    print(('Shovey' if args.standalone_shovey else 'Arcade') + ' native build passed')


if __name__ == '__main__':
    main()
