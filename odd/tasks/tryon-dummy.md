# Try-on featureless dummy (V6)

## Objective

Make the "Verlo puesto" render read as a neutral, featureless dummy instead of a random real person: no head,
flat matte skin in a tone the owner picks, a woman or man base, on a transparent background composed on the
linen canvas on Hoy. Follows `odd/tasks/virtual-tryon.md` (V0-V5 closed).

## Problem and why

The owner finds the current render (CatVTON on the M12 photo) "random" and "very artificial": a real face, real
skin and a real studio backdrop behind a generated outfit. Spike V6-0/V6-0b (2026-10-12,
`~/pachapp-data/eval-results/tryon-v6-dummy-2026-10-12/report.md`, `report_round2.md`) showed that
post-processing a normal CatVTON result gives a convincing dummy at about 1 s extra per render.

## Owner decisions (2026-10-12)

- Simple version: 2 free-licence bases, flat matte skin ("me vale con el plano, luego lo podemos refinar").
- Bases: M12 woman (`m12-woman-crop-shorts`, current) and **M13 man** (`m13-man-beige-shorts`, Pexels 28079564,
  hands in pockets accepted). M13 is the only male base that dresses long trousers, shorts and leggings
  correctly; M10, M5, M1, M14, M15 and the M10 full-leg mask all fail on at least one length.
- Model settings live in the app as a "Tu modelo" settings screen (gender, skin tone; build later).

## Design (parent, from the spike and the code map of 2026-10-12)

- **Bases catalog**: each base has `meta.json` with `gender` and the calibrated cut lines (`dummy.chin_row`,
  `dummy.ankle` rule) so the cut does not vary per garment colour (the spike used the minimum chin per base).
  `tryon_mannequin_woman` / `tryon_mannequin_man` (replacing `tryon_mannequin`) map the owner's gender setting to
  a base; an explicit `mannequin_id` still wins.
- **Post-processing in the worker**, after `_dress_all` and an explicit `engine.unload()`: SegFormer-b2
  (`mattmdjaga/segformer_b2_clothes`, already in `backend/src/ml/garment_parse.py`) -> alpha = foreground,
  crop chin-to-ankle, hair below the chin transparent, pad to 3:4. Output a neutral RGBA plus a skin mask.
- **Tone server-side**: the worker writes the 6 tone variants at render time (about 0.2 s for all 6) next to
  the render (`tryon/<id>_t<n>.webp`); the API returns the variant for the owner's current tone, so changing
  the tone needs no re-render. A `postprocess` version joins the cache key so old renders are not served.
- **Settings**: `tryon_gender` (`woman` default) and `tryon_skin_tone` (1-6, default 3) in the singleton
  `Setting` row, exposed by `GET/PATCH /settings`.
- **App**: "Tu modelo" screen (gender segmented control, 6 tone swatches, static previews per gender x tone),
  linked from settings; Hoy draws the transparent render on the linen gradient with a soft shadow instead of
  the blurred backdrop.

## V6c design (parent, 2026-10-13)

- Keep CatVTON warm: run the SegFormer-b2 parse on the **CPU** by default (`tryon_dummy_device`, default `cpu`)
  instead of unloading CatVTON after every render (a cold load costs about 12 s on the next render). The parser is
  built lazily by the worker and kept resident; its weights are already in the ML cache.
- Feature switch `tryon_dummy_enabled` (default true). Off keeps today's full-frame output.
- Cut lines are calibrated per base as ratios of the render height in `meta.json` (`dummy.chin`, `dummy.ankle`
  rule) from the spike's per-base minimum chin, so the cut does not depend on the garment colour.
- Files: the raw CatVTON output stays at `tryon/<id>.webp` (`img_path`); the dummy writes the 6 tone variants
  `tryon/<id>_t<n>.webp` (RGBA, 3:4). `render.params.dummy` records the version; `GET /tryon/{id}` returns the
  variant for the stored tone plus `transparent: true`, else `img_path` and `transparent: false`.
- The cache key gains the post-processing version (`none` when the switch is off).

## V6d design (parent, 2026-10-13)

- Follow the owner's prototype (`propotipo.html`, settings card "Tu modelo" and the "Elige tu modelo" sheet
  styles): a "Tu modelo" card at the top of the existing settings screen (`app/app/settings.tsx`) with a 3:4
  preview on the linen gradient, a gender choice (Mujer / Hombre) and 6 round tone swatches (radiogroup), saving on
  change through `PATCH /settings` with a short "Guardado" confirmation. The first-run "Elige tu modelo" sheet is
  out of scope (not asked).
- Previews: 12 static WebPs bundled in the app (gender x tone), generated once with the shipped `tryon/dummy.py`
  pipeline from the spike's raw renders of the same outfit on M12 and M13; the generator script and its source
  images are recorded in this document, not shipped.
- After a change, the Hoy render follows: a tone change refetches the render read (the `img` variant changes); a
  gender change requests the render again (another base, another cache key).

## Scope

In: the tasks below. Out: complexion/body-type bases, a rounded neck cap, BiRefNet alpha (SegFormer alone was
as good, IoU 0.97-0.99), refining the tone look, changing config C or the spec v2 items flagged as conflicts
(steps, CPU offload, GPU lock, canvas ratio).

## Tasks

- [x] V6a: validate M13 (and M12 as reference) on the untested garment sets g02, g03, g05, g07, g08, g09 with
  the spike script (GPU run, no repo change). Gate for shipping M13; record failures and the decision.
- [x] V6b: bases catalog and settings (backend): add M13 to `assets/tryon/mannequins/` (person, masks, meta with
  source, licence, gender), add `gender` to M12's meta (the cut lines moved to V6c), `tryon_gender` and
  `tryon_skin_tone` columns + Alembic migration + `GET/PATCH /settings`, `POST /tryon` resolves the mannequin
  from the gender setting when no `mannequin_id` is given, `/tryon/capabilities` lists genders and tones;
  regenerate the app client.
- [x] V6c: dummy post-processing in the worker: calibrated cut lines (`dummy.chin` ratio, ankle rule) in both
  metas, CatVTON kept loaded (parse on the CPU), SegFormer parse, crop, alpha, flat recolour into
  6 tone variants, store them; `postprocess` version in the cache key; `GET /tryon/{id}` returns the image for
  the current tone; cleanup removes the variants.
- [x] V6d: "Tu modelo" screen in the app (gender, tone, previews), linked from settings, writes `/settings`
  and refreshes the Hoy render.
- [ ] V6e: Hoy composition: transparent render on the linen gradient with a drop shadow, no blurred backdrop;
  check on web and phone with real data.

## Acceptance criteria

- A render on Hoy shows a headless dummy cut at the ankle, in the chosen tone, on the linen canvas; no face,
  no studio background.
- Switching gender re-renders on the other base; switching tone changes the image without a new CatVTON run.
- Uploads keep priority; VRAM stays within the V1d budget (CatVTON unloaded before SegFormer).
- All checks below pass; owner checks on web (localhost:8081) and phone (exp://192.168.1.41:8081).

## Route and checks

TDD mode: off (no project/session TDD configuration, as in `virtual-tryon.md`). Backend runner:
`cd backend && uv run pytest`, plus `uv run ruff format --check .`, `uv run ruff check .`, `uv run ty check src`.
App: `cd app && npm test`, `npm run lint`, `npm run typecheck`, prettier check.
Route: V6a delegated (GPU run with the worker stopped). V6b, V6c delegated writer (2+ non-trivial files each;
code mapped by a read-only explorer on 2026-10-12). V6d, V6e delegated writer with the design skills
(frontend-design, ux-copy, design-critique, accessibility-review).
Forecast about 1200 authored lines over V6b-V6e (> 400): stacked-to-main, one PR per task (as in V1-V5).

## Analysis: is a separate "shorts" base worth it? (owner question, 2026-10-12)

No. In the spike the garment length follows the mask and the base's legs: a base in long trousers (M5) turns
shorts into long trousers, and a base in shorts with a short mask (M10) turns trousers into shorts. Widening
M10's mask only flipped the defect. M12 and M13 are both bases in shorts with bare shins and shoes, and both
dressed long trousers, shorts and leggings correctly (g01, g04, g06), so one base per gender covers both
lengths. A second base per gender (chosen by garment length) would only pay off if V6a finds a length that M13
fails; it would cost a second set of assets and a garment-length signal in the request.

## Progress

- 2026-10-12: owner approved V6 with M13; feature document created on `feat/tryon-dummy`.
- 2026-10-12 V6a (delegated GPU run, worker stopped during the run and restarted after): M12 and M13 on g02, g03,
  g05, g07, g08, g09 (`~/pachapp-data/eval-results/tryon-v6-dummy-2026-10-12/round3/report_round3.md`, sheets in
  `round3/sheets/`; script `v6_round3.py`). M12: all 6 correct (g02 small white blobs at the hands). M13: long
  trousers g02/g03, shorts g05 and dress g09 correct; **g07 mini skirt fails** (baggy long trousers plus a dark
  fur-like artefact on the thigh); g08 pleated skirt renders as wide knee shorts; the base's white undershirt hem
  shows under short tops (g02, g07, g08). Face removed, ankle cut clean, no garment recoloured on all 12.
  Timings: CatVTON warm pass 18 s, first 38.8 s; SegFormer 0.11 s; recolour 0.035 s/tone; VRAM peak 5649 MiB
  (2058 after unload), RSS 2787 MiB. Decision: M13 ships as the single male base; skirts on the man base are a
  known limit to show the owner (options: accept, or let skirts use the woman base). No separate shorts or
  long-trousers base.
- 2026-10-12 V6b (delegated writer, 2+ non-trivial files): 53fe9d9 `feat(tryon): pick the base by gender and store
  the model settings`; 25 files, +315/-14 (PNGs excluded). M13 assets (768x1024, masks at CatVTON 7818397, the
  clone's HEAD) and `gender` in both metas; `tryon/tones.py`; `tryon_mannequin_woman`/`_man` settings; migration
  `d5f1a9b73e20` (`tryon_gender` default woman, `tryon_skin_tone` default 3); `GET/PATCH /settings`; `POST /tryon`
  resolves the base by gender; capabilities list `genders` and `skin_tones`; client regenerated. Checks (writer):
  ruff format/check, ty clean; pytest 978 passed; app typecheck, lint, prettier clean; jest 476 passed. Parent
  spot check: pytest on test_api_tryon, test_api_settings, test_migrations: 81 passed. Native review assess
  (base aff8a1f, committed-only): risk high, review due (high_risk). 2026-10-13: owner granted the review (START
  rated it medium, 26 files, 447 lines; 1 lens); approved and acknowledged (lineage review-09c0fb95352994ab,
  aff8a1f..5308c2c). Advisories, non-blocking: R3-gender-without-loadable-base (WARNING, a stored gender whose
  base does not load fails every `POST /tryon` with no fallback), R3-renamed-env-silently-ignored (WARNING,
  `PACHAPP_TRYON_MANNEQUIN` is now ignored because settings use `extra="ignore"`; the owner's `.env`/`.env.lan`
  do not set it), R3-capabilities-full-load-per-request, R3-gender-meta-unchecked,
  R3-settings-read-strict-literal (suggestions), R3-task-doc-claims-cut-lines (fixed in this document).
- 2026-10-13 V6b follow-up (parent inline, 1 source file + its test): 992c612 `fix(tryon): fall back to the woman
  base when the chosen base is unusable` fixes R3-gender-without-loadable-base (owner: "si dale"); an explicit
  `mannequin_id` still gets 422. Checks: ruff format/check, ty clean; pytest 980 passed (+2). Assess (base 5308c2c):
  medium, under budget (54 lines), stays pending in the next slice. The other advisories stay open as follow-ups.
- 2026-10-13: owner decision on skirts on the man base (g07 mini skirt renders as trousers, g08 as wide shorts):
  "se queda así", accepted as a known limit; skirts are not routed to the woman base.

- 2026-10-13 V6c (delegated writer, 2+ non-trivial files): 0dc1d64 `feat(tryon): turn the render into a featureless
  dummy in six skin tones`; 23 files, +961/-19 (source and config about +353/-17, tests about +585; over the 400
  heuristic only because of tests). New `tryon/dummy.py` (`DUMMY_VERSION="dummy-1"`), worker parses with
  SegFormer-b2 on the CPU (parser built once per process, CatVTON kept loaded), raw output kept at `img_path` plus
  6 RGBA variants `tryon/<id>_t<n>.webp`, `params.dummy`, `postprocess` in the cache key and params, `GET /tryon`
  returns the tone variant and `transparent`, cleanup removes variants, `tryon_dummy_enabled`/`tryon_dummy_device`
  settings. Calibrated cut lines in meta: M12 chin 153/768 (0.1992), ankle shoe top, fallback 0.7852; M13 chin
  138/768 (0.1797), fallback 0.8060. Failure path: any post-processing error keeps the raw output (`done`, no
  `params.dummy`, `transparent=false`), logs and deletes partial variants; it stays cached under the dummy key until
  purged or the version is bumped (no `dummy_failed` code). Pending renders created before this change fail as
  `invalid_params`/`garment_changed` (key lacks `postprocess`); a resubmit makes a new render.
  Checks (writer): ruff format/check, ty clean; pytest 1018 passed (+38); app typecheck, lint, prettier clean; jest
  476 passed. Smoke (CPU, real b2 on 4 spike renders, `~/pachapp-data/eval-results/tryon-v6c-smoke-2026-10-13/`):
  model load 19.7 s once; parse 2.6-3.0 s, post total 2.8-3.2 s per render; look matches the spike sheets.
  Parent: spot check pytest on worker, API, cleanup and dummy tests: 128 passed. End-to-end on a migrated copy
  of the owner's data (API :8010 + real worker from this branch, GPU): polo + trousers on M12 (gender woman) and
  M13 (gender man): both `done`, `transparent: true`, 6 variants each; `PATCH tryon_skin_tone=6` switches `img` to
  `_t6`; durations 115 s (first, with CatVTON and parser loads) and 45 s; peak VRAM 2859 MB (torch). Sheet:
  `~/pachapp-data/eval-results/tryon-v6c-e2e-2026-10-13/e2e-sheet.jpg`. Known look issue from CatVTON, not the
  post-processing: white hand-shaped blobs at the pockets on both bases (as g02 in V6a).
- 2026-10-13 native review of the V6c slice (5308c2c..b197b02, includes 992c612): owner granted (high, 24 files,
  1105 lines), 4 lenses, approved and acknowledged (lineage review-1708e9c74e26e0cc). Advisories (non-blocking):
  WARNING R3-transient-dummy-failure-cached-permanently / R4-transient-dummy-failure-pinned (a transient
  post-processing failure pins the raw image under the dummy key, no retry), R3-unguarded-variant-cleanup-in-except
  (rollback delete can raise), R3-legacy-inflight-render-postprocess-key (pending pre-V6c renders index
  `params["postprocess"]` with no test), R2-task-doc-v6c-misdescribes-impl (V6c task text says `chin_row` and
  "unload CatVTON"); suggestions: R2-shoe-row-threshold-unscaled, R3-tone-fallback-assumes-default-present,
  R4-unguarded-variant-delete, R3-task-doc-mismatch.
- 2026-10-13 V6c follow-up (delegated writer, owner: "si adelante"): 33a815a `fix(tryon): retry the dummy on
  resubmit and harden its failure path`; 4 files, +245/-30. A done render whose dummy failed (dummy postprocess,
  no `params.dummy`) is re-queued on resubmit (202, shared re-queue reset, `img_path` kept) while `attempts <
  MAX_RENDER_ATTEMPTS`; past the budget it is served raw. Rollback deletes guarded with `except OSError`.
  Pre-V6c pending renders end as `invalid_params` (already true through `_validate_params`; now pinned by a test,
  reads use `.get`). Checks (writer): ruff format/check, ty clean; pytest 1027 passed. Parent spot check:
  test_api_tryon + test_tryon_worker 104 passed. Assess (base b197b02): medium, under budget, pending in the next
  slice.
- 2026-10-13: #69 (V6c) merged as 64ce22b; owner: "si, adelante" to V6d.
- 2026-10-13 V6d (delegated writer with frontend-design, ux-copy, design-critique, accessibility-review loaded):
  bbe4d07 `feat(app): let the owner pick the try-on model in settings`; 18 files, +500/-1 (12 preview WebPs,
  about 186 KB, 450x600). `ModelSettingsCard` at the top of Ajustes: 3:4 preview on linen (radial gradient on web,
  vertical on native), Mujer/Hombre (`Segmented`, shown with 2+ offered genders), 6 tone radios (44x44, "Tono N de
  6", ring + check), saves on change (optimistic, reverts with an inline error), "Guardado", hidden when try-on
  is disabled or capabilities are unknown; offline disables it. Hoy follows: tone change invalidates
  `tryon.details()`; gender change resets `tryon.byLooks()` so "Verlo puesto" asks again (not automatic, to avoid
  GPU work and offline failures). Previews generated by
  `~/pachapp-data/eval-results/tryon-v6d-previews-2026-10-13/make_previews.py` (shipped pipeline, CPU) from the
  spike raws `round2/raw/m12-woman_g04.png` and `m13-man_g04.png`. Checks (writer): typecheck, lint, prettier
  clean; jest 486 passed (+10; one known load flake in garment-detail.test.tsx on the first full run, also on the
  base; rerun green). Parent: browser check on Expo web (:8091) against a migrated data copy (API :8010):
  screenshots in `~/pachapp-data/eval-results/tryon-v6d-ui-2026-10-13/` (phone 390 px and 1280 px), choosing tone 6
  and Hombre saved `man`/6 on the server, no console errors. Not checked on the phone.

## Next step

Review of the V6d slice (base b197b02, includes 33a815a), PR for V6d, then V6e. The owner's DB needs `make migrate` before running V6b code.
