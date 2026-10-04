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

## Owner decisions (2026-10-04, second round)

1. Style score uses embeddings now: C_style = mean of formality variance, style_tags Jaccard and mean pairwise
   cosine of embeddings (same `embedding_model` only; a garment without an embedding contributes no cosine term).
2. Hoy: the best of the 5 proposals is the look of the day, the other 4 go to "Otras opciones". "Otra
   sugerencia" moves to the next cached proposal without calling the backend (works offline); when all 5 have
   been shown it requests 5 new ones (new seed).
3. "% match" hidden for now (score uncalibrated); show the explanation ("por qué"). Look name: hidden unless a
   template gives something meaningful; formality label from formality.
4. Refresh once a day: generate on the first Hoy visit of the day and again when the wardrobe changes (upload,
   archive, laundry, edit); offline shows the last saved batch.
5. "Me lo pongo" on a day already logged: ask "Hoy ya registraste otro outfit. ¿Cambiarlo por este?" and on
   accept replace it (`PUT /wear-log/{date}`), recomputing wear counts of both outfits' garments.
6. After the MVP: "Crear outfit con esta prenda" first (Detalle -> generate with `fixed_garment_ids`).
- Eligibility per spec: only `status=active` garments (laundry and archived excluded).

## Proposed tasks (refine after the decisions)

- [x] **E1** Engine core (pure `backend/src/engine/`): candidate filtering, base enumeration with numpy masks,
  colour/style/novelty/preference scores, layers and accessories greedy, MMR to 5, explanations; unit tests +
  benchmark (5 of 300 under 1 s).
- [x] **E2** API: `POST /outfits/generate`, `POST /outfits` (dedupe 5 min), `POST /wear-log` (409 when the day is
  logged) + `PUT`/`DELETE /wear-log/{date}` with the transactional `wear_count`/`last_worn_at` recompute for
  every affected garment; contract tests; regenerate `app/src/api-client/schema.ts` (`make gen-client`).
- [ ] **E3** App Hoy: `useGenerateOutfits` (persisted on native, daily + wardrobe-change refresh), response ->
  `LookProposal`/`AltLook` mapper (no match %), "Otra sugerencia" cycles cached proposals then regenerates,
  "Me lo pongo" with the replace confirmation, offline behaviour (saved batch, wear disabled); UI task ->
  frontend-design + ux-copy, critique + a11y on screenshots.
- [ ] **E5** (after the MVP) "Crear outfit con esta prenda" in Detalle.
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

- 2026-10-04: E1 `42fb1fa` (delegated writer): pure `backend/src/engine/` (`types`, `constants`, `context`,
  `scoring`, `generate`, `explain`), `generate_outfits(GenerationRequest)` -> <= 5 proposals, `InvalidRequest`
  (Spanish) for impossible fixed sets; numpy-batched stage 1/2, stage 2 only adds hard-filter-valid pieces
  (ENG-REQ-023 fallback by construction); spec defaults in `constants.py` with open-item comments; judgment
  calls: fixed garments exempt from the MMR cap (SCN-002 vs REQ-015), colour cap counts distinct dominant
  colour names, ENG-REQ-024 checked against the real limits, recent-set filter on the final set, K widening
  whenever < 5 proposals, style = mean of available terms, fixed one_piece excludes template A and fixed
  top/bottom excludes B. Benchmark 300 garments: 0.30-0.34 s (asserted < 1 s). ~996 source + ~1220 test lines.
- 2026-10-04: E2 `83f914d`: `POST /outfits/generate`, `POST /outfits` (5-min dedupe for generated sets,
  canonical layers), `POST /wear-log` (409 `WEAR_LOG_CONFLICT` with the existing entry in details),
  `PUT`/`DELETE /wear-log/{date}`, recompute of `wear_count`/`last_worn_at` for both outfits in one transaction;
  `api/engine_inputs.py` builds inputs (active garments, float32 embeddings, wear window, liked/disliked pairs);
  `api/clock.py`; schema regenerated (`make gen-client`). Not implemented (not in scope): `/outfits/{id}/favorite`,
  `/dislike`, `GET /outfits/favorites`, `/history/*`. Checks: ruff, format, ty clean; pytest 579 -> 605; app
  typecheck/lint/format/jest 347 clean. RED probes (one redundant: the same-day 409 is also enforced by the
  unique date). Parent spot check: ruff, ty clean; pytest 605 passed.
- Writer note for E3: the seed only breaks exact ties (ENG-REQ-019), so "request 5 new ones with a new seed"
  would usually return the same proposals -> needs another mechanism (owner decision).

## Next step

Native reviews of E1 (`b8d4b7f..42fb1fa`) and E2 (`42fb1fa..HEAD`), decide the "new proposals" mechanism, then E3.
