"""The same Chess identity belongs to both harnesses; Arcade owns no game fork."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import hashlib

ROOT = Path(__file__).resolve().parents[1]
inbe = Path(os.environ['INBE_SOURCE']) if 'INBE_SOURCE' in os.environ else Path(
    subprocess.check_output(["ziran", "pkg", "path", "inbe"], cwd=ROOT, text=True).strip())
catalog = json.loads((ROOT / "build/catalog.json").read_text())["games"]
chess = next(game for game in catalog if game["name"] == "chess")
assert chess["id"] == "inbe.chess"
# Inbe releases before its node apps have no node_apps ledger at all.
assert "chess" not in json.loads((inbe / "apps/versions.json").read_text()).get("node_apps", {})
assert set(chess["harnesses"]) == {"arcade", "inbe"}
assert chess["kind"] == "game"
assert (ROOT / "apps/chess/engine.zi").is_file(), "Arcade must own the game"
assert not (inbe / "apps/chess").exists(), "Inbe must consume Chess, not own another copy"
assert chess["contract_version"] == 1 and chess["module_api"] == 2
assert chess["host_api"] == 12 and chess["save_schema"] == 1
assert (ROOT / chess["preview"]).is_file()
env = {key: value for key, value in os.environ.items()
       if key not in {"DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS"}}
listed = subprocess.run([str(ROOT / "build/arcade"), "--list"], env=env, capture_output=True, timeout=10)
assert listed.returncode == 0 and b"inbe.chess" not in listed.stderr + listed.stdout
assert b"arcade.shovey\n" in listed.stderr + listed.stdout
unknown = subprocess.run([str(ROOT / "build/arcade"), "--app", "unknown"],
                         env=env, capture_output=True, timeout=10)
assert unknown.returncode == 1 and b"unknown game" in unknown.stderr
original = (ROOT / 'build/games/chess.zx').read_bytes()
container = (ROOT / 'build/arcade.zx').read_bytes()
metadata = json.loads((ROOT / 'build/arcade.json').read_text())
assert original not in container, 'Disabled Chess must not remain in the published collection'
assert {child['id'] for child in metadata['children']} == {'arcade.shovey', 'arcade.shovey-editor', 'xyz.waozi.wurm'}
for child in metadata['children']:
    name = child['expected_id']
    exact = (ROOT / f'build/games/{name}.zx').read_bytes()
    assert exact not in container, 'Arcade must carry no prepackaged game bytes'
    assert hashlib.sha256(exact).hexdigest() == child['sha256']
    assert child['cover']['portrait'] and child['cover']['landscape']
refused = subprocess.run([str(ROOT / 'build/arcade'), '--app', 'chess'], env=env, capture_output=True, timeout=10)
assert refused.returncode == 1 and b'unknown game' in refused.stderr
print('Game identities, direct collection leaves, full cover resources and disabled Chess passed')
