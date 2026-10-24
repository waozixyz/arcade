#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 - <<'PY'
from pathlib import Path
import re
import json
import sys
sys.path.insert(0, 'scripts')
from game_packages import declared_apps
version = re.search(r'^## (\d+\.\d+\.\d+)\s*$', Path('CHANGELOG.md').read_text(), re.M)
if version is None:
    raise SystemExit('CHANGELOG.md needs a numeric release entry')
Path('VERSION').write_text(version[1] + '\n')
ledger_path = Path('apps/versions.json')
if ledger_path.exists():
    ledger = json.loads(ledger_path.read_text())
    # New games get their initial version from their numeric changelog,
    # through the same synchronizer as subsequent game releases.
    changelogs = {}
    for app in declared_apps('.'):
        # Games from other packages (Shovey) keep their changelog there.
        game = app['descriptor']
        changelogs[game['name']] = app['manifest'].parent / 'CHANGELOG.md'
        if game['name'] not in ledger['node_apps']:
            entry = re.search(r'^## \[(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}$',
                              changelogs[game['name']].read_text(), re.M)
            if entry is None:
                raise SystemExit(f'{game["name"]} needs a numeric changelog entry')
            ledger['node_apps'][game['name']] = dict(
                id=game['id'], title=game['title'], version=entry[1], sequence=1, host_api=game['host_api'])
    for name, component in ledger['node_apps'].items():
        # Arcade itself is released at the version of the root changelog.
        if name == 'arcade':
            current = version[1]
        else:
            entry = re.search(r'^## \[(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}$',
                              changelogs[name].read_text(), re.M)
            if entry is None:
                raise SystemExit(f'{name} needs a numeric changelog entry')
            current = entry[1]
        if component['version'] != current:
            old = tuple(map(int, component['version'].split('.')))
            new = tuple(map(int, current.split('.')))
            if new <= old:
                raise SystemExit(f'{name} version must increase')
            component['version'] = current
            component['sequence'] += 1
    ledger_path.write_text(json.dumps(ledger, indent=2) + '\n')
PY
