#!/usr/bin/env python3
"""Sign and verify Arcade's Android APKs: the normal and F-Droid editions,
which hold no Google library, and the Google Play edition, the only one with
Play Billing. Each carries the whole library for offline play."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ABIS = ['arm64-v8a', 'armeabi-v7a']


def verify_launcher(apk, tools, names):
    """Resolve compiled resource IDs, including shortened release paths."""
    resources = subprocess.check_output(
        [str(tools / 'aapt'), 'dump', '--values', 'resources', str(apk)], text=True)
    entries = re.findall(r'resource (0x[0-9a-f]+) [^\n]+:(drawable/ic_launcher_\w+|mipmap/ic_launcher):[^\n]*\n\s*\(string8\) "([^"]+)"', resources)
    paths = {path for _, _, path in entries}
    assert paths <= set(names), 'A launcher resource is missing from the APK'
    legacy = [path for _, name, path in entries if name == 'mipmap/ic_launcher' and path.endswith('.png')]
    assert len(legacy) == 5, 'All five legacy icon densities must be present'
    adaptive = [path for _, name, path in entries if name == 'mipmap/ic_launcher' and path.endswith('.xml')]
    assert len(adaptive) == 1 and 'config anydpi-v26:' in resources, 'The Android adaptive icon is missing'
    layers = {name: identifier for identifier, name, _ in entries if name.startswith('drawable/')}
    tree = subprocess.check_output(
        [str(tools / 'aapt'), 'dump', 'xmltree', str(apk), adaptive[0]], text=True)
    assert 'E: adaptive-icon' in tree, 'The launcher XML is not adaptive'
    for layer in ('background', 'foreground'):
        identifier = layers.get('drawable/ic_launcher_' + layer)
        assert identifier and re.search(r'E: ' + layer + r'[^\n]*\n[^\n]*@' + identifier, tree), \
            f'The adaptive {layer} drawable is missing'


def build_tools():
    sdk = Path(os.environ.get('ANDROID_SDK_ROOT') or os.environ.get('ANDROID_HOME') or Path.home() / 'Android/Sdk')
    folders = sorted((sdk / 'build-tools').glob('*'), key=lambda p: tuple(int(n) for n in re.findall(r'\d+', p.name)))
    return next(p for p in reversed(folders) if all((p / name).is_file() for name in ('aapt', 'apksigner', 'zipalign')))


def verify(apk, version, tools, edition='direct'):
    assert re.fullmatch(r'\d+\.\d+\.\d+', version), 'A numeric release version is required'
    changelog = (ROOT / 'CHANGELOG.md').read_text()
    assert re.search(r'^## \[?' + re.escape(version) + r'\]?\s', changelog, re.M), 'Release version is absent from the changelog'
    badging = subprocess.check_output([str(tools / 'aapt'), 'dump', 'badging', str(apk)], text=True)
    package = re.search(r"^package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'", badging, re.M)
    assert package and package[1] == 'xyz.waozi.arcade' and package[3] == version, 'APK identity or version differs'
    assert "application-label:'Arcade'" in badging, 'The APK is not labelled Arcade'
    # Release builds shorten resource names; the manifest names the icon.
    icon = re.search(r"^application: label='Arcade' icon='(res/[^']+\.(?:png|xml))'", badging, re.M)
    assert icon, "Arcade's launcher icon is missing"
    assert 'application-debuggable' not in badging, 'A debug build cannot be published'
    google_play = edition == 'gplay'
    assert ("'com.android.vending.BILLING'" in badging) == google_play, \
        'Only the Google Play edition may ask for Play Billing'
    certificate = subprocess.check_output(['openssl', 'x509', '-in', str(ROOT / 'packaging/android/certificate.pem'), '-outform', 'DER'])
    expected = hashlib.sha256(certificate).hexdigest()
    signature = subprocess.check_output([str(tools / 'apksigner'), 'verify', '--verbose', '--print-certs', str(apk)], text=True)
    actual = re.findall(r'^(?:Signer #\d+|V[\d.]+ Signer:) certificate SHA-256 digest: ([0-9a-f]+)$', signature, re.M)
    assert 'Number of signers: 1' in signature and set(actual) == {expected}, 'APK signer differs from the Arcade release certificate'
    subprocess.run([str(tools / 'zipalign'), '-c', '-P', '16', '4', str(apk)], check=True, capture_output=True)
    with zipfile.ZipFile(apk) as archive:
        names = archive.namelist()
        abis = sorted(p.split('/')[1] for p in names if re.fullmatch(r'lib/[^/]+/libmain\.so', p))
        assert abis == ABIS, 'Both supported ARM architectures must be present'
        assert icon[1] in names, "Arcade's launcher icon is missing"
        if tuple(map(int, version.split('.'))) >= (0, 7, 115):
            verify_launcher(apk, tools, names)
        metadata = json.loads(archive.read('assets/arcade.json'))
        payload = archive.read('assets/arcade.zx')
        assert metadata['id'] == 'inbe.arcade' and metadata['version'] == version
        assert metadata['sha256'] == hashlib.sha256(payload).hexdigest(), 'Embedded collection differs from its receipt'
        # Offline play: every game in the catalog is packed into the collection.
        assert metadata.get('games') == 'packed' and 'art' not in metadata and metadata['children'], \
            'The collection must pack its games and art'
        for child in metadata['children']:
            assert child['bundle'].encode() in payload, f"{child['id']} is not packed for offline play"
        dex = b''.join(archive.read(name) for name in names if re.fullmatch(r'classes\d*\.dex', name))
        for marker in (b'Lorg/kryonlabs/play/PlayBilling;', b'Lcom/android/billingclient/'):
            assert (marker in dex) == google_play, 'Only the Google Play edition may include Play Billing'
    return dict(version=version, version_code=int(package[2]), package=package[1], abis=abis, edition=edition,
                sha256=hashlib.sha256(apk.read_bytes()).hexdigest(), certificate_sha256=expected,
                payload_sha256=metadata['sha256'], games=[child['id'] for child in metadata['children']],
                bytes=apk.stat().st_size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('sign', 'verify'))
    parser.add_argument('apk', type=Path)
    parser.add_argument('--version', required=True)
    parser.add_argument('--edition', choices=('direct', 'fdroid', 'gplay'), default='direct')
    parser.add_argument('--output', type=Path, help='Signed APK; build/android/arcade-VERSION[-EDITION].apk by default')
    parser.add_argument('--keystore', type=Path, default=ROOT / 'backup/android-signing/arcade-release.p12')
    parser.add_argument('--password-file', type=Path, default=ROOT / 'backup/android-signing/password')
    parser.add_argument('--alias', default='arcade')
    args = parser.parse_args()
    tools = build_tools()
    apk = args.apk.resolve(strict=True)
    if args.action == 'verify':
        verify(apk, args.version, tools, args.edition)
        print(f'Arcade {args.version} {args.edition}: APK identity, signer, alignment and offline games verified')
        return
    suffix = '' if args.edition == 'direct' else '-' + args.edition
    output = (args.output or ROOT / f'build/android/arcade-{args.version}{suffix}.apk').resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    aligned = output.with_name(output.stem + '.aligned-unsigned.apk')
    temporary = output.with_name(output.stem + '.new.apk')
    if subprocess.run([str(tools / 'zipalign'), '-c', '-P', '16', '4', str(apk)], capture_output=True).returncode == 0:
        shutil.copyfile(apk, aligned)
    else:
        subprocess.run([str(tools / 'zipalign'), '-P', '16', '-f', '4', str(apk), str(aligned)], check=True)
    try:
        # Keep the aligned entries as they are, so a rebuild from source can
        # take this signature unchanged.
        subprocess.run([str(tools / 'apksigner'), 'sign', '--alignment-preserved',
                        '--ks', str(args.keystore.resolve(strict=True)), '--ks-key-alias', args.alias,
                        '--ks-pass', 'file:' + str(args.password_file.resolve(strict=True)),
                        '--out', str(temporary), str(aligned)], check=True)
    finally:
        aligned.unlink(missing_ok=True)
    try:
        result = verify(temporary, args.version, tools, args.edition)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    temporary.replace(output)
    temporary.with_name(temporary.name + '.idsig').unlink(missing_ok=True)
    result['apk'] = str(output)
    records = ROOT / 'backup/android-release'
    records.mkdir(parents=True, exist_ok=True)
    (records / f'verification{suffix}.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f'Arcade {args.version} {args.edition}: signed {output}; identity, signer, alignment and offline games verified')


if __name__ == '__main__':
    main()
