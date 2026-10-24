#!/usr/bin/env python3
"""Check game ownership, shared interface versions, translations and update metadata."""
import json
from pathlib import Path
import re
from game_packages import declared_apps

ROOT = Path(__file__).resolve().parents[1]


def check():
    standard = json.loads((ROOT / 'standards/game-v1.json').read_text())
    ledger = json.loads((ROOT / 'apps/versions.json').read_text())
    for app in declared_apps(ROOT):
        source, manifest, game = app['source'], app['manifest'], app['descriptor']
        for field in ['contract_version', 'module_api', 'host_api']:
            assert game[field] == standard[field], f'{game["name"]}: incompatible {field}'
        component = ledger['node_apps'][game['name']]
        assert game['id'] == component['id'] and game['host_api'] == component['host_api']
        assert game['kind'] == 'game' and 'arcade' in game['harnesses']
        assert set(game['harnesses']) <= {'arcade', 'inbe'}
        assert game['save_schema'] == 1
        assert (source / game['source']).is_file() and (source / game['preview']).is_file()
        changelog = manifest.with_name('CHANGELOG.md').read_text()
        version = re.search(r'^## \[(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}$', changelog, re.M)
        assert version and version[1] == component['version'], 'Run ./update_version.sh'
        assert component['sequence'] > 0
        required = set()
        for file in manifest.parent.glob('*.zi'):
            required.update(re.findall(r'"(' + re.escape(game['locale_prefix']) + r'[a-z0-9_]+)"', file.read_text()))
        locales = {}
        for file in (source / game['locales']).glob('*.txt'):
            text = file.read_text()
            locales[file.stem] = {match[1] for match in re.finditer(r'^\[([^\]]+)\]$', text, re.M)}
            entries = {}
            heading = None
            value = []
            for line in text.splitlines():
                if line.startswith('[') and line.endswith(']'):
                    if heading is not None:
                        entries[heading] = '\n'.join(value).strip()
                    heading = line[1:-1]
                    value = []
                elif heading is not None and line != '---':
                    value.append(line)
            if heading is not None:
                entries[heading] = '\n'.join(value).strip()
            empty = [key for key in required if not entries.get(key, '').strip()]
            assert not empty, f'{file.name}: empty translations {empty[:3]}'
        assert len(locales) >= 12
        for language, keys in locales.items():
            assert required <= keys, f'{language}: missing {sorted(required - keys)}'
    return ledger


if __name__ == '__main__':
    check()
    print('Game contract, package sources, translated text and independent version ledger passed')
