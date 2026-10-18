#!/bin/sh
# Use the same toolchain for bundles and the native runtime.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
# A reviewed local Apps handoff supplies an explicit retained toolchain and
# import map. Resolve test package roots from that map, without refreshing a
# production lock or trying to fetch unpublished dependencies.
if [ -n "${TOOLCHAIN_SOURCE:-}" ] && [ -n "${APPS_SOURCE:-}" ]; then
    if [ "${1:-}" = pkg ] && [ "${2:-}" = path ]; then
        if [ "${3:-}" = ziran ]; then
            printf '%s\n' "$TOOLCHAIN_SOURCE"
            exit 0
        fi
        python3 - "$root/build/collection-source-check/module-map.tsv" "${3:-}" <<'PY'
from pathlib import Path
import sys
import tomllib
name = sys.argv[2].lower().replace('-', '').replace('_', '')
for row in Path(sys.argv[1]).read_text().splitlines():
    parts = row.split('\t')
    if parts[0] != 'P':
        continue
    path = Path(parts[2])
    manifest = path / 'ziran.toml'
    if manifest.exists():
        package = tomllib.loads(manifest.read_text())['package']['name']
        if package.lower().replace('-', '').replace('_', '') == name:
            print(path)
            raise SystemExit(0)
raise SystemExit('Package is absent from the explicit source map: ' + sys.argv[2])
PY
        exit $?
    fi
    exec env -u ZIRAN_PACKAGE_MAP "$TOOLCHAIN_SOURCE/build/bin/ziran" "$@"
fi
flags=--locked
if [ -f ziran.local.toml ]; then flags=; fi
tool_root=$(ziran pkg path ziran $flags)
compiler="$tool_root/build/bin/ziran"
if [ ! -x "$compiler" ]; then
    compiler="$root/build/toolchain/bin/ziran"
    env -u DISPLAY -u WAYLAND_DISPLAY -u XAUTHORITY -u DBUS_SESSION_BUS_ADDRESS \
        make -s -C "$tool_root" BUILD_DIR="$root/build/toolchain" all >&2
fi
exec "$compiler" "$@"
