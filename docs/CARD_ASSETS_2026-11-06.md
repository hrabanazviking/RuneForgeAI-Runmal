# Card thumbnails & assets (P-023) — 2026-11-06

Roadmap line: *card art, alternate expressions and asset packs
stored per character (Part X animates them).*

This slice closes the gap P-022 recorded verbatim: "card asset
bytes are noted, not persisted — P-023". Asset bytes are now
persisted per character, indexed in the database, and retrievable
over HTTP — never just noted.

## What was built

- `src/runmal/assets/` — new package.
  - `models.py`: closed vocabularies as `StrEnum`s — kinds
    (`card_art`, `expression`, `background`, `embedded`, `pack`),
    statuses (`stored`, `external_unfetched`, `missing_bytes`),
    thumbnail statuses (`ready`, `unavailable_non_png`,
    `unavailable_decode`, `not_applicable`) — plus `ImageInfo`
    and `asset_to_dict` (metadata only; never bytes, never
    absolute paths).
  - `imaging.py`: stdlib-only image inspection. `sniff_image`
    reads format + dimensions from the bytes themselves
    (content-first, never extension-first): PNG signature +
    IHDR, JPEG segment walk to SOF0/1/2, GIF header, WebP
    VP8X/VP8/VP8L. A claimed format with a broken header is
    `corrupt`, never guessed. `make_png_thumbnail` is a real
    pure-Python PNG decoder (bit depth 8, colour types 0/2/3/4/6,
    interlace 0, all five unfilter types) with a box-average
    downscale to at most 256 px and pixel/decompressed-size
    caps; anything it cannot decode correctly returns `None`
    honestly instead of an approximation.
  - `service.py`: the store. `build_asset_plan` is a pure
    classification of a parsed card: the PNG container itself
    first (card art, when the caller threads the source bytes),
    then one entry per declared v3 asset descriptor — `icon` →
    card_art, `emotion` → expression (named by the descriptor),
    `background` → background, any other type → embedded with
    the source type kept verbatim — then every embedded archive
    member no descriptor consumed (an archive member that is
    itself a ZIP is a `pack`). `ingest_card_assets` executes the
    plan: bytes are written under
    `assets/characters/<character_id>/p023/` with flattened,
    sanitised, collision-safe storage names (byte-identical
    collisions share one file; byte-different collisions get a
    sha256 suffix), one `character_assets` row per entry, and
    a derived PNG thumbnail file when the stored bytes are a
    decodable PNG. Also `add_asset` (single upload),
    `list_assets` / `get_asset` (owner-scoped),
    `read_asset_content` (containment-checked),
    `read_asset_thumbnail` (self-healing: a missing thumbnail
    file is regenerated from the stored bytes),
    `clone_character_assets`, `rebuild_asset_bytes` (the stored
    bytes keyed for CHARX re-export), and
    `purge_character_asset_files` (rollback compensation).
  - `router.py`: `GET /characters/{id}/assets`,
    `GET /characters/{id}/assets/{asset_id}`,
    `GET .../content`, `GET .../thumbnail`,
    `POST /characters/{id}/assets` (multipart, `kind`/`name`
    form fields, 201). Error mapping mirrors the avatar routes;
    a thumbnail that does not exist answers 404 with
    `thumbnail_unavailable:<status>` — the original bytes are
    never served dressed as a thumbnail.
- Migration `0020` + ORM `CharacterAsset`: one row per asset
  with kind, descriptor name/type/URI/ext verbatim, status, a
  closed-vocabulary `detail`, sniffed format/media type/
  dimensions, byte size, sha256, storage + thumbnail relpaths,
  and thumbnail status.
- Wiring: `characters.create_character_from_card` gains
  `source_bytes` and ingests the card's assets in the same
  transaction (an asset failure never refuses an otherwise
  valid card — the failed entry is recorded, or the ingest is
  rolled back with its files purged and the card still
  created); `duplicate_character` clones the asset rows (its
  existing copytree already carries the files);
  `library` bulk import passes PNG source bytes through and
  reports `assets_stored_p023:<n>` on real runs and
  `assets_would_store_p023:<n>` on dry runs (which store
  nothing), purging a created character's asset files when its
  per-file transaction rolls back; `diagnostics/cleanup` now
  treats database-referenced asset + thumbnail files as
  referenced, in the scan and in the delete-time revalidation;
  the portable archive exports the asset rows plus their files
  (thumbnails excluded as derived data — they regenerate on
  read) and restore imports both.

## Honest handling

- A descriptor whose `embeded://` / `embedded://` URI resolves
  to no embedded bytes becomes a `missing_bytes` row — recorded,
  never dropped. A descriptor with an external URI (`https://`
  and any other scheme) becomes an `external_unfetched` row:
  Rúnmál never fetches it. A descriptor with no URI is
  `missing_bytes` / `no_uri`.
- Corrupt image bytes are stored verbatim (CHARX fidelity) and
  flagged: header-corrupt → `detail=corrupt_image`;
  header-valid but undecodable → thumbnail
  `unavailable_decode`. Non-image members (notes, audio, JSON)
  are stored with format `unknown`, thumbnail `not_applicable`.
- Oversize: the card parser's caps (16 MiB per asset, 64 MiB
  total) already bind CHARX input; a single asset over the cap
  reaching ingest directly becomes `missing_bytes` /
  `oversize_not_stored`, and the upload route refuses oversize
  with a 400, mirroring the avatar route. There is no
  per-character aggregate cap in this slice.
- Unknown fields are preserved: descriptor rows keep type/URI/
  name/ext verbatim, unrecognised descriptor types are stored
  as embedded (not refused), descriptor-level extra keys ride
  the stored card JSON exactly as before (INV-009), and the
  storage name never leaks into the recorded name — a
  descriptor named `../../evil` is recorded verbatim and
  contributes nothing to any filesystem path.
- Soft-deleted characters keep their rows and files (S303);
  the asset API 404s while trashed and works again after
  restore with no re-ingest.

## Not in this slice

- No animation or expression switching in chat — Part X
  animates what this slice stores.
- No thumbnails for JPEG/GIF/WebP bytes (no image library in
  the core dependency set): those assets record
  `unavailable_non_png` and serve their original bytes from
  the content route.
- Updating a character's card (`update_character`) does not
  re-ingest assets; asset rows belong to the card as imported
  or to explicit uploads.
- The gallery grid still shows the avatar (S303 surface);
  wiring it to card-art thumbnails is a UI slice's work.

## Clean-room basis

Shapes rest on the P-002 census, the public Character Card v3
spec's `assets` descriptors as already logged for P-016, and
the P-005 authored corpus. No SillyTavern or Voxta source was
inspected; no asset file was downloaded — the battery's images
are authored or generated in the test module.

## Evidence

`tests/test_p023_card_assets.py` (43 tests) — battery,
neighbours and full-suite counts in the worktree's
`hidden_files/` logs.
