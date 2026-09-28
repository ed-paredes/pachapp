# SPEC-ML — local vision spec pass

Locator: `odd/tasks/spec-ml-local-vision.md` · Engram mirror: `odd/spec-ml-local-vision/tasks`
Branch: `docs/spec-ml-local-vision` (from `main` `6a54741`)

## Objective

Integrate the user's `SPEC-ML.md` (local vision module: BiRefNet cutout, Marqo-FashionSigLIP zero-shot + kNN, LLM only as optional fallback) into the spec set, adapted to the real architecture, before any ML code is written. The user set SPEC-ML as the priority (2026-09-28).

## Problem / why

SPEC-ML was written against a different layout (`backend/app/ml/`, a `SPEC.md` that does not exist here, Docker/VPS, bare `ML_*` env vars) and contradicts current specs (LLM as required primary classifier, fixed 512-d embeddings). Code built on it as-is would fight specs 01/02/03 and C4.

## Decisions (user, 2026-09-28)

1. Code lives in a new package `backend/src/ml/`, used only by the worker (never imported by `api`; never in `engine`, DEV-REQ-002).
2. Settings use the `PACHAPP_ML_*` prefix in the single `Settings` model (D16); model cache lives under `PACHAPP_DATA_DIR` (not `HF_HOME=/data/...`).
3. The vision LLM becomes optional: `PACHAPP_LLM_*` required only when the LLM fallback is enabled.
4. Hardware (checked 2026-09-28): NVIDIA RTX 2060 6 GB visible from WSL (driver 591.86), 8 cores, ~7 GB RAM in WSL. CUDA torch is viable; final torch variant to be confirmed with the user during SPEC-ML step 1.
5. Evaluation photos: the user will provide 20–40 labeled photos. Default location: outside the repo, under the data dir (personal images).

Parent defaults (stated in the spec, open to user change): `reembed` as a worker CLI module + Make target (no API endpoint in iteration 1); one worker process, one job at a time; kNN pool = garments with `user_verified = true` (D19); embeddings compared only within the same `embedding_model`; stored enum values stay those of 02-data-model.md (taxonomy maps prompts to them).

## Scope

- New `docs/specs/08-local-vision.md` (Spanish, like the other specs) derived from `SPEC-ML.md`, adapted to decisions above, with requirement IDs.
- Updates for consistency: `00-index.md`, `01-dev-tooling.md`, `02-data-model.md`, `03-garment-ingestion.md`, `docs/architecture/c4.md`.
- Out of scope: any code; deleting or editing the user's root `SPEC-ML.md` (user decides).

## TDD

Mode: off (documentation only). Checks: structural readback; cross-reference consistency (IDs, settings names, step names, enum values) across the touched specs.

## Tasks

- [ ] **T1 — Write `08-local-vision.md`.** Route: delegated direct (writer trigger: 6 non-trivial docs, preparation reading 4+ files).
- [ ] **T2 — Align 00/01/02/03/C4 with 08.** Route: same writer (shared context).
- [ ] **T3 — Parent readback + consistency check, commit per task, PR.**

## Acceptance criteria

No contradictions left between 08 and 00–07/C4 on: package path, settings names and requiredness, LLM role, embedding dimension/model columns, `ai_confidence` shape, `needs_review` rule, worker concurrency, deployment model, taxonomy vs enums. Every open item is listed as an open question, not silently decided.

## Delivery

Forecast: ~400–600 authored lines (docs). Strategy: `ask-on-risk` (ask about chaining only if the final diff is well over budget).

## Progress

- 2026-09-28: phase 0 merged; branch and feature document created; hardware checked.

## Next step

Delegate T1+T2 to one writer.
