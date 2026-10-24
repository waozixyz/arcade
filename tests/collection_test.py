"""Exercise packaging from the actual registered game builds, preserving bytes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import shutil
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("build_collection", ROOT / "scripts/build-collection.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class CollectionTests(unittest.TestCase):
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
        # Only a native VM identity gate can trust a controller. This fixture
        # tests packing and its exact-content requirement, not that handshake.
        self.controller = self.root / "controller.zx"
        self.controller.write_bytes(b"controller exact-content fixture")
        self.controller_digest = builder.digest(self.controller)
        self.output = self.root / "staged"

    def stage(self):
        return builder.stage(self.root, self.controller, self.controller_digest, self.output)[0]

    def test_unchanged_games_keep_canonical_identity_and_version(self):
        catalog, packages = builder.stage(self.root, self.controller, self.controller_digest, self.output)
        self.assertEqual(catalog["id"], "inbe.arcade")
        # Inbe draws the launcher icon from the collection's own assets.
        self.assertEqual((self.output / "assets/arcade/sidebar.shape").read_bytes(),
                         (ROOT / "assets/arcade/sidebar.shape").read_bytes())
        # The ledger also versions Arcade itself, which is not one of its games.
        ledger = json.loads((ROOT / "apps/versions.json").read_text())["node_apps"]
        self.assertEqual({c["id"] for c in catalog["children"]},
                         {"arcade.shovey", "arcade.shovey-editor"})
        # Each leaf keeps the cover its own package declares.
        self.assertEqual([c["cover"]["caption"] for c in catalog["children"]], ["Classic", "Editor"])
        self.assertEqual([(p["name"], p["id"], p["children"]) for p in packages],
                         [("shovey", "arcade.shovey-player", ["arcade.shovey", "arcade.shovey-editor"])])
        for child in catalog["children"]:
            name = child["expected_id"]
            packed = self.output / child["bundle"]
            self.assertEqual(packed.read_bytes(), (ROOT / f"build/games/{name}.zx").read_bytes())
            self.assertEqual(builder.digest(packed), child["sha256"])
            self.assertEqual(child["version"], ledger[name]["version"])
            self.assertEqual(child["protocol"], "node/2")
            self.assertEqual((self.output / child["preview"]).read_bytes(),
                             (ROOT / f"build/games/{name}-preview.png").read_bytes())
        self.assertEqual((self.output / catalog["harness"]).read_bytes(), self.controller.read_bytes())

    def test_changed_controller_preserves_previous_stage(self):
        self.stage()
        previous = (self.output / "assets/apps/catalog.json").read_bytes()
        self.controller.write_bytes(b"unreviewed replacement")
        with self.assertRaisesRegex(ValueError, "trusted SHA-256"):
            self.stage()
        self.assertEqual((self.output / "assets/apps/catalog.json").read_bytes(), previous)

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
        self.assertFalse((self.output / "assets/arcade/covers/shovey-portrait.png").exists())

    def test_unknown_declaration_field_rejected(self):
        declaration = json.loads((self.root / "apps.json").read_text())
        declaration["apps"][0]["cover_art"] = "assets/chess/preview.png"
        (self.root / "apps.json").write_text(json.dumps(declaration))
        with self.assertRaisesRegex(ValueError, "unknown apps.json field"):
            self.stage()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
