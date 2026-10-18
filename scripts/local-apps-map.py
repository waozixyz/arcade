#!/usr/bin/env python3
"""Build an explicit local consumer import map without inventing an Apps pin.

This is for source-handoff checks while Apps has no published Git source.
It leaves manifests/locks unchanged and is not a release dependency graph.
"""
import argparse
from pathlib import Path
import tomllib
import re


def build(consumer, apps, output):
    lines = (consumer / "build/.ziran/module-map.tsv").read_text().splitlines()
    # These checks deliberately use Apps' retained IR55 compiler and std,
    # even when the consumer has an ignored newer local toolchain override.
    lines = [row for row in lines if not row.startswith(("P\tstd\t", "M\tstd\t"))]
    package = "p0000000000000001"
    owned_paths = {row.split("\t")[1]: row.split("\t")[2]
                   for row in lines if row.startswith("P\t")}
    app_map = (apps / "build/.ziran/module-map.tsv").read_text().splitlines()
    for row in app_map:
        fields = row.split("\t")
        if len(fields) > 1 and fields[1] == "root":
            fields[1] = package
        if fields[0] == "P":
            previous = owned_paths.get(fields[1])
            if previous and previous != fields[2]:
                raise ValueError("Consumer and Apps map dependency " + fields[1] + " to different source roots")
            owned_paths[fields[1]] = fields[2]
        lines.append("\t".join(fields))
    manifest = tomllib.loads((consumer / "ziran.toml").read_text())
    roots = list(manifest["package"].get("module_roots", ["src"]))
    if (consumer / "apps").is_dir():
        roots.append("apps")
    # File imports need one module identity per physical source, including
    # games that legitimately each own engine.zi/view.zi. Basename collisions
    # must not silently compile Chess's engine for Pushy (or vice versa).
    names = {}
    paths = {}
    for row in lines:
        fields = row.split("\t")
        if fields[:2] == ["M", "root"]:
            names[fields[2]] = fields[3]
            paths[fields[3]] = fields[2]
    for module_root in roots:
        for path in sorted((consumer / module_root).rglob("*.zi")):
            if str(path) in paths:
                continue
            name = path.stem
            if name in names and names[name] != str(path):
                name = re.sub(r"[^a-zA-Z0-9_]", "_", str(path.relative_to(consumer).with_suffix("")))
            if name in names and names[name] != str(path):
                raise ValueError("Ambiguous local module: " + name)
            lines.append(f"M\troot\t{name}\t{path}")
            names[name] = str(path)
            paths[str(path)] = name
    app_manifest = tomllib.loads((apps / "ziran.toml").read_text())
    for name, filename in app_manifest["exports"].items():
        lines.append(f"D\troot\tapps/{name}\t{package}\t{Path(filename).stem}")
    # Refresh newly committed upstream exports from the same source roots;
    # package identities and all existing dependency revisions stay unchanged.
    modules = {}
    for row in lines:
        fields = row.split("\t")
        if fields[0] == "M":
            modules[(fields[1], fields[3])] = fields[2]
    kryon = next((identity, Path(path)) for identity, path in owned_paths.items()
                 if identity not in {"root", package, "std"}
                 and (Path(path) / "ziran.toml").exists()
                 and tomllib.loads((Path(path) / "ziran.toml").read_text())["package"]["name"].lower() == "kryon")
    identity, source = kryon
    # Inbe still builds its host with plain Kryon module paths. Preserve that
    # existing short-import surface while Apps uses declared package exports.
    root_names = {row.split("\t")[2] for row in lines
                  if row.startswith(("M\troot\t", "D\troot\t", "A\troot\t"))}
    for row in list(lines):
        fields = row.split("\t")
        if fields[0] == "M" and fields[1] not in {"root", package, "std"} and fields[2] not in root_names:
            lines.append(f"D\troot\t{fields[2]}\t{fields[1]}\t{fields[2]}")
            root_names.add(fields[2])
    for owner in ("root", package):
        for name, filename in tomllib.loads((source / "ziran.toml").read_text())["exports"].items():
            module = modules.get((identity, str(source / filename)))
            if module:
                lines.append(f"D\t{owner}\tkryon/{name}\t{identity}\t{module}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(dict.fromkeys(lines)) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consumer", type=Path, required=True)
    parser.add_argument("--apps", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.consumer.resolve(), args.apps.resolve(), args.output.resolve())
    print("Local Apps consumer map prepared; production manifests and locks unchanged")


if __name__ == "__main__":
    main()
