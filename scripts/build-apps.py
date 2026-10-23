#!/usr/bin/env python3
"""Build the reviewed Apps controller from its locked package, including in development."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def build(root, output):
    (root / 'build').mkdir(exist_ok=True)
    # --locked rejects local overrides. Resolve using only the committed
    # package inputs, so local Kryon/toolchain work cannot change trusted bytes.
    with tempfile.TemporaryDirectory(prefix='apps-lock-', dir=root / 'build') as directory:
        context = Path(directory)
        for name in ('ziran.toml', 'ziran.lock'):
            shutil.copyfile(root / name, context / name)
        package = Path(subprocess.check_output(
            ['ziran', 'pkg', 'path', 'apps', '--locked'], cwd=context, text=True).strip())
        subprocess.run([sys.executable, str(package / 'scripts/build-ui.py'),
                        '--output', str(output.resolve())], cwd=root, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/apps-ui')
    build(ROOT, parser.parse_args().output)


if __name__ == '__main__':
    main()
