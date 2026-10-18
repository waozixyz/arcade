#!/usr/bin/env python3
"""Check game ownership, shared interface versions, translations and update metadata."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def check():
    standard = json.loads((ROOT / 'standards/game-v1.json').read_text())
    ledger = json.loads((ROOT / 'apps/versions.json').read_text())
    for registration in json.loads((ROOT / 'games.json').read_text())['games']:
        assert registration['package'] == 'self', 'Game source must be owned by Arcade'
        game = json.loads((ROOT / registration['manifest']).read_text())
        for field in ['contract_version', 'module_api', 'host_api']:
            assert game[field] == standard[field], f'{game["name"]}: incompatible {field}'
        component = ledger['node_apps'][game['name']]
        assert game['id'] == component['id'] and game['host_api'] == component['host_api']
        assert game['kind'] == 'game' and set(game['harnesses']) == {'arcade', 'inbe'}
        assert game['save_schema'] == 1
        assert (ROOT / game['source']).is_file() and (ROOT / game['preview']).is_file()
        changelog = (ROOT / 'apps' / game['name'] / 'CHANGELOG.md').read_text()
        version = re.search(r'^## \[(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}$', changelog, re.M)
        assert version and version[1] == component['version'], 'Run ./update_version.sh'
        assert component['sequence'] > 0
        locales = {}
        for file in (ROOT / game['locales']).glob('*.txt'):
            locales[file.stem] = {match[1] for match in re.finditer(r'^\[([^\]]+)\]$', file.read_text(), re.M)}
        required = set()
        for file in (ROOT / 'apps' / game['name']).glob('*.zi'):
            required.update(re.findall(r'"(chess_[a-z0-9_]+)"', file.read_text()))
        assert len(locales) >= 12
        for language, keys in locales.items():
            assert required <= keys, f'{language}: missing {sorted(required - keys)}'
    return ledger


if __name__ == '__main__':
    check()
    print('Game contract, owned source, translated text and independent version ledger passed')
