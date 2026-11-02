#!/usr/bin/env python3
"""Data fields must not suppress translation validation for actual labels."""
import importlib.util
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'scripts'))
spec = importlib.util.spec_from_file_location('check_games', root / 'scripts/check-games.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
code = '\n'.join([
    '#import "shovey_data"',
    'owned := ShopInteger(reply, "shovey_owned", 7)',
    'coins := ShopInteger(reply, "shovey_coins", 1000)',
    'Text(Label("shovey_title"))',
])
assert checker.translation_keys(code, 'shovey_') == {'shovey_title'}
assert checker.translation_keys(code + '\nText(Label("shovey_owned"))', 'shovey_') == {'shovey_title', 'shovey_owned'}
assert checker.translation_keys('Label("shovey_missing_translation")', 'shovey_') == {'shovey_missing_translation'}
print('JSON fields excluded; actual labels still require translations')
