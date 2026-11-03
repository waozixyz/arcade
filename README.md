# Arcade

Games and entertainment, alongside Werkzeug for practical tools and Inner
Breeze for personal growth. Arcade opens on a console home from the shared Apps controller.
Landscape fills the screen with the selected game’s screenshot above one bottom
row of wide covers. Portrait centers a large tall cover, with neighbours peeking
in and the same game colouring the background. A glowing outline marks focus. There is no home title or cover caption.
Arrow keys, controller D-pad or left stick, swipes and the wheel select games;
Enter or controller A opens the selection. Click a cover to open
an installed game or open its artwork launch page first. Download consent,
progress and retry stay in that page, without a modal. Back keeps the transfer
running and returns to the same selected cover. Verified games open their own
title screen. A house-shaped Arcade control stays above hosted games and editors;
F1 or a controller’s View/Select button returns directly to the library after saving.
Standalone Shovey opens on its own cover carousel;
swipe, use the arrows or scroll the wheel to choose, then press Play/Open.
Its desktop startup first draws a small full-colour title preview, then uses
the original artwork when the collection is ready.
Chess is temporarily disabled in Arcade; its code and
existing saved games remain available for a later return.
Each edition has a separate save and earned unlocks. Unlocked puzzles show
their whole board; locked puzzles keep their lock until earned.

The published Arcade carries only its catalog, well under one megabyte. Its host supplies the shared Apps controller (Inner Breeze its own, standalone Arcade the `apps.zx` installed beside it), and the covers and previews download once as one separate art bundle. Library previews stay at 256 pixels. Real gameplay screenshots supply landscape heroes up to 1600 pixels and portrait covers up to 1080 pixels on the longest side, encoded as quality-80 WebP. The complete separate art bundle has a 2 MiB budget for the current games. Full-size originals stay in their game repositories. The verified art bundle stays cached across restarts and is replaced when its content changes. The art lives in `assets/arcade/library/` (`python3 scripts/library-art.py` refreshes it when a game's art changes; the build stops until it does). Inner Breeze needs host interface 35 for it. Each game
downloads when opened, with its existing identity and saved progress. This
catalog requires Inner Breeze host API 41. Downloaded games work offline;
standalone Shovey keeps its complete offline collection. Apfelwurm comes from
its own package, with the same game identity and private editor records.

Arcade lists games only. Each game opens on its own normal title screen.
Editors open from inside their games; installed editor add-ons and saved drafts
keep their existing identities and records. Shovey’s Classic editor remains an
add-on. Its named install dialog lists Shovey when needed and shows the total
download size. The Island editor stays private. Once Shovey is installed, only
the editor’s additions download. The editor reuses the original game’s art
and sounds, and both remain available offline. The top-right HUD uses the shared
painted Dew jewel and profile medallion in one frame. Its two icons ship with the
host independently of the remote library, so they also work offline.

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

Arcade includes the reviewed shared `apps.zx` controller and a small seed
catalog. It asks before connecting to its node for the signed app library
and compressed previews. Profile’s Library connection control can switch back to offline;
verified cached apps, previews and saved progress remain available.
The catalog fixes the digest of every separately downloaded game. Each game package lists its apps in its own `apps.json`:
the app's `catalog.json`, and for an app the library opens from a cover, the
cover's portrait art, landscape art and action. `games.json`
names the game packages, and Arcade's own `apps.json` its own apps. Arcade
presents the games directly, and a cover opens the game's normal title screen.
Editor add-ons remain declared for verified installation and save compatibility,
and open from inside their game. Shovey’s separate standalone collection uses
the same game identities and saves. The shared Apps console handles navigation
and painting with Kryon widgets. Library refreshes use the reusable Apps signed catalog
loader and do not update the native host. Inbe supplies its own account and package policy.
Arcade's launcher icon is MingCute's `game_2` gamepad (Apache-2.0).

An optional `artwork` mapping in `games.json` names a locked source-only
dependency for a game's library pictures. Its paths still come from that
game's declarations. This lets covers advance independently of playable
code; the thumbnail source hashes remain checked when the catalog builds.

## One Chess game

Chess remains an installable app in Inner Breeze, where it also fits thoughtful
play and personal growth. Arcade owns its rules, computer opponent, screens,
assets, translations and release ledger at `apps/chess/`. Inbe consumes the
same signed package from its node. Both harnesses recognize `inbe.chess`.
The game's `catalog.json` declares its membership in both harnesses.

Arcade builds that source into a `.zx` and runs it through the same bounded
app and Kryon widget interface Inbe uses. The bundle contains its existing
piece images and translated Chess text. Arcade validates its game identity,
capabilities and resource paths before opening it.

Standalone Arcade and Shovey provide Profile at the top right of their
covers, with the Dew balance directly inside it for connected Waozi-node
accounts. A game opened from a cover fills the screen with its own header.
They use the shared Entity profile for account creation, key recovery and device
connection. Connected Waozi-node accounts see Dew directly in Profile and can
get a funding address and confirm a storage-plan purchase. These services belong
to the outer native host. Portable Arcade and Shovey collections carry no profile
bundle, so Inbe supplies its existing profile and account. Inbe retains its
existing game sync and friend games. Arcade and Inbe keep separate
saved games; this version does not migrate or synchronize games between them.

## Website

https://arcade.waozi.xyz runs Arcade in the browser: the latest published
`arcade.zx`, the same collection Inner Breeze downloads, with Arcade's own host
(`src/web/runtime.zi`) compiled to WebAssembly by Entity's web build. Games
download from the node when someone opens them; saves stay in the browser.
`.github/workflows/site.yml` rebuilds and publishes it after every push to
master and every Arcade release, after `tests/web_site_test.mjs` opens the
library in a private browser. `scripts/cloudflare-site.py` creates the Pages
project and connects the domain with the repository's `CLOUDFLARE_API_TOKEN`
and `CLOUDFLARE_ACCOUNT_ID` secrets.

Build it locally from this checkout's collection with `make collection`,
`python3 scripts/build-entity.py` and `python3 scripts/build-web.py`, then serve
`build/web-site`.

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

## Android

Arcade's APK contains only the catalog, shared Apps controller, Entity host,
font and launcher resources. Library thumbnails download when needed; games
and their declared dependencies install after download consent. Installed
games remain available offline, and updates preserve downloads and saves.
Entity keeps ordinary profile pictures; optional game imagery falls back to
the profile picture when absent.
Standalone Shovey retains its complete offline collection. `make android` builds an
unsigned release APK in `build/android/`. `make android-fdroid` and
`make android-gplay` build the other editions; only `-gplay` carries a Google
library (Play Billing). Builds need the Android SDK with NDK 28.2.13676358,
build-tools 36.0.0, platform 36 and CMake 3.22.1, and Java 21.

```sh
make android
python3 scripts/android-release.py sign build/android/arcade-unsigned.apk --version "$(cat VERSION)"
make android-offline-ui-test
```

The release key is `backup/android-signing/arcade-release.p12` (ignored) and
the GitHub secrets `ARCADE_ANDROID_KEYSTORE` and
`ARCADE_ANDROID_KEYSTORE_PASSWORD`; `packaging/android/certificate.pem` is its
public certificate. The Android workflow attaches `arcade-VERSION.apk`,
`arcade-VERSION-fdroid.apk` and `arcade-VERSION-gplay.apk` to a native
`arcade-VERSION` release after verifying all three editions. Existing APKs
on older `node-arcade-VERSION` releases keep their original URLs.

The native host uses root `CHANGELOG.md` and `VERSION`; synchronize a native
release with `sh update_version.sh`. The signed game catalog uses
`catalog/CHANGELOG.md` and `catalog/VERSION`; synchronize its release with
`sh update_version.sh --catalog`. Both use numeric changelog entries and keep
each game's own version ledger. Catalog publication keeps the existing
`node-arcade-VERSION` tags and never starts Android builds. Game updates
advance the catalog only, leaving pending native changes for the next host
release. An APK's embedded seed catalog may have a different version from
its native host.

Game packages are registered in `games.json`; each declares its apps in its
`apps.json`. Arcade is a catalog and downloader: games build and publish
in their own repositories. `scripts/build-games.py` imports their portable
exports byte for byte and generates catalog metadata; it never compiles game
source, prepares assets, or runs game payloads. Disabled entries remain catalog
metadata only, and private external editions (including Island) stay excluded.

Before a local integrated build, export in each owning repository:

- Shovey: `build-queue -- python3 scripts/player.py collection --web` exports
  `build/player/games/{shovey,shovey-editor}.zx` and `-resources.json`.
- Wurm: `build-queue -- python3 tools/build_portable.py` exports
  `build/games/{wurm,wurm-editor}.zx`, `-resources.json` and `-preview.png`.
- Choano: `build-queue -- make portable` exports `build/choano.zx`.

Shovey and Choano previews come unchanged from their declared game preview
paths. Every payload must embed its public app catalog at
`assets/NAME/catalog.json`; add-ons must also embed `requirements.json` naming
the exact imported dependency hashes. Import rejects identity, entry, resource
link and dependency mismatches and payloads over 64 MiB before replacing prior
staged games or catalogs. No compiler fallback exists.

Clean locked/downloaded packages may have no local exports. Supply
`--artifact-manifest PATH` to the importer (or `make
GAME_ARTIFACT_MANIFEST=PATH`) with already exported artifacts. The JSON shape
is `{"apps":{"APP_ID":{"bundle":"exports/game.zx",
"preview":"exports/preview.png","resources":"exports/game-resources.json"}}}`.
Paths are relative to the manifest or absolute; name exactly the enabled public
IDs, including editor add-ons. `resources` may be omitted only for apps with
no dependencies. Payloads and supplied sidecars are copied unchanged.
Automatic remote release artifact retrieval/export wiring is not currently
available here: obtain exports from the game owner or run its command above.
The existing published web catalog build does not invoke game builds.
Inbe remains a dependency for the existing shared interface and signed publisher.

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
make navigation-ui-test
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

`make collection` writes the same catalog to `build/arcade.zx`
and `build/node-apps/arcade.zx`. Its exact game payloads
are in `build/node-apps/arcade.games/`, named by their SHA-256, and in
`build/node-apps/arcade.games.tar` for the existing signed node publisher.
`make install-arcade` updates only Arcade's desktop launcher and catalog;
it does not install game payloads. Previously downloaded games and saves stay
in the person's private data directory.

## Shovey

[Shovey](https://github.com/waozixyz/shovey) has its own repository: Classic
and the Editor, their artwork, puzzles and tests live there. Arcade builds
Shovey from that package and offers it as a separate download. Opening Classic
or Editor goes straight to its own screen; Levels lets you replay any unlocked
puzzle. Shovey also runs as its own desktop app.

## Shared Entity profile

Leaderboard is inside the shared Profile, including standalone Arcade and
Shovey. Games report their own level totals under their verified identity;
Profile shows only games that are installed, with friend rankings for a
connected account. Removing a game hides its board while retaining its save
and reported score. Account switches keep rankings separate.

Standalone Shovey's Profile control on its covers opens the shared `entity.zx`
supplied by the Entity package. The host keeps account keys and native file
access behind Entity's versioned management service. Returning from Profile
keeps the current game and its existing save directory. Account connection does
not claim that standalone saved games synchronize with Inbe.

`tests/entity_ui_test.py` checks the standalone profile route and retained game
progress. Run it with `--binary build/shovey --inbe-source PATH` only on a private
Xvfb display after scrubbing the inherited desktop environment.
