# Arcade

Games and entertainment, alongside Werkzeug for practical tools and Inner
Breeze for personal growth. The library opens Shovey Classic and Editor
directly from full-screen covers.
Swipe, turn the arrows, scroll the wheel, or use the arrow keys to choose;
press Play/Open or Enter to launch. Standalone Shovey uses the same carousel
on its title screen. Chess is temporarily disabled in Arcade; its code and
existing saved games remain available for a later return.
Each edition has a separate save and earned unlocks. Unlocked puzzles show
their whole board; locked puzzles keep their lock until earned.

Chess’s retained implementation can choose a side and one of four computer
levels. A local game
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
verified collection. Arcade presents the verified Classic and Editor leaves
directly, without
a second chooser. Shovey’s separate standalone collection uses the same
leaves and saves. Cover entries declare portrait art, landscape art, logo,
caption and action in `games.json`; Kryon’s shared `Carousel` handles
navigation and painting. The local player does not offer node updates or OS
actions it
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

Native standalone Shovey uses the shared Entity profile for account creation,
key recovery and device connection. Connected Waozi-node accounts can view Dew,
get a funding address and confirm a storage-plan purchase. These services belong
to the outer native host. Portable Arcade and Shovey collections carry no profile
bundle, so Inbe supplies its existing profile and account. Inbe retains its
existing game sync and friend games. Arcade and Inbe keep separate
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
./build/arcade --app shovey
./build/arcade --list
./build/shovey
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

Inside Inbe, Arcade's verified games use the active Inbe account's nested-app
records, so their progress follows that profile and its sync. Standalone
Arcade never opens that account: its games and collection settings stay in
the private local profile above.

## Checks

```sh
make test
make ui-test
make standalone-ui-test
make collection-ui-test
make scroll-ui-test
make inbe-ui-test INBE_BINARY=/absolute/path/to/intended/inbe
make compatibility-test INBE_BINARY=/absolute/path/to/intended/inbe
```

The UI tests scrub the inherited desktop and run on private Xvfb displays.
The collection check verifies covers in both orientations, direct play and
editor launch, swipe/wheel/keyboard navigation, Back and retained saves.
The retained Chess-specific check opens Chess, plays a move, waits for the
computer's legal response, checks
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
The cover collection requires an Inbe host with API 28 and the reviewed
carousel controller. Older hosts must keep their compatible Arcade release.
Building or installing never publishes.

## Shovey

[Shovey](https://github.com/waozixyz/shovey) has its own repository: Classic,
Island and Editor, their artwork, puzzles and tests live there. Arcade installs
Shovey by default and builds it from that package. Opening Classic
or Editor goes straight to its own screen; Levels lets you replay any unlocked
puzzle. Shovey also runs as its own desktop app.

## Shared Entity profile

Standalone Shovey's title-screen Profile control opens the shared `entity.zib`
supplied by the Entity package. The host keeps account keys and native file
access behind Entity's versioned management service. Returning from Profile
keeps the current game and its existing save directory. Account connection does
not claim that standalone saved games synchronize with Inbe.

`tests/entity_ui_test.py` checks the standalone profile route and retained game
progress. Run it with `--binary build/shovey --inbe-source PATH` only on a private
Xvfb display after scrubbing the inherited desktop environment.
