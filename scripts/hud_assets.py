"""The two shared painted HUD icons shipped with the host, independent of catalogs."""
import hashlib
from pathlib import Path
import shutil

HUD_PATHS = ('assets/hud/profile.webp', 'assets/hud/dew.webp')


def hud_asset_hashes(apps):
    return {name: hashlib.sha256((Path(apps) / name).read_bytes()).hexdigest() for name in HUD_PATHS}


def stage_hud_assets(apps, output):
    for name in HUD_PATHS:
        target = Path(output) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(apps) / name, target)
