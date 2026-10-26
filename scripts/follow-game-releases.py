#!/usr/bin/env python3
"""Follow the published releases of Arcade's game packages.

`pin` moves each game package in ziran.lock to the commit of its repository's
latest published GitHub release, when that commit is ahead of the current pin.
Only the game's own entry changes: its dependencies keep Arcade's pins, so the
games build against the same Kryon and Apps as Arcade. The ids and layout are
the ones `ziran lock` writes. The updates are recorded in build/game-updates.json.

`changelog` adds an Arcade release entry naming each updated game with the
notes of its newest release, for update_version.sh to synchronize.

`art` remakes the library's small copies of game art (scripts/library-art.py)
only when a game's art changed, so unchanged copies keep their bytes.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPDATES = ROOT / 'build/game-updates.json'


def package_id(url, commit):
    """The id `ziran lock` gives a source at a commit (PkgSourceId)."""
    return 'p' + hashlib.sha256((url + '\n' + commit).encode()).hexdigest()[:16]


def write_lock(lock):
    """The lock as Ziran writes it: sorted keys, one-line maps, packages kept
    in their order."""
    def value(item):
        if isinstance(item, dict):
            return '{' + ', '.join(json.dumps(k) + ': ' + json.dumps(item[k]) for k in sorted(item)) + '}'
        return json.dumps(item)

    def block(item, indent):
        pad = ' ' * indent
        fields = [pad + '  ' + json.dumps(k) + ': ' + value(item[k]) for k in sorted(item)]
        return pad + '{\n' + ',\n'.join(fields) + '\n' + pad + '}'

    text = '{\n  "format": ' + json.dumps(lock['format']) + ',\n  "packages": [\n'
    text += ',\n'.join(block(item, 4) for item in lock['packages']) + '\n  ],\n'
    text += '  "root": ' + block(lock['root'], 2).lstrip() + ',\n'
    text += '  "toolchain": ' + block(lock['toolchain'], 2).lstrip() + '\n}\n'
    return text


def gh(*args):
    return subprocess.check_output(['gh', *args], text=True).strip()


def repository(url):
    match = re.fullmatch(r'https://github\.com/([A-Za-z0-9._-]+/[A-Za-z0-9._-]+?)(\.git)?', url)
    if not match:
        raise SystemExit(f'Not a GitHub package: {url}')
    return match[1]


def pin():
    lock_path = ROOT / 'ziran.lock'
    lock = json.loads(lock_path.read_text())
    if write_lock(lock) != lock_path.read_text():
        raise SystemExit('ziran.lock is not in the layout ziran lock writes')
    names = json.loads((ROOT / 'games.json').read_text())['packages']
    ledger = json.loads((ROOT / 'apps/versions.json').read_text())['node_apps']
    updates = []
    for name in names:
        old_id = lock['root']['dependencies'][name]
        entry = next(item for item in lock['packages'] if item['id'] == old_id)
        repo = repository(entry['url'])
        tag = gh('release', 'view', '--repo', repo, '--json', 'tagName', '--jq', '.tagName')
        commit = gh('api', f'repos/{repo}/commits/{tag}', '--jq', '.sha')
        if commit == entry['commit']:
            continue
        # A later tag of the version Arcade already ships is not a new release.
        if name in ledger and ledger[name]['version'] == tag.removeprefix('v'):
            continue
        # Never move back: the release must contain the pinned commit.
        status = gh('api', f'repos/{repo}/compare/{entry["commit"]}...{commit}', '--jq', '.status')
        if status != 'ahead':
            print(f'{name}: release {tag} is {status} of the pinned {entry["commit"][:12]}; kept')
            continue
        new_id = package_id(entry['url'], commit)
        entry['commit'] = commit
        entry['id'] = new_id
        for owner in [lock['root'], *lock['packages']]:
            for alias, target in owner['dependencies'].items():
                if target == old_id:
                    owner['dependencies'][alias] = new_id
        updates.append({'name': name, 'repository': repo, 'tag': tag, 'commit': commit})
        print(f'{name}: {repo} {tag} ({commit[:12]})')
    lock_path.write_text(write_lock(lock))
    UPDATES.parent.mkdir(parents=True, exist_ok=True)
    UPDATES.write_text(json.dumps(updates, indent=2) + '\n')


def newest_notes(changelog):
    """The bullets of a changelog's newest numeric release."""
    text = changelog.read_text()
    heading = re.search(r'^## \[?(\d+\.\d+\.\d+)\]?.*$', text, re.M)
    if heading is None:
        raise SystemExit(f'{changelog} needs a numeric release entry')
    following = re.search(r'^## ', text[heading.end():], re.M)
    section = text[heading.end():heading.end() + following.start()] if following else text[heading.end():]
    notes = [line[2:].strip() for line in section.splitlines() if line.startswith('- ')]
    return heading[1], notes


def changelog(ziran):
    updates = json.loads(UPDATES.read_text())
    if not updates:
        return
    lines = []
    for update in updates:
        source = Path(subprocess.check_output([ziran, 'pkg', 'path', update['name']], cwd=ROOT, text=True).strip())
        declaration = json.loads((source / 'apps.json').read_text())
        # The package's first app is the game itself; its changelog sits beside its catalog.
        manifest = source / declaration['apps'][0]['manifest']
        version, notes = newest_notes(manifest.with_name('CHANGELOG.md'))
        title = declaration['title']
        lines += [f'- {title} {version}: {note}' for note in notes] or [f'- {title} {version}.']
    path = ROOT / 'CHANGELOG.md'
    text = path.read_text()
    current = re.search(r'^## (\d+)\.(\d+)\.(\d+)\s*$', text, re.M)
    if current is None:
        raise SystemExit('CHANGELOG.md needs a numeric release entry')
    version = f'{current[1]}.{current[2]}.{int(current[3]) + 1}'
    entry = f'## {version}\n\n' + '\n'.join(lines) + '\n\n'
    path.write_text(text[:current.start()] + entry + text[current.start():])
    print(f'Arcade {version}')


def art():
    sys.path.insert(0, str(ROOT / 'scripts'))
    spec = importlib.util.spec_from_file_location('library_art', ROOT / 'scripts/library-art.py')
    library = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(library)
    recorded = json.loads((library.LIBRARY / 'sources.json').read_text())
    current = {f'{name}-{key}': hashlib.sha256(data).hexdigest() for name, key, data in library.art()}
    if {copy: item['source_sha256'] for copy, item in recorded.items()} != current:
        library.main()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['pin', 'changelog', 'art'])
    parser.add_argument('--ziran', default=str(ROOT / 'scripts/ziran.sh'))
    args = parser.parse_args()
    if args.command == 'pin':
        pin()
    elif args.command == 'changelog':
        changelog(args.ziran)
    else:
        art()
