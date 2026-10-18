"""The same Chess identity belongs to both harnesses; Arcade owns no game fork."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
inbe = Path(subprocess.check_output(["ziran", "pkg", "path", "inbe"], cwd=ROOT, text=True).strip())
catalog = json.loads((ROOT / "build/catalog.json").read_text())["games"]
chess = next(game for game in catalog if game["name"] == "chess")
assert chess["id"] == json.loads((inbe / "apps/versions.json").read_text())["node_apps"]["chess"]["id"]
assert set(chess["harnesses"]) == {"arcade", "inbe"}
assert chess["kind"] == "game"
assert not (ROOT / "apps/chess").exists(), "Arcade forked Chess's source"
env = {key: value for key, value in os.environ.items()
       if key not in {"DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS"}}
listed = subprocess.run([str(ROOT / "build/arcade"), "--list"], env=env, capture_output=True, timeout=10)
assert listed.returncode == 0 and b"inbe.chess" in listed.stderr + listed.stdout
unknown = subprocess.run([str(ROOT / "build/arcade"), "--app", "unknown"],
                         env=env, capture_output=True, timeout=10)
assert unknown.returncode == 1 and b"unknown game" in unknown.stderr
print("Chess is registered in Arcade and Inbe under one identity; unknown games are refused without opening a window")
