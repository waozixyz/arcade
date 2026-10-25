#!/usr/bin/env python3
"""Build the reviewed Apps controller from its locked package, including in development."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def controller_context(root, context):
    """Keep the host's exact launcher graph without fetching unrelated games."""
    manifest = tomllib.loads((root / 'ziran.toml').read_text())
    lock = json.loads((root / 'ziran.lock').read_text())
    packages = {package['id']: package for package in lock['packages']}
    needed = set()

    def include(identifier):
        if identifier in needed:
            return
        needed.add(identifier)
        for dependency in packages[identifier]['dependencies'].values():
            include(dependency)

    launcher = lock['root']['dependencies']['apps']
    include(launcher)
    lock['packages'] = [package for package in lock['packages'] if package['id'] in needed]
    lock['root']['dependencies'] = {'apps': launcher}
    lines = ['[package]', 'name = ' + json.dumps(lock['root']['name'])]
    for section, values in [('toolchain', manifest['toolchain']),
                            ('dependencies.apps', manifest['dependencies']['apps'])]:
        lines.extend(['', '[' + section + ']'])
        lines.extend(key + ' = ' + json.dumps(value) for key, value in values.items())
    (context / 'ziran.toml').write_text('\n'.join(lines) + '\n')
    (context / 'ziran.lock').write_text(json.dumps(lock, indent=2) + '\n')


def build(root, output):
    (root / 'build').mkdir(exist_ok=True)
    # --locked rejects local overrides. Resolve using only the committed
    # package inputs, so local Kryon/toolchain work cannot change trusted bytes.
    with tempfile.TemporaryDirectory(prefix='apps-lock-', dir=root / 'build') as directory:
        context = Path(directory)
        controller_context(root, context)
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
