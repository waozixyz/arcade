#!/usr/bin/env python3
"""Game imports select scoped Kryon paths; real bundles cover theme collisions."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from game_module_paths import kryon_module_paths


class SourceFixture(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / 'work/game-module-path-tests'
        subprocess.run(['git', 'check-ignore', '-q', str(scratch)], cwd=ROOT, check=True)
        scratch.mkdir(parents=True, exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.source = self.root / 'game'
        self.ui = self.root / 'kryon/src/ui'
        self.ui.mkdir(parents=True)
        for name in ('scroll', 'theme', 'geometry'):
            (self.ui / (name + '.zi')).touch()

    def write(self, path, text=''):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def paths(self, entry='src/app.zi'):
        return kryon_module_paths(self.source, {'source': entry}, self.root / 'kryon')


class ModulePathsTest(SourceFixture):
    def test_qualified_imports_and_owned_theme_stay_scoped(self):
        self.write(self.source / 'src/app.zi', '#import "theme"\n#import "kryon/scroll"')
        self.write(self.source / 'src/theme.zi')
        self.assertEqual(self.paths(), ['--module-path', 'kryon=' + str(self.ui),
                                       '--module-path', 'kryon=' + str(self.ui.parent / 'backend')])

    def test_short_import_in_nested_source_needs_plain_path(self):
        self.write(self.source / 'src/app.zi', '#import "theme"')
        self.write(self.source / 'src/theme.zi')
        self.write(self.source / 'src/views/game.zi', 'Geometry :: #import /* reason */ "geometry";')
        self.assertEqual(self.paths()[:2], ['--module-path', str(self.ui)])

    def test_entry_outside_src_and_package_without_src(self):
        self.write(self.source / 'src/host.zi')
        self.write(self.source / 'apps/chess/view.zi', '#import "geometry"')
        self.assertEqual(self.paths('apps/chess/view.zi')[:2], ['--module-path', str(self.ui)])
        self.write(self.source / 'view.zi', '#import "scroll"')
        (self.source / 'src/host.zi').unlink()
        (self.source / 'src').rmdir()
        self.assertEqual(self.paths('view.zi')[:2], ['--module-path', str(self.ui)])

    def test_only_owned_root_names_shadow_shared_modules(self):
        self.write(self.source / 'src/app.zi', '#import "geometry"')
        self.write(self.source / 'src/nested/geometry.zi')
        self.assertIn(str(self.ui), self.paths())
        self.write(self.source / 'src/geometry/module.zi')
        self.assertNotIn(str(self.ui), self.paths())

    def test_comments_strings_file_imports_and_other_packages_do_not_flatten(self):
        self.write(self.source / 'src/app.zi', '''
// #import "scroll"
/* #import "geometry" */
Text :: "#import \\"scroll\\""
#import, file "scroll.zi";
#import "other/geometry"
#import "not_a_ui_module"
''')
        self.assertNotIn(str(self.ui), self.paths())


class BundleTest(SourceFixture):
    @classmethod
    def setUpClass(cls):
        wrapper = str(ROOT / 'scripts/ziran.sh')
        flags = [] if (ROOT / 'ziran.local.toml').exists() else ['--locked']

        def package(name):
            return Path(subprocess.check_output([wrapper, 'pkg', 'path', name, *flags], cwd=ROOT, text=True).strip())

        cls.toolchain = Path(os.environ['ZIRAN_SOURCE']) if 'ZIRAN_SOURCE' in os.environ else package('ziran')
        cls.kryon = Path(os.environ['KRYON_SOURCE']) if 'KRYON_SOURCE' in os.environ else package('kryon')
        cls.compiler = os.environ.get('ZIRAN', str(cls.toolchain / 'build/bin/ziran'))

    def compiler_run(self, *args):
        env = os.environ.copy()
        for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS'):
            env.pop(key, None)
        return subprocess.run([self.compiler, *map(str, args)],
                              cwd=ROOT, env=env, text=True, capture_output=True, timeout=180)

    def bundle(self, imports, local_theme=False, old_paths=False):
        entry = self.source / 'src/guest.zi'
        self.write(entry, imports + '''
using ButtonState;
#program_export
Answer :: () -> s32 {
    thumb := ScrollFace(StyleKindScrollThumb(), 0, false,
        cast(s32)ButtonStateNormal, 10.0)
''' + ('    if AppTheme.LocalTheme() != cast(u32)0xaabbccdd { return 1 }\n' if local_theme else '') + '''
    if thumb.value.background != cast(u32)0x889faaff { return 2 }
    return 42
}
''')
        if local_theme:
            self.write(entry.with_name('theme.zi'), '''
#program_export
LocalTheme :: () -> u32 { return cast(u32)0xaabbccdd }
''')
        paths = kryon_module_paths(self.source, {'source': 'src/guest.zi'}, self.kryon)
        if old_paths:
            paths = ['--module-path', str(self.kryon / 'src/ui'), *paths]
        output = self.root / 'guest.zx'
        result = self.compiler_run('bundle', '--root', entry.parent, *paths,
                                   '--module-path', self.toolchain / 'std',
                                   '--entry', 'guest:Answer', '-o', output, entry)
        return result, output

    def test_scoped_bundle_preserves_app_theme_and_kryon_palette(self):
        imports = '''AppTheme :: #import "theme";
#import "kryon/scroll"
#import "kryon/style_sheet"
#import "kryon/control_props"
'''
        old, _ = self.bundle(imports, local_theme=True, old_paths=True)
        self.assertNotEqual(old.returncode, 0, old.stdout)
        self.assertIn('LightBorderStrong', old.stderr + old.stdout)
        result, output = self.bundle(imports, local_theme=True)
        self.assertEqual(result.returncode, 0, (result.stderr + result.stdout)[-8000:])
        run = self.compiler_run('run', output)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), '42')

    def test_legacy_short_import_bundle_keeps_shared_path(self):
        result, output = self.bundle('''#import "scroll"
#import "style_sheet"
#import "control_props"
''')
        self.assertEqual(result.returncode, 0, (result.stderr + result.stdout)[-8000:])
        run = self.compiler_run('run', output)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), '42')


if __name__ == '__main__':
    unittest.main()
