#!/usr/bin/env python3
"""Build native Arcade and Pushy from an explicit local Apps source handoff.

Apps currently has no fetchable repository. This mode uses the retained
compiler and a declared source map; it must not be presented as a release lock.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

from importlib.machinery import SourceFileLoader

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apps-source', type=Path, required=True)
    parser.add_argument('--toolchain', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/arcade')
    parser.add_argument('--standalone-pushy', action='store_true')
    parser.add_argument('--preview-export', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    purpose = ROOT / ('build/pushy-preview-export' if args.preview_export else 'build/pushy-native' if args.standalone_pushy else 'build/arcade-native')
    purpose.mkdir(parents=True, exist_ok=True)
    module_map = purpose / 'module-map.tsv'
    helper = SourceFileLoader('apps_map', str(ROOT / 'scripts/local-apps-map.py')).load_module()
    helper.build(ROOT, args.apps_source.resolve(), module_map)
    if args.preview_export:
        rows = []
        for row in module_map.read_text().splitlines():
            fields = row.split('\t')
            if fields[:2] == ['M', 'root']:
                if '/apps/chess/' in fields[3] or '/apps/pushy/island/' in fields[3]:
                    continue
                # IR55 file imports still resolve a local module basename;
                # this authoring entry compiles only the Pushy source scope.
                if fields[3] == str(ROOT / 'apps/pushy/engine.zi'):
                    fields[2] = 'engine'
                    row = '\t'.join(fields)
            rows.append(row)
        module_map.write_text('\n'.join(rows) + '\n')
        with module_map.open('a') as stream:
            stream.write('M\troot\tpushy_preview_export\t' + str(ROOT / 'tests/pushy_preview_export.zi') + '\n')
    generated = purpose / 'c'
    # Only this build purpose owns generated C. Never replace an installed
    # binary in place: link separately, then atomically replace the path.
    if generated.exists():
        shutil.rmtree(generated)
    subprocess.run([str(args.toolchain / 'build/bin/zi2c'), '--define', 'PLATFORM_DESKTOP',
                    *(['--define', 'PUSHY_STANDALONE'] if args.standalone_pushy else []),
                    '--root', str(ROOT), '--entry', 'pushy_preview_export:main' if args.preview_export else 'desktop:main', '-o', str(generated),
                    'tests/pushy_preview_export.zi' if args.preview_export else 'src/desktop.zi'], cwd=ROOT,
                   env=os.environ | {'ZIRAN_PACKAGE_MAP': str(module_map)}, check=True)
    libraries = subprocess.check_output(['pkg-config', '--libs', 'sdl2', 'cairo', 'freetype2',
                                         'fontconfig', 'pangocairo'], text=True).split()
    temporary = output.with_suffix('.new')
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-O2', '-ffunction-sections',
                    '-fdata-sections', '-I' + str(args.toolchain / 'include'), '-iquote', str(generated),
                    *[item for path in generated.rglob('*') if path.is_dir()
                      for item in ('-iquote', str(path))],
                    *map(str, generated.rglob('*.c')), str(ROOT / 'build/ziran/libziran.a'),
                    '-Wl,--gc-sections', *libraries, '-lm', '-lpthread', '-o', str(temporary)], check=True)
    temporary.replace(output)
    print(('Pushy' if args.standalone_pushy else 'Arcade') + ' native source-handoff build passed')


if __name__ == '__main__':
    main()
