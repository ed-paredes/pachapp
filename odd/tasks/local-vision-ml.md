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

- [ ] **T1 — Step 1: settings, `ml` package skeleton, registry + device, preload.** Route: delegated direct (writer trigger: settings, ml package, worker, tests, Makefile, pyproject).
  - `PACHAPP_ML_*` settings (08 table), conditional `PACHAPP_LLM_*` (VIS-REQ-021 / DEV-REQ-011), cache dir under data dir with D14 guard, `HF_HOME`/`U2NET_HOME` derived in the worker (VIS-REQ-008), pinned embed revision (VIS-REQ-002), `api`↛`ml` test (VIS-REQ-005), `make ml-preload`.
  - Done when (08 step 1): `make ml-preload` downloads BiRefNet and SigLIP into `PACHAPP_ML_CACHE_DIR` and `ml.registry` reports the selected device (expected `cuda`).
- [ ] **T2 — Step 2: BiRefNet cutout (`BackgroundRemover`).** Gate needs the user's photos (18/20 clean cutouts).
- [ ] **T3 — Step 3: embedder + zero-shot + `make ml-eval`.** Gate needs the user's photos (≥85 % category accuracy without kNN).

## Delivery

Forecast: T1 ~400–600 authored lines (lockfile excluded). Strategy `ask-on-risk`; chain strategy reused from phase 0: stacked-to-main, one PR per step.

## Progress

- 2026-09-28: PR #4 (specs) opened; torch variant CUDA chosen; branch `feat/ml-1-registry` created from `docs/spec-ml-local-vision`.

## Next step

Delegate T1.
