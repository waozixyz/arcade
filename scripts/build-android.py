#!/usr/bin/env python3
"""Package Arcade's existing native host with the standalone Shovey collection."""
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
    assets = ROOT / 'build/android-shovey-assets'
    assets.mkdir(parents=True, exist_ok=True)
    for suffix in ('zib', 'json'):
        shutil.copyfile(ROOT / f'build/shovey.{suffix}', assets / f'arcade.{suffix}')
    # Density variants are mechanical packaging of the original generated logo.
    icon = Image.open(package('shovey') / 'assets/branding/shovey-icon.png').convert('RGBA')
    resources = ROOT / 'build/android-shovey-res'
    for density, size in (('mdpi', 48), ('hdpi', 72), ('xhdpi', 96), ('xxhdpi', 144), ('xxxhdpi', 192)):
        folder = resources / ('mipmap-' + density)
        folder.mkdir(parents=True, exist_ok=True)
        icon.resize((size, size), Image.Resampling.LANCZOS).save(folder / 'ic_launcher.png')
    sdk = Path(os.environ.get('ANDROID_SDK_ROOT') or os.environ.get('ANDROID_HOME') or Path.home() / 'Android/Sdk')
    env = {key: value for key, value in os.environ.items() if key not in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS')}
    env.update(ANDROID_HOME=str(sdk), ANDROID_SDK_ROOT=str(sdk))
    command = ['sh', str(ROOT / 'droid/gradlew'), '-p', str(ROOT / 'droid'), '--no-daemon', '--max-workers=4',
               '-Papp.product=shovey', '-Papp.abis=arm64-v8a,armeabi-v7a',
               '-Pkryon.dir=' + str(package('kryon')), '-Pziran.dir=' + str(package('ziran')),
               '-Praylib.dir=' + str(package('raylib') / 'src'),
               '-Pandroid.aapt2FromMavenOverride=' + str(sdk / 'build-tools/36.0.0/aapt2'), 'assembleDebug']
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    apk = ROOT / 'droid/app/build/outputs/apk/debug/app-debug.apk'
    output = ROOT / 'build/shovey.apk'
    shutil.copyfile(apk, output)
    print(f'Standalone Shovey APK: {output}')

if __name__ == '__main__':
    main()
