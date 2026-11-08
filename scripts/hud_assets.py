"""Host HUD icons, independent of downloaded catalogs."""
import hashlib
from pathlib import Path
import shutil

HUD_PATHS = ('assets/hud/profile.webp', 'assets/hud/dew.webp')


def hud_source(apps, name):
    if name == "assets/hud/profile.webp":
        return Path(__file__).resolve().parents[1] / name
    return Path(apps) / name


def hud_asset_hashes(apps):
    return {name: hashlib.sha256(hud_source(apps, name).read_bytes()).hexdigest() for name in HUD_PATHS}


def stage_hud_assets(apps, output):
    for name in HUD_PATHS:
        target = Path(output) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(hud_source(apps, name), target)
