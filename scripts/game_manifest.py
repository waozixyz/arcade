"""Resolve game catalogs across Shovey's standalone source-layout move."""
from pathlib import Path


def game_manifest(source, registration):
    source = Path(source)
    relative = Path(registration['manifest'])
    manifest = source / relative
    if manifest.is_file():
        return manifest
    # Retain clean builds with Arcade's existing locked Shovey revision.
    if registration['package'] == 'shovey' and relative.parts[0] == 'src':
        previous = source / 'apps/shovey' / relative.relative_to('src')
        if previous.is_file():
            return previous
    raise FileNotFoundError(manifest)
