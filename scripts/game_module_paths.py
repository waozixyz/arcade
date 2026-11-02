"""Select Kryon namespaces from a game's own source imports."""
import re
from pathlib import Path


_TOKENS = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|#import\b|\S', re.DOTALL)


def _imports(text):
    previous = None
    for match in _TOKENS.finditer(text):
        token = match.group()
        if token.startswith(('//', '/*')):
            continue
        if previous == '#import' and token.startswith('"'):
            yield token[1:-1]
        previous = token


def _module_names(root):
    return ({path.stem for path in root.glob('*.zi')} |
            {path.parent.name for path in root.glob('*/module.zi')})


def kryon_module_paths(source: Path, descriptor: dict, kryon: Path) -> list[str]:
    """Keep qualified UI imports scoped unless game code needs short imports.

    Registering the UI directory both plain and named makes Ziran load Kryon
    into the application's flat namespace. Only direct imports of UI modules
    the application does not own justify that legacy mode.
    """
    ui = kryon / 'src/ui'
    roots = {source / 'src' if (source / 'src').is_dir() else source,
             (source / descriptor['source']).parent}
    owned = set().union(*(_module_names(root) for root in roots))
    shared = _module_names(ui) - owned
    needs_plain = any(name in shared for root in roots for path in root.rglob('*.zi')
                      for name in _imports(path.read_text()))
    paths = [str(ui)] if needs_plain else []
    paths += ['kryon=' + str(ui), 'kryon=' + str(kryon / 'src/backend')]
    return [flag for path in paths for flag in ('--module-path', path)]
