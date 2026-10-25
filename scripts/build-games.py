#!/usr/bin/env python3
"""Build the apps Arcade and its game packages declare, without copying source."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path
from game_packages import declared_apps

ROOT = Path(__file__).resolve().parents[1]


def leave_out(rules_path, resources, release):
    """Removes what the game's bundle.json says its bundle leaves out (top-level
    glob patterns of its assets), so the collection and the games a host opens
    fit its memory budget; the manifest keeps only what remains."""
    rules = json.loads(rules_path.read_text()) if rules_path.exists() else {}
    patterns = rules.get("leave_out", []) + (rules.get("release_leave_out", []) if release else [])
    for pattern in patterns:
        for path in resources.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    art_path = resources / "art.json"
    if patterns and art_path.exists():
        art = json.loads(art_path.read_text())
        art["files"] = [item for item in art["files"] if (resources / item["path"]).is_file()]
        art_path.write_text(json.dumps(art, indent=2) + "\n")


def build(ziran, lock_flags):
    def package(name):
        return Path(subprocess.check_output(
            [ziran, "pkg", "path", name, *lock_flags], cwd=ROOT, text=True).strip())

    kryon = package("kryon")
    toolchain = package("ziran")
    entity = package("entity")
    entries = []
    for app in declared_apps(ROOT, ziran, lock_flags):
        source, manifest, descriptor = app["source"], app["manifest"], app["descriptor"]
        if descriptor["kind"] != "game" or "arcade" not in descriptor["harnesses"]:
            raise ValueError("Only games registered for Arcade belong in its catalog")
        name = descriptor["name"]
        if not name.isascii() or not name.replace("-", "").isalnum():
            raise ValueError("Invalid game name")
        staged = ROOT / "build/game-assets" / name
        # Start empty: files a game no longer has must not reach its bundle.
        shutil.rmtree(staged, ignore_errors=True)
        resources = staged / "assets" / name
        resources.mkdir(parents=True)
        shutil.copytree(source / descriptor["assets"], resources, dirs_exist_ok=True)
        shared = manifest.with_name("shared_assets.json")
        for copy in json.loads(shared.read_text())["copies"] if shared.exists() else []:
            asset_source, target = source / copy["from"], resources / copy["to"]
            target.parent.mkdir(parents=True, exist_ok=True)
            if asset_source.is_dir():
                shutil.copytree(asset_source, target)
            else:
                shutil.copyfile(asset_source, target)
        # Build flags are source metadata, not part of the signed node/2
        # descriptor schema accepted by existing hosts.
        (resources / 'catalog.json').write_text(json.dumps(
            {key: value for key, value in descriptor.items() if key != 'build_defines'}, indent=2) + '\n')
        defines = descriptor.get('build_defines', [])
        if 'SHOVEY_RELEASE' in defines:
            subprocess.run(["python3", str(source / 'scripts/release_assets.py'), str(resources)], check=True)
        leave_out(manifest.with_name("bundle.json"), resources, 'SHOVEY_RELEASE' in defines)
        locales = resources / "locales"
        locales.mkdir(exist_ok=True)
        translations = {}
        for locale in sorted((source / descriptor["locales"]).glob("*.txt")):
            blocks = []
            values = {}
            for block in locale.read_text().split("---\n"):
                lines = block.splitlines()
                heading = next((line for line in lines if line), "")
                if heading.startswith("[" + descriptor["locale_prefix"]):
                    blocks.append(heading + "\n" + "\n".join(lines[lines.index(heading) + 1:]).rstrip() + "\n---\n")
                    values[heading[1:-1]] = "\n".join(lines[lines.index(heading) + 1:]).rstrip()
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
        bundle = ROOT / "build/games" / (name + ".zx")
        bundle.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            ziran, "bundle", "--root", str(source),
            # Game packages without a src folder (Shovey) keep sources beside their catalogs.
            *(["--module-path", str(source / "src")] if (source / "src").is_dir() else []),
            "--module-path", str(generated),
            "--module-path", str(kryon / "src/ui"),
            "--module-path", "kryon=" + str(kryon / "src/ui"),
            "--module-path", "kryon=" + str(kryon / "src/backend"),
            "--module-path", "std=" + str(toolchain / "std"),
            "--module-path", str(toolchain / "std"),
            "--module-path", "apps=" + str(package("apps") / "src"),
            "--module-path", "mingcute=" + str(package("mingcute") / "src"),
            "--module-path", "entity=" + str(entity / "src"),
            *[flag for name in defines for flag in ('--define', name)],
            "--define", "KRYON_HOSTED_UI", "--asset-dir", "assets=" + str(staged / "assets"),
            "--entry", descriptor["entry"], "-o", str(bundle),
            str(source / descriptor["source"])], cwd=ROOT, check=True)
        preview = ROOT / "build/games" / (name + "-preview.png")
        shutil.copyfile(source / descriptor["preview"], preview)
        entries.append(descriptor | {"enabled": app["enabled"], "package": app["package"]})
    if not entries or len(entries) > 16 or len({entry["id"] for entry in entries}) != len(entries):
        raise ValueError("Arcade needs 1 to 16 distinct games")
    text = ("// Generated from the apps.json of Arcade and its game packages.\n"
            "Game :: struct {\n    id: string\n    name: string\n    title: string\n    bundle: string\n    preview: string\n    package: string\n    enabled: bool\n}\n\n"
            f"GameCount :: {len(entries)}\n\nGameAt :: (index: s32) -> Game {{\n")
    for index, entry in enumerate(entries):
        fields = ", ".join("." + field + " = " + json.dumps(value, ensure_ascii=False)
                           for field, value in [("id", entry["id"]), ("name", entry["name"]),
                                                ("title", entry["title"]), ("bundle", entry["name"] + ".zx"),
                                                ("preview", entry["name"] + "-preview.png"), ("package", entry["package"])])
        fields += ", .enabled = " + str(entry["enabled"]).lower()
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
