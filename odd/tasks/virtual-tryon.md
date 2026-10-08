# Virtual try-on ("Verlo puesto") with CatVTON

## Objective

Show an outfit worn on a neutral model, generated locally with CatVTON on the worker GPU, as an on-demand,
asynchronous extra view next to the collage on Hoy (`docs/specs/09-virtual-tryon.md`).

## Status

Spec stored in the repo with integration notes (§12) on 2026-10-04. Owner decision 2026-10-04: do U5
(`odd/tasks/u5-garment-cutout.md`) first so the try-on gets clean garment images. 2026-10-05: owner started
V0 assuming U5 done (U5a in review); V0a tooling done, V0b (real run) pending. 2026-10-07: V0b-V0f run.
2026-10-08: owner closed V0 ("alpha: the simple, recommended option"): config C, mannequin M12 alone; V1 started.

## Key constraints (from §12)

- RTX 2060 6 GB (fp16); the worker already holds BiRefNet + SigLIP (5.7 of 6 GB measured) -> unload before
  CatVTON, reload after.
- WSL RAM ~7 GB: the spike runs with API, worker and Expo stopped and measures peak RAM and VRAM.
- Own `tryon_renders` table and states; uploads keep priority in the worker.
- Licence CC BY-NC-SA 4.0: personal use only; CatVTON code as an external pinned dependency.

## Tasks (spec §10)

- [x] **V0** Spike + report (§4, plus peak RAM, current vs clean cutouts) -> stop for the owner's validation.
  - [x] **V0a** Tooling: `ml/tryon_spike.py` + `make tryon-setup|tryon-masks|tryon-spike`,
    `backend/scripts/tryon_build_masks.py`; unit tests with a fake dresser.
  - [x] **V0b** Run on the RTX 2060 with the stack stopped -> report -> owner validates (§4 criterion).
  - [x] **V0c** (owner 2026-10-07: V0b not conclusive, more tests with 9 free-licence mannequins) Spike tooling:
    `--seeds`, config D 768x1024/20 (native CatVTON resolution), an `overall` case for one-piece garments,
    a per-garment-set comparison sheet across mannequins. Route: delegated writer. Delivery: PR + review + merge.
    Merged in #49.
  - [x] **V0d** Broad round (stack stopped): 9 mannequins (Pexels/Unsplash licence, sources in
    `~/pachapp-data/tryon/candidates/SOURCES.md`) x ~8 garment sets from the owner's FASHN cutouts, config C,
    one seed -> which mannequins and garment types work.
  - [x] **V0e** Fine round: best 2-3 mannequins x C and D x 3 seeds -> config choice and seed variance ->
    owner picks mannequin and config (closes V0). Owner 2026-10-07: M1, M2, M8.
  - [x] **V0f** Short garments (shorts, skirts) fail on long-trouser mannequins (V0d): 3 bare-leg mannequins
    M10-M12 (Pexels) with CatVTON's lower mask and with a mask trimmed to the garment length.
- [x] **V0 decision** (owner 2026-10-08): config C (576x768, 20 steps, guidance 2.5, seed 42, fp16) and
  mannequin M12 (`m12-woman-crop-shorts`, Pexels 30554616) alone.
- [x] **V1** Mannequin + precomputed masks + `CatVTONEngine` + GPU memory management. Delivery: one PR per
  task to main (owner 2026-10-08, stacked-to-main), each reviewed and merged before the next.
  - [x] **V1a** Mannequin asset + settings + dependencies: `assets/tryon/mannequins/m12-woman-crop-shorts/`
    (`person.png` 768x1024, `mask_{upper,lower,overall}.png`, `meta.json` with source and licence); flat
    `tryon_*` settings (`PACHAPP_TRYON_*`, V0 defaults, pinned base/attention revisions, `tryon_enabled=false`)
    in `.env.example`; `diffusers`/`accelerate` as backend dependencies (the Makefile stops passing `--with`).
  - [x] **V1b** `backend/src/tryon/`: `TryOnEngine` Protocol + `TryOnParams`, `CatVTONEngine` (lazy load
    from the pinned CatVTON clone, `dress`, `unload`, blank check, OOM -> free and retry once at 384x512),
    mannequin loader, image preparation shared with the spike, `FakeTryOnEngine`; unit tests without GPU.
  - [x] **V1c** GPU memory management: unload hooks for BiRefNet (registry), FASHN (`CutoutEngine`) and
    SigLIP (`LazyModels`) with `gc.collect()` + `torch.cuda.empty_cache()`; release them before CatVTON
    loads; CatVTON idle unload after `tryon_idle_unload_seconds`. Not wired into the worker loop yet (V2).
  - [x] **V1d** Real GPU smoke (stack stopped): load via settings, dress one outfit on M12, measure time,
    VRAM and RSS, check the BiRefNet/SigLIP reload afterwards.
- [ ] **V2** Service, cache, `tryon_renders` + migration, worker integration, endpoints, backend tests,
  `make gen-client`. Delivery: one PR per task to main (stacked-to-main, as in V1). Owner 2026-10-08: plan
  accepted; RAM approach = measure first (lower the CatVTON load peak in V2c, measure with the full stack in
  V2d), a CatVTON subprocess only if it still does not fit.
  - [x] **V2a** Data and pure logic (torch-free): `TryOnRender` model (`tryon_renders`, spec §6.6; `status`
    reuses the job states, `step` is free text) + Alembic migration; `tryon/mapping.py` (category -> cloth
    type, pass plan with `tryon_max_passes`, skipped and unsupported ids; spec §5.2, §5.3, §12.8);
    `tryon/cache.py` (`cache_key` from mannequin id + version, sha256 of each cutout file in pass order, params,
    model version); `storage` path `tryon/<id>.webp`; unit tests.
  - [ ] **V2b** API: `GET /tryon/capabilities`, `POST /tryon` (200 cached / 202 created / 503 disabled / 422
    no compatible garment; `garment_ids` or optional `outfit_id`), `GET /tryon/{id}`, errors, schemas,
    `make gen-client`, tests. The API never imports torch.
  - [ ] **V2c** Worker: claim renders only when no upload job is pending, stuck-render recovery,
    `tryon/service.run_render` (residents released, passes, progress per diffusion step, OOM retry, WebP,
    `duration_ms`, `peak_vram_mb`), `CutoutEngine`/`LazyModels` reachable from the loop, `unload_if_idle()`
    on idle iterations, engine built lazily and only with `tryon_enabled`; lower the CatVTON load RAM peak;
    V1c/V1d advisories for V2.
  - [ ] **V2d** End-to-end smoke with the real API + worker on the GPU: spec §9 criteria 1-3 and peak RAM
    with the stack up (parent; no code).
- [ ] **V3** App: "Verlo puesto", polling, Collage | Puesto, states, offline storage of renders, tests.
- [ ] **V4** Polish: copy, cache cleanup, docs (licence note in the backend README).

## Route and checks (V1)

TDD mode: off (no project/session TDD configuration). Runner: `cd backend && uv run pytest`; plus
`uv run ruff format --check .`, `uv run ruff check .`, `uv run ty check src`. Route: V1a-V1c delegated writer
(each touches 2+ non-trivial files; mapping done by a read-only explorer on 2026-10-08), V1d parent (GPU run).
Forecast ~900 authored lines over V1a-V1d (> 400): delivery `ask-on-risk` -> owner chose stacked-to-main.
V2: same TDD mode, runner and checks. Route: V2a-V2c delegated writer (each touches 2+ non-trivial files;
backend mapped by a read-only explorer on 2026-10-08), V2d parent (GPU run). Forecast ~1300 authored lines
over V2a-V2c: stacked-to-main, one PR per task.

## Research notes (2026-10-05, reading CatVTON at `7818397f`)

- `CatVTONPipeline` (`model/pipeline.py`) is not a diffusers `DiffusionPipeline`: no
  `enable_model_cpu_offload`, no step callback. Per-step progress works by wrapping
  `noise_scheduler.step` (keeping its signature: the pipeline inspects it for `eta`/`generator`).
- Models: base `booksforcharlie/stable-diffusion-inpainting` (runwayml's repo was deleted), attention
  weights `zhengchong/CatVTON` `mix-48k-1024` (trained at 768x1024), VAE `stabilityai/sd-vae-ft-mse`
  hard-coded and unpinnable without patching. Upstream defaults: 50 steps, guidance 2.5, bf16 (we use fp16).
- Weights are small in fp16 (SD 1.5 inpainting UNet ~1.7 GB + VAE ~0.2 GB): CPU offload would save little;
  the spike measures without it and §5.5's `TRYON_CPU_OFFLOAD=true` default waits for V0b numbers.
- The SD safety checker is skipped (VRAM, and it can swap a mannequin for NSFW.jpg).
- Masks: app.py blurs the AutoMasker mask (`blur_factor=9`) and the pipeline binarises it at 0.5. The
  AutoMasker also offers `inner`/`outer` (layering, §5.3); `tryon-masks` saves all five types.
- Install: the README's Python 3.9 + `requirements.txt` no longer resolves (diffusers from git main needs
  Python >= 3.10 and is too new for its torch 2.4; `peft>=0.17` needs a newer accelerate). `tryon-setup`
  uses Python 3.10 with diffusers 0.30.3 + accelerate 1.2.1 overrides (AutoMasker imports checked).
- The pipeline also imports and runs in the backend venv (torch 2.14, transformers 5, diffusers 0.40,
  accelerate 1.15): checked with tiny random UNet/VAE on CPU through `CatVTONDresser` + `run_spike`
  (3 cases, chained outfit pass). No real weights or GPU were available in that session (Hugging Face
  and the PyTorch index blocked), so V0b is the first real run.

## Progress

- 2026-10-05: V0a (cloud session): spike tooling. Configs A 576x768/30, B 384x512/30, C 576x768/20;
  cases upper, lower, outfit (lower then upper, chained); several `--mannequin` and `--garments` folders
  (e.g. current cutouts vs U5 clean cutouts vs original photos). Records per pass time, torch peak, median
  ms/step, OOM (recorded, run continues), blank output (fp16 NaN guard); per run model load time,
  nvidia-smi peak, peak RSS; writes images, contact sheets and `tryon_spike_report.md` with the §4
  criterion. Weights go to `PACHAPP_ML_CACHE_DIR` (HF_HOME) instead of §5.5's `TRYON_WEIGHTS_DIR`.
  diffusers/accelerate come in with `uv run --with` (uv.lock untouched; V1 adds them for real). Checks:
  ruff, format, ty clean; pytest 644 (17 new).

- 2026-10-06: V0b first real run (parent, owner away; stack stopped). Branch rebased on main after U5
  (#46/#47, Makefile conflicts resolved, pytest 724). `make tryon-setup` OK (pinned CatVTON, py3.10 venv);
  `make tryon-masks` OK on a **provisional** mannequin built from an owner screenshot (cropped at the thighs,
  personal use, only to measure; not a V1 mannequin, §5.1 choice still open); garments = two U5 cutouts
  (brown tee, beige trousers). `make tryon-spike` without code changes: model load 273 s (first download
  included), peak RSS 4995 MiB, nvidia-smi peak 4907 MiB, torch peak 2859 MiB (A/C) / 2457 MiB (B); no OOM, no
  blank output. Outfit (2 chained passes): A 576x768/30 = 35.8 s (~570 ms/step), B 384x512/30 = 15.2 s,
  C 576x768/20 = 24.6 s; all meet the §4 criterion (<= 90 s). Quality by eye: A and C dress both garments
  convincingly (C close to A); B loses the colour (tee turns white) and garbles the trousers. Results in
  `~/pachapp-data/eval-results/tryon-v0b-2026-10-06/`. VAE `sd-vae-ft-mse` still unpinned (upstream
  hard-codes it). Pending owner: validate quality, choose the mannequin (§5.1), choose A vs C.
- 2026-10-07: V0c (delegated writer, branch `tryon/v0c-more-tests`): spike tooling only, no model run.
  `--seeds` (default 42, threaded to the dresser; files `<config>_<case>_s<seed>.png`), config D 768x1024/20
  (opt-in: default `--configs` stays A,B,C), case `overall` (garment `overall.*` + `mask_overall.png`, skipped
  with a note when missing; opt-in: default `--cases` stays upper,lower,outfit; never part of `outfit`),
  `compare_<set>.jpg` sheet per garment set (header row of garments, one row per mannequin, one column per
  config/case/seed), report aggregates OOM/blank counts per config plus a per-mannequin table and a seed
  column, and `tryon_spike_report.md` is rewritten (marked PARTIAL) after every mannequin x garment set
  (review advisory R4-spike-abort-loses-report). Checks: ruff format/check, ty clean; pytest 735 (11 new).

- 2026-10-07: V0d broad round (parent; stack stopped; no code change). 9 mannequins M1-M9 x 10 garment sets
  (g01-g08 FASHN cutouts of the owner's garments as upper+lower, g09 dress as `overall`, g10 the original
  photos of g01), config C, seed 42: 333 passes, 0 OOM, 0 blank, outfit max 31.3 s, median ~14 s per pass,
  nvidia-smi peak 5055 MiB, RSS peak 4821 MiB. By eye: tops (tee, polo, sweatshirt, work jacket) and long
  trousers/leggings good on every human mannequin, skin tone and pose; original photos ~= U5 cutouts; the
  dress keeps its shape but flattens the print, and fails on M7 (crossed legs). **Shorts and skirts (g04,
  g05, g07, g08) fail almost everywhere**: the leg area gets invented textures or the short becomes long
  trousers; crop tops leave a white band. Cause by inspection: the mannequins wear long trousers and the
  lower mask covers the whole leg, so CatVTON must invent bare legs. Mannequins: M8 (hands in pockets) best;
  M1, M2, M5 very good; M4 good with a stray artefact; M3, M6 short garments bad; M7 short garments and dress
  bad; M9 (store dummy) bad (floating, deformed garments) -> discarded. Results and `compare_<set>.jpg` in
  `~/pachapp-data/eval-results/tryon-v0d-2026-10-07/`.
- 2026-10-07: V0e fine round (parent; stack stopped; no code change). M1, M2, M8 x g01, g02, g03, g06
  (upper/lower/outfit) + g09 (overall), seeds 42, 7, 1234. A first attempt with `--configs C,D` in one process
  was aborted: after the first D outfit nvidia-smi showed 5.9 of 6 GB and every later pass slowed down (D
  outfit 155 s, C 36 s per pass instead of 14 s); partial results kept in `tryon-v0e-2026-10-07-aborted-mixed/`.
  Re-run with one process per config: **C** 576x768/20 = 14.2 s per pass, outfit max 29.7 s, nvidia-smi peak
  4831 MiB; **D** 768x1024/20 = 35.2 s per pass, outfit max 71.5 s (meets the 90 s criterion with little
  margin), nvidia-smi peak 5757 MiB; 0 OOM, 0 blank in both. Quality by eye (`grid_C_vs_D.jpg`,
  `grid_seeds.jpg`): C and D are close for tops and trousers; D renders the dress as a dress (C turned it into
  a jumpsuit on M1) and shows fewer white bands under tops; D once turned the leggings red (M1 g06). Seeds:
  same garment and fit across 42/7/1234, only small artefacts change (one white band under the sweatshirt in
  C seed 1234). Implication for V1: never run C and D in the same process, and D leaves ~0.4 GB of VRAM.
- 2026-10-07: V0f short garments (parent; no code change). M10 man in shorts, M11 woman in denim shorts
  (small in frame), M12 woman in crop top and shorts (Pexels, sources appended to `SOURCES.md`), each with
  CatVTON's lower mask and a `-trim` copy whose lower mask stops at 0.45 (M10: 0.55, to cover its own shorts)
  of the waist-to-ankle span; g04, g05, g07, g08 + g01 as control; config C, seed 42; 0 OOM, 0 blank. By eye
  (`grid_short_outfit.jpg`): **bare legs fix shorts and skirts**. M12 with the normal mask dresses shorts,
  mini skirt, pleated skirt and long trousers correctly; M10 dresses shorts well but renders skirts as shorts
  and long trousers as shorts; M11 fails with the normal mask (long invented trousers) and works for short
  garments with the trimmed mask; the trimmed mask always breaks long trousers (they become shorts). So a mask
  per garment length is only a fallback; the mannequin choice matters more. Results in
  `~/pachapp-data/eval-results/tryon-v0f-2026-10-07/`.

- 2026-10-08: V1a (delegated writer, branch `tryon/v1a-mannequin-settings`, commit 2b9a80e): M12 asset in
  `assets/tryon/mannequins/m12-woman-crop-shorts/` (person + upper/lower/overall masks, `meta.json`, folder
  README); flat `tryon_*` settings (V0 defaults, multiple-of-8 sizes incl. the OOM retry size, pinned base/attn
  revisions, `tryon_catvton_dir` derived from the data dir, no CPU-offload setting) in `.env.example` and §5.5;
  `diffusers==0.40.0` + `accelerate==1.15.0` in the backend (uv.lock adds 5 packages, no existing version
  changed); Makefile drops `--with`. Checks: ruff format/check, ty clean; pytest 749. Native review (medium,
  granted, 1 lens): approved and acknowledged; advisories for later: R3-catvton-dir-default-divergence (the
  Makefile clones to `$HOME/pachapp-data/vendor/CatVTON` ignoring `PACHAPP_DATA_DIR`; fix in V1b),
  R3-mannequin-id-unvalidated, R3-oom-retry-size-unchecked.

- 2026-10-08: V1b (delegated writer, branch `tryon/v1b-engine`, commit b71ad8e; resumed from the paused
  partial work): `backend/src/tryon/` with `images.py` (prep helpers moved out of the spike), `mannequin.py`
  (`load_mannequin`, id checked against `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`, mask size and `meta.json` checks),
  `engine.py` (`TryOnParams` validating multiple-of-8 sizes and a retry size not larger than the main one;
  `TryOnEngine` Protocol; `TryOnError` -> `TryOnOutOfMemory`/`TryOnBlankOutput`/`TryOnUnavailable`;
  `CatVTONEngine` with lazy load, `pipeline_factory` seam, `on_step` via a wrapped `noise_scheduler.step`,
  one OOM retry at the retry size, blank check, `unload`), `fake_engine.py`; Makefile `TRYON_CATVTON_DIR`
  follows `PACHAPP_TRYON_CATVTON_DIR` > `PACHAPP_DATA_DIR/vendor/CatVTON` > `~/pachapp-data/vendor/CatVTON`.
  Closes V1a advisories R3-catvton-dir-default-divergence, R3-mannequin-id-unvalidated,
  R3-oom-retry-size-unchecked. 871 authored lines (~100 of them the helper move). Checks: ruff format/check,
  ty clean; pytest 786 (+37). Native review (high, granted, 4 lenses): approved and acknowledged (lineage
  review-cbf7225ab01d9afd). Advisories for later (non-blocking): R3/R4-garment-error-escapes-contract
  (`GarmentError` is a `ValueError`, not a `TryOnError`), R3-on-step-overcount-on-oom-retry (progress keeps
  counting across the retry), R2/R3-moved-helper-coverage-dropped (the helper tests left with the spike and
  `tryon/images.py` has no direct tests), R4-oom-retry-inside-except, R3/R4-silent-degraded-size (caller
  is not told the result came out at the retry size), R2-garment-error-type-change / R3-spike-error-type-changed,
  R2-tautological-config-d-assert, R2-duplicated-model-constants, R2-protocol-output-size-undocumented,
  R3-tracked-asset-dependency, R1-001.

- 2026-10-08: V1b merged in #52 (owner: "revisa la pr si todo ok, merge y sigue"); parent read `engine.py`
  before merging and added two V1c items (OOM retry inside `except`, OOM while loading).
- 2026-10-08: V1c (delegated writer, branch `tryon/v1c-gpu-memory`, commit faba529). Shared
  `ml.device.free_gpu_memory()`; unload hooks returning whether a model was loaded:
  `registry.unload_background_remover()` (BiRefNet), `registry.unload_embedder()` + `LazyModels.unload()`
  (SigLIP, via an optional `AiModels.release` hook), `CutoutEngine.unload()` (remover + FASHN `parser.close()`);
  `tryon/memory.py`: `resident_unloaders(cutout, models)` + `release_resident_models(unloaders)` (runs all,
  logs and counts failures, frees once). `CatVTONEngine(idle_unload_seconds=0, clock=time.monotonic)` +
  `unload_if_idle()` on the Protocol: timer starts at load and resets after every `dress`; 0 = never (spec
  §5.5), so V2 must pass `settings.tryon_idle_unload_seconds`; meant to be polled by V2's single-threaded
  worker loop (no threads, no locks). V1b advisories folded in: retry outside the `except` (`_run_or_none`,
  no exception chaining), `TryOnInvalidInput` for bad garments (prepared before loading), `on_retry`
  callback (then `on_step` counts from zero), result `.size` is the size used (documented, tested), tests for
  `tryon/images.py`, OOM while loading -> `TryOnOutOfMemory`. Not wired into the worker (V2). 635 authored
  lines (~225 tests; six advisories folded in). Checks: ruff format/check, ty clean; pytest 812 (+26).
  Native review (medium, granted, 1 lens): approved and acknowledged (lineage review-cf9091d595f6f403).
  Advisories for V2: R3-idle-timer-mid-dress (`unload_if_idle` is safe only from the thread that calls
  `dress`; if V2 ever polls from another thread, mark the engine in use during `dress`),
  R3-oom-cause-dropped (log the original OOM message before dropping it). Writer notes for V2:
  `make_cutout_step` builds its `CutoutEngine` internally, so V2 needs access to it for `resident_unloaders`;
  `FakeTryOnEngine` has no OOM simulation and never calls `on_retry`; Pillow `getdata` deprecation warnings in
  the new images tests.

- 2026-10-08: V1c merged in #53. V1d real GPU smoke (parent; no code change; stack not running, checked: no
  API/worker/Expo processes, no GPU compute apps). Script `v1d_smoke.py` (kept with the results) runs in one
  process: BiRefNet + SigLIP loaded and used as the worker does -> `unload_background_remover()` +
  `unload_embedder()` -> `CatVTONEngine` from `Settings` (M12, config C, fp16) dresses g01 lower then upper
  (chained outfit) -> `unload()` -> BiRefNet + SigLIP reloaded and used. FASHN was not exercised (its
  `CutoutEngine` needs a worker `StepContext`). The first run downloaded the weights into
  `~/.cache/huggingface`: `.env` sets no `PACHAPP_ML_CACHE_DIR`, so the V0 weights were not found. Second run,
  weights on disk:
  | step | time | nvidia-smi | RSS (peak) |
  |---|---|---|---|
  | baseline (Windows desktop) | - | 1110 MiB | 519 MiB |
  | residents loaded + used | 26.5 s | 5574 MiB | 2882 MiB (3694) |
  | residents released | 0.6 s | 1164 MiB | 2876 MiB |
  | CatVTON load + first pass | 119.6 s | 4799 MiB | 2727 MiB (**5910**) |
  | second pass (warm) | 12.4 s | 4736 MiB, torch peak 2858 MiB | 2727 MiB |
  | CatVTON unloaded | 0.3 s | 1142 MiB | 2615 MiB |
  | residents reloaded + used | 16.1 s | 5637 MiB | 2439 MiB |
  20 steps per pass, 576x768 output, no OOM retry, no blank. Unloading gives the VRAM back (~4.4 GB each way)
  and the residents reload fine. By eye (`sheet.jpg`): g01 tee and trousers dressed convincingly on M12.
  Findings for V2: (1) CatVTON load from disk takes ~107 s (the pass itself ~12 s), so the first render after
  an idle unload is slow: the app needs a "preparing" state and the idle timeout matters; (2) unloading frees
  VRAM but not host RAM (RSS stays ~2.7 GB after releasing the residents) and the CatVTON load peaks at 5.9 GB
  RSS in a 7.9 GB WSL, so running the try-on with API and Expo up risks memory pressure; (3) set
  `PACHAPP_ML_CACHE_DIR` (or accept `~/.cache/huggingface`, 8.4 GB now) so the worker does not download twice.
  Results in `~/pachapp-data/eval-results/tryon-v1d-2026-10-08/`.

- 2026-10-08: V2a (delegated writer, branch `tryon/v2a-data`, commit b1a7a67). `TryOnRender` (`tryon_renders`:
  job-like status/step/progress/attempts/claim columns, JSON `garment_ids`/`skipped_garment_ids`/
  `unsupported_garment_ids`/`params`, plain nullable `outfit_id`, `uq_tryon_renders_cache_key`,
  `idx_tryon_renders_status`) + migration `c4e8f21a6d93`. `tryon/mapping.py`: `ClothType`, `cloth_type()`,
  `plan_passes(garments, max_passes) -> PassPlan(passes, skipped, unsupported, is_empty)`; deterministic rules by
  input order (first of a category wins, a one-piece wins over tops/bottoms but keeps mid layer/outerwear after
  it, over the limit keep the base pass, then the innermost and outermost upper). `tryon/cache.py`:
  `cache_key(...)` over canonical JSON; `hash_cutout`, `mannequin_version` (digest of the person image, masks
  and `meta.json`), `model_version` (pinned revisions + `ATTN_VERSION`, moved here so the module stays
  torch-free). `storage.tryon_path`, `imaging.encode_webp`. A subprocess test checks `tryon.mapping`/`tryon.cache`
  import no torch. 738 authored lines (~370 tests). Checks: ruff format/check, ty clean; pytest 860 (+48).
  Native review (high: the torch-free test starts a subprocess; granted, 4 lenses): approved and acknowledged
  (lineage review-4c9a0105e4af3e1a). To fix in V2b (first user of `cache_key`): R3-cache-key-omits-cloth-type
  (a recategorised garment with the same cutout keeps its key -> stale render; add the cloth type per pass),
  R2-shadowed-version-params (rename the `cache_key` parameters). Other advisories: R3-max-passes-not-enforced-
  below-base (settings already require >= 1), R3-cache-key-numeric-canonicalisation, R3/R2-encode-webp-palette-
  alpha, R2-attn-constant-split, R2-dense-slot-trim. Writer notes for V2b/V2c: store `params` with the mannequin
  and model versions; 422 when a garment has no `img_cutout`; refresh `last_accessed_at` on a cache hit;
  consistent `step` names.

## Next step

V2b (API; fixes the two V2a cache-key advisories), then V2c, V2d, one PR each.
