#!/bin/sh
set -eu

# Chess from its real package in the portable VM: a game against the
# computer that survives a restart, and a game between two friends through
# a fake node that keeps shared records as Daochi's shared lists do.
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ziran=${1:-"$root/scripts/ziran.sh"}
apps=$("$ziran" pkg path apps)
kryon=$("$ziran" pkg path kryon)
toolchain=$("$ziran" pkg path ziran)
work=${CHESS_APP_TEST_DIR:-"$root/build/chess-app-test"}
unset DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS
rm -rf "$work"
mkdir -p "$work/c"
cp "$root/build/games/chess.zib" "$work/chess.zib"
"$ziran" build --target=c --no-main --entry chess_app_behavior:main --root "$root/tests" \
    --module-path "$root/src" --module-path "apps=$apps/src" \
    --module-path "$root/build/game-generated/chess" \
    --module-path "$kryon/src/backend" --module-path "$kryon/src/ui" \
    --module-path "$toolchain/std" -o "$work/c" "$root/tests/chess_app_behavior.zi"
# Modules imported by file keep their directories in the generated C.
includes=$(find "$work/c" -type d -printf ' -iquote %p')
# shellcheck disable=SC2046,SC2086
"${CC:-cc}" -O1 -std=c11 -ffunction-sections -fdata-sections $includes -I"$toolchain/include" \
    $(find "$work/c" -name '*.c') "${ZIRAN_LIB:-$root/build/ziran/libziran.a}" \
    -Wl,--gc-sections -lm -lpthread -o "$work/run"
(cd "$work" && ./run) || {
    echo "chess app check $? failed" >&2
    exit 1
}
echo "Chess plays the computer, restores its game and plays a friend through shared records"
