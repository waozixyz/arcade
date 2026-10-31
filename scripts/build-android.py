#!/usr/bin/env python3
"""Package Arcade's native Android host: Arcade with its whole library offline,
or the older standalone Shovey collection."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

def package(name):
    return Path(subprocess.check_output([str(ROOT / 'scripts/ziran.sh'), 'pkg', 'path', name], cwd=ROOT, text=True).strip())

def ziran_bundle(*arguments):
    # A local checkout overrides packages in ziran.local.toml, as make does.
    locked = [] if (ROOT / 'ziran.local.toml').exists() else ['--locked']
    subprocess.run([str(ROOT / 'scripts/ziran.sh'), 'bundle', '--project', *locked, *arguments],
                   cwd=ROOT, check=True)

def launcher_icon(source, resources):
    """Density variants are mechanical packaging of the original logo."""
    icon = Image.open(source).convert('RGBA')
    if resources.exists():
        shutil.rmtree(resources)
    for density, size in (('mdpi', 48), ('hdpi', 72), ('xhdpi', 96), ('xxhdpi', 144), ('xxxhdpi', 192)):
        folder = resources / ('mipmap-' + density)
        folder.mkdir(parents=True)
        icon.resize((size, size), Image.Resampling.LANCZOS).save(folder / 'ic_launcher.png')

def stage_arcade():
    """Pack the staged collection with its games, art and Apps controller, so
    the APK opens the whole library offline. Returns Arcade's release."""
    collection = ROOT / 'build/collection'
    receipt = json.loads((collection / 'receipt.json').read_text())
    release = json.loads((ROOT / 'apps/versions.json').read_text())['node_apps']['arcade']
    if receipt['version'] != release['version'] or receipt['version'] != (ROOT / 'VERSION').read_text().strip():
        raise ValueError('The Arcade version changed; rebuild the collection first')
    controller = (collection / 'assets/apps/apps.zx').read_bytes()
    if hashlib.sha256(controller).hexdigest() != receipt['apps_sha256']:
        raise ValueError('The staged Apps controller differs from the receipt')
    assets = ROOT / 'build/android-assets'
    if assets.exists():
        shutil.rmtree(assets)
    assets.mkdir(parents=True)
    ziran_bundle('--root', str(ROOT / 'src'), '--entry', 'collection:Main',
                 '--asset-dir', 'assets=' + str(collection / 'assets'), '-o', str(assets / 'arcade.zx'),
                 str(ROOT / 'src/collection.zi'))
    # The library packs its games and art: the host downloads nothing.
    offline = {key: value for key, value in receipt.items() if key != 'art'} | {'games': 'packed'}
    offline['sha256'] = hashlib.sha256((assets / 'arcade.zx').read_bytes()).hexdigest()
    (assets / 'arcade.json').write_text(json.dumps(offline, indent=2) + '\n')
    # Android before 10 has no font lookup; the Windows build ships the same font.
    shutil.copyfile(package('kryon') / 'assets/fonts/LiberationSans-Regular.ttf', assets / 'kryon-font.ttf')
    launcher_icon(ROOT / 'site/android-launcher-512.png', ROOT / 'build/android-res')
    # Only Arcade gets this adaptive icon; standalone Shovey keeps its art.
    shutil.copytree(ROOT / 'packaging/android/icon-res', ROOT / 'build/android-res', dirs_exist_ok=True)
    return release

def stage_shovey():
    """Shovey's standalone collection from Arcade's staging. Returns its release."""
    metadata = json.loads((ROOT / 'build/shovey.json').read_text())
    payload = (ROOT / 'build/shovey.zx').read_bytes()
    if hashlib.sha256(payload).hexdigest() != metadata['sha256']:
        raise ValueError('The Shovey payload changed; rebuild the collection first')
    release = json.loads((ROOT / 'apps/versions.json').read_text())['node_apps']['shovey']
    if release['version'] != metadata['version']:
        raise ValueError('The Shovey version changed; rebuild the collection first')
    assets = ROOT / 'build/android-shovey-assets'
    assets.mkdir(parents=True, exist_ok=True)
    for suffix in ('zx', 'json'):
        shutil.copyfile(ROOT / f'build/shovey.{suffix}', assets / f'arcade.{suffix}')
    shutil.copyfile(package('kryon') / 'assets/fonts/LiberationSans-Regular.ttf', assets / 'kryon-font.ttf')
    launcher_icon(package('shovey') / 'assets/branding/shovey-icon.png', ROOT / 'build/android-shovey-res')
    return release

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--product', choices=('shovey', 'arcade'), default='shovey',
                        help='arcade: Arcade with its whole library; shovey: the standalone Shovey collection')
    parser.add_argument('--release', action='store_true', help='Build an unsigned release APK for the release signer')
    parser.add_argument('--edition', choices=('direct', 'fdroid', 'gplay'), default='direct',
                        help='The APK edition; only gplay carries a Google library')
    parser.add_argument('--bundle', action='store_true',
                        help="Build the Google Play edition's unsigned release Android App Bundle")
    parser.add_argument('--application-id', help='Use an isolated package for device tests')
    parser.add_argument('--abis', default='arm64-v8a,armeabi-v7a', help='Native ABIs to build')
    parser.add_argument('--build-dir', type=Path, help='Separate Gradle and CMake output for verification')
    args = parser.parse_args()
    subprocess.run(['python3', str(ROOT / 'tests/android_jni_contract_test.py')],
                   cwd=ROOT, check=True)
    arcade = args.product == 'arcade'
    if arcade and args.bundle:
        parser.error('Arcade builds APKs; the App Bundle is the standalone Shovey one')
    subprocess.run(['make', 'build/entity.zx'], cwd=ROOT, check=True)
    release = stage_arcade() if arcade else stage_shovey()
    sdk = Path(os.environ.get('ANDROID_SDK_ROOT') or os.environ.get('ANDROID_HOME') or Path.home() / 'Android/Sdk')
    env = {key: value for key, value in os.environ.items() if key not in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS')}
    env.update(ANDROID_HOME=str(sdk), ANDROID_SDK_ROOT=str(sdk),
               LIBOQS_DIR=str(package('liboqs')), MONOCYPHER_DIR=str(package('monocypher')))
    command = ['sh', str(ROOT / 'droid/gradlew'), '-p', str(ROOT / 'droid'), '--no-daemon', '--max-workers=2',
               '-Papp.product=' + args.product, '-Papp.abis=' + args.abis,
               '-Pkryon.dir=' + str(package('kryon')), '-Pziran.dir=' + str(package('ziran')),
               '-Praylib.dir=' + str(package('raylib') / 'src'),
               '-Papp.versionName=' + release['version'], '-Papp.versionCode=' + str(release['sequence']),
               '-Pandroid.aapt2FromMavenOverride=' + str(sdk / 'build-tools/36.0.0/aapt2'),
               'bundleRelease' if args.bundle else 'assembleRelease' if args.release else 'assembleDebug']
    # Kryon's Google Play edition adds Play Billing, so Dew is bought through Play.
    edition = 'gplay' if args.bundle else args.edition
    if edition == 'gplay':
        command[-1:-1] = ['-Papp.edition=gplay', '-Pandroid.useAndroidX=true']
    elif edition == 'fdroid':
        command.insert(-1, '-Papp.edition=fdroid')
    if args.application_id:
        command.insert(-1, '-Papp.id=' + args.application_id)
    if args.build_dir:
        command.insert(-1, '-Papp.outputDir=' + str(args.build_dir.resolve()))
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    app_output = args.build_dir.resolve() if args.build_dir else ROOT / 'droid/app/build'
    if args.bundle:
        bundle = app_output / 'outputs/bundle/release/app-release.aab'
        output = ROOT / ('build/shovey-test-unsigned.aab' if args.application_id else 'build/shovey-unsigned.aab')
        shutil.copyfile(bundle, output)
        print(f'Standalone Shovey Android App Bundle: {output}')
        return
    apk = app_output / ('outputs/apk/release/app-release-unsigned.apk' if args.release else
                        'outputs/apk/debug/app-debug.apk')
    if arcade:
        suffix = '' if edition == 'direct' else '-' + edition
        output = ROOT / 'build/android' / (f'arcade{suffix}-unsigned.apk' if args.release else f'arcade{suffix}.apk')
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(apk, output)
        print(f'Arcade APK: {output}')
        return
    output = ROOT / ('build/shovey-test-unsigned.apk' if args.application_id else
                     'build/shovey-unsigned.apk' if args.release else 'build/shovey.apk')
    shutil.copyfile(apk, output)
    print(f'Standalone Shovey APK: {output}')

if __name__ == '__main__':
    main()
