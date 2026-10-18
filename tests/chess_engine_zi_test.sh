#!/bin/sh
set -eu

# Chess rules and computer opponent as native code: perft counts of the
# standard positions, notation, draw rules and search answers.
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ziran=${1:-"$root/scripts/ziran.sh"}
toolchain=$("$ziran" pkg path ziran)
work=$root/build/chess-engine-zi-test
include="$toolchain/include"
unset DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS
rm -rf "$work"
mkdir -p "$work/c"
"$ziran" build --target=c --no-main --entry chess_engine_behavior:Check --root "$root/tests" \
    --module-path "$toolchain/std" -o "$work/c" "$root/tests/chess_engine_behavior.zi"
cat > "$work/c/main.c" <<'C'
#include <stdio.h>
#include "chess_engine_behavior.h"
int main(void)
{
    int result = Check();
    if (result != 0) fprintf(stderr, "chess engine check %d failed\n", result);
    return result == 0 ? 0 : 1;
}
C
# Modules imported by file keep their directories in the generated C.
includes=$(find "$work/c" -type d -printf ' -iquote %p')
# shellcheck disable=SC2046,SC2086
"${CC:-cc}" -std=c11 -O2 -I"$include" $includes $(find "$work/c" -name '*.c') -o "$work/test"
env -u DISPLAY -u WAYLAND_DISPLAY "$work/test"
echo "chess engine Ziran test passed"
