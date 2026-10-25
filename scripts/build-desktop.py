#!/usr/bin/env python3
"""Build native Arcade, or standalone Shovey, from the project's locked packages."""
import argparse
import fcntl
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ZIRAN = str(ROOT / 'scripts/ziran.sh')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--standalone-shovey', action='store_true')
    parser.add_argument('--generated', type=Path, help='Private generated-source output for an isolated build')
    args = parser.parse_args()
    output = (args.output or ROOT / 'build' / ('shovey' if args.standalone_shovey else 'arcade')).resolve()
    lock = [] if (ROOT / 'ziran.local.toml').exists() else ['--locked']
    toolchain = Path(subprocess.check_output([ZIRAN, 'pkg', 'path', 'ziran', *lock],
                                             cwd=ROOT, text=True).strip())
    generated = args.generated.resolve() if args.generated else ROOT / ('build/shovey-native' if args.standalone_shovey else 'build/arcade-native') / 'c'
    # Only this build purpose owns generated C. Never replace an installed
    # binary in place: link separately, then atomically replace the path.
    if generated.exists():
        shutil.rmtree(generated)
    subprocess.run([ZIRAN, 'build', '--project', *lock, '--target=c', '--define', 'PLATFORM_DESKTOP',
                    *(['--define', 'SHOVEY_STANDALONE'] if args.standalone_shovey else []),
                    '--entry', 'desktop:main', '-o', str(generated), 'src/desktop.zi'], cwd=ROOT, check=True)
    libraries = subprocess.check_output(['pkg-config', '--libs', 'sdl2', 'cairo', 'freetype2',
                                         'fontconfig', 'pangocairo', 'gtk+-3.0'], text=True).split()
    def package(name):
        return Path(subprocess.check_output([ZIRAN, 'pkg', 'path', name, *lock], cwd=ROOT, text=True).strip())
    oqs_source = package('liboqs')
    oqs = ROOT / 'build' / ('entity-oqs-' + oqs_source.name)
    # Arcade and standalone Shovey share this library; parallel make builds
    # both, so only one may configure and build it at a time.
    with open(oqs.with_name(oqs.name + '.lock'), 'w') as exclusive:
        fcntl.flock(exclusive, fcntl.LOCK_EX)
        subprocess.run(['cmake', '-S', str(oqs_source), '-B', str(oqs),
                        '-DCMAKE_BUILD_TYPE=MinSizeRel', '-DBUILD_SHARED_LIBS=OFF',
                        '-DOQS_BUILD_ONLY_LIB=ON', '-DOQS_USE_OPENSSL=OFF', '-DOQS_DIST_BUILD=OFF',
                        '-DOQS_OPT_TARGET=generic', '-DOQS_MINIMAL_BUILD=SIG_ml_dsa_44'], check=True)
        subprocess.run(['cmake', '--build', str(oqs), '--target', 'oqs', '-j2'], check=True)
    temporary = output.with_suffix('.new')
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-O2', '-ffunction-sections',
                    '-fdata-sections', '-I' + str(toolchain / 'include'), '-iquote', str(generated),
                    *[item for path in generated.rglob('*') if path.is_dir()
                      for item in ('-iquote', str(path))],
                    *map(str, generated.rglob('*.c')), str(ROOT / 'build/ziran/libziran.a'),
                    '-I' + str(package('monocypher') / 'src'), str(package('monocypher') / 'src/monocypher.c'),
                    # Entity's device keys sign with Monocypher's standard Ed25519.
                    str(package('monocypher') / 'src/optional/monocypher-ed25519.c'), str(oqs / 'lib/liboqs.a'),
                    '-Wl,--gc-sections', *libraries, '-lX11', '-l:libcurl.so.4', '-lz', '-lm', '-lpthread', '-o', str(temporary)], check=True)
    temporary.replace(output)
    if args.standalone_shovey:
        from PIL import Image
        source = Path(subprocess.check_output([ZIRAN, 'pkg', 'path', 'shovey', *lock], cwd=ROOT, text=True).strip())
        startup = output.parent / 'startup/shovey'
        startup.mkdir(parents=True, exist_ok=True)
        for name in ('title-portrait.png', 'title-landscape.png', 'logo.png'):
            shutil.copyfile(source / 'assets/shovey' / name, startup / name)
        Image.open(source / 'assets/branding/shovey-icon.png').resize((256, 256), Image.Resampling.LANCZOS).save(output.parent / 'shovey-icon.png')
    print(('Shovey' if args.standalone_shovey else 'Arcade') + ' native build passed')


if __name__ == '__main__':
    main()
