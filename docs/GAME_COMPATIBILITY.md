# Game compatibility

Arcade owns games. A harness owns navigation, the drawing area, input,
account services, storage and delivery. A game owns its rules, screens,
translations, assets and saved-game migrations. Inner Breeze consumes Chess
from its Daochi node; it no longer builds or versions Chess.

The machine-readable standard is `standards/game-v1.json`. Every game has a
descriptor in its own source folder. `scripts/check-games.py` checks that
descriptor, the release ledger, translations and owned resources before a
bundle is built. The native loader also checks the embedded descriptor,
interface versions, identity, resource boundaries and actual imported calls
before starting a game.

## Shared interface

The existing Kryon node-app interface is the common interface: module ABI 2,
with Chess requiring host API 12. Its records and codecs are exported by the
Inbe package and used directly by Arcade and Chess. There is one interface,
not a second Arcade-specific Chess API.

Records match fields by name. Optional frame fields default to zero when an
older host omits them. `top` and `bottom` reserve harness navigation space;
the game draws inside the remaining area. Arcade uses a top Back button,
while Inner Breeze retains its own navigation. The core game test explicitly
runs without `top` to check the older frame layout.

Every foreign capability must be granted before execution. Widgets use the
normal Kryon interface; game images come only from the game's validated
`assets/<name>/` resources. Games cannot use arbitrary OS calls, native
texture handles, another game's records or the host's secrets.

Account-dependent features are explicit. Inner Breeze supplies its existing
friends and shared-game transport. An offline harness reports those services
as unavailable and never claims an invitation or move was delivered.

## Identity, text and saves

Chess keeps the signed package ID `inbe.chess` and app name `chess`, despite
its source moving to Arcade. Existing publisher pins, installation marks,
`cell.chess.*` records, shared game IDs and save schema 1 remain valid.
Changing source ownership is not a reason to reset or rename user data.

The package includes its own translations. A current Inbe host uses those
first, then its existing translated text for older packages. New game text
can therefore travel in a game update without a complete Inbe release. The
build also embeds the game-owned translations as a module, so legacy hosts
that only know their root locale file can display newly added labels too.
Unknown languages fall back to the game's English text.

Arcade and Inbe still provide separate local/account storage. Sharing one
game implementation does not silently merge or migrate their saved games.

## Updates and publication gate

Chess's numeric changelog and `apps/versions.json` live in Arcade. Run
`./update_version.sh` after adding a release entry; it advances the game
version and sequence together. No release tags are created manually.

`scripts/package-release.py` invokes the Apps package's signed Daochi
publisher, `scripts/node_release.py`, with Arcade's ledger and bundle
directory and the publisher pins released Inbe ships. It preserves the existing
publisher key, `inbe.chess` identity, immutable payloads, increasing release
sequence and node receiver. No second update protocol is introduced.

Before node publication, run:

```sh
make compatibility-test INBE_BINARY=/absolute/path/to/intended/inbe
```

For a node release, also supply `OLDEST_INBE_BINARY` for the oldest released
Inbe the game claims to support. A development-host check alone cannot
authorize an upload; the publisher requires that older-host result too.

The gate checks the exact bundle in Arcade and the supplied Inbe host,
including actual rendering, input and save restoration. The intended and
oldest host checks also exercise study, hints, analysis, clipboard export and
takebacks at a narrow window size. The same native import flow checks PGN
main lines, custom FEN promotion/numbering, failed-import recovery and
preservation of the live game in both harnesses. It also tests Chess's
rules, computer play and friend-game protocol. The saved receipt is bound to
the bundle hash, release version and sequence. The publisher refuses a
remote upload if that receipt is missing or stale.

Host API numbers alone do not prove compatibility: the intended host must
also understand the bundle's VM format. Test each platform and oldest host
version a release is intended to support. An unsupported VM format requires
a compatible build or a host update; never relabel a package to bypass it.
Passing checks prepares a release; the owner still approves publication.

Chess 1.1.0 requires host API 12. Public Inbe 2.1.34 supplies API 11 and
predates installable Chess apps, so it is outside the declared range. The
released-host gate waits for a released compatible API 12+ host; a current
development candidate does not satisfy that gate.
