#!/usr/bin/env python3
"""Build registered games from their owning Ziran packages, without copying source."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(ziran, lock_flags):
    def package(name):
        return Path(subprocess.check_output(
            [ziran, "pkg", "path", name, *lock_flags], cwd=ROOT, text=True).strip())

    kryon = package("kryon")
    toolchain = package("ziran")
    entries = []
    for registration in json.loads((ROOT / "games.json").read_text())["games"]:
        source = ROOT if registration["package"] == "self" else package(registration["package"])
        descriptor = json.loads((source / registration["manifest"]).read_text())
        if descriptor["kind"] != "game" or "arcade" not in descriptor["harnesses"]:
            raise ValueError("Only games registered for Arcade belong in its catalog")
        name = descriptor["name"]
        if not name.isascii() or not name.replace("-", "").isalnum():
            raise ValueError("Invalid game name")
        staged = ROOT / "build/game-assets" / name
        resources = staged / "assets" / name
        resources.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source / descriptor["assets"], resources, dirs_exist_ok=True)
        shutil.copyfile(source / registration["manifest"], resources / "catalog.json")
        locales = resources / "locales"
        locales.mkdir(exist_ok=True)
        for locale in sorted((source / descriptor["locales"]).glob("*.txt")):
            blocks = []
            for block in locale.read_text().split("---\n"):
                lines = block.splitlines()
                if lines and lines[0].startswith("[" + descriptor["locale_prefix"]):
                    blocks.append(block.rstrip() + "\n---\n")
            (locales / locale.name).write_text("".join(blocks))
        bundle = ROOT / "build/games" / (name + ".zib")
        bundle.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            ziran, "bundle", "--root", str(source),
            "--module-path", str(source / "src"),
            "--module-path", str(kryon / "src/ui"),
            "--module-path", str(toolchain / "std"),
            "--module-path", "inbe=" + str(package("inbe") / "src/cells"),
            "--define", "KRYON_HOSTED_UI", "--asset-dir", "assets=" + str(staged / "assets"),
            "--entry", descriptor["entry"], "-o", str(bundle),
            str(source / descriptor["source"])], cwd=ROOT, check=True)
        preview = ROOT / "build/games" / (name + "-preview.png")
        shutil.copyfile(source / descriptor["preview"], preview)
        entries.append(descriptor)
    if not entries or len(entries) > 16 or len({entry["id"] for entry in entries}) != len(entries):
        raise ValueError("Arcade needs 1 to 16 distinct games")
    text = ("// Generated from games.json and the owning packages' game catalogs.\n"
            "Game :: struct {\n    id: string\n    name: string\n    title: string\n    bundle: string\n    preview: string\n}\n\n"
            f"GameCount :: {len(entries)}\n\nGameAt :: (index: s32) -> Game {{\n")
    for index, entry in enumerate(entries):
        fields = ", ".join("." + field + " = " + json.dumps(value, ensure_ascii=False)
                           for field, value in [("id", entry["id"]), ("name", entry["name"]),
                                                ("title", entry["title"]), ("bundle", entry["name"] + ".zib"),
                                                ("preview", entry["name"] + "-preview.png")])
        text += f"    if index == {index} {{ return Game.{{{fields}}} }}\n"
    text += "    return Game.{}\n}\n"
    (ROOT / "src/catalog.zi").write_text(text)
    (ROOT / "build/catalog.json").write_text(json.dumps({"games": entries}, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ziran", default="ziran")
    parser.add_argument("--locked", action="store_true")
    args = parser.parse_args()
    build(args.ziran, ["--locked"] if args.locked else [])
