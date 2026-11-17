# Arcade on the released graph — open work

- The raylib-free lane left uncommitted native work in this checkout: Ziran
  515449986e40, Kryon 028d42cb157a, and changes to the Android, packaging,
  app, main, sound and Windows sources, the game-updates workflow, the
  README, `mk/` and the game-update commit script and test. It builds on
  newer Ziran and Kryon than the graph the catalog now uses (Ziran 0.6.0
  d17c7aa1, Kryon 1b290f19, Apps 7854da88). Move those pins onto that graph,
  or onto a new Ziran release, before committing that work.
- `scripts/android_catalog.py` reads only the ZX 26 and 27 bundle layout, so
  `tests/android_catalog_test.py` rejects the ZX 28 catalog. Read the seed
  catalog's assets through the Ziran runtime, as `build/zx-metadata` reads
  their index, before the next Android host release.
