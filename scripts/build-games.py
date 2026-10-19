#!/usr/bin/env python3
"""Build registered games from their owning Ziran packages, without copying source."""
import argparse
import os
import json
import shutil
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(ziran, lock_flags, module_map=None, compiler_dir=None):
    rows = module_map.read_text().splitlines() if module_map else []
    def package(name):
        if module_map:
            if name == 'ziran':
                return compiler_dir.parent.parent
            identity = next((row.split('\t')[3] for row in rows
                             if row.startswith('D\troot\t' + name + '/')), None)
            if identity:
                return Path(next(row.split('\t')[2] for row in rows
                                 if row.startswith('P\t' + identity + '\t')))
            # Packages without exports, such as Pushy, are found by name.
            for row in rows:
                fields = row.split('\t')
                manifest = Path(fields[2]) / 'ziran.toml' if fields[0] == 'P' else None
                if manifest and manifest.exists() and \
                        tomllib.loads(manifest.read_text())['package']['name'].lower() == name:
                    return Path(fields[2])
            raise ValueError('Package is absent from the source map: ' + name)
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
        translations = {}
        for locale in sorted((source / descriptor["locales"]).glob("*.txt")):
            blocks = []
            values = {}
            for block in locale.read_text().split("---\n"):
                lines = block.splitlines()
                if lines and lines[0].startswith("[" + descriptor["locale_prefix"]):
                    blocks.append(block.rstrip() + "\n---\n")
                    values[lines[0][1:-1]] = "\n".join(lines[1:]).rstrip()
            (locales / locale.name).write_text("".join(blocks))
            translations[locale.stem] = values
        # Text also lives in the game itself: released legacy hosts only know
        # their own locale file and cannot provide newly added game strings.
        generated = ROOT / 'build/game-generated' / name
        generated.mkdir(parents=True, exist_ok=True)
        code = 'GameLocaleText :: (language: string, key: string) -> string {\n'
        for language, values in sorted(translations.items(), key=lambda item: item[0] == 'en'):
            if language != 'en':
                code += '    if language == ' + json.dumps(language) + ' {\n'
            for key, value in values.items():
                code += ('        ' if language != 'en' else '    ') + 'if key == ' + json.dumps(key) + ' { return ' + json.dumps(value, ensure_ascii=False) + ' }\n'
            if language != 'en':
                code += '    }\n'
        code += '    return ""\n}\n'
        (generated / 'translations.zi').write_text(code)
        bundle = ROOT / "build/games" / (name + ".zib")
        bundle.parent.mkdir(parents=True, exist_ok=True)
        command = [ziran, "bundle"]
        env = os.environ.copy()
        if module_map:
            # Game source still uses its established node/2 named module
            # paths. It does not import Apps; an Apps root map would combine
            # unrelated legacy game module basenames such as engine/progress.
            env.pop('ZIRAN_PACKAGE_MAP', None)
            command = [str(compiler_dir / 'zi2zib'), 'bundle']
        subprocess.run([
            *command, "--root", str(source),
            "--module-path", str(source / "src"),
            "--module-path", str(generated),
            "--module-path", str(kryon / "src/ui"),
            "--module-path", "kryon=" + str(kryon / "src/ui"),
            "--module-path", "kryon=" + str(kryon / "src/backend"),
            "--module-path", "std=" + str(toolchain / "std"),
            "--module-path", str(toolchain / "std"),
            "--module-path", "apps=" + str(package("apps") / "src"),
            "--define", "KRYON_HOSTED_UI", "--asset-dir", "assets=" + str(staged / "assets"),
            "--entry", descriptor["entry"], "-o", str(bundle),
            str(source / descriptor["source"])], cwd=ROOT, env=env, check=True)
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
    parser.add_argument('--module-map', type=Path)
    parser.add_argument('--compiler-dir', type=Path)
    args = parser.parse_args()
    if bool(args.module_map) != bool(args.compiler_dir):
        parser.error('--module-map and --compiler-dir must be supplied together')
    build(args.ziran, ["--locked"] if args.locked else [], args.module_map, args.compiler_dir)
