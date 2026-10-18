#!/usr/bin/env python3
"""Verify one exact game bundle in Arcade and an intended Inbe host."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inbe-binary', required=True, type=Path)
    parser.add_argument('--oldest-inbe-binary', type=Path,
                        help='oldest released Inbe this game claims to support; required before upload')
    args = parser.parse_args()
    binary = args.inbe_binary.resolve(strict=True)
    subprocess.run(['make', '-s', 'test', 'ui-test'], cwd=ROOT, check=True)
    inbe = Path(subprocess.check_output([str(ROOT / 'scripts/ziran.sh'), 'pkg', 'path', 'inbe'],
                                       cwd=ROOT, text=True).strip())
    bundle = ROOT / 'build/games/chess.zib'
    subprocess.run(['sh', str(inbe / 'tests/chess_ui_test.sh'), str(binary), str(bundle)],
                   cwd=inbe, check=True)
    oldest = args.oldest_inbe_binary.resolve(strict=True) if args.oldest_inbe_binary else None
    if oldest:
        subprocess.run(['sh', str(inbe / 'tests/chess_ui_test.sh'), str(oldest), str(bundle)],
                       cwd=inbe, check=True)
    component = json.loads((ROOT / 'apps/versions.json').read_text())['node_apps']['chess']
    receipt = {'app_id': component['id'], 'version': component['version'],
               'sequence': component['sequence'], 'sha256': sha256(bundle.read_bytes()).hexdigest(),
               'inbe_binary_sha256': sha256(binary.read_bytes()).hexdigest(),
               'oldest_inbe': oldest is not None,
               'oldest_inbe_binary_sha256': sha256(oldest.read_bytes()).hexdigest() if oldest else None,
               'arcade': True, 'inbe': True, 'rules': True, 'friend_protocol': True,
               'rendering': True, 'save_restore': True}
    target = ROOT / 'build/compatibility.json'
    temporary = target.with_suffix('.pending')
    temporary.write_text(json.dumps(receipt, indent=2) + '\n')
    temporary.replace(target)
    print('Exact Chess bundle passed Arcade and Inbe compatibility checks')
