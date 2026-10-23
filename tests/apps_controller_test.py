"""A local dependency override must never select the trusted controller's source."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_apps', ROOT / 'scripts/build-apps.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class ControllerSourceTests(unittest.TestCase):
    def test_local_overrides_do_not_reach_locked_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'ziran.toml').write_text('committed manifest')
            (root / 'ziran.lock').write_text('committed lock')
            (root / 'ziran.local.toml').write_text('unreviewed local dependency')
            package = root / 'cached-apps'
            output = root / 'output'
            contexts = []

            def resolve(command, *, cwd, text):
                self.assertEqual(command, ['ziran', 'pkg', 'path', 'apps', '--locked'])
                self.assertTrue(text)
                self.assertEqual((cwd / 'ziran.toml').read_text(), 'committed manifest')
                self.assertEqual((cwd / 'ziran.lock').read_text(), 'committed lock')
                self.assertEqual({p.name for p in cwd.iterdir()}, {'ziran.toml', 'ziran.lock'})
                contexts.append(cwd)
                return str(package) + '\n'

            with patch.object(builder.subprocess, 'check_output', side_effect=resolve), \
                 patch.object(builder.subprocess, 'run') as run:
                builder.build(root, output)
            run.assert_called_once_with(
                [builder.sys.executable, str(package / 'scripts/build-ui.py'),
                 '--output', str(output)], cwd=root, check=True)
            self.assertFalse(contexts[0].exists())
            self.assertEqual((root / 'ziran.local.toml').read_text(), 'unreviewed local dependency')


if __name__ == '__main__':
    unittest.main()
