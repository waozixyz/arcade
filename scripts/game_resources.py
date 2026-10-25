"""Pack additions once; signed collection links bind shared game resources."""
import json
from pathlib import Path
import shutil


def dependency_order(apps):
    by_id = {app['descriptor']['id']: app for app in apps}
    visiting, ordered, complete = set(), [], set()

    def visit(app):
        identifier = app['descriptor']['id']
        if identifier in visiting:
            raise ValueError('Cyclic game dependency')
        if identifier in complete:
            return
        visiting.add(identifier)
        for dependency in app.get('requires', []):
            if dependency not in by_id or (app['enabled'] and not by_id[dependency]['enabled']):
                raise ValueError(f'{identifier}: missing dependency {dependency}')
            visit(by_id[dependency])
        visiting.remove(identifier)
        complete.add(identifier)
        ordered.append(app)

    for app in apps:
        visit(app)
    return ordered


def shared_copies(app):
    path = app['manifest'].with_name('shared_assets.json')
    return json.loads(path.read_text())['copies'] if path.exists() else []


def share_resources(app, apps, resources, staged):
    """Alias only complete, byte-identical resources from a declared dependency.

    Each source has already undergone its game's asset preparation. Comparing
    the actual staged bytes prevents reusing a differently cropped or edited
    picture merely because it came from the same original filename.
    """
    requirements = app.get('requires', [])
    by_id = {item['descriptor']['id']: item for item in apps}
    links = []
    for dependency in requirements:
        original = by_id[dependency]
        if app['source'] != original['source']:
            continue
        descriptor = original['descriptor']
        prefixes = [{'from': descriptor['assets'], 'to': ''}, *shared_copies(original)]
        original_root = staged / descriptor['name'] / 'assets' / descriptor['name']
        for copy in shared_copies(app):
            for prefix in prefixes:
                try:
                    relative = Path(copy['from']).relative_to(prefix['from'])
                except ValueError:
                    continue
                target = resources / copy['to']
                source = original_root / prefix['to'] / relative
                if not target.exists() or not source.exists():
                    continue
                if target.is_dir() != source.is_dir():
                    continue
                if target.is_dir():
                    files = [p for p in target.rglob('*') if p.is_file()]
                    if not files or any(not (source / p.relative_to(target)).is_file() or
                                        p.read_bytes() != (source / p.relative_to(target)).read_bytes() for p in files):
                        continue
                    suffix = '/'
                else:
                    if target.read_bytes() != source.read_bytes():
                        continue
                    suffix = ''
                links.append(dict(dependency=dependency,
                    path=f'assets/{app["descriptor"]["name"]}/{Path(copy["to"]).as_posix()}' + suffix,
                    source=f'assets/{descriptor["name"]}/{(Path(prefix["to"]) / relative).as_posix()}' + suffix))
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                break
    if len(links) > 16:
        raise ValueError('Too many shared resource links')
    return dict(dependencies=requirements, resources=links)
