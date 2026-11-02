#!/usr/bin/env python3
"""Pack the apps Arcade and its game packages declare, unchanged, with the
shared Apps controller."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
from game_packages import declared_packages
from node_config import node_source

ROOT = Path(__file__).resolve().parents[1]
MAX_PAYLOAD_BYTES = 64 * 1024 * 1024
MAX_GAMES = 16


def payload_limit(size, label):
    if size > MAX_PAYLOAD_BYTES:
        raise ValueError(f"{label} exceeds the host's payload limit")


def catalog_bytes(catalog):
    return (json.dumps(catalog, indent=2) + "\n").encode()


def child_paths(child):
    return [child["bundle"], child["preview"], *(
        value for key, value in child.get("cover", {}).items()
        if key in ("portrait", "landscape", "logo"))]


def package_catalog(package, children):
    return dict(schema=1, id=package["id"], title=package["title"],
                harness="assets/apps/apps.zx", children=children)


def bundle(command, root, source, entry, assets, target, env):
    """Check the complete ZX (including code/index overhead) before promotion."""
    work = root / "work"
    subprocess.run(["git", "check-ignore", "-q", "work/"], cwd=root, check=True)
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="collection-bundle-", dir=work) as directory:
        candidate = Path(directory) / target.name
        subprocess.run([*command, "--root", str(root / "src"), "--entry", entry,
            "--asset-dir", "assets=" + str(assets), "-o", str(candidate),
            str(root / "src" / source)], cwd=root, env=env, check=True)
        payload_limit(candidate.stat().st_size, target.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        candidate.replace(target)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def catalog_version(root):
    """The node receipt must name the synchronized catalog release."""
    version = (root / "catalog/VERSION").read_text().strip()
    component = json.loads((root / "apps/versions.json").read_text())["node_apps"]["arcade"]
    if (not re.fullmatch(r"\d+\.\d+\.\d+", version)
            or component["id"] != "inbe.arcade" or component["version"] != version):
        raise ValueError("Catalog version differs from its signed release ledger; run update_version.sh --catalog")
    return version


def library_art(root, name, key, source):
    """Arcade's committed library thumbnail (scripts/library-art.py), as
    (bytes, suffix): a PNG, or a JPEG for opaque cover art. Never pack a copy
    of outdated art."""
    library = Path(root) / "assets/arcade/library"
    sources = json.loads((library / "sources.json").read_text())
    copy = f"{name}-{key}"
    if sources.get(copy, {}).get("source_sha256") != hashlib.sha256(source).hexdigest():
        raise ValueError(f"{copy} art changed; run scripts/library-art.py")
    for suffix in (".png", ".jpg"):
        if (library / (copy + suffix)).is_file():
            return (library / (copy + suffix)).read_bytes(), suffix
    raise ValueError(f"{copy} has no library copy; run scripts/library-art.py")


def stage(root, controller, expected_controller_digest, output):
    """Validate before replacing a previously staged collection. Returns the
    catalog and each game package with the IDs of its packed apps."""
    if not re.fullmatch(r"[0-9a-f]{64}", expected_controller_digest):
        raise ValueError("An exact trusted Apps controller SHA-256 is required")
    payload_limit(controller.stat().st_size, "Apps controller")
    controller_bytes = controller.read_bytes()
    controller_digest = hashlib.sha256(controller_bytes).hexdigest()
    if controller_digest != expected_controller_digest:
        raise ValueError(f"Apps controller differs from the trusted SHA-256: {controller_digest} != {expected_controller_digest}")
    payload_limit(len(controller_bytes), "Apps controller")
    lock_flags = () if (root / "ziran.local.toml").is_file() else ("--locked",)
    packages = declared_packages(root, lock_flags=lock_flags)
    arcade = packages[0]
    if not 1 <= sum(len(package["apps"]) for package in packages) <= MAX_GAMES:
        raise ValueError("Arcade needs 1 to 16 games")
    ledger = json.loads((root / "apps/versions.json").read_text())["node_apps"]
    children, copies, identities = [], [], set()
    collection_ids = {package["id"] for package in packages}
    for package in packages:
        package["children"] = []
        for app in package["apps"]:
            if not app["enabled"]:
                continue
            game = app["descriptor"]
            name, identifier = game["name"], game["id"]
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
                raise ValueError("Invalid game name")
            if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", identifier) or len(identifier) >= 128:
                raise ValueError("Invalid game identity")
            if identifier in identities or identifier in collection_ids:
                raise ValueError("Duplicate or recursive game identity")
            identities.add(identifier)
            component = ledger[name]
            if (component["id"] != identifier or game["kind"] != "game"
                    or "arcade" not in game["harnesses"]
                    or game["contract_version"] != 1 or game["module_api"] != 2
                    or game["host_api"] != component["host_api"]):
                raise ValueError("Incompatible game descriptor or version ledger")
            bundle = root / "build/games" / (name + ".zx")
            preview = root / "build/games" / (name + "-preview.png")
            # The game build embeds this exact legacy descriptor. Its verified
            # name binds node/2's legacy handshake to the stable signed app ID.
            payload_limit(bundle.stat().st_size, f"Game {name}")
            bundle_bytes, preview_bytes = bundle.read_bytes(), preview.read_bytes()
            if not bundle_bytes or not preview_bytes:
                raise ValueError("Game bundles and previews must be built first")
            payload_limit(len(bundle_bytes), f"Game {name}")
            preview_bytes, preview_suffix = library_art(root, name, "preview",
                (app["art_source"] / game["preview"]).read_bytes())
            child = dict(
                id=identifier, title=game["title"],
                bundle=f"assets/arcade/games/{name}.zx", protocol="node/2",
                expected_id=name, version=component["version"],
                sha256=hashlib.sha256(bundle_bytes).hexdigest(),
                bytes=len(bundle_bytes),
                preview=f"assets/arcade/previews/{name}{preview_suffix}",
                icon=f"assets/arcade/previews/{name}{preview_suffix}")
            # A thin add-on links its required games' verified code as libraries.
            if app.get('shared_code'):
                child['shared_code'] = True
            if app.get('shared_records'):
                child['shared_records'] = app['shared_records']
            if app.get('requires'):
                shared = json.loads((root / 'build/games' / (name + '-resources.json')).read_text())
                if shared['dependencies'] != app['requires']:
                    raise ValueError('Game resource dependencies differ from its manifest')
                child['dependencies'] = shared['dependencies']
                if shared['resources']:
                    child['resources'] = shared['resources']
            # The package's declared cover: the library opens the app from it.
            cover = app["cover"]
            if cover:
                packed_cover = {key: cover[key] for key in ("caption", "action") if key in cover}
                for key in ("portrait", "landscape", "logo"):
                    if key not in cover:
                        continue
                    relative = Path(cover[key])
                    if relative.is_absolute() or ".." in relative.parts or relative.suffix not in {".png", ".jpg"}:
                        raise ValueError("Invalid cover asset path")
                    contents, suffix = library_art(root, name, key, (app["art_source"] / relative).read_bytes())
                    destination = Path("arcade/covers") / f"{name}-{key}{suffix}"
                    packed_cover[key] = "assets/" + destination.as_posix()
                    copies.append((contents, destination))
                child["cover"] = packed_cover
            children.append(child)
            package["children"].append(identifier)
            copies += [(bundle_bytes, Path("arcade/games") / (name + ".zx")),
                       (preview_bytes, Path("arcade/previews") / (name + preview_suffix))]
    catalog = dict(schema=1, id=arcade["id"], title=arcade["title"],
                   harness="assets/apps/apps.zx", presentation={"mode": "covers"}, children=children)
    sidebar = (root / "assets/arcade/sidebar.shape").read_bytes()
    # The stage is a source for several independently loaded roots, not one
    # root containing the whole library. Bound their input bytes separately;
    # bundle() also checks the final compiled sizes, including ZX overhead.
    payloads = {"assets/" + path.as_posix(): data for data, path in copies}
    art_paths = {path for child in children for path in child_paths(child)[1:]}
    payload_limit(sum(len(payloads[path]) for path in art_paths), "Library art")
    payload_limit(len(catalog_bytes(catalog)) + len(sidebar), "Arcade catalog")
    for package in packages[1:]:
        if not (root / "src" / f"{package['name']}_collection.zi").is_file():
            continue
        leaves = [child for child in children if child["id"] in package["children"]]
        if not leaves:
            raise ValueError(f"{package['name']} declares no enabled apps")
        paths = {path for child in leaves for path in child_paths(child)}
        size = (len(controller_bytes) + len(catalog_bytes(package_catalog(package, leaves)))
                + sum(len(payloads[path]) for path in paths))
        payload_limit(size, f"Standalone {package['name']}")
    # This stable directory contains disposable build output only. Clear it
    # after all inputs validate so removed registrations cannot linger.
    if output.exists():
        shutil.rmtree(output)
    assets = output / "assets"
    (assets / "apps").mkdir(parents=True)
    (assets / "apps/apps.zx").write_bytes(controller_bytes)
    (assets / "apps/catalog.json").write_bytes(catalog_bytes(catalog))
    for contents, relative in copies:
        destination = assets / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents)
    # Inbe draws Arcade's launcher icon from assets/arcade/sidebar.shape.
    (assets / "arcade").mkdir(exist_ok=True)
    (assets / "arcade/sidebar.shape").write_bytes(sidebar)
    return catalog, packages[1:]


def stage_downloads(catalog, source, output, games, art):
    """Keep only Arcade's catalog; serve each game and the library art separately.

    The published Arcade is a launcher: the host supplies the shared Apps
    controller, and the games' covers and previews go to ART for one separate
    download. The full staging directory is also used by standalone players,
    which keep their bundled games, art and controller. Validate every game
    before replacing outputs.
    """
    payloads = {}
    for child in catalog["children"]:
        data = (source / child["bundle"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != child["sha256"]:
            raise ValueError("Game differs from the collection's declared digest")
        payload_limit(len(data), f"Game {child['id']}")
        payloads[child["sha256"]] = data
    for directory in (output, games, art):
        if directory.exists():
            shutil.rmtree(directory)
    shutil.copytree(source, output)
    games.mkdir(parents=True)
    (output / catalog["harness"]).unlink()
    for child in catalog["children"]:
        (output / child["bundle"]).unlink()
        pictures = [child["preview"]] + [path for key, path in child.get("cover", {}).items()
                                         if key in ("portrait", "landscape", "logo")]
        for relative in pictures:
            if not (output / relative).exists():
                continue
            destination = art / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(output / relative, destination)
    for digest, data in payloads.items():
        (games / (digest + ".zx")).write_bytes(data)


def add_art(output, games, art_bundle):
    """Publish the art bundle beside the games and name it in the catalog."""
    data = art_bundle.read_bytes()
    payload_limit(len(data), "Library art bundle")
    digest = hashlib.sha256(data).hexdigest()
    (games / (digest + ".zx")).write_bytes(data)
    path = output / "assets/apps/catalog.json"
    catalog = json.loads(path.read_text())
    catalog["art"] = dict(sha256=digest, bytes=len(data))
    path.write_text(json.dumps(catalog, indent=2) + "\n")
    return catalog["art"]


def archive_downloads(games, archive):
    """The release asset contains only the immutable game payloads."""
    with tarfile.open(archive, "w") as output:
        for path in sorted(games.glob("*.zx")):
            entry = tarfile.TarInfo(path.name)
            entry.size = path.stat().st_size
            entry.mode = 0o644
            with path.open("rb") as data:
                output.addfile(entry, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ziran", default=str(ROOT / "scripts/ziran.sh"))
    parser.add_argument("--locked", action="store_true")
    parser.add_argument("--apps-bundle", type=Path, required=True)
    parser.add_argument("--apps-sha256", required=True)
    args = parser.parse_args()
    version = catalog_version(ROOT)
    output = ROOT / "build/collection"
    catalog, packages = stage(ROOT, args.apps_bundle, args.apps_sha256, output)
    command = [args.ziran, "bundle", "--project", *(["--locked"] if args.locked else [])]
    env = os.environ.copy()

    # A game package with a standalone player (src/NAME_collection.zi) also
    # gets its own collection of exactly the leaves Arcade packs, with their
    # independent verified IDs; it takes its first app's version.
    for package in packages:
        name = package["name"]
        if not (ROOT / "src" / f"{name}_collection.zi").is_file():
            continue
        children = [child for child in catalog["children"] if child["id"] in package["children"]]
        if not children:
            raise ValueError(f"{name} declares no enabled apps")
        standalone = ROOT / f"build/{name}-collection"
        if standalone.exists():
            shutil.rmtree(standalone)
        assets = standalone / "assets"
        (assets / "apps").mkdir(parents=True)
        shutil.copyfile(output / "assets/apps/apps.zx", assets / "apps/apps.zx")
        standalone_catalog = package_catalog(package, children)
        (assets / "apps/catalog.json").write_bytes(catalog_bytes(standalone_catalog))
        for child in children:
            for relative in child_paths(child):
                destination = standalone / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(output / relative, destination)
        bundle(command, ROOT, f"{name}_collection.zi", f"{name}_collection:Main",
               assets, ROOT / f"build/{name}.zx", env)
        metadata = dict(id=package["id"], version=children[0]["version"],
            sha256=digest(ROOT / f"build/{name}.zx"), apps_sha256=args.apps_sha256,
            children=children, source_mode="project")
        (ROOT / f"build/{name}.json").write_text(json.dumps(metadata, indent=2) + "\n")
    # Arcade carries only its catalog. Standalone players keep their offline
    # games; Arcade downloads the library art once and exactly the game the
    # person selects.
    node_apps = ROOT / "build/node-apps"
    catalog_assets = node_apps / "arcade-catalog"
    game_downloads = node_apps / "arcade.games"
    art_assets = node_apps / "arcade-art"
    stage_downloads(catalog, output, catalog_assets, game_downloads, art_assets)
    bundle(command, ROOT, "art.zi", "art:Main", art_assets / "assets", node_apps / "arcade-art.zx", env)
    art = add_art(catalog_assets, game_downloads, node_apps / "arcade-art.zx")
    archive_downloads(game_downloads, node_apps / "arcade.games.tar")
    bundle(command, ROOT, "collection.zi", "collection:Main", catalog_assets / "assets", node_apps / "arcade.zx", env)
    shutil.copyfile(node_apps / "arcade.zx", ROOT / "build/arcade.zx")
    # The desktop host supplies its controller from beside the collection.
    shutil.copyfile(args.apps_bundle, ROOT / "build/apps.zx")
    receipt = dict(id=catalog["id"], version=version,
                   sha256=digest(ROOT / "build/arcade.zx"),
                   apps_sha256=args.apps_sha256, children=catalog["children"], art=art,
                   source_mode="project", node=node_source(ROOT))
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    (ROOT / "build/arcade.json").write_text(json.dumps(receipt, indent=2) + "\n")
    node_receipt = receipt | {"sha256": digest(node_apps / "arcade.zx")}
    (node_apps / "arcade.json").write_text(json.dumps(node_receipt, indent=2) + "\n")
    print("Arcade catalog built with separate unchanged game downloads; standalone players keep their games")


if __name__ == "__main__":
    main()
