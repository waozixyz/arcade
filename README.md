# Arcade

Games and entertainment, alongside Werkzeug for practical tools and Inner
Breeze for personal growth. The first game is Chess.

Open Chess from the home screen, choose a side and one of three computer
levels, and play. The library uses preview cards in a responsive grid; the
top Back button returns from a game. A local game
survives returning to the library and restarting the app.

## One Chess app, two harnesses

Chess remains an installable app in Inner Breeze, where it also fits thoughtful
play and personal growth. Arcade owns its rules, computer opponent, screens,
assets, translations and release ledger at `apps/chess/`. Inbe consumes the
same signed package from its node. Both harnesses recognize `inbe.chess`.
The game's `catalog.json` declares its membership in both harnesses.

Arcade builds that source into a `.zib` and runs it through the same bounded
app and Kryon widget interface Inbe uses. The bundle contains its existing
piece images and translated Chess text. Arcade validates its game identity,
capabilities and resource paths before opening it.

This first version is a Linux desktop harness. Its games are local; Arcade
does not connect an account or provide friend-game transport. Inbe retains
its existing account sync and friend games. Arcade and Inbe keep separate
saved games; this version does not migrate or synchronize games between them.

## Build and run

Dependencies are Git repositories pinned in `ziran.lock`. The toolchain
wrapper uses the resolved compiler for both bundles and the host runtime.
Local development uses ignored `ziran.local.toml` overrides pointing to the
real source repositories. Without that file, package resolution uses the lock.

```sh
make
./build/arcade
./build/arcade --app chess
./build/arcade --list
make install
```

Desktop builds need SDL2, Cairo, FreeType, Fontconfig and Pango development
packages, a C compiler, Python 3 and Ziran. `make install` installs the command
and desktop-menu entry for the current user; it does not publish a release.
Harmony registry delivery and Android builds are not implemented in this first
desktop version.

Games are registered in `games.json`, which points to the owning package's
game descriptor. `scripts/build-games.py` generates the catalog and bundles
the owned game. Inbe remains a dependency for the existing shared interface
and signed publisher, rather than for the Chess implementation.

## Saved games

Each game has its own directory under `$XDG_DATA_HOME/arcade/games/`, or
`~/.local/share/arcade/games/`. Files are private, and only one process may
write a game's profile at a time. A game receives named records, not arbitrary
filesystem access. `ARCADE_DATA` chooses a disposable profile for tests.

## Checks

```sh
make test
make ui-test
make compatibility-test INBE_BINARY=/absolute/path/to/intended/inbe
```

The UI test scrubs the inherited desktop and runs on its own Xvfb display.
It opens Chess, plays a move, waits for the computer's legal response, checks
the rendered piece, returns through the library, restarts and verifies the
saved position. It also checks private file permissions and refuses a second
writer. Test screenshots and outputs stay in `build/ui-test/`.

The compatibility gate checks the exact bundle in both harnesses. See
[Game compatibility](docs/GAME_COMPATIBILITY.md) for the checked contract,
independent game versions, save compatibility and existing signed node
publisher. Both hosts must support the compiler's VM format. Local overrides
may use a newer format than released Inbe; their output must pass the
intended host before publication. Building or installing never publishes.
