#!/usr/bin/env python3
"""Package Arcade's existing native host with the standalone Shovey collection."""
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

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', action='store_true', help='Build an unsigned release APK for the release signer')
    parser.add_argument('--bundle', action='store_true', help='Build an unsigned release Android App Bundle for Google Play')
    parser.add_argument('--application-id', help='Use an isolated package for device tests')
    args = parser.parse_args()
    subprocess.run(['make', 'build/entity.zx'], cwd=ROOT, check=True)
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
    # Android before 10 has no font lookup; the Windows build ships the same font.
    shutil.copyfile(package('kryon') / 'assets/fonts/LiberationSans-Regular.ttf', assets / 'kryon-font.ttf')
    # Density variants are mechanical packaging of the original generated logo.
    icon = Image.open(package('shovey') / 'assets/branding/shovey-icon.png').convert('RGBA')
    resources = ROOT / 'build/android-shovey-res'
    for density, size in (('mdpi', 48), ('hdpi', 72), ('xhdpi', 96), ('xxhdpi', 144), ('xxxhdpi', 192)):
        folder = resources / ('mipmap-' + density)
        folder.mkdir(parents=True, exist_ok=True)
        icon.resize((size, size), Image.Resampling.LANCZOS).save(folder / 'ic_launcher.png')
    sdk = Path(os.environ.get('ANDROID_SDK_ROOT') or os.environ.get('ANDROID_HOME') or Path.home() / 'Android/Sdk')
    env = {key: value for key, value in os.environ.items() if key not in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS')}
    env.update(ANDROID_HOME=str(sdk), ANDROID_SDK_ROOT=str(sdk),
               LIBOQS_DIR=str(package('liboqs')), MONOCYPHER_DIR=str(package('monocypher')))
    command = ['sh', str(ROOT / 'droid/gradlew'), '-p', str(ROOT / 'droid'), '--no-daemon', '--max-workers=4',
               '-Papp.product=shovey', '-Papp.abis=arm64-v8a,armeabi-v7a',
               '-Pkryon.dir=' + str(package('kryon')), '-Pziran.dir=' + str(package('ziran')),
               '-Praylib.dir=' + str(package('raylib') / 'src'),
               '-Papp.versionName=' + metadata['version'], '-Papp.versionCode=' + str(release['sequence']),
               '-Pandroid.aapt2FromMavenOverride=' + str(sdk / 'build-tools/36.0.0/aapt2'),
               'bundleRelease' if args.bundle else 'assembleRelease' if args.release else 'assembleDebug']
    if args.application_id:
        command.insert(-1, '-Papp.id=' + args.application_id)
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    if args.bundle:
        bundle = ROOT / 'droid/app/build/outputs/bundle/release/app-release.aab'
        output = ROOT / ('build/shovey-test-unsigned.aab' if args.application_id else 'build/shovey-unsigned.aab')
        shutil.copyfile(bundle, output)
        print(f'Standalone Shovey Android App Bundle: {output}')
        return
    apk = ROOT / ('droid/app/build/outputs/apk/release/app-release-unsigned.apk' if args.release else
                  'droid/app/build/outputs/apk/debug/app-debug.apk')
    output = ROOT / ('build/shovey-test-unsigned.apk' if args.application_id else
                     'build/shovey-unsigned.apk' if args.release else 'build/shovey.apk')
    shutil.copyfile(apk, output)
    print(f'Standalone Shovey APK: {output}')

if __name__ == '__main__':
    main()
