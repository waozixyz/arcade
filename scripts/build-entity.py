#!/usr/bin/env python3
"""Build Entity once for the outer native host; never pack it into a game.

Entity owns its Profile bundle and the assets embedded in it: the locked
toolchain's artifact helper asks Entity's project tool for
entity:native-profile, as Shovey's player does.
"""
from pathlib import Path
import importlib.util
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ZIRAN = ROOT / 'scripts/ziran.sh'
flags = [] if (ROOT / 'ziran.local.toml').exists() else ['--locked']
toolchain = Path(subprocess.check_output([str(ZIRAN), 'pkg', 'path', 'ziran', *flags],
                                         cwd=ROOT, text=True).strip().splitlines()[-1])
spec = importlib.util.spec_from_file_location('ziran_artifacts', toolchain / 'scripts/ziran_artifacts.py')
artifacts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(artifacts)
profile = artifacts.request('entity:native-profile', 'linux-x86_64-gnu', project=ROOT, ziran=ZIRAN)
shutil.copyfile(profile.output('entity.zx'), ROOT / 'build/entity.zx')

assets = ROOT / 'build/entity-assets'
assets.mkdir(parents=True, exist_ok=True)
shutil.copyfile(ROOT / 'build/entity.zx', assets / 'entity.zx')
