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
- [ ] **T2 — Step 2: BiRefNet cutout (`BackgroundRemover`).** Gate needs the user's photos (18/20 clean cutouts).
- [ ] **T3 — Step 3: embedder + zero-shot + `make ml-eval`.** Gate needs the user's photos (≥85 % category accuracy without kNN).

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

## Follow-ups

- `snapshot_download` fetches every file of the pinned revision (~5 GB cache); add `allow_patterns` for the files open_clip's `local-dir:` loader needs. Needs a clean-cache download to verify — do with T3.

- Worker cold start ~100 s from `/mnt/d` imports: consider a checkout on WSL ext4 or `UV_PROJECT_ENVIRONMENT` outside `/mnt` before T2 perf measurements (VIS-REQ-026 budget is per garment, not startup).
- `.env` / `.env.test` lack `PACHAPP_ML_EMBED_REVISION` (required, no default): user must add it.

## Next step

Commit T1, assess review, open the T1 PR (stacked on `docs/spec-ml-local-vision`). Then T2 (needs the user's eval photos for its gate).
