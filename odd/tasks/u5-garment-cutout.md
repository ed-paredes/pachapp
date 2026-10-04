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

- [ ] **U5a** Evaluation tooling (reusable, like `make ml-eval`): run current BiRefNet vs BiRefNet + SegFormer
  (b3 and/or b2) vs BiRefNet + `u2net_cloth_seg` on the eval sets in `~/pachapp-data/eval` (and the owner's
  photos under `~/pachapp-data-test/images`), select person-worn photos, write contact sheets, a colour proxy
  (dominant colours before/after), per-image latency, peak VRAM and peak RAM; unit tests with fakes, no models
  or network in `make test` (VIS-REQ-029).
- [ ] **U5b** Run the evaluation with the stack stopped (API, worker, Expo) -> report -> owner picks the parser.
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

## Next step

U5a with one delegated writer; then ask the owner to stop the stack for U5b.
