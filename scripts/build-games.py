#!/usr/bin/env python3
"""Import game-owned portable exports unchanged; never build games in Arcade."""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import tempfile
from pathlib import Path
from game_packages import declared_apps, portable_artifacts
from game_resources import dependency_order

ROOT = Path(__file__).resolve().parents[1]
MAX_PAYLOAD_BYTES = 64 * 1024 * 1024
MAX_ASSET_BYTES = 16 * 1024 * 1024
METADATA_LIMIT = 1024 * 1024


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def bundle_metadata(path, name):
    """Read bounded metadata and the asset index of ZX 26/27; execute nothing."""
    size = path.stat().st_size
    if not 0 < size <= MAX_PAYLOAD_BYTES:
        raise ValueError(f'{path}: exceeds the host payload limit')
    with path.open('rb') as source:
        def skip(count):
            if count > size - source.tell():
                raise ValueError(f'{path}: truncated bundle')
            source.seek(count, 1)

        def take(count):
            if count > size - source.tell():
                raise ValueError(f'{path}: truncated bundle')
            data = source.read(count)
            if len(data) != count:
                raise ValueError(f'{path}: truncated bundle')
            return data

        def number():
            return struct.unpack('<I', take(4))[0]

        def text():
            length = number()
            if length > METADATA_LIMIT:
                raise ValueError(f'{path}: oversized metadata')
            return take(length).decode('utf-8')

        def count():
            value = number()
            if value > 100000:
                raise ValueError(f'{path}: oversized bundle index')
            return value

        if take(8) not in (b'ZX\0\0\x1a\0\0\0', b'ZX\0\0\x1b\0\0\0'):
            raise ValueError(f'{path}: unsupported bundle')
        entry = text() + ':' + text()
        for _ in range(count()):
            text(); text()
        for _ in range(count()):
            for _ in range(7):
                text()
            skip(8); text(); skip(4)
        for _ in range(count()):
            text(); text(); text()
        skip(number())
        metadata, paths = {}, set()
        wanted = {f'assets/{name}/catalog.json', f'assets/{name}/requirements.json'}
        asset_count = count()
        if not 1 <= asset_count <= 2048:
            raise ValueError(f'{path}: invalid game asset count')
        for _ in range(asset_count):
            asset, length = text(), number()
            if length > MAX_ASSET_BYTES:
                raise ValueError(f'{path}: asset exceeds the host asset limit')
            if asset in paths or asset.startswith('/') or '..' in Path(asset).parts:
                raise ValueError(f'{path}: invalid or duplicate bundle asset {asset}')
            paths.add(asset)
            if asset in wanted:
                if length > METADATA_LIMIT:
                    raise ValueError(f'{path}: oversized metadata')
                metadata[asset.rsplit('/', 1)[1]] = json.loads(take(length))
            else:
                skip(length)
        if source.tell() != size:
            raise ValueError(f'{path}: trailing bundle bytes')
    return entry, metadata, paths


def validate_artifact(app, bundle, resources, imported):
    descriptor = app['descriptor']
    name, identifier = descriptor['name'], descriptor['id']
    entry, metadata, paths = bundle_metadata(bundle, name)
    if any(not path.startswith(f'assets/{name}/') or path == f'assets/{name}/' for path in paths):
        raise ValueError(f'{identifier}: exported assets escape the game namespace; re-export in its game repository')
    public = {key: value for key, value in descriptor.items()
              if key not in ('build_defines', 'prepare_assets')}
    if entry != descriptor['entry'] or metadata.get('catalog.json') != public:
        raise ValueError(f'{identifier}: embedded catalog/entry mismatch or missing; '
                         're-export the portable bundle in its game repository with its app catalog')
    requires = app['requires']
    if (not isinstance(resources, dict) or set(resources) != {'dependencies', 'resources'}
            or resources['dependencies'] != requires):
        raise ValueError(f'{identifier}: exported dependency identities mismatch')
    links = resources['resources']
    if not isinstance(links, list) or len(links) > 16:
        raise ValueError(f'{identifier}: invalid resource links')
    targets = set()
    for link in links:
        if not isinstance(link, dict) or set(link) != {'dependency', 'path', 'source'}:
            raise ValueError(f'{identifier}: invalid resource link')
        dependency, target, original = link['dependency'], link['path'], link['source']
        if not isinstance(dependency, str) or dependency not in requires or dependency not in imported:
            raise ValueError(f'{identifier}: undeclared resource dependency')
        base = imported[dependency]
        for value in (target, original):
            if not isinstance(value, str) or value.startswith('/') or '..' in Path(value).parts:
                raise ValueError(f'{identifier}: unsafe resource link')
        if (not target.startswith(f'assets/{name}/') or target in targets
                or not original.startswith(f'assets/{base["name"]}/')
                or target.endswith('/') != original.endswith('/')):
            raise ValueError(f'{identifier}: invalid resource namespace')
        targets.add(target)
        if not any(p.startswith(original) if original.endswith('/') else p == original for p in base['paths']):
            raise ValueError(f'{identifier}: missing dependency resource')
        if any(p.startswith(target) if target.endswith('/') else p == target for p in paths):
            raise ValueError(f'{identifier}: resource link shadows bundled data')
    expected = resources | {'sha256': {dep: imported[dep]['sha256'] for dep in requires}}
    if requires and metadata.get('requirements.json') != expected:
        raise ValueError(f'{identifier}: embedded requirements/hash mismatch')
    if not requires and metadata.get('requirements.json') not in (None, expected):
        raise ValueError(f'{identifier}: unexpected embedded requirements')
    return dict(name=name, paths=paths, sha256=digest(bundle))


def promote(replacements, scratch):
    """Rollback all prior outputs if promotion fails; validation precedes writes."""
    completed = []
    try:
        for index, (candidate, target) in enumerate(replacements):
            target.parent.mkdir(parents=True, exist_ok=True)
            backup = scratch / f'previous-{index}'
            existed = target.exists()
            if existed:
                os.replace(target, backup)
            completed.append((target, backup, existed))
            os.replace(candidate, target)
    except BaseException:
        for target, backup, existed in reversed(completed):
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
            if existed:
                os.replace(backup, target)
        raise


def build(ziran, lock_flags, artifact_manifest=None):
    apps = declared_apps(ROOT, ziran, lock_flags)
    if not 1 <= len(apps) <= 16 or len({a['descriptor']['id'] for a in apps}) != len(apps):
        raise ValueError('Arcade needs 1 to 16 distinct games')
    if len({a['descriptor']['name'] for a in apps}) != len(apps):
        raise ValueError('Duplicate game name')
    apps = dependency_order(apps)
    exports = None
    if artifact_manifest is not None:
        artifact_manifest = Path(artifact_manifest).resolve()
        exports = json.loads(artifact_manifest.read_text())
        if not isinstance(exports, dict) or set(exports) != {'apps'} or not isinstance(exports['apps'], dict):
            raise ValueError('Artifact manifest must contain an apps mapping')
        expected_ids = {a['descriptor']['id'] for a in apps if a['enabled']}
        if set(exports['apps']) != expected_ids:
            raise ValueError('Artifact manifest must name exactly the enabled public app IDs')
    scratch_root = ROOT / 'work/console-redesign'
    scratch_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='game-import-', dir=scratch_root) as directory:
        scratch = Path(directory)
        games = scratch / 'games'
        games.mkdir()
        entries, imported = [], {}
        for app in apps:
            descriptor = app['descriptor']
            name = descriptor['name']
            if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', name):
                raise ValueError('Invalid game name')
            if descriptor['kind'] != 'game' or 'arcade' not in descriptor['harnesses']:
                raise ValueError('Only games registered for Arcade belong in its catalog')
            entries.append(descriptor | {'enabled': app['enabled'], 'package': app['package']})
            if not app['enabled']:
                continue
            locations, instruction = portable_artifacts(app, artifact_manifest, exports)
            for kind, source in locations.items():
                if not source.is_file():
                    raise ValueError(f'{descriptor["id"]}: missing {kind} export: {source}. {instruction}')
                limit = METADATA_LIMIT if kind == 'resources' else MAX_PAYLOAD_BYTES
                if not 0 < source.stat().st_size <= limit:
                    raise ValueError(f'{source}: exceeds the host payload limit')
                suffix = {'bundle': '.zx', 'preview': '-preview.png', 'resources': '-resources.json'}[kind]
                target = games / (name + suffix)
                shutil.copyfile(source, target)
                if not 0 < target.stat().st_size <= limit:
                    raise ValueError(f'{source}: export changed or exceeds the host payload limit')
            resource_file = games / (name + '-resources.json')
            if not resource_file.exists():
                if app['requires']:
                    raise ValueError(f'{name}: dependencies require exported resources metadata')
                resource_file.write_text(json.dumps(dict(dependencies=[], resources=[]), indent=2) + '\n')
            resources = json.loads(resource_file.read_text())
            imported[descriptor['id']] = validate_artifact(app, games / (name + '.zx'), resources, imported)
        text, catalog = catalog_outputs(entries)
        (scratch / 'catalog.zi').write_text(text)
        (scratch / 'catalog.json').write_text(catalog)
        promote([(games, ROOT / 'build/games'), (scratch / 'catalog.zi', ROOT / 'src/catalog.zi'),
                 (scratch / 'catalog.json', ROOT / 'build/catalog.json')], scratch)
    print(f'Imported {len(imported)} verified game-owned artifacts unchanged')


def catalog_outputs(entries):
    if not entries or len(entries) > 16 or len({entry["id"] for entry in entries}) != len(entries):
        raise ValueError("Arcade needs 1 to 16 distinct games")
    text = ("// Generated from the apps.json of Arcade and its game packages.\n"
            "Game :: struct {\n    id: string\n    name: string\n    title: string\n    bundle: string\n    preview: string\n    package: string\n    enabled: bool\n}\n\n"
            f"GameCount :: {len(entries)}\n\nGameAt :: (index: s32) -> Game {{\n")
    for index, entry in enumerate(entries):
        fields = ", ".join("." + field + " = " + json.dumps(value, ensure_ascii=False)
                           for field, value in [("id", entry["id"]), ("name", entry["name"]),
                                                ("title", entry["title"]), ("bundle", entry["name"] + ".zx"),
                                                ("preview", entry["name"] + "-preview.png"), ("package", entry["package"])])
        fields += ", .enabled = " + str(entry["enabled"]).lower()
        text += f"    if index == {index} {{ return Game.{{{fields}}} }}\n"
    text += "    return Game.{}\n}\n"
    return text, json.dumps({"games": entries}, indent=2) + "\n"


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ziran', default='ziran', help='package path resolver only')
    parser.add_argument('--locked', action='store_true')
    parser.add_argument('--artifact-manifest', type=Path, help='explicit already-exported app artifact paths')
    args = parser.parse_args()
    try:
        build(args.ziran, ['--locked'] if args.locked else [], args.artifact_manifest)
    except (ValueError, OSError) as error:
        parser.exit(1, f'Game artifact import failed: {error}\n')
