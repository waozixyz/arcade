"""New game-owned labels remain translated and keep format placeholders."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def entries(path):
    values = {}
    for block in path.read_text().split('---\n'):
        lines = block.splitlines()
        if lines and lines[0].startswith('[chess_'):
            values[lines[0][1:-1]] = '\n'.join(lines[1:]).rstrip()
    return values


english = entries(ROOT / 'apps/chess/locales/en.txt')
new_keys = {'chess_' + suffix for suffix in [
    'copy', 'analysis', 'back_board', 'depth', 'export_help', 'first', 'flip', 'hint',
    'last_move', 'latest', 'level_expert', 'next', 'notation', 'previous',
    'review', 'suggestion', 'tab_study', 'undo', 'white_eval']}
loanwords = {('cs', 'chess_level_expert'), ('fr', 'chess_level_expert'),
             ('fr', 'chess_notation'), ('de', 'chess_notation')}
languages = set()
for path in (ROOT / 'apps/chess/locales').glob('*.txt'):
    languages.add(path.stem)
    values = entries(path)
    assert values.keys() == english.keys(), path.name
    for key, value in values.items():
        assert value and re.findall(r'%[sd]', value) == re.findall(r'%[sd]', english[key]), (path.name, key)
        if key in new_keys and path.stem != 'en' and (path.stem, key) not in loanwords:
            assert value != english[key], (path.name, key, 'untranslated game label')
assert len(languages) == 12
print('Chess: all 12 languages retain their labels and format placeholders')
