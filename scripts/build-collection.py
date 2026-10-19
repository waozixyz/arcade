#!/usr/bin/env python3
"""Pack Arcade's unchanged game bundles and the shared Apps controller."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
COLLECTION_ID = "inbe.arcade"
MAX_PAYLOAD_BYTES = 64 * 1024 * 1024
MAX_GAMES = 16


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(root, controller, expected_controller_digest, output):
    """Validate before replacing a previously staged collection."""
    if not re.fullmatch(r"[0-9a-f]{64}", expected_controller_digest):
        raise ValueError("An exact trusted Apps controller SHA-256 is required")
    controller_bytes = controller.read_bytes()
    if hashlib.sha256(controller_bytes).hexdigest() != expected_controller_digest:
        raise ValueError("Apps controller differs from the trusted SHA-256")
    registrations = json.loads((root / "games.json").read_text())["games"]
    if not 1 <= len(registrations) <= MAX_GAMES:
        raise ValueError("Arcade needs 1 to 16 games")
    ledger = json.loads((root / "apps/versions.json").read_text())["node_apps"]
    children, copies, identities = [], [], set()
    total = len(controller_bytes)
    for registration in registrations:
        if registration["package"] != "self":
            raise ValueError("Arcade must own each registered game")
        manifest = root / registration["manifest"]
        game = json.loads(manifest.read_text())
        name, identifier = game["name"], game["id"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
            raise ValueError("Invalid game name")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", identifier) or len(identifier) >= 128:
            raise ValueError("Invalid game identity")
        if identifier in identities or identifier == COLLECTION_ID:
            raise ValueError("Duplicate or recursive game identity")
        identities.add(identifier)
        component = ledger[name]
        if (component["id"] != identifier or game["kind"] != "game"
                or "arcade" not in game["harnesses"]
                or game["contract_version"] != 1 or game["module_api"] != 2
                or game["host_api"] != component["host_api"]):
            raise ValueError("Incompatible game descriptor or version ledger")
        bundle = root / "build/games" / (name + ".zib")
        preview = root / "build/games" / (name + "-preview.png")
        # The game build embeds this exact legacy descriptor. Its verified
        # name binds node/2's legacy handshake to the stable signed app ID.
        bundle_bytes, preview_bytes = bundle.read_bytes(), preview.read_bytes()
        if not bundle_bytes or not preview_bytes:
            raise ValueError("Game bundles and previews must be built first")
        total += len(bundle_bytes) + len(preview_bytes)
        children.append(dict(
            id=identifier, title=game["title"],
            bundle=f"assets/arcade/games/{name}.zib", protocol="node/2",
            expected_id=name, version=component["version"],
            sha256=hashlib.sha256(bundle_bytes).hexdigest(),
            preview=f"assets/arcade/previews/{name}.png"))
        copies += [(bundle_bytes, Path("arcade/games") / (name + ".zib")),
                   (preview_bytes, Path("arcade/previews") / (name + ".png"))]
    if total > MAX_PAYLOAD_BYTES:
        raise ValueError("Arcade collection exceeds the host's payload limit")
    catalog = dict(schema=1, id=COLLECTION_ID, title="Arcade",
                   harness="assets/apps/apps.zib", children=children)
    # This stable directory contains disposable build output only. Clear it
    # after all inputs validate so removed registrations cannot linger.
    if output.exists():
        shutil.rmtree(output)
    assets = output / "assets"
    (assets / "apps").mkdir(parents=True)
    (assets / "apps/apps.zib").write_bytes(controller_bytes)
    (assets / "apps/catalog.json").write_text(json.dumps(catalog, indent=2) + "\n")
    for contents, relative in copies:
        destination = assets / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents)
    return catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ziran", default=str(ROOT / "scripts/ziran.sh"))
    parser.add_argument("--locked", action="store_true")
    parser.add_argument("--apps-bundle", type=Path, required=True)
    parser.add_argument("--apps-sha256", required=True)
    args = parser.parse_args()
    output = ROOT / "build/collection"
    catalog = stage(ROOT, args.apps_bundle, args.apps_sha256, output)
    command = [args.ziran, "bundle", "--project", *(["--locked"] if args.locked else [])]
    env = os.environ.copy()
    def bundle(source, entry, assets, target):
        subprocess.run([*command, "--root", str(ROOT / "src"), "--entry", entry,
            "--asset-dir", "assets=" + str(assets), "-o", str(target),
            str(ROOT / "src" / source)], cwd=ROOT, env=env, check=True)

    # One Pushy edition collection is both the standalone payload and the
    # exact child embedded in Arcade. Its Classic/Island leaves keep their IDs.
    editions = [child.copy() for child in catalog["children"]
                if child["id"] in {"arcade.pushy", "arcade.pushy-island"}]
    if len(editions) != 2:
        raise ValueError("Pushy requires both verified Classic and Island leaves")
    for child in editions:
        if child["id"] == "arcade.pushy":
            child["title"] = "Pushy Classic"
    pushy_output = ROOT / "build/pushy-collection"
    if pushy_output.exists():
        shutil.rmtree(pushy_output)
    assets = pushy_output / "assets"
    (assets / "apps").mkdir(parents=True)
    shutil.copyfile(output / "assets/apps/apps.zib", assets / "apps/apps.zib")
    pushy_catalog = dict(schema=1, id="arcade.pushy-player", title="Pushy",
                         harness="assets/apps/apps.zib", children=editions)
    (assets / "apps/catalog.json").write_text(json.dumps(pushy_catalog, indent=2) + "\n")
    for child in editions:
        for field in ("bundle", "preview"):
            relative = child[field]
            destination = pushy_output / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(output / relative, destination)
    bundle("pushy_collection.zi", "pushy_collection:Main", assets, ROOT / "build/pushy.zib")
    pushy_metadata = dict(id="arcade.pushy-player", version=(ROOT / "VERSION").read_text().strip(),
        sha256=digest(ROOT / "build/pushy.zib"), apps_sha256=args.apps_sha256,
        children=editions, source_mode="project")
    (ROOT / "build/pushy.json").write_text(json.dumps(pushy_metadata, indent=2) + "\n")
    parent_entry = dict(id="arcade.pushy-player", title="Pushy",
        bundle="assets/arcade/games/pushy-player.zib", protocol="collection/1",
        expected_id="pushy", version=pushy_metadata["version"], sha256=pushy_metadata["sha256"],
        preview="assets/arcade/previews/pushy.png")
    catalog["children"] = [child for child in catalog["children"]
                           if child["id"] not in {"arcade.pushy", "arcade.pushy-island"}]
    catalog["children"].append(parent_entry)
    shutil.copyfile(ROOT / "build/pushy.zib", output / parent_entry["bundle"])
    for child in editions:
        (output / child["bundle"]).unlink()
        if child["preview"] != parent_entry["preview"]:
            (output / child["preview"]).unlink()
    (output / "assets/apps/catalog.json").write_text(json.dumps(catalog, indent=2) + "\n")
    bundle("collection.zi", "collection:Main", output / "assets", ROOT / "build/arcade.zib")
    receipt = dict(id=COLLECTION_ID, version=(ROOT / "VERSION").read_text().strip(),
                   sha256=digest(ROOT / "build/arcade.zib"),
                   apps_sha256=args.apps_sha256, children=catalog["children"],
                   source_mode="project")
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    (ROOT / "build/arcade.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("Arcade collection built with unchanged game bundles and verified Apps controller")


if __name__ == "__main__":
    main()
