#!/usr/bin/env python3
"""Release Arcade-owned games through the existing signed Daochi publisher."""
from pathlib import Path
from hashlib import sha256
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

if __name__ == '__main__':
    if '--ssh-target' in sys.argv or any(value.startswith('--ssh-target=') for value in sys.argv):
        try:
            receipt = json.loads((ROOT / 'build/compatibility.json').read_text())
            component = json.loads((ROOT / 'apps/versions.json').read_text())['node_apps']['chess']
            valid = all(receipt.get(key) == component[field] for key, field in
                        [('app_id', 'id'), ('version', 'version'), ('sequence', 'sequence')])
            valid = valid and receipt.get('sha256') == sha256((ROOT / 'build/games/chess.zib').read_bytes()).hexdigest()
            valid = valid and all(receipt.get(key) is True for key in
                                  ['arcade', 'inbe', 'oldest_inbe', 'rules', 'friend_protocol', 'rendering', 'save_restore'])
        except (OSError, ValueError, KeyError):
            valid = False
        if not valid:
            raise SystemExit('Node publication requires this exact Chess bundle to pass Arcade, intended Inbe and oldest supported Inbe checks')
    flags = [] if (ROOT / 'ziran.local.toml').exists() else ['--locked']
    inbe = Path(subprocess.check_output(
        [str(ROOT / 'scripts/ziran.sh'), 'pkg', 'path', 'inbe', *flags],
        cwd=ROOT, text=True).strip())
    # The publisher retains its signed IDs, release sequence checks, pinned
    # keys and receiver. Source and build outputs belong to Arcade.
    command = [sys.executable, str(inbe / 'scripts/package-release.py'),
               '--node-app', 'chess', '--app-ledger', str(ROOT / 'apps/versions.json'),
               '--bundle-directory', str(ROOT / 'build/games'), *sys.argv[1:]]
    raise SystemExit(subprocess.run(command, cwd=ROOT).returncode)
