#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 - <<'PY'
from pathlib import Path
import re
version = re.search(r'^## (\d+\.\d+\.\d+)\s*$', Path('CHANGELOG.md').read_text(), re.M)
if version is None:
    raise SystemExit('CHANGELOG.md needs a numeric release entry')
Path('VERSION').write_text(version[1] + '\n')
PY
