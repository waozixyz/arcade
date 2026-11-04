#!/usr/bin/env python3
"""Download Wurm's portable exports from its exact pinned release; compile nothing."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

EXPORT_FILES = {name + suffix for name in ('wurm', 'wurm-editor')
                for suffix in ('.zx', '-resources.json', '-catalog.json', '-preview.png')}
MAX_FILE_BYTES = 64 * 1024 * 1024


def unpack(archive, source):
    build = source / 'build'
    build.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, 'r:gz') as bundle:
        members = bundle.getmembers()
        if len(members) != len(EXPORT_FILES) or {m.name for m in members} != EXPORT_FILES:
            raise ValueError('Wurm release must contain exactly its eight portable exports')
        if any(not m.isfile() or not 0 < m.size <= MAX_FILE_BYTES for m in members):
            raise ValueError('Wurm release contains an invalid portable export')
        # Validate the complete member list before any output is replaced.
        with tempfile.TemporaryDirectory(prefix='portable-export-', dir=build) as directory:
            stage = Path(directory)
            for member in members:
                with bundle.extractfile(member) as incoming, (stage / member.name).open('wb') as output:
                    shutil.copyfileobj(incoming, output)
            exports = build / 'games'
            exports.mkdir(exist_ok=True)
            for name in EXPORT_FILES:
                (stage / name).replace(exports / name)


def fetch(source, commit):
    version = json.loads((source / 'version.json').read_text())['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version) or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Invalid Wurm release identity')
    tag = 'v' + version
    released = subprocess.check_output(['gh', 'api', f'repos/waozixyz/wurm/commits/{tag}',
                                        '--jq', '.sha'], text=True).strip()
    if released != commit:
        raise ValueError('Wurm release does not match Arcade\'s pinned commit')
    downloads = source / 'build/downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    name = f'wurm-portable-{tag}.tar.gz'
    subprocess.run(['gh', 'release', 'download', tag, '--repo', 'waozixyz/wurm',
                    '--pattern', name, '--dir', str(downloads), '--clobber'], check=True)
    unpack(downloads / name, source)
    print(f'Imported Wurm {version} portable release at {commit}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    fetch(args.source.resolve(), args.commit)
