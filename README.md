# Arcade

Games and entertainment, alongside Werkzeug for practical tools and Inner
Breeze for personal growth. The library includes Chess and Pushy. Pushy opens
an edition chooser for Classic and Island, and also runs as its own desktop app.
Each edition has a separate save and earned unlocks. Unlocked puzzles show
their whole board; locked puzzles keep their lock until earned.

Open Chess from the home screen, choose a side and one of four computer
levels, and play. The library uses preview cards in a responsive grid; the
top Back button returns from a game. A local game
survives returning to the library and restarting the app. Ask for a hint, take
back a complete turn, or flip the board. Expert searches more deeply without
added evaluation noise; it has no claimed Elo rating.

The Study tab keeps a separate board: step through algebraic move history,
try a different continuation, and analyze a position with an evaluation bar,
best move and completed search depth. Copy the game as PGN or the displayed
position as FEN. Study never overwrites the saved computer game. Analysis and
hints are available for computer play and study, rather than active friend
games. In Notation, choose Import to paste one PGN game or FEN position.
PGN imports keep the main line and standard game details; comments and side
variations are skipped. Custom starting positions keep their side and move
number. A failed or canceled import preserves the previous study. Studies
stay available while switching tabs during the same session.

Clocked games, puzzles, lessons, public matchmaking and automated full-game
review are not implemented.

## Shared Apps library

Arcade embeds the shared `apps.zib` controller and exact game bundles in a
verified collection. Pushy's edition collection is both the standalone payload
and the same nested child inside Arcade. Preview cards open directly; their
vertical options menu can mark an app installed or favorite without deleting
its saves. The local player does not offer node updates or OS actions it
cannot perform. Inbe supplies its own account and package policy.
Arcade's launcher icon is MingCute's `game_2` gamepad (Apache-2.0).

## One Chess game

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

Apps is an ordinary dependency. `make` builds the shared Apps controller
from the locked Apps package and accepts it only when its digest matches the
reviewed one in `apps-controller.sha256`:

```sh
make
./build/arcade
./build/arcade --app chess
./build/arcade --app pushy
./build/arcade --list
./build/pushy
```

`make install` installs both commands and desktop entries.

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
make standalone-ui-test
make collection-ui-test
make inbe-ui-test INBE_BINARY=/absolute/path/to/intended/inbe
make compatibility-test INBE_BINARY=/absolute/path/to/intended/inbe
```

The UI test scrubs the inherited desktop and runs on its own Xvfb display.
It opens Chess, plays a move, waits for the computer's legal response, checks
the rendered piece, returns through the library, restarts and verifies the
saved position. It checks hints, study variations, bounded analysis, actual
PGN/FEN clipboard contents, board flipping, complete-turn takebacks, a Black
opening and an Expert response. It also checks private file permissions and
refuses a second writer. Test screenshots and outputs stay in `build/ui-test/`.

The Inbe UI check exercises hints, study, analysis, native PGN/FEN copying
and takebacks at a narrow window size. The compatibility gate checks the
exact bundle in both harnesses. See
[Game compatibility](docs/GAME_COMPATIBILITY.md) for the checked contract,
independent game versions, save compatibility and existing signed node
publisher. Both hosts must support the compiler's VM format. Local overrides
must preserve a compatible VM format; the toolchain is pinned to the IR55
compiler used by the compatible Inbe hosts. Each output must pass the
intended host before publication. A released API 12+ Inbe host is required;
public Inbe 2.1.34 is API 11 and outside this game's supported range. The
current dependency graph also includes local, unpublished Self source.
Building or installing never publishes.

## Pushy

[Pushy](https://github.com/waozixyz/pushy) has its own repository: its
two editions, Classic and Island, their artwork, puzzles and tests live
there. Arcade installs Pushy by default, like Chess, and builds it from that
package. Opening Classic or Island goes straight to your newest unlocked
level; Levels lets you replay any unlocked puzzle. Pushy also runs as its own
desktop app.
