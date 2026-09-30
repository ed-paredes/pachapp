# Local vision ML — SPEC-ML steps 1–3

Locator: `odd/tasks/local-vision-ml.md` · Engram mirror: `odd/local-vision-ml/tasks`
Spec: `docs/specs/08-local-vision.md` (PR #4). Branches stacked on `docs/spec-ml-local-vision`: `feat/ml-1-registry` (T1) → later slices for T2/T3.

## Objective

Implement the steps of 08-local-vision.md that need no database (plan steps 1–3): model registry + device selection + preload, BiRefNet cutout, SigLIP embedder + zero-shot + evaluation script. Priority set by the user (2026-09-28).

## Constraints

- 08-local-vision.md is authoritative (VIS-REQ-*). `ml` is worker-only; `api` never imports it; `engine` stays pure.
- torch variant: **CUDA** (user decision 2026-09-28; RTX 2060 6 GB in WSL, driver 591.86, ~7 GB RAM in WSL).
- `make test` never downloads models or touches the network (VIS-REQ-029).
- Allowed deps per SPEC-ML: torch, open_clip_torch, rembg, pillow, numpy, scikit-learn; anything else (e.g. onnxruntime-gpu for rembg on CUDA) must be named in the report and justified.
- Eval photos: provided later by the user, outside the repo (`PACHAPP_ML_EVAL_DIR`). T2/T3 "done when" gates need them.

## TDD

Mode: off (no project/session TDD configuration). Runner: `uv run pytest` (backend). Ordinary functional checks apply.

## Tasks

- [x] **T1 — Step 1: settings, `ml` package skeleton, registry + device, preload.** Route: delegated direct (writer trigger: settings, ml package, worker, tests, Makefile, pyproject).
  - `PACHAPP_ML_*` settings (08 table), conditional `PACHAPP_LLM_*` (VIS-REQ-021 / DEV-REQ-011), cache dir under data dir with D14 guard, `HF_HOME`/`U2NET_HOME` derived in the worker (VIS-REQ-008), pinned embed revision (VIS-REQ-002), `api`↛`ml` test (VIS-REQ-005), `make ml-preload`.
  - Done when (08 step 1): `make ml-preload` downloads BiRefNet and SigLIP into `PACHAPP_ML_CACHE_DIR` and `ml.registry` reports the selected device (expected `cuda`).
- [x] **T2 — Step 2: BiRefNet cutout (`BackgroundRemover`).** Gate needs the user's photos (18/20 clean cutouts). Branch `feat/ml-2-cutout` (stacked on `feat/ml-1-registry`). Route: delegated direct (writer trigger: background.py + tests + CLI + Makefile/README).
  - `ml/background.py`: `remove(img) -> RGBA cropped to bbox` (08 interfaces); near-empty mask raises a dedicated error so the worker's `cutout` step (plan step 4) can apply ING-SCN-005's soft failure (fallback to the preprocessed image + `needs_review`). Empty-mask threshold is a documented tunable default.
  - Gate helper: `python -m ml.cutout_preview` / `make ml-cutouts` writes cutouts from `PACHAPP_ML_EVAL_DIR` (or a CLI dir) to an output dir for visual inspection, with per-image timing (VIS-REQ-026 context). Not in 08's CLI list — named in the report as a gate aid.
- [x] **T3 — Step 3: embedder + zero-shot + `make ml-eval`.** Gate: ≥85 % category accuracy without kNN. Branch `feat/ml-3-zero-shot` (worktree `~/pachapp-worktrees/ml-3`, from main `eff0114`). Route: delegated direct (writer trigger: embedder, taxonomy, zero_shot, eval CLI, tests, Makefile/README).
  - `GarmentEmbedder.embed_image/embed_texts` (L2-normalized, text cache); `ml/taxonomy.py` (08 TAXONOMY with enum keys, prompt templates, prompt→subcategory, VIS-REQ-011/012); `ml/zero_shot.py` (softmax single-label VIS-REQ-013, low-confidence/margin rule VIS-REQ-016, ordinal formality VIS-REQ-017, multi-label style_tags VIS-REQ-018, `{value, confidence, source}` VIS-REQ-019); `python -m ml.eval` / `make ml-eval` (cutout → embed → zero-shot; per-attribute accuracy, category confusion matrix, % needs_review, mean time per garment — VIS-REQ-028/030). Seasons/warmth rules (VIS-REQ-012) and kNN are out of scope (step 4 / later).
  - Eval sets (outside the repo, from the CC0 public dataset; user's own photos still welcome): `~/pachapp-data/eval/public-garments` (36 photos, 4 per class — gate set) and `~/pachapp-data/eval/public-test-full` (300 photos). Class mapping: dress→one_piece, hat→accessory, outwear→outerwear, pants/shorts/skirt→bottom, shirt/t-shirt→top, shoes→shoes. `longsleeve` is excluded: the dataset mixes long-sleeve tees (top) and sweaters (mid_layer). No mid_layer examples in the public set.
  - Implementation (writer, 2026-09-29): `embed_image`/`embed_texts` are methods of `GarmentEmbedder` in `ml/registry.py` (image: EXIF + RGBA-over-white via `background._to_rgb`, `no_grad`, L2-normalized float32; texts: per-text in-process cache). `ml/taxonomy.py` (08 TAXONOMY with enum-value keys, templates, prompt->subcategory dict, `expand_prompts`), `ml/zero_shot.py` (pure numpy math + `ZeroShotClassifier`, ensemble = mean of prompt x template embeddings re-normalized, computed once at construction), `ml/eval.py` + `make ml-eval [EVAL_DIR=...]`, preload now also embeds the taxonomy and prints the prompt count. Defaults: needs_review_threshold 0.7, margin = `settings.ml_margin_threshold`; style_tags = `sigmoid(100 * (cos_sim - 0.10))`, keep tags with p >= 0.5, max 3 (uncalibrated, tunable); formality std = probability-weighted std of the ordinal values, confidence `1 - std/2`, value = half-up rounded weighted mean clamped to [1,5]; subcategory confidence = softmax among the chosen category's prompts. Low-confidence rule (VIS-REQ-016) is applied to category, pattern, material, formality (formality: confidence < threshold only, no margin); subcategory and style_tags never trigger it.
  - Eval (a) `public-garments` (36 photos, cutout on): category 94.4 % (34/36; gate 85 % met), subcategory 90.0 % (18/20); both errors are dress -> top; needs_review 94.4 % (low-confidence by attribute: category 3, pattern 8, material 25, formality 18); cutout mean 3.2 s (2.3 s on a quieter run), embed+classify ~0.02 s per garment; 0 empty cutouts.
  - Eval (b) `public-test-full` (300 photos): category 97.0 % (291/300), subcategory 82.2 % (111/135). Errors: 7 dress -> top, 1 hat -> top, 1 outwear -> mid_layer. needs_review 90.3 % (category 14, pattern 101, material 178, formality 184); cutout mean 2.31 s / median 2.29 s, embed+classify mean 0.019 s; 0 empty cutouts. Pattern/formality accuracy not measured (public labels have neither).

## Delivery

Forecast: T1 ~400–600 authored lines (lockfile excluded). Strategy `ask-on-risk`; chain strategy reused from phase 0: stacked-to-main, one PR per step.

## Progress

- 2026-09-28: PR #4 (specs) opened; torch variant CUDA chosen; branch `feat/ml-1-registry` created from `docs/spec-ml-local-vision`.

## T1 verification (2026-09-29, resumed session)

- `ruff check`, `ruff format --check`, `ty check src`: pass. `make lint/fmt-check/typecheck`: pass (backend + app). `uv run pytest`: 80 passed (76 before the guard below + 4 new). App jest: 3 passed.
- **Defect found and fixed on resume:** `onnxruntime-gpu 1.30.0` (via `rembg[gpu]`) is built against CUDA 13, but torch came from the cu126 index (CUDA 12 libs), so the ORT CUDA provider failed to load and rembg ran BiRefNet on CPU with only a warning. Fix: torch/torchvision moved to the `pytorch-cu130` index (driver 591.86 supports CUDA 13.1); new `ml.device.check_session_providers` makes `get_background_remover` raise instead of silently falling back to CPU on `cuda`.
- `make ml-preload` (cache `~/pachapp-data-test/models`, revision `c56244cc…`): device `cuda`, BiRefNet session on `CUDAExecutionProvider`, embedding dim 768, cache size unchanged before/after (5 543 440 KB) → no re-download. Elapsed 194 s, of which ~104 s is importing torch/open_clip/rembg/transformers from `backend/.venv` on `/mnt/d` (9p) — environment cost, not code.
- Deps beyond SPEC-ML's base list: `torchvision` (open_clip), `transformers` + `sentencepiece` (Marqo-FashionSigLIP's HF tokenizer), `onnxruntime-gpu` via `rembg[gpu]` (CUDA inference for BiRefNet; avoids the conflicting CPU `onnxruntime`).
- Route: delegated direct (writer, previous session); resume fixes inline (2 small mechanical edits + test).

## T1 native review (2026-09-29)

- Commit `516183e` assessed high (subprocess in the api↛ml boundary test); consent granted by the user; 4-lens review `review-a661f49fafcd1a10` **approved** and acknowledged (authority burned). Reviewed boundary → `516183e`.
- 12 advisory (non-blocking) findings. Fixed in a follow-up commit (route: delegated direct writer, 6 files): moving-ref guard for `PACHAPP_ML_EMBED_REVISION` (rejects latest/main/master/HEAD/refs/heads/*, accepts SHA or tag — the spec allows "commit/tag", so no 40-hex requirement) with VIS-REQ-002 in its errors; `.env.example` no longer points to a non-existent `make reembed`; pyproject comment points here instead of an external "report"; comment on the 08-table defaults; `test_ml_cache` env isolation via monkeypatch; new `test_ml_registry.py` (fake rembg, no torch/network). pytest 92 passed.
- Not changed, by decision: `PACHAPP_ML_EMBED_REVISION` stays required for every process incl. the API (08 table says "obligatorio"; findings R3/R4 suggested validating it only in the worker) — **open question for the user**. Duplicated `ml_cache_dir` assert (suggestion) left as is.

## T2 progress (2026-09-29)

- Implemented by a delegated writer: `ml/background.py` (`BackgroundRemover` Protocol, `BiRefNetRemover`, torch-free `alpha_coverage`/`crop_to_foreground`, `EmptyCutoutError` for ING-SCN-005 with `OPACITY_THRESHOLD=10`, `MIN_COVERAGE=0.5%` as tunable defaults), gate aid `python -m ml.cutout_preview` / `make ml-cutouts`, `test_ml_background.py`. Checks: ruff, format, ty pass; pytest 106 passed.
- **Performance finding (blocks VIS-REQ-026 `<2 s` on the RTX 2060):** smoke on 3 synthetic 1024 px images took 18–41 s/image on cuda. Isolated ORT benchmark (steady-state, per image): `birefnet-general` fp32 14 s (4.2 s with `cudnn_conv_algo_search=HEURISTIC` + `arena_extend_strategy=kSameAsRequested`); `birefnet-general` fp16 9 s; `birefnet-general-lite` fp32 6.5 s; **`birefnet-general-lite` fp16 0.66 s**, masks vs fp32 IoU ≥ 0.9998. Root cause: fp32 BiRefNet at 1024 px needs more than the ~5.5 GB free VRAM (a single 822 MB tensor on the lite model; `gpu_mem_limit=3 GB` OOMs), so the Windows driver spills to shared system memory. All nodes are placed on the CUDA provider (no CPU fallback).
- **Decision taken by the user (2026-09-29): (a)** default background model `birefnet-general-lite` converted to fp16 on `cuda`. Implemented by a delegated writer: `ml_bg_model` default `birefnet-general-lite`, new `ml_bg_fp16=True` (`PACHAPP_ML_BG_FP16`); `ml/bg_fp16.py` (pure `should_use_fp16`/`fp16_path`/`model_precision`, `ensure_fp16_model` converting once with atomic tmp+`os.replace`, lazy `onnx`/`onnxconverter_common`); registry builds the session from a subclass of rembg's session class whose `download_models` returns the fp16 file (rembg pre/post-processing untouched); CUDA provider options `HEURISTIC` + `kSameAsRequested` (`ml.device.CUDA_PROVIDER_OPTIONS`) passed as a `(name, options)` tuple, `check_session_providers` still guards the no-silent-CPU fallback; `ml-preload` converts, prints BG file/precision and times one warm 1024 px inference. Deps added: `onnx`, `onnxconverter-common`. Docs (08 spec table + VIS-REQ-026 note, `.env.example`, README) updated. Smoke (cache `~/pachapp-data-test/models`, cuda): `make ml-preload` converted once and reports `birefnet-general-lite.fp16.onnx (fp16)`, warm synthetic 1024 px 1531 ms/image, elapsed 233.8 s; `ml.cutout_preview` on 3 images: 121 233 ms first (warm-up incl. session init from /mnt/d, unexplained beyond that), then 1975 and 1672 ms, median 1823 ms (< 2000 target, but ~1.1 s above the 0.66 s ORT-only figure: rembg's LANCZOS resizes/post-processing on CPU, not optimised). Pipeline still has cutout + embedding to add, so the < 2 s per-garment budget is tight.
- Gate (18/20 clean cutouts) waits for the user's eval photos.

## ML slice review and public-sample check (2026-09-29)

- Branches rebased onto main after PRs #5–#9 (T1 `bd1c1d9` = old `516183e`). Rebase surfaced a semantic conflict: data model tests built `Settings` without the required embed revision — fixed in `0d5cec4`.
- Native review of `bd1c1d9..0d5cec4` (review-c0145b3e15e7f24f, user granted): approved and acknowledged. Advisory findings fixed in a follow-up commit: `ml-cutouts` output names keep the input filename (`a.jpg.png`) so same-stem inputs no longer overwrite each other; loop tests (success, warm-up excluded from median, empty mask, collision); fp16 session uses the same ORT SessionOptions as rembg's `new_session`; error-path tests. pytest 163 passed.
- Public sample (not the spec's gate set): CC0 `alexeygrigorev/clothing-dataset-small`, 20 photos (2 per class, test split, ~400 px) → 20/20 non-empty, median 1568 ms/image, visually 18/20 clean (fails: beige shorts with a hole; white-striped tee on a white sheet). Hangers kept in ~7. **Gate accepted by the user on 2026-09-29 with this public sample** (18/20 clean); re-run `make ml-cutouts` on the user's own photos when available.

## Follow-ups

- `snapshot_download` fetches every file of the pinned revision (~5 GB cache); add `allow_patterns` for the files open_clip's `local-dir:` loader needs. Needs a clean-cache download to verify — do with T3.

- Worker cold start ~100 s from `/mnt/d` imports: consider a checkout on WSL ext4 or `UV_PROJECT_ENVIRONMENT` outside `/mnt` before T2 perf measurements (VIS-REQ-026 budget is per garment, not startup).
- `.env` / `.env.test` lack `PACHAPP_ML_EMBED_REVISION` (required, no default): user must add it.

## Next step

T1 committed (`516183e` reviewed+acknowledged, `8314fd0` follow-up, medium/under budget → pending in slice). PR #4 already merged into main, so the T1 PR targets `main`; push/PR await the user. Then T2 (needs the user's eval photos for its gate).
