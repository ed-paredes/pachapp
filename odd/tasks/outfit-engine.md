# Outfit engine — look of the day and suggestions

## Objective

Generate outfit proposals from the owner's wardrobe (look of the day + alternatives on Hoy), let the owner wear,
favourite or dislike them, and record wear so `wear_count`/`last_worn_at` and Historial become real.

## Problem / why

The engine is fully specified but not implemented. Hoy hard-codes `proposal = undefined`
(`app/app/(tabs)/index.tsx` ~31-91); there are no `/outfits*`, `/wear-log*` or `/history*` endpoints, and
`wear_count`/`last_worn_at` are never written. A15 (PR #41, merged 2026-10-04) now gives every garment category,
formality, style_tags and a 768-d embedding, which the engine needs.

## Specs (source of truth)

- `docs/specs/05-outfit-engine.md` (ENG-REQ-001..026): templates A top+bottom+shoes / B one_piece+shoes, optional
  1 mid_layer, 1 outerwear, up to `setting.max_accessories` accessories (no two of the same subcategory); hard
  filters: status active, formality spread <= 1, no exact set worn within `no_repeat_days`, pinned
  `fixed_garment_ids`, <= 2 non-neutral dominant colours (accessories excluded); score
  `S = .35 color + .25 style + .25 novelty + .15 preference` (weights in `setting.weight_*`); two-stage
  generation (numpy bases top K~300, greedy layers/accessories), MMR lambda 0.7 -> 5 proposals, a garment in at
  most 2; deterministic with optional `seed`; one-sentence Spanish `explanation` from templates; < 1 s for 300
  garments; `backend/src/engine/` pure functions, no I/O (DEV-REQ-002).
- API (ENG-REQ-020): `POST /outfits/generate {fixed_garment_ids?, replace_garment_id?, seed?}` ->
  `{proposals[<=5]: {items[{garment_id, slot, layer}], score, score_breakdown, explanation}, generated_at}`;
  proposals not persisted at generation (D6); small/empty wardrobe -> 200 with fewer/zero proposals.
- `docs/specs/06-feedback-history.md`: "Siguiente" persists nothing; dislike/favourite -> `POST /outfits`
  (rating/is_favorite) or `/outfits/{id}/dislike|favorite`; "Me lo pongo hoy" -> `POST /outfits` then
  `POST /wear-log {outfit_id, date?}` (409 if the day is logged; PUT/DELETE `/wear-log/{date}`), recomputing
  `wear_count`/`last_worn_at` in the same transaction; `POST /outfits` deduplicated for 5 min;
  `GET /outfits/favorites`, `GET /history/calendar?month=`, `GET /history/stats`.
- `docs/specs/07-app-ui.md` UI-REQ-005/009/011/015, SCN-004; decisions D1, D6, D8 (season removed), D17, D18 in
  `docs/architecture/c4.md`. Weather and occasion out of iteration 1. Trained compatibility model out
  (`SPEC-ML.md`).

## Existing pieces

- Backend tables exist (`backend/src/shared/models.py` ~121-180): `Outfit` (source, score, score_breakdown,
  is_favorite, rating, name, explanation), `OutfitItem` (slot, layer), `WearLog` (date UNIQUE), `Setting`
  weights/no_repeat_days/max_accessories. No migration needed. `backend/src/engine/__init__.py` is an empty pure
  package. Colours have Lab per colour (hue for the colour score); embeddings float32 bytes +
  `embedding_model` (compare only same model).
- App (`app/src/components/today/*`): `TodayView` props `proposal?: LookProposal`, `alternatives?: AltLook[]`,
  `onWear`, `onShuffle`, `onOpenPiece`, `onOpenAlternative`, `weather?` (unused); `types.ts` `LookProposal
  {name?, pieces[{garmentId, role, name, imageUri, color?}], formalityLabel?, matchPercent?, reasons?}`;
  `LookCanvas`, `LookWhyCard`, `AltLookCard`; Detalle hides "Crear outfit con esta prenda" and shows
  `outfit_count` (0); Favoritos is a static empty state; Historial calendar placeholder; Ajustes already edits
  the four weights.
- Offline (`odd/tasks/offline-app.md`, merged): the last proposals must be a persisted query on Android
  (add outfit keys to `query-keys.ts`, persistence families and `src/lib/wardrobe-filters.ts`/sync if synced);
  wear/favourite/dislike/shuffle are mutations -> disabled offline; Hoy offline shows the last saved proposal.

## Scope (owner decisions)

- 2026-10-04: A15 first (done, PR #41). Engine MVP includes the base templates **plus mid_layer, outerwear and
  accessories** from day one.
- Weather/season out (spec). User management deferred (personal use).

## Open decisions (ask the owner at the start of the next session, one at a time)

1. Style score in the MVP: formality variance + style_tags Jaccard only, or also embedding cosine now (A15
   provides embeddings; style_tags threshold is uncalibrated, 2 of 4 test garments got none).
2. Hoy layout: hero + up to 4 alternatives from the 5 proposals (recommended) vs strict spec list; "Otra
   sugerencia" = next cached proposal vs a new `generate` with a new seed.
3. Presentation: `matchPercent` = round(score*100) or hidden until calibrated; look `name` from a template or
   hidden; `formalityLabel` from formality.
4. Refresh policy: regenerate once a day / on wardrobe change / on demand; what offline shows.
5. Wear 409 UX (day already logged: replace or keep) and whether garments in laundry are excluded (spec:
   only active).
6. Order of follow-ups after the MVP: Favoritos, Historial calendar/stats, "Crear outfit con esta prenda",
   dislike/preference learning.

## Proposed tasks (refine after the decisions)

- [ ] **E1** Engine core (pure `backend/src/engine/`): candidate filtering, base enumeration with numpy masks,
  colour/style/novelty/preference scores, layers and accessories greedy, MMR to 5, explanations; unit tests +
  benchmark (5 of 300 under 1 s).
- [ ] **E2** API: `POST /outfits/generate`, `POST /outfits` (dedupe), `POST /wear-log` (+ PUT/DELETE) with the
  transactional `wear_count`/`last_worn_at` recompute; contract tests; regenerate `app/src/api-client/schema.ts`
  (`make gen-client`).
- [ ] **E3** App Hoy: `useGenerateOutfits` (persisted on native), response -> `LookProposal`/`AltLook` mapper,
  wire `onWear`/`onShuffle`, offline behaviour (saved proposal, actions disabled); UI task -> frontend-design +
  ux-copy, critique + a11y on screenshots.
- [ ] **E4** Owner check on the phone (rebuild APK with `make android-apk`).

## TDD / checks

TDD: off (no project/session TDD configuration). Backend: ruff, ruff format, ty, pytest (`make lint`,
`make fmt-check`, `make typecheck`, `make test`); app: prettier, eslint, tsc, jest.

## Delivery

Forecast > 1,500 authored lines (engine + API + app) -> owner's chain strategy **stacked-to-main**, one PR per
reviewed slice (E1, E2, E3). Branch `feat/outfit-engine` from `main` `b8d4b7f`.

## Routes

- E1/E2: delegated writer(s) (backend, 2+ non-trivial files each). E3: delegated writer with design skills.
  Parallel writers only in isolated worktrees with the owner's approval.

## Progress

- 2026-10-04: groundwork exploration (delegated, read-only) summarised above; feature document created for the
  next session.

## Next step

Next session: ask the open decisions (1-6), refine the tasks, then E1.
