#!/usr/bin/env python3
"""Portable guests through Arcade's production Collection notification boundary."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'work/notification-api42'
ZIRAN = ROOT / 'scripts/ziran.sh'
LOCK = [] if (ROOT / 'ziran.local.toml').exists() else ['--locked']


def run(*args):
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True)


def package(name):
    return Path(subprocess.check_output([ZIRAN, 'pkg', 'path', name, *LOCK],
                                       cwd=ROOT, text=True).strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api41-games', action='store_true', help='Also identify the built API41 Chess and Shovey games')
    args = parser.parse_args()
    for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS',
                'SESSION_MANAGER', 'DESKTOP_SESSION', 'XDG_SESSION_ID', 'XDG_SESSION_TYPE'):
        os.environ.pop(key, None)
    os.environ.update(YUE_DESKTOP_RECOVERY='0', SDL_AUDIODRIVER='dummy', ZIRAN_JOBS='1')
    run('git', 'check-ignore', '-q', 'work/')
    WORK.mkdir(parents=True, exist_ok=True)
    if args.api41_games:
        for name in ('chess', 'shovey'):
            path = ROOT / 'build/games' / (name + '.zx')
            (WORK / (name + '-41.sha256')).write_text(hashlib.sha256(path.read_bytes()).hexdigest())
    apps = package('apps')
    toolchain = package('ziran')
    compiler = toolchain / 'build/bin/zi2c'
    if not compiler.is_file():
        compiler = ROOT / 'build/toolchain/bin/zi2c'
    zx = compiler.with_name('zi2zx')
    # Reuse the locked package's maintained recording scheduler provider.
    # No package source or cache is modified; only OS effects are substituted.
    source = ROOT / 'tests/collection_notifications_guest.zi'
    for game, identifier in [('wurm', 'xyz.waozi.wurm'), ('shovey', 'arcade.shovey')]:
        assets = WORK / game / 'assets/notification'
        assets.mkdir(parents=True, exist_ok=True)
        (assets / 'catalog.json').write_text(json.dumps(dict(id=identifier, name='notification',
            contract_version=1, module_api=2, host_api=42, save_schema=1)))
        for protocol in (1, 2):
            defines = ['--define', 'KRYON_HOSTED_UI']
            if protocol == 2:
                defines += ['--define', 'APPS_NOTIFICATION_NODE']
            if game == 'shovey':
                defines += ['--define', 'APPS_NOTIFICATION_SHOVEY']
            common = ['--project', *LOCK, '--root', ROOT / 'tests',
                      '--entry', 'collection_notifications_guest:Main', *defines]
            path = WORK / f'{game}-{protocol}.zx'
            run(ZIRAN, 'bundle', *common, '--asset-dir', 'assets=' + str(assets.parent),
                '-o', path, source)
            (WORK / f'{game}-{protocol}.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest())
            ir = WORK / f'ir-{game}-{protocol}'
            run(ZIRAN, 'ir', *common, '-o', ir, source)
            saved = WORK / f'{game}-{protocol}-saved.zx'
            run(zx, 'bundle', '--root', ir, '--module-path', ir,
                '--entry', 'collection_notifications_guest:Main', '--asset-dir', 'assets=' + str(assets.parent),
                '-o', saved, ir / 'collection_notifications_guest.zir')
            if path.read_bytes() != saved.read_bytes():
                raise RuntimeError(f'Source/saved guest differs: {game} protocol {protocol}')
    lines = (ROOT / 'build/.ziran/module-map.tsv').read_text().splitlines()
    replacements = {'notification_schedule': apps / 'tests/notification_provider.zi',
                    'collection_notification_platform': ROOT / 'tests/collection_notification_native_fixture.zi'}
    kryon_id = next(fields[3] for line in lines
                    if len(fields := line.split('\t')) == 5
                    and fields[:3] == ['D', 'root', 'kryon/notification_schedule'])
    replaced = dict.fromkeys(replacements, 0)
    for index, line in enumerate(lines):
        fields = line.split('\t')
        if len(fields) == 4 and fields[0] == 'M' and fields[2] in replacements:
            # Replace only Arcade's own OS facts and its resolved Kryon provider.
            if fields[2] == 'collection_notification_platform' and fields[1] != 'root':
                continue
            if fields[2] == 'notification_schedule' and fields[1] != kryon_id:
                continue
            fields[3] = str(replacements[fields[2]])
            replaced[fields[2]] += 1
            lines[index] = '\t'.join(fields)
    if any(count != 1 for count in replaced.values()):
        raise RuntimeError(f'Expected unique OS providers: {replaced}')
    # Reuse Apps' display-free raster exports without exposing test modules
    # through either package's production module roots.
    lines.append(f'M\troot\tgame_hud_host\t{apps / "tests/game_hud_host.zi"}')
    mapping = WORK / 'module-map.tsv'
    mapping.write_text('\n'.join(lines) + '\n')
    os.environ['ZIRAN_PACKAGE_MAP'] = str(mapping)
    output = WORK / 'c'
    run(compiler, '--prune-stale', '--module-path', toolchain / 'std', '--no-main',
        '--define', 'PLATFORM_DESKTOP', *(['--define', 'ARCADE_API41_GAMES'] if args.api41_games else []),
        '--entry', 'collection_notifications_behavior:Check',
        '--root', ROOT / 'tests', '-o', output, ROOT / 'tests/collection_notifications_behavior.zi',
        apps / 'tests/game_hud_host.zi')
    (output / 'entry.c').write_text('#include <stdio.h>\n#include "collection_notifications_behavior.h"\n'
        'int main(void) { int r=Check(); if(r) fprintf(stderr,"Arcade notification test %d failed\\n",r); return r; }\n')
    runtime = ROOT / 'build/ziran/libziran.a'
    run('make', '-j1', 'build/ziran/libziran.a')
    oqs_source = package('liboqs')
    oqs = ROOT / 'build' / ('entity-oqs-' + oqs_source.name)
    if not (oqs / 'lib/liboqs.a').is_file():
        run('cmake', '-S', oqs_source, '-B', oqs, '-DCMAKE_BUILD_TYPE=MinSizeRel',
            '-DBUILD_SHARED_LIBS=OFF', '-DOQS_BUILD_ONLY_LIB=ON', '-DOQS_USE_OPENSSL=OFF',
            '-DOQS_DIST_BUILD=OFF', '-DOQS_OPT_TARGET=generic',
            '-DOQS_MINIMAL_BUILD=SIG_ml_dsa_44;KEM_ml_kem_768')
        run('cmake', '--build', oqs, '--target', 'oqs', '--', '-j1')
    libraries = subprocess.check_output(['pkg-config', '--libs', 'sdl2', 'cairo', 'freetype2',
        'fontconfig', 'pangocairo', 'gtk+-3.0'], text=True).split()
    monocypher = package('monocypher')
    includes = [arg for p in [output, *sorted(output.rglob('*'))] if p.is_dir()
                for arg in ('-iquote', str(p))]
    temporary = WORK / 'test.new'
    run(os.environ.get('CC', 'cc'), '-std=c11', '-O1', '-ffunction-sections', '-fdata-sections',
        '-I' + str(toolchain / 'include'), *includes, *sorted(output.rglob('*.c')),
        runtime, '-I' + str(monocypher / 'src'), monocypher / 'src/monocypher.c',
        monocypher / 'src/optional/monocypher-ed25519.c', oqs / 'lib/liboqs.a',
        '-Wl,--gc-sections', *libraries, '-lX11', '-l:libcurl.so.4', '-lz', '-lm', '-lpthread', '-o', temporary)
    temporary.replace(WORK / 'test')
    run(WORK / 'test')
    print('Arcade Collection API42: source/saved node/2 + app/1 guests, native schedules, verified identity, permission, focus and tag isolation passed')
    if args.api41_games:
        print('Arcade API42 host also identified the built API41 Chess and Shovey games')


if __name__ == '__main__':
    main()
