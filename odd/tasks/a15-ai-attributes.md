# A15 — AI attributes and embeddings in the worker

## Objective

Make the worker classify every uploaded garment (category, subcategory, pattern, material, formality,
style_tags) and store its embedding, so the outfit engine has real data to combine
(`docs/specs/08-local-vision.md` implementation plan step 4; Hito A follow-up A15).

## Problem / why

`ai_attributes` and `embedding` are no-op `deferred_step`s in `backend/src/worker/runner.py` (~79-103), so new
garments only get colours; category, formality, style_tags and embeddings stay empty unless typed by hand in
Revisión. The outfit engine (`docs/specs/05-outfit-engine.md`) needs them (hard filters on category and
formality, style score from formality, style_tags and embeddings). The ML code already exists in
`backend/src/ml/` (registry `GarmentEmbedder`, `taxonomy.py`, `zero_shot.py` `ZeroShotClassifier`), validated by
`make ml-eval` (step 3 gate >= 85 % category accuracy, `odd/tasks/local-vision-ml.md`).

## Scope (owner decisions, 2026-10-04)

- Owner chose A15 before the outfit engine; the engine MVP comes next and includes base templates plus
  mid_layer, outerwear and accessories.
- In: plan step 4 — zero-shot only (alpha = 1, `source="zero_shot"`): VIS-REQ-013, 016 (needs_review only from
  `category` and `pattern`, top-1 < `setting.needs_review_threshold` or margin < `PACHAPP_ML_MARGIN_THRESHOLD`),
  017 (formality), 018 (style_tags, max 3), 019 (`ai_confidence` `{value, confidence, source}`), and the
  embedding columns `embedding`, `embedding_model` (`id@revision`, VIS-REQ-002), `embedding_dim` (read from the
  model, never hard-coded).
- In: a backfill for garments that already exist (classify and embed active/laundry/archived garments missing
  an embedding or attributes) that never overwrites a field the user set (`ai_confidence[field].source ==
  "user"` or a later `ai_correction` row), exposed as a make target. This is the minimal subset of step 6's
  `reembed` the engine needs.
- Out (later): kNN and blending (step 5), duplicate warning (VIS-REQ-022, step 6), full `reembed` on model
  change (step 6), LLM fallback (step 7), style_tags prompts for elegant/bohemian/preppy (open question).

## Tasks

- [ ] **T1** `ai_attributes` worker step: embed the cutout (or the preprocessed image if no cutout), run the
  zero-shot classifier, write the attributes and `ai_confidence`, set `needs_review` per VIS-REQ-016, never
  overwrite user-set fields; respect the API/ML process boundary (VIS-REQ-005) and keep `make test` offline
  (VIS-REQ-029: synthetic embeddings/fakes in tests).
- [ ] **T2** `embedding` worker step: persist the image embedding computed in T1 (no second inference),
  `embedding_model`, `embedding_dim`; `consolidate` behaviour unchanged except for the new fields.
- [ ] **T3** Backfill command + `make` target for existing garments (idempotent, skips user-set fields, reports
  counts), with tests.
- [ ] **T4** Owner check on real data: run the backfill on the owner's wardrobe and upload a photo from the app;
  attributes and embeddings filled, Revisión shows them.

## Acceptance criteria

- Uploading a photo fills category, subcategory, pattern, material, formality and style_tags with `source` and
  `confidence`, and writes `embedding`/`embedding_model`/`embedding_dim` (plan step 4 "done when").
- Existing garments get embeddings and missing attributes from the backfill; user-set fields untouched.
- `make test` passes with no network and no models; worker per-garment time stays within VIS-REQ-026 (< 2 s on
  the GPU).

## TDD / checks

TDD: off (no project/session TDD configuration). Runner: backend `uv run pytest` (via `make test`). Per task:
`make lint`, `make fmt-check`, `make typecheck`, `make test` (backend part at least). T4: owner + real models.

## Delivery

Forecast ~400-600 authored lines (backend + tests). Branch `feat/a15-ai-attributes` from `main` `c57d9cd` in the
worktree `~/code/pachapp-worktrees/a15` (the main checkout is busy with `feat/offline-app`). Strategy
`ask-on-risk`, owner's cached chain strategy stacked-to-main if it exceeds the budget.

## Routes

- T1-T3: one delegated writer (2+ non-trivial backend files; preparation reading belongs to the writer).
- T4: parent runs the backfill with the owner's stack; owner checks the app.

## Progress

- 2026-10-04: groundwork exploration (delegated) for the outfit engine found the deferred steps; owner chose A15
  first. Feature document created.

## Next step

T1-T3 with one delegated writer.
