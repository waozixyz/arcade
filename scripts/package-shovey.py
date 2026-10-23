#!/usr/bin/env python3
"""Pack standalone Shovey's desktop download: the native player beside its
verified game collection, profile and startup pictures."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ['shovey.zib', 'shovey.json', 'entity.zib', 'startup/shovey/title-portrait.png',
        'startup/shovey/title-landscape.png', 'startup/shovey/logo.png']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform', choices=('linux', 'windows'))
    parser.add_argument('--binary', type=Path, help='The built player; build/shovey on Linux')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'build/downloads')
    args = parser.parse_args()
    metadata = json.loads((ROOT / 'build/shovey.json').read_text())
    if hashlib.sha256((ROOT / 'build/shovey.zib').read_bytes()).hexdigest() != metadata['sha256']:
        raise ValueError('The Shovey payload changed; rebuild the collection first')
    version = metadata['version']
    binary = args.binary or ROOT / 'build/shovey'
    program = 'shovey.exe' if args.platform == 'windows' else 'shovey'
    files = [(program, binary.read_bytes(), 0o755)]
    files += [(name, (ROOT / 'build' / name).read_bytes(), 0o644) for name in DATA]
    stamp = int(os.environ.get('SOURCE_DATE_EPOCH') or time.time())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.platform == 'linux':
        output = args.output_dir / f'shovey-v{version}-linux-x86_64.tar.gz'
        temporary = output.with_suffix('.new')
        with tarfile.open(temporary, 'w:gz') as archive:
            for name, contents, mode in files:
                entry = tarfile.TarInfo('shovey/' + name)
                entry.size, entry.mode, entry.mtime = len(contents), mode, stamp
                archive.addfile(entry, io.BytesIO(contents))
    else:
        output = args.output_dir / f'shovey-v{version}-windows-x86_64.zip'
        temporary = output.with_suffix('.new')
        moment = time.gmtime(max(stamp, 315532800))[:6]
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, contents, mode in files:
                entry = zipfile.ZipInfo('Shovey/' + name, moment)
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = mode << 16
                archive.writestr(entry, contents)
    temporary.replace(output)
    print(f'Shovey {version} {args.platform} download: {output}')


if __name__ == '__main__':
    main()
