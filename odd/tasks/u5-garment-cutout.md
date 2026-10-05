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
- [x] **U5b** (first run 2026-10-04 inconclusive: no worn photos; waiting for the owner's worn photos) Run the evaluation with the stack stopped (API, worker, Expo) -> report -> owner picks the parser.
- [x] **U5b2** (owner 2026-10-05: "vamos con las 2 y luego decidimos") Eval round 3: add a subtractive mask mode
  (BiRefNet matte minus body classes face/hair/arms/legs/neck, holes filled) next to today's intersect mode, and
  two new parsers, FASHN Human Parser (SegFormer-B4) and SCHP (ATR/LIP), to the eval tooling; rerun on
  `~/pachapp-data/eval/worn/` with the stack stopped -> owner picks parser + mask mode. Route: delegated writer
  (eval tooling, 2+ non-trivial files + tests + model research); parent runs the eval.
- [x] **U5c** Integrate the chosen parser in the worker cutout step (class selection, no-person skip, eroded
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

- 2026-10-05: U5b second run (parent, stack stopped) on 29 owner photos in `~/pachapp-data/eval/worn/` (no
  `labels.json`, so the parser keeps the largest clothing region; no `--worn-only`). Results in
  `~/pachapp-data/eval-results/u5-2026-10-05/`. Cost: BiRefNet 545 ms; +b3 678 ms (torch ~321 MB); +b2 661 ms
  (~284 MB); +u2net 732 ms (3/29 fallbacks). Colours improve clearly on worn photos (e.g. negro 83% -> 99%,
  blanco 74% -> 96%, marino 40% -> 77%; skin/legs no longer counted). Quality: every parser removes face, arms
  and legs well on clean tops/bottoms, but each one shreds or punches holes in ~1/3 of the photos (b3 ~12, b2
  ~10, u2net ~10 by eye): dark shorts, stripes, denim, boots, pleated skirt; u2net dissolved a printed dress.
  The holes come from intersecting with one garment class (part of the garment is labelled as another class).
  Non-worn photos (flat sneakers, shoe, jacket on a hanger) are harmed by every parser -> the no-person skip
  stays essential. Waiting on the owner's choice.

- 2026-10-05: U5b2 implementation (delegated writer; U5b2 stays open until the real run). `ml.garment_parse`:
  `cut_garment(..., mode="intersect"|"subtract")`; subtract = BiRefNet matte minus body classes (hair, face,
  arms/legs/hands/torso/neck, sunglasses, jewelry) and, with a `labels.json` category, other-garment groups
  (top/mid_layer/outerwear: pants/skirt/footwear/hat/bag/scarf/belt; bottom: upper/coat/footwear/hat/bag/scarf;
  one_piece: footwear/hat/bag; shoes: keep only shoe/feet pixels), then `scipy.ndimage.binary_fill_holes` (body
  pixels are never refilled); same small-mask fallback. Shared label vocabulary extended (FASHN `top`->
  `upper_clothes`, `glasses`->`sunglasses`, `arms/legs/hands/feet/torso/jewelry`; LIP `coat/jumpsuits/socks/glove`).
  New parsers: `fashn` = `fashn-ai/fashn-human-parser` (SegFormer-B4, 18 classes, 384x576, ~64M params, licence
  NVIDIA SegFormer source licence = non-commercial; reuses the transformers path; revision pinned in
  `PACHAPP_ML_PARSE_FASHN_REVISION`, default `1f80c34d...` read from the Hub API; FASHN has no shoe class, `feet`
  stands in); `schp-atr` / `schp-lip` in new `ml/schp.py` = pure-PyTorch re-implementation of the SCHP
  AugmentCE2P ResNet-101 inference path (no `inplace_abn` compiled op, no OpenCV; MIT code by Peike Li, attribution
  in the header), checkpoints from HF `zhengchong/CatVTON` `SCHP/*.pth` (~267 MB each, CC BY-NC-SA 4.0 repo; same
  files CatVTON uses), pinned by `PACHAPP_ML_PARSE_SCHP_REVISION` (default `2969fcf8...`) and sha256-verified
  before unpickling. Unverified until the real run: that the ABN `abs(weight)+eps` port reproduces the compiled op
  (checkpoint load is `strict=True`; check the contact sheet for sane SCHP masks). Eval: `--mask-modes` (default both),
  each parser parsed once per photo and combined per mode; columns/folders/sheets `birefnet+<parser>.<mode>`. No
  new dependency (scipy already comes with scikit-learn; torch/huggingface_hub/transformers already present).
  Checks: ruff, ruff format, ty, pytest 672 passed.

- 2026-10-05: U5b2 review: four-lens native review granted by the owner, approved without correction and
  acknowledged (lineage review-ea9b5bd59558891f, base 4e397d6, through d583e42). 11 non-blocking advisories kept
  for U5c: parser failure aborts the whole run, photo-key collision across dirs, matte-size assumption, eval-dir
  assert, unpinned b2/b3 revision defaults, duplicated GPU release, small CLI validation/naming nits.

- 2026-10-05: U5b2 run (parent, stack stopped) on the 29 worn photos, all parsers x both modes; results and
  focused sheets (`focus_1..4.jpg`: orig, birefnet, b2.subtract, fashn.intersect/subtract,
  schp-atr.intersect/subtract, schp-lip.subtract) in `~/pachapp-data/eval-results/u5-2026-10-05-r3/`.
  Findings by eye: (1) subtract mode removes the shredding for every parser (no holes), but without a category
  it keeps the other garments (jeans under a sweatshirt or jacket, the top above shorts, the skirt under a
  top). (2) FASHN intersect is the best clothing cutout: removes skin and the other garments with almost no
  holes (jacket, sweatshirt, shorts, crop tops, denim tube, skirt, dress); it fails on footwear (no shoe class:
  boots shredded, converse keep legs) and, like every parser, on non-worn photos. (3) SCHP-ATR intersect shreds
  like SegFormer b3; SCHP-LIP subtract leaves necks/faces/arms; SCHP brings no advantage and is the slowest
  (889-940 ms, ~560 MB torch). (4) Cost: FASHN 838 ms vs BiRefNet 579 ms, torch peak ~320 MB.
  Recommendation to the owner: FASHN; clothing -> intersect with the garment group + hole fill; footwear and
  accessories -> subtract body only; no person -> keep the matte. Waiting on the owner's choice.

- 2026-10-05: owner decision ("si daleeee"): FASHN Human Parser for U5c with the rule: clothing -> intersect
  with the garment group + hole fill; footwear and accessories -> subtract body only; no person -> keep the
  BiRefNet matte. U5b and U5b2 closed. U5c+U5d go on branch `u5/02-worker-cutout`, stacked on
  `feat/u5-garment-cutout` (slice 1: eval tooling U5a+U5b2). Eval-tool review advisories (parser failure
  aborts the run, key collision, matte size, eval-dir assert, exit code, --limit validation, duplicated GPU
  release, b2/b3 revision defaults) stay as follow-ups unless U5c touches that code.

- 2026-10-05: U5c (delegated writer; route: delegated direct, trigger: 2+ non-trivial files). Pipeline order
  finding: `preprocess -> cutout -> color -> ai_attributes -> embedding -> consolidate` (ING-REQ-006) and the
  upload creates the garment with no category, so on a fresh upload the category is NOT known at cutout time
  (A15 classifies after the cutout). Chosen option (a), no reordering (moving `ai_attributes` before `cutout`
  would change which image SigLIP embeds and the A15 behaviour): the cutout step reads `garment.category` from
  the database (set on a retry/reprocess or by the user) and otherwise uses the unknown-category path
  (largest clothing region). Rules in `ml.garment_parse.cut_garment_by_rule`: no person -> BiRefNet cutout
  unchanged; clothing -> intersect with the category's class group (bottom = pants+skirt; FASHN has no
  separate shorts class, shorts are `pants`) + `fill_garment_holes` (enclosed matte pixels that are not body);
  `shoes`/`accessory` -> subtract body classes only (`body_only`); unknown -> largest clothing region + hole
  fill. Small mask (< 1 % of the image) or parser exception -> BiRefNet matte kept and `ctx.data["cutout_review"]`
  (`garment_mask_too_small` / `garment_parser_failed`), which `consolidate` turns into `needs_review`. Colours:
  the cutout step leaves `ctx.data["color_image"]` = `erode_alpha(cutout)` (4 px) and `color` samples it; a
  job resumed from disk without it falls back to the stored cutout. `person_present` is now stricter: face
  >= 0.5 % (`MIN_FACE_RATIO`) OR arms/hands/legs >= 5 % (`MIN_PERSON_RATIO`, was 0.02 on any person class);
  hair, torso, neck, jewelry and skin-like classes alone never count; vocabularies without face/limb classes
  (U2Net) keep the clothing fallback. The parser needs the uncropped matte, so `BiRefNetRemover.matte()` /
  `finish_full()` were added (`remove` = bbox crop of it; `MatteRemover` runtime protocol); a remover without
  `matte` (test fakes) skips parsing. GPU strategy: FASHN is built lazily on the first job and kept resident,
  like BiRefNet and SigLIP (~130 MB fp16 weights, ~320 MB torch peak); the single worker runs matte then
  parse serially on the job thread (VIS-REQ-025). Setting `PACHAPP_ML_GARMENT_PARSE` (`ml_garment_parse`,
  default true); off = today's behaviour. Also renamed `_SEGFORMER_CLOTHING` -> `_ATR_CLOTHING` and added
  `CLOTHING_CLASSES` (review advisory R2). Spec 08 updated (VIS-REQ-031, models row, settings row, VIS-REQ-025),
  `.env.example`. Tests: `tests/unit/test_worker_cutout_parse.py` + new cases in `test_ml_garment_parse.py`
  (fakes only). Checks: ruff format/check, ty, pytest 691 passed. Open for U5d (real photos): flat-lay sandals
  and insoles under FASHN `person_present`; footwear with an unknown category on a worn photo (largest clothing
  region is wrong for shoes until a re-cut with a known category); `make ml-preload` does not fetch FASHN yet.
  Correction (review lineage review-64c35701e702c6b6, R3-fresh-upload-footwear-misroute): unknown category now
  picks the largest of clothing/footwear/carried groups (items -> subtract body only) and keeps a lost item group
  covering >= `MIN_UNSELECTED_ITEM_RATIO` (0.10) of the matte via subtract, setting `cutout_review` = `garment_item_kept`.

- 2026-10-05: U5c review (owner granted; medium, one reliability lens, lineage review-64c35701e702c6b6, base
  d583e42 through 3fc2ed8): one CRITICAL finding (fresh uploads with worn shoes/bags lost the item on the
  unknown-category path) fixed in the single bounded correction 3fc2ed8 (delegated writer, +100/-5),
  targeted validation approved, acknowledged. pytest 693. Advisories for later: BiRefNet matte/finish_full
  refactor has no direct test; broad except in the cutout step can mask DB errors; the eroded colour image is
  not persisted, so a resumed job samples the uneroded cutout. Next: U5d (re-cut command, `make ml-preload`
  fetches FASHN, owner check on real photos with the stack stopped).

## Next step

Owner provides 20-30 photos of garments worn (several categories; optional `labels.json`) in a folder (e.g.
`D:\Educcio\pachapp-eval-worn\` or `~/pachapp-data/eval/worn/`); rerun `make ml-cutout-eval` on it with the stack
stopped (drop `--worn-only` or keep it to test the person check), then the owner picks the parser; tighten
`person_present` in U5c.
