"""Find the apps Arcade and each registered game package declare.

Every package lists its apps in apps.json: the app's own catalog.json and,
for an app the library opens from a full-screen cover, that cover's art,
caption and action. games.json names the game packages Arcade includes.
"""
import json
import re
from pathlib import Path
import subprocess

APP_KEYS = {'manifest', 'cover', 'enabled', 'requires', 'shared_code', 'library_entries', 'shared_records', 'external', 'standalone_bundle'}
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
    registration = json.loads((Path(root) / 'games.json').read_text())
    names = ['self', *registration['packages']]
    if len(set(names)) != len(names):
        raise ValueError('Duplicate game package')
    artwork = registration.get('artwork', {})
    if not isinstance(artwork, dict) or any(name not in names[1:] or
            not isinstance(alias, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', alias)
            for name, alias in artwork.items()):
        raise ValueError('Invalid artwork package')
    packages = []
    for name in names:
        source = package_root(root, name, ziran, lock_flags)
        art_source = package_root(root, artwork[name], ziran, lock_flags) if name in artwork else source
        declaration = json.loads((source / 'apps.json').read_text())
        apps = []
        for app in declaration['apps']:
            if not set(app) <= APP_KEYS or not set(app.get('cover', {})) <= COVER_KEYS:
                raise ValueError(f'{name}: unknown apps.json field')
            if app.get('external', False):
                # Independently published editions stay in their own game.
                if app['external'] is not True or not str(relative_path(app.get('standalone_bundle', ''))).endswith('.zx'):
                    raise ValueError(f'{name}: invalid external game edition')
                continue
            manifest = source / relative_path(app['manifest'])
            requires = app.get('requires', [])
            if not isinstance(requires, list) or len(requires) > 8 or \
                    any(not isinstance(item, str) or not item for item in requires) or \
                    len(set(requires)) != len(requires):
                raise ValueError(f'{name}: invalid app dependencies')
            shared_code = app.get('shared_code', False)
            if type(shared_code) is not bool or (shared_code and not requires):
                raise ValueError(f'{name}: shared code needs declared dependencies')
            shared_records = app.get('shared_records', [])
            if not isinstance(shared_records, list) or len(shared_records) > 8 or any(
                    not isinstance(item, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,63}', item) or
                    item in ('.', '..') for item in shared_records) or len(set(shared_records)) != len(shared_records):
                raise ValueError(f'{name}: invalid shared records')
            library_entries = app.get('library_entries', [])
            if not isinstance(library_entries, list) or len(library_entries) > 64 or \
                    any(not isinstance(item, str) or len(item) > 253 or
                        not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*:[A-Za-z_][A-Za-z0-9_]*', item)
                        for item in library_entries) or len(set(library_entries)) != len(library_entries):
                raise ValueError(f'{name}: invalid portable library entries')
            app_art_source = art_source
            descriptor = json.loads(manifest.read_text())
            cover_crops = {}
            cover = app.get('cover')
            internal = descriptor['name'].endswith('-editor')
            if cover:
                cover = dict(cover)
                if internal:
                    cover['action'] = 'internal'
            apps.append(dict(package=name, source=source, art_source=app_art_source, manifest=manifest,
                             descriptor=descriptor,
                             cover=cover, cover_crops=cover_crops, internal=internal, requires=requires, shared_code=shared_code,
                             shared_records=shared_records,
                             library_entries=library_entries, enabled=app.get('enabled', True)))
        packages.append(dict(name=name, source=source, id=declaration['id'],
                             title=declaration['title'], apps=apps))
    return packages


def declared_apps(root, ziran=None, lock_flags=()):
    return [app for package in declared_packages(root, ziran, lock_flags) for app in package['apps']]


def portable_artifacts(app, manifest=None, exports=None):
    """Locate game-owned exports. Resolving paths never builds or runs a game.

    An explicit manifest is useful with clean locked/downloaded packages whose
    source cache deliberately has no build outputs. Paths are relative to it.
    """
    descriptor, source = app['descriptor'], app['source']
    name, package = descriptor['name'], app['package']
    instruction = ('Supply --artifact-manifest with exports from the game owner; '
                   'Arcade never compiles games.')
    if exports is not None:
        record = exports['apps'][descriptor['id']]
        if (not isinstance(record, dict) or not {'bundle', 'preview'} <= set(record)
                or not set(record) <= {'bundle', 'preview', 'resources'}):
            raise ValueError(f'{name}: artifact entry needs bundle, preview and optional resources paths')
        locations = {}
        for kind, value in record.items():
            if not isinstance(value, str) or not value:
                raise ValueError(f'{name}: invalid artifact path')
            path = Path(value)
            locations[kind] = path if path.is_absolute() else manifest.parent / path
        return locations, instruction
    folders = {'shovey': 'build/player/games', 'wurm': 'build/games', 'choano': 'build'}
    commands = {'shovey': 'build-queue -- python3 scripts/player.py collection --web',
                'wurm': 'build-queue -- python3 tools/build_portable.py',
                'choano': 'build-queue -- make portable'}
    if package not in folders:
        raise ValueError(f'{name}: no game-owned artifact location. {instruction}')
    folder = source / folders[package]
    locations = dict(bundle=folder / (name + '.zx'),
                     preview=folder / (name + '-preview.png') if package == 'wurm'
                     else source / relative_path(descriptor['preview']))
    if package in ('shovey', 'wurm'):
        locations['resources'] = folder / (name + '-resources.json')
    return locations, f'In {source}, run {commands[package]}. {instruction}'
