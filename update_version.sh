#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 - <<'PY'
from pathlib import Path
import re
import json
version = re.search(r'^## (\d+\.\d+\.\d+)\s*$', Path('CHANGELOG.md').read_text(), re.M)
if version is None:
    raise SystemExit('CHANGELOG.md needs a numeric release entry')
Path('VERSION').write_text(version[1] + '\n')
ledger_path = Path('apps/versions.json')
if ledger_path.exists():
    ledger = json.loads(ledger_path.read_text())
    for name, component in ledger['node_apps'].items():
        entry = re.search(r'^## \[(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}$',
                          Path('apps', name, 'CHANGELOG.md').read_text(), re.M)
        if entry is None:
            raise SystemExit(f'{name} needs a numeric changelog entry')
        if component['version'] != entry[1]:
            old = tuple(map(int, component['version'].split('.')))
            new = tuple(map(int, entry[1].split('.')))
            if new <= old:
                raise SystemExit(f'{name} version must increase')
            component['version'] = entry[1]
            component['sequence'] += 1
    ledger_path.write_text(json.dumps(ledger, indent=2) + '\n')
PY
