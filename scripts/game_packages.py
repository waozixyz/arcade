"""Find the apps Arcade and each registered game package declare.

Every package lists its apps in apps.json: the app's own catalog.json and,
for an app the library opens from a full-screen cover, that cover's art,
caption and action. games.json names the game packages Arcade includes.
"""
import json
from pathlib import Path
import subprocess

APP_KEYS = {'manifest', 'cover', 'enabled', 'requires'}
COVER_KEYS = {'portrait', 'landscape', 'logo', 'caption', 'action'}


def package_root(root, name, ziran=None, lock_flags=()):
    """Arcade's own apps live in its root; game packages come from its pins."""
    if name == 'self':
        return Path(root)
    command = [str(ziran or Path(root) / 'scripts/ziran.sh'), 'pkg', 'path', name, *lock_flags]
    return Path(subprocess.check_output(command, cwd=root, text=True).strip())


def relative_path(text):
    path = Path(text)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError(f'Invalid package path: {text}')
    return path


def declared_packages(root, ziran=None, lock_flags=()):
    """Arcade first, then each registered game package, with their apps."""
    names = ['self', *json.loads((Path(root) / 'games.json').read_text())['packages']]
    if len(set(names)) != len(names):
        raise ValueError('Duplicate game package')
    packages = []
    for name in names:
        source = package_root(root, name, ziran, lock_flags)
        declaration = json.loads((source / 'apps.json').read_text())
        apps = []
        for app in declaration['apps']:
            if not set(app) <= APP_KEYS or not set(app.get('cover', {})) <= COVER_KEYS:
                raise ValueError(f'{name}: unknown apps.json field')
            manifest = source / relative_path(app['manifest'])
            requires = app.get('requires', [])
            if not isinstance(requires, list) or len(requires) > 8 or \
                    any(not isinstance(item, str) or not item for item in requires) or \
                    len(set(requires)) != len(requires):
                raise ValueError(f'{name}: invalid app dependencies')
            apps.append(dict(package=name, source=source, manifest=manifest,
                             descriptor=json.loads(manifest.read_text()),
                             cover=app.get('cover'), requires=requires, enabled=app.get('enabled', True)))
        packages.append(dict(name=name, source=source, id=declaration['id'],
                             title=declaration['title'], apps=apps))
    return packages


def declared_apps(root, ziran=None, lock_flags=()):
    return [app for package in declared_packages(root, ziran, lock_flags) for app in package['apps']]
