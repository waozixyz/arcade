"""Exercise packaging from the actual registered game builds, preserving bytes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_collection", ROOT / "scripts/build-collection.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="collection-", dir=ROOT / "build")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "apps").mkdir()
        shutil.copyfile(ROOT / "games.json", self.root / "games.json")
        shutil.copyfile(ROOT / "apps/versions.json", self.root / "apps/versions.json")
        for registration in json.loads((ROOT / "games.json").read_text())["games"]:
            manifest = Path(registration["manifest"])
            (self.root / manifest).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / manifest, self.root / manifest)
        shutil.copytree(ROOT / "build/games", self.root / "build/games")
        (self.root / "assets/arcade").mkdir(parents=True)
        shutil.copyfile(ROOT / "assets/arcade/sidebar.shape", self.root / "assets/arcade/sidebar.shape")
        # Only a native VM identity gate can trust a controller. This fixture
        # tests packing and its exact-content requirement, not that handshake.
        self.controller = self.root / "controller.zib"
        self.controller.write_bytes(b"controller exact-content fixture")
        self.controller_digest = builder.digest(self.controller)
        self.output = self.root / "staged"

    def stage(self):
        return builder.stage(self.root, self.controller, self.controller_digest, self.output)

    def test_unchanged_games_keep_canonical_identity_and_version(self):
        catalog = self.stage()
        self.assertEqual(catalog["id"], "inbe.arcade")
        # Inbe draws the launcher icon from the collection's own assets.
        self.assertEqual((self.output / "assets/arcade/sidebar.shape").read_bytes(),
                         (ROOT / "assets/arcade/sidebar.shape").read_bytes())
        ledger = json.loads((ROOT / "apps/versions.json").read_text())["node_apps"]
        self.assertEqual({c["id"] for c in catalog["children"]},
                         {entry["id"] for entry in ledger.values()})
        for child in catalog["children"]:
            name = child["expected_id"]
            packed = self.output / child["bundle"]
            self.assertEqual(packed.read_bytes(), (ROOT / f"build/games/{name}.zib").read_bytes())
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
        registrations["games"].append(registrations["games"][0])
        (self.root / "games.json").write_text(json.dumps(registrations))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.stage()
        self.assertTrue((self.output / "assets/arcade/games/chess.zib").is_file())

    def test_ledger_identity_mismatch_rejected(self):
        ledger_path = self.root / "apps/versions.json"
        ledger = json.loads(ledger_path.read_text())
        ledger["node_apps"]["chess"]["id"] = "other.chess"
        ledger_path.write_text(json.dumps(ledger))
        with self.assertRaisesRegex(ValueError, "version ledger"):
            self.stage()
        self.assertFalse(self.output.exists())

    def test_removed_game_leaves_no_stale_payload(self):
        self.stage()
        registrations = json.loads((self.root / "games.json").read_text())
        registrations["games"] = registrations["games"][:1]
        (self.root / "games.json").write_text(json.dumps(registrations))
        self.stage()
        self.assertFalse((self.output / "assets/arcade/games/pushy.zib").exists())
        self.assertFalse((self.output / "assets/arcade/previews/pushy.png").exists())


if __name__ == "__main__":
    unittest.main()
