# U5 — Garment-only cutout

## Objective

Cut out only the garment, not the person wearing it or other clothes, so the collage, the colours and the
future virtual try-on (`docs/specs/09-virtual-tryon.md` §12.4) get clean garment images.

## Problem / why

BiRefNet (`backend/src/worker/steps/cutout.py`, `ml/background.py`) removes the background but keeps every
foreground object: on photos of a garment being worn the cutout includes arms, face, trousers. That pollutes
colour extraction (trousers counted as "negro 27 %", owner test 2026-09-30), the Hoy collage and any try-on
input. Originally task U5 in `odd/tasks/ux-probador.md` (research notes there, 2026-09-30); the first
evaluation spike was OOM-killed (WSL ~7-8 GB RAM with the owner's stack running) and its scratch output lost.

## Scope (owner decisions)

- 2026-09-30: personal use only -> non-commercial model licences are acceptable (SegFormer clothes).
- 2026-09-30: evaluate SegFormer clothes against `rembg` `u2net_cloth_seg` on the eval photos and keep the best.
- 2026-10-04: do U5 before the virtual try-on so it gets clean garment images.

Design (from the U5 task): human-parsing mask (candidate SegFormer b3/b2 clothes, fallback `u2net_cloth_seg`)
intersected with the BiRefNet matte; keep the class set of the garment (from its category, or the largest
clothing region when the category is not known yet); skip parsing when no person is present; colours from the
eroded garment mask; fall back to today's matte + `needs_review` when the garment mask is too small.

## Research notes (2026-09-30, web research, unbenchmarked; see ux-probador.md)

- `u2net_cloth_seg` (rembg): upper/lower/full classes, MIT, cheapest; coarse, no shoes/accessories.
- SegFormer clothes (mattmdjaga b2, sayeed99 b3): 18 ATR classes incl. upper-clothes, pants, skirt, dress, shoes,
  bag, scarf, belt, hat, arms/legs/face; mIoU ~0.69; licence non-commercial (accepted).
- FASHN parser / Sapiens: better but heavier or non-commercial; GroundingDINO/SAM2: over budget.
- Gaps: latency/VRAM on the RTX 2060, ONNX export, quality on our photos.

## Tasks

- [x] **U5a** Evaluation tooling (reusable, like `make ml-eval`): run current BiRefNet vs BiRefNet + SegFormer
  (b3 and/or b2) vs BiRefNet + `u2net_cloth_seg` on the eval sets in `~/pachapp-data/eval` (and the owner's
  photos under `~/pachapp-data-test/images`), select person-worn photos, write contact sheets, a colour proxy
  (dominant colours before/after), per-image latency, peak VRAM and peak RAM; unit tests with fakes, no models
  or network in `make test` (VIS-REQ-029).
- [ ] **U5b** (first run 2026-10-04 inconclusive: no worn photos; waiting for the owner's worn photos) Run the evaluation with the stack stopped (API, worker, Expo) -> report -> owner picks the parser.
- [ ] **U5c** Integrate the chosen parser in the worker cutout step (class selection, no-person skip, eroded
  colour mask, small-mask fallback + `needs_review`), keeping GPU use serial (VIS-REQ-025) and VRAM within the
  6 GB budget alongside SigLIP; tests with fakes.
- [ ] **U5d** Re-cut existing garments (backfill-style command, idempotent, never touching user edits) and owner
  check on real photos.

## TDD / checks

TDD: off (no project/session TDD configuration). Backend: `uv run ruff check .`, `uv run ruff format --check .`,
`uv run ty check src`, `uv run pytest`. Real-model runs only in U5b/U5d, with the stack stopped.

## Delivery

Branch `feat/u5-garment-cutout` from `main` `4e397d6`. Forecast ~600-1,000 lines -> stacked-to-main slices
(U5a, U5c+U5d).

## Routes

- U5a, U5c: delegated writer (backend ML, several files). U5b, U5d: parent runs with the owner's stack stopped.

## Progress

- 2026-10-04: feature document created; spec 09 (try-on) merged as #45.

- 2026-10-04: U5a `a001b79` (delegated writer): `ml/garment_parse.py` (`GarmentParser`, `SegformerClothesParser`
  b3/b2 fp16 on CUDA, `U2NetClothParser`, category -> class sets, `person_present`, `garment_mask`/`cut_garment`
  with small-mask fallback, `erode_alpha`; thresholds `MIN_GARMENT_RATIO` 0.01, `MIN_PERSON_RATIO` 0.02,
  `COLOR_ERODE_PX` 4), `ml/cutout_eval.py` + `make ml-cutout-eval CUTOUT_EVAL_ARGS=...` (BiRefNet mattes cached
  then freed, one parser at a time, serial; warm median/p95 latency, nvidia-smi VRAM sampling, torch peak,
  /proc RSS; contact sheets + `report.md` flagging dominant-colour changes; `--worn-only`, `--methods`,
  `--limit`; optional `labels.json` for categories), settings `PACHAPP_ML_PARSE_B3/B2_REVISION` (moving refs
  rejected). No new dependencies. Checks: ruff, format, ty clean; pytest 652. RED probes. Never run on real
  models. Expected downloads: segformer b3 ~190 MB, b2 ~110 MB, u2net_cloth_seg ~170 MB.

- 2026-10-04: U5b first run (parent, stack stopped): all four methods over `public-garments`, `public-sample`,
  `public-test-full` and `~/pachapp-data-test/images` with `--worn-only`: 356 photos, only 2 "with a person" and
  both false positives (sandals, skin-toned insoles); 354 skipped. The eval sets are flat-lay product photos, so
  the run cannot measure the target case (garment worn by a person). Findings: (1) on non-person photos the
  parser is harmful (SegFormer b3 shredded both sandal cutouts; b2 fell back; u2net fell back on one, shredded
  the other) -> the no-person skip is essential and `person_present` must be stricter (e.g. require face/arms,
  not any skin-like class; raise `MIN_PERSON_RATIO`); (2) cost: BiRefNet 706 ms; +SegFormer b3 785 ms (torch peak
  ~322 MB, fits next to SigLIP); +b2 1044 ms (~284 MB); +u2net-cloth 906 ms (~3.5 GB total VRAM sampled). Peak RSS
  ~2.4-2.5 GB. Report + contact sheet saved to `~/pachapp-data/eval-results/u5-2026-10-04/`. Stack left stopped.

## Next step

Owner provides 20-30 photos of garments worn (several categories; optional `labels.json`) in a folder (e.g.
`D:\Educcio\pachapp-eval-worn\` or `~/pachapp-data/eval/worn/`); rerun `make ml-cutout-eval` on it with the stack
stopped (drop `--worn-only` or keep it to test the person check), then the owner picks the parser; tighten
`person_present` in U5c.
