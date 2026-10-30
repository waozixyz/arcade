"""Exercise packaging from the actual registered game builds, preserving bytes."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shlex
import shutil
import tempfile
import unittest
import sys
import tarfile
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("build_collection", ROOT / "scripts/build-collection.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
art_spec = importlib.util.spec_from_file_location("library_art", ROOT / "scripts/library-art.py")
artist = importlib.util.module_from_spec(art_spec)
art_spec.loader.exec_module(artist)
spec = importlib.util.spec_from_file_location("published_games", ROOT / "scripts/wait-published-games.py")
published_games = importlib.util.module_from_spec(spec)
spec.loader.exec_module(published_games)


def bundle_asset_paths(path):
    """Read the actual bundle index without loading its images or executing it."""
    with published_games.Reader(path) as reader:
        if reader.take(8) != b"ZX\0\0\x1a\0\0\0":
            raise ValueError("Unsupported game bundle")
        reader.text()
        reader.text()
        for _ in range(reader.number()):
            reader.text()
            reader.text()
        for _ in range(reader.number()):
            for _ in range(7):
                reader.text()
            reader.take(8)
            reader.text()
            reader.take(4)
        for _ in range(reader.number()):
            for _ in range(3):
                reader.text()
        reader.skip(reader.number())
        paths = set()
        for _ in range(reader.number()):
            name = reader.text().decode()
            if name in paths:
                raise ValueError("Duplicate game asset: " + name)
            paths.add(name)
            reader.skip(reader.number())
        reader.finish()
    return paths


class CollectionTests(unittest.TestCase):
    def test_choano_runtime_images_are_packed_at_their_runtime_paths(self):
        # Fixed runtime references catch a doubled namespace in the real
        # compiled payload, independently of the packaging declaration.
        assets = bundle_asset_paths(ROOT / "build/games/choano.zx")
        for path in ("assets/choano/background-inside.png", "assets/choano/organisms-hd.png",
                     "assets/choano/title-landscape.jpg", "assets/choano/fish/sea.png"):
            self.assertTrue(path in assets, "Choano runtime image missing from its bundle: " + path)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="collection-", dir=ROOT / "build")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "apps").mkdir()
        for name in ("games.json", "apps.json", "apps/versions.json"):
            shutil.copyfile(ROOT / name, self.root / name)
        # Arcade's own apps are declared beside it.
        for app in json.loads((ROOT / "apps.json").read_text())["apps"]:
            manifest = Path(app["manifest"])
            (self.root / manifest).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / manifest, self.root / manifest)
        # Games from another package (Shovey) resolve through Arcade's own pins.
        (self.root / "scripts").mkdir()
        resolver = self.root / "scripts/ziran.sh"
        resolver.write_text(f'#!/bin/sh\ncd {shlex.quote(str(ROOT))} && exec ./scripts/ziran.sh "$@"\n')
        resolver.chmod(0o755)
        shutil.copytree(ROOT / "build/games", self.root / "build/games")
        (self.root / "assets/arcade").mkdir(parents=True)
        shutil.copyfile(ROOT / "assets/arcade/sidebar.shape", self.root / "assets/arcade/sidebar.shape")
        shutil.copytree(ROOT / "assets/arcade/library", self.root / "assets/arcade/library")
        # Only a native VM identity gate can trust a controller. This fixture
        # tests packing and its exact-content requirement, not that handshake.
        self.controller = self.root / "controller.zx"
        self.controller.write_bytes(b"controller exact-content fixture")
        self.controller_digest = builder.digest(self.controller)
        self.output = self.root / "staged"

    def stage(self):
        return builder.stage(self.root, self.controller, self.controller_digest, self.output)[0]

    def assert_children_match_declarations(self, catalog, packages, payload_root):
        declarations = builder.declared_packages(self.root)
        ledger = json.loads((self.root / "apps/versions.json").read_text())["node_apps"]
        expected_children = []
        for app in (app for package in declarations for app in package["apps"] if app["enabled"]):
            descriptor = app["descriptor"]
            cover = app["cover"] or {}
            expected_children.append((
                descriptor["id"], descriptor["title"], descriptor["name"],
                ledger[descriptor["name"]]["version"], cover.get("caption", ""),
                cover.get("action"), tuple(app["requires"]), app["shared_code"],
            ))
        self.assertEqual([(
            child["id"], child["title"], child["expected_id"], child["version"],
            child.get("cover", {}).get("caption", ""), child.get("cover", {}).get("action"),
            tuple(child.get("dependencies", [])), child.get("shared_code", False),
        ) for child in catalog["children"]], expected_children)
        self.assertEqual([(p["name"], p["id"], p["children"]) for p in packages],
                         [(package["name"], package["id"],
                           [app["descriptor"]["id"] for app in package["apps"] if app["enabled"]])
                          for package in declarations[1:]])
        library = payload_root / "assets/arcade/library"
        for child in catalog["children"]:
            name = child["expected_id"]
            source = payload_root / f"build/games/{name}.zx"
            packed = self.output / child["bundle"]
            self.assertEqual(packed.read_bytes(), source.read_bytes())
            self.assertEqual(builder.digest(packed), child["sha256"])
            self.assertEqual(child["bytes"], source.stat().st_size)
            self.assertEqual(child["protocol"], "node/2")
            expected_preview = next(library.glob(f"{name}-preview.*"))
            self.assertEqual(child["preview"], child["icon"])
            self.assertEqual(child["preview"], f"assets/arcade/previews/{name}{expected_preview.suffix}")
            self.assertEqual((self.output / child["preview"]).read_bytes(), expected_preview.read_bytes())
            for key in ("portrait", "landscape", "logo"):
                if key not in child.get("cover", {}):
                    continue
                expected_cover = next(library.glob(f"{name}-{key}.*"))
                self.assertEqual(child["cover"][key],
                                 f"assets/arcade/covers/{name}-{key}{expected_cover.suffix}")
                self.assertEqual((self.output / child["cover"][key]).read_bytes(),
                                 expected_cover.read_bytes())

    def add_library_copy(self, name, key, data):
        library = self.root / "assets/arcade/library"
        sources = json.loads((library / "sources.json").read_text())
        contents, suffix = artist.small_copy(data, key)
        copy = library / f"{name}-{key}{suffix}"
        copy.write_bytes(contents)
        sources[f"{name}-{key}"] = {"source_sha256": hashlib.sha256(data).hexdigest()}
        (library / "sources.json").write_text(json.dumps(sources))

    def stage_four_leaf_wurm_fixture(self):
        registration = self.root / 'games.json'
        value = json.loads(registration.read_text())
        value.pop('artwork', None)
        registration.write_text(json.dumps(value))
        source = self.root / "fixture-packages/wurm"
        (source / "editor").mkdir(parents=True)
        (source / "assets").mkdir()

        def image(color, path):
            picture = Image.new("RGB", (640, 480), color)
            picture.save(path)
            return path.read_bytes()

        (source / "catalog.json").write_text(json.dumps({
            "id": "xyz.waozi.wurm", "name": "wurm", "title": "Apfelwurm",
            "kind": "game", "contract_version": 1, "module_api": 2, "host_api": 41,
            "harnesses": ["arcade"], "preview": "assets/wurm-preview.png",
        }))
        (source / "editor/catalog.json").write_text(json.dumps({
            "id": "xyz.waozi.wurm-editor", "name": "wurm-editor", "title": "Apfelwurm Editor",
            "kind": "game", "contract_version": 1, "module_api": 2, "host_api": 41,
            "harnesses": ["arcade"], "preview": "assets/wurm-editor-preview.png",
        }))
        images = {
            "wurm-preview": image((255, 0, 0), source / "assets/wurm-preview.png"),
            "wurm-portrait": image((0, 255, 0), source / "assets/wurm-portrait.png"),
            "wurm-editor-preview": image((0, 0, 255), source / "assets/wurm-editor-preview.png"),
            "wurm-editor-portrait": image((255, 255, 0), source / "assets/wurm-editor-portrait.png"),
        }
        (source / "apps.json").write_text(json.dumps({
            "id": "xyz.waozi.wurm-player", "title": "Apfelwurm", "apps": [
                {"manifest": "catalog.json", "cover": {
                    "portrait": "assets/wurm-portrait.png", "caption": "Classic", "action": "play"}},
                {"manifest": "editor/catalog.json",
                 "requires": ["xyz.waozi.wurm"], "cover": {
                     "portrait": "assets/wurm-editor-portrait.png", "caption": "Editor", "action": "open"}},
            ],
        }))
        games = self.root / "build/games"
        for name, prefix in (("wurm", b"synthetic wurm payload\n"),
                             ("wurm-editor", b"synthetic wurm editor payload\n")):
            (games / f"{name}.zx").write_bytes(prefix + name.encode())
            preview_name = f"{name}-preview.png"
            (games / preview_name).write_bytes(images[f"{name}-preview"])
        (games / "wurm-editor-resources.json").write_text(json.dumps({
            "dependencies": ["xyz.waozi.wurm"],
            "resources": [{"dependency": "xyz.waozi.wurm", "path": "assets/wurm/classic/",
                           "source": "assets/wurm-preview.png"}],
        }))
        for name, key in (("wurm", "preview"), ("wurm", "portrait"),
                          ("wurm-editor", "preview"), ("wurm-editor", "portrait")):
            self.add_library_copy(name, key, images[f"{name}-{key}"])
        ledger_path = self.root / "apps/versions.json"
        ledger = json.loads(ledger_path.read_text())
        ledger["node_apps"]["wurm-editor"] = {
            "id": "xyz.waozi.wurm-editor", "title": "Apfelwurm Editor", "version": "0.1.0",
            "sequence": 1, "host_api": 41,
        }
        ledger_path.write_text(json.dumps(ledger))
        resolver = self.root / "scripts/ziran.sh"
        resolver.write_text(
            f'#!/bin/sh\n'
            f'if [ "$1" = pkg ] && [ "$2" = path ] && [ "$3" = wurm ]; then\n'
            f'  printf \'%s\\n\' {shlex.quote(str(source))}\n'
            f'  exit 0\n'
            f'fi\n'
            f'cd {shlex.quote(str(ROOT))} && exec ./scripts/ziran.sh "$@"\n'
        )

    def test_unchanged_games_keep_canonical_identity_and_version(self):
        catalog, packages = builder.stage(self.root, self.controller, self.controller_digest, self.output)
        self.assertEqual(catalog["id"], "inbe.arcade")
        # Inbe draws the launcher icon from the collection's own assets.
        self.assertEqual((self.output / "assets/arcade/sidebar.shape").read_bytes(),
                         (ROOT / "assets/arcade/sidebar.shape").read_bytes())
        # Expected identities and versions come from each package's declarations.
        self.assert_children_match_declarations(catalog, packages, ROOT)
        self.assertEqual((self.output / catalog["harness"]).read_bytes(), self.controller.read_bytes())

        pinned_ledger = json.loads((ROOT / "apps/versions.json").read_text())["node_apps"]
        wurm_version = pinned_ledger["wurm"]["version"]
        self.stage_four_leaf_wurm_fixture()
        catalog, packages = builder.stage(self.root, self.controller, self.controller_digest, self.output)
        self.assert_children_match_declarations(catalog, packages, self.root)
        self.assertEqual([child["id"] for child in catalog["children"]],
                         ["arcade.shovey", "arcade.shovey-editor",
                          "xyz.waozi.wurm", "xyz.waozi.wurm-editor", "xyz.waozi.choano"])
        wurm_package = next(package for package in packages if package["name"] == "wurm")
        self.assertEqual(wurm_package["children"], ["xyz.waozi.wurm", "xyz.waozi.wurm-editor"])
        children = {child["id"]: child for child in catalog["children"]}
        self.assertEqual(children["xyz.waozi.choano"]["title"], "Choano")
        self.assertEqual(children["xyz.waozi.choano"]["version"], "0.1.3")
        self.assertEqual(children["xyz.waozi.choano"]["expected_id"], "choano")
        self.assertEqual(children["xyz.waozi.wurm"]["version"], wurm_version)
        self.assertEqual(children["xyz.waozi.wurm-editor"]["version"], "0.1.0")
        self.assertEqual(children["xyz.waozi.wurm"]["cover"]["caption"], "Classic")
        self.assertEqual(children["xyz.waozi.wurm-editor"]["cover"]["caption"], "Editor")
        self.assertEqual(children["xyz.waozi.wurm-editor"]["dependencies"], ["xyz.waozi.wurm"])
        self.assertFalse(children["xyz.waozi.wurm-editor"].get("shared_code", False))
        self.assertEqual(children["xyz.waozi.wurm-editor"]["resources"], [{
            "dependency": "xyz.waozi.wurm", "path": "assets/wurm/classic/",
            "source": "assets/wurm-preview.png"}])
        self.assertEqual(children["xyz.waozi.wurm"]["expected_id"], "wurm")
        self.assertEqual(children["xyz.waozi.wurm-editor"]["expected_id"], "wurm-editor")
        self.assertNotEqual(children["xyz.waozi.wurm"]["bundle"],
                            children["xyz.waozi.wurm-editor"]["bundle"])

    def test_changed_game_art_needs_fresh_library_copies(self):
        sources = self.root / "assets/arcade/library/sources.json"
        value = json.loads(sources.read_text())
        value["wurm-portrait"]["source_sha256"] = "0" * 64
        sources.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "wurm-portrait art changed"):
            self.stage()

    def test_artwork_input_changes_no_game_payload_or_version(self):
        packages = builder.declared_packages(self.root)
        game = next(app for package in packages for app in package['apps']
                    if app['descriptor']['name'] == 'wurm-editor')
        self.assertNotEqual(game['source'], game['art_source'])
        self.assertEqual(hashlib.sha256((game['art_source'] / game['cover']['portrait']).read_bytes()).hexdigest(),
                         '07ff2ff0142c262cdcba3643bbc4d7d3d71643b7f9f4e678a910fee2bfd3eba1')
        catalog = self.stage()
        child = next(item for item in catalog['children'] if item['expected_id'] == 'wurm-editor')
        self.assertEqual(child['version'], '0.1.0')
        self.assertEqual(child['sha256'], builder.digest(self.root / 'build/games/wurm-editor.zx'))

    def test_artwork_override_must_name_a_registered_game(self):
        path = self.root / 'games.json'
        value = json.loads(path.read_text())
        value['artwork'] = {'unknown-game': 'wurm_art'}
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'Invalid artwork package'):
            self.stage()

    def test_every_library_cover_uses_a_bounded_thumbnail(self):
        catalog, packages = builder.stage(self.root, self.controller, self.controller_digest, self.output)
        children = {child['id']: child for child in catalog['children']}
        for package in packages:
            for app in package['apps']:
                if not app['enabled'] or not app['cover']:
                    continue
                child = children[app['descriptor']['id']]
                for key in ('portrait', 'landscape', 'logo'):
                    if key not in app['cover']:
                        continue
                    original = (app['art_source'] / app['cover'][key]).read_bytes()
                    with self.subTest(app=child['id'], image=key):
                        with Image.open(io.BytesIO(original)) as source:
                            with Image.open(self.output / child['cover'][key]) as thumbnail:
                                limit = 512 if key == 'logo' else 640
                                self.assertLessEqual(max(thumbnail.size), limit)
                                self.assertLessEqual(thumbnail.width, source.width)
                                self.assertLessEqual(thumbnail.height, source.height)
                                expected_ratio = source.width / source.height
                                if key == 'portrait':
                                    expected_ratio = max(2 / 3, expected_ratio)
                                self.assertAlmostEqual(thumbnail.width / thumbnail.height,
                                                       expected_ratio, delta=0.01)
                                self.assertIn(thumbnail.mode, ('RGB', 'RGBA'))
                                # Opaque cover art is a JPEG; transparency stays PNG.
                                self.assertEqual(thumbnail.format, 'JPEG' if key != 'logo' and
                                                 thumbnail.mode == 'RGB' else 'PNG')

    def test_editor_download_reuses_verified_shovey_assets(self):
        catalog = self.stage()
        children = {child['id']: child for child in catalog['children']}
        editor = children['arcade.shovey-editor']
        original = children['arcade.shovey']
        self.assertEqual(editor['dependencies'], [original['id']])
        self.assertTrue(editor['resources'])
        self.assertLess(editor['bytes'], original['bytes'])
        for link in editor['resources']:
            self.assertEqual(link['dependency'], original['id'])
            self.assertTrue(link['path'].startswith('assets/shovey-editor/'))
            self.assertTrue(link['source'].startswith('assets/shovey/'))

    def test_changed_dependency_metadata_preserves_previous_stage(self):
        self.stage()
        previous = (self.output / 'assets/apps/catalog.json').read_bytes()
        path = self.root / 'build/games/shovey-editor-resources.json'
        shared = json.loads(path.read_text())
        shared['dependencies'] = []
        path.write_text(json.dumps(shared))
        with self.assertRaisesRegex(ValueError, 'dependencies differ'):
            self.stage()
        self.assertEqual((self.output / 'assets/apps/catalog.json').read_bytes(), previous)

    def test_changed_controller_preserves_previous_stage(self):
        self.stage()
        previous = (self.output / "assets/apps/catalog.json").read_bytes()
        self.controller.write_bytes(b"unreviewed replacement")
        with self.assertRaisesRegex(ValueError, "trusted SHA-256"):
            self.stage()
        self.assertEqual((self.output / "assets/apps/catalog.json").read_bytes(), previous)

    def test_arcade_downloads_preserve_catalog_and_standalone_payloads(self):
        catalog = self.stage()
        small = self.root / "small"
        games = self.root / "arcade.games"
        builder.stage_downloads(catalog, self.output, small, games, self.root / "art")
        art = self.root / "art"
        self.assertEqual((small / "assets/apps/catalog.json").read_bytes(),
                         (self.output / "assets/apps/catalog.json").read_bytes())
        # The published launcher packs neither the host's controller nor art.
        self.assertFalse((small / catalog["harness"]).exists())
        self.assertTrue((self.output / catalog["harness"]).is_file(), "Standalone players keep the controller")
        for child in catalog["children"]:
            full = self.output / child["bundle"]
            self.assertTrue(full.is_file(), "Standalone players retain the game")
            self.assertFalse((small / child["bundle"]).exists())
            self.assertEqual((games / (child["sha256"] + ".zx")).read_bytes(), full.read_bytes())
            pictures = [child["preview"]] + [child["cover"][key] for key in child["cover"].keys() & {"portrait", "landscape", "logo"}]
            for relative in pictures:
                self.assertFalse((small / relative).exists())
                self.assertEqual((art / relative).read_bytes(), (self.output / relative).read_bytes())
        packed = sum(path.stat().st_size for path in small.rglob("*") if path.is_file())
        self.assertLess(packed, 1024 * 1024, "Arcade itself stays under one megabyte")

    def test_art_bundle_is_published_and_named_by_the_catalog(self):
        catalog = self.stage()
        small = self.root / "small"
        games = self.root / "arcade.games"
        builder.stage_downloads(catalog, self.output, small, games, self.root / "art")
        art_bundle = self.root / "art.zx"
        art_bundle.write_bytes(b"ZX\0\0art fixture")
        art = builder.add_art(small, games, art_bundle)
        self.assertEqual(art, dict(sha256=builder.digest(art_bundle), bytes=art_bundle.stat().st_size))
        self.assertEqual((games / (art["sha256"] + ".zx")).read_bytes(), art_bundle.read_bytes())
        self.assertEqual(json.loads((small / "assets/apps/catalog.json").read_text())["art"], art)

    def test_changed_download_preserves_previous_outputs(self):
        catalog = self.stage()
        small = self.root / "small"
        games = self.root / "arcade.games"
        builder.stage_downloads(catalog, self.output, small, games, self.root / "art")
        (self.output / catalog["children"][0]["bundle"]).write_bytes(b"changed game")
        with self.assertRaisesRegex(ValueError, "declared digest"):
            builder.stage_downloads(catalog, self.output, small, games, self.root / "art")
        self.assertTrue((small / "assets/apps/catalog.json").exists())
        self.assertTrue((games / (catalog["children"][0]["sha256"] + ".zx")).exists())

    def test_download_archive_contains_exact_hash_named_games(self):
        catalog = self.stage()
        small = self.root / "small"
        games = self.root / "arcade.games"
        builder.stage_downloads(catalog, self.output, small, games, self.root / "art")
        archive = self.root / "arcade.games.tar"
        builder.archive_downloads(games, archive)
        with tarfile.open(archive) as content:
            self.assertEqual(set(content.getnames()), {child["sha256"] + ".zx" for child in catalog["children"]})
            for member in content:
                self.assertTrue(member.isfile())
                self.assertEqual(member.mtime, 0)
                self.assertEqual(content.extractfile(member).read(), (games / member.name).read_bytes())

    def test_removed_download_does_not_leave_stale_payload(self):
        catalog = self.stage()
        small = self.root / "small"
        games = self.root / "arcade.games"
        builder.stage_downloads(catalog, self.output, small, games, self.root / "art")
        catalog["children"] = []
        # Build a fresh full stage as a real removed registration does.
        (self.root / "games.json").write_text(json.dumps({"packages": []}))
        catalog = self.stage()
        builder.stage_downloads(catalog, self.output, small, games, self.root / "art")
        self.assertEqual(list(games.iterdir()), [])
        self.assertFalse((small / "assets/arcade/games/shovey.zx").exists())

    def test_invalid_controller_digest_rejected(self):
        with self.assertRaisesRegex(ValueError, "exact trusted"):
            builder.stage(self.root, self.controller, "", self.output)
        self.assertFalse(self.output.exists())

    def test_duplicate_game_rejected_before_replacing_stage(self):
        self.stage()
        registrations = json.loads((self.root / "games.json").read_text())
        registrations["packages"].append(registrations["packages"][0])
        (self.root / "games.json").write_text(json.dumps(registrations))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.stage()
        self.assertTrue((self.output / "assets/arcade/games/shovey.zx").is_file())

    def test_ledger_identity_mismatch_rejected(self):
        ledger_path = self.root / "apps/versions.json"
        ledger = json.loads(ledger_path.read_text())
        ledger["node_apps"]["shovey"]["id"] = "other.shovey"
        ledger_path.write_text(json.dumps(ledger))
        with self.assertRaisesRegex(ValueError, "version ledger"):
            self.stage()
        self.assertFalse(self.output.exists())

    def test_removed_package_leaves_no_stale_payload(self):
        self.stage()
        (self.root / "games.json").write_text(json.dumps({"packages": []}))
        self.assertEqual(self.stage()["children"], [])
        self.assertFalse((self.output / "assets/arcade/games/shovey.zx").exists())
        self.assertFalse((self.output / "assets/arcade/covers/shovey-portrait.jpg").exists())

    def test_unknown_declaration_field_rejected(self):
        declaration = json.loads((self.root / "apps.json").read_text())
        declaration["apps"][0]["cover_art"] = "assets/chess/preview.png"
        (self.root / "apps.json").write_text(json.dumps(declaration))
        with self.assertRaisesRegex(ValueError, "unknown apps.json field"):
            self.stage()
        self.assertFalse(self.output.exists())


class LibraryThumbnailTests(unittest.TestCase):
    def test_tall_portrait_keeps_title_inside_the_library_card(self):
        source = Image.new('RGB', (800, 1600), (25, 50, 75))
        source.paste((220, 180, 40), (80, 100, 720, 220))
        data = io.BytesIO()
        source.save(data, 'PNG')
        contents, suffix = artist.small_copy(data.getvalue(), 'portrait')
        self.assertEqual(suffix, '.jpg')
        with Image.open(io.BytesIO(contents)) as thumbnail:
            self.assertEqual(thumbnail.size, (427, 640))
            # The real card's centred cover fit now leaves the title intact.
            red, green, blue = thumbnail.getpixel((213, 85))
            self.assertGreater(red, 200)
            self.assertGreater(green, 160)
            self.assertLess(blue, 60)

    def test_cover_keeps_full_colour_at_thumbnail_resolution(self):
        source = Image.new('RGB', (900, 1200))
        source.putdata([(x % 256, y % 256, (x + y) % 256)
                        for y in range(1200) for x in range(900)])
        data = io.BytesIO()
        source.save(data, 'PNG')
        contents, suffix = artist.small_copy(data.getvalue(), 'portrait')
        self.assertEqual(suffix, '.jpg')
        with Image.open(io.BytesIO(contents)) as thumbnail:
            self.assertEqual(thumbnail.format, 'JPEG')
            self.assertEqual(thumbnail.size, (480, 640))
            self.assertEqual(thumbnail.mode, 'RGB')
            self.assertIsNone(thumbnail.getcolors(256))

    def test_logo_retains_transparency(self):
        source = Image.new('RGBA', (1200, 400), (45, 155, 90, 0))
        source.paste((200, 35, 100, 255), (100, 50, 1100, 350))
        data = io.BytesIO()
        source.save(data, 'PNG')
        contents, suffix = artist.small_copy(data.getvalue(), 'logo')
        self.assertEqual(suffix, '.png')
        with Image.open(io.BytesIO(contents)) as thumbnail:
            self.assertEqual(thumbnail.size, (512, 171))
            self.assertEqual(thumbnail.mode, 'RGBA')
            self.assertEqual(thumbnail.getpixel((0, 0))[3], 0)
            self.assertEqual(thumbnail.getpixel((256, 85))[3], 255)

    def test_small_covers_are_not_enlarged(self):
        source = Image.new('RGB', (120, 180), (25, 50, 75))
        data = io.BytesIO()
        source.save(data, 'PNG')
        contents, suffix = artist.small_copy(data.getvalue(), 'portrait')
        self.assertEqual(suffix, '.jpg')
        with Image.open(io.BytesIO(contents)) as thumbnail:
            self.assertEqual(thumbnail.size, (120, 180))

    def test_small_transparent_art_is_not_reencoded(self):
        source = Image.new('RGBA', (120, 60), (25, 50, 75, 128))
        data = io.BytesIO()
        source.save(data, 'PNG')
        self.assertEqual(artist.small_copy(data.getvalue(), 'logo'), (data.getvalue(), '.png'))

    def test_thin_logos_keep_at_least_one_pixel(self):
        source = Image.new('RGBA', (4096, 1), (25, 50, 75, 255))
        data = io.BytesIO()
        source.save(data, 'PNG')
        with Image.open(io.BytesIO(artist.small_copy(data.getvalue(), 'logo')[0])) as thumbnail:
            self.assertEqual(thumbnail.size, (512, 1))


if __name__ == "__main__":
    unittest.main()
