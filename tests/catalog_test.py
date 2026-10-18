"""The same Chess identity belongs to both harnesses; Arcade owns no game fork."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
inbe = Path(subprocess.check_output(["ziran", "pkg", "path", "inbe"], cwd=ROOT, text=True).strip())
catalog = json.loads((ROOT / "build/catalog.json").read_text())["games"]
chess = next(game for game in catalog if game["name"] == "chess")
assert chess["id"] == "inbe.chess"
assert "chess" not in json.loads((inbe / "apps/versions.json").read_text())["node_apps"]
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
assert listed.returncode == 0 and b"inbe.chess" in listed.stderr + listed.stdout
unknown = subprocess.run([str(ROOT / "build/arcade"), "--app", "unknown"],
                         env=env, capture_output=True, timeout=10)
assert unknown.returncode == 1 and b"unknown game" in unknown.stderr
original = (ROOT / 'build/games/chess.zib').read_bytes()
with tempfile.TemporaryDirectory(prefix='contract-', dir=ROOT / 'build') as directory:
    work = Path(directory)
    binary = work / 'arcade'
    shutil.copyfile(ROOT / 'build/arcade', binary)
    binary.chmod(0o700)
    (work / 'games').mkdir()
    for old, new in [(b'"contract_version": 1', b'"contract_version": 9'),
                     (b'"module_api": 2', b'"module_api": 9'),
                     (b'"host_api": 12', b'"host_api": 99'),
                     (b'"id": "inbe.chess"', b'"id": "fake.chess"')]:
        assert original.count(old) == 1
        (work / 'games/chess.zib').write_bytes(original.replace(old, new))
        rejected = subprocess.run([str(binary), '--app', 'chess'],
                                  env=env | {'ARCADE_DATA': str(work / 'profile')},
                                  capture_output=True, timeout=10)
        assert rejected.returncode == 1, 'Incompatible game metadata was accepted'
        assert b'Arcade: could not open game' in rejected.stderr, 'Game reached window startup before rejection'
        assert not (work / 'profile/games/inbe.chess/records/computer').exists()
print("Chess is registered in Arcade and Inbe under one identity; unknown games are refused without opening a window")
