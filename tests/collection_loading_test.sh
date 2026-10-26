#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
mkdir -p build/collection-loading-test
./scripts/ziran.sh bundle --project --root "$root" \
    --entry collection_loading_behavior:Check \
    -o build/collection-loading-test/test.zx tests/collection_loading_behavior.zi
test "$(./scripts/ziran.sh run build/collection-loading-test/test.zx)" = 42
echo 'Local collection loading test: late image requests, consecutive ready frames and navigation'
