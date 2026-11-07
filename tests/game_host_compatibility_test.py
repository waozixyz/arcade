"""Supported host range retains older games and refuses unsupported metadata."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('check_games', ROOT / 'scripts/check-games.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class HostCompatibility(unittest.TestCase):
    def test_supported_and_unsupported_interfaces(self):
        standard = json.loads((ROOT / 'standards/game-v1.json').read_text())
        for host_api in (43,):
            checker.compatible(dict(name='fixture', contract_version=1, module_api=2,
                                    host_api=host_api), standard)
        for field, value in [('host_api', 42), ('host_api', 44), ('host_api', True),
                             ('module_api', 1), ('contract_version', 2)]:
            game = dict(name='fixture', contract_version=1, module_api=2, host_api=43)
            game[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(AssertionError):
                checker.compatible(game, standard)


if __name__ == '__main__':
    unittest.main()
