# Phase 1 — Data model (spec 02)

Locator: `odd/tasks/phase-1-data-model.md` · Engram mirror: `odd/phase-1-data-model/tasks`
Branch: `feat/phase-1-data-model` (from `main` `525e8fb`), worktree `~/pachapp-worktrees/data-model`. Runs in parallel with `feat/ml-1-registry` (user approved isolated worktrees, 2026-09-29).

## Objective

Implement `docs/specs/02-data-model.md`: closed enums, SQLModel tables (`garment`, `outfit`, `outfit_item`, `wear_log`, `job`, `setting`, `ai_correction`), JSON column schemas, relations/constraints, SQLite pragmas (WAL, busy_timeout, D4), the initial Alembic migration and tests. Prerequisite for 03 (ingestion), 04 (API) and 08 steps 4–7.

## Constraints

- Spec 02 is authoritative, including the 08-local-vision changes merged in PR #4 (`embedding_model`, `embedding_dim`, `ai_confidence` as `{value, confidence, source}`, margin rule is worker logic, not schema).
- Models live in `shared` (DAT-REQ-001: one enum definition reused everywhere). No I/O in `engine`.
- Do not touch `shared/settings.py` beyond what the DB session strictly needs (the ML branch edits it in parallel); no new env settings unless the spec requires one.
- No ML deps.

## TDD

Mode: off. Runner: `uv run pytest`. Ordinary functional checks.

## Tasks

- [ ] **T1 — Enums, models, DB session/pragmas, initial migration, tests.** Route: delegated direct (writer trigger: several non-trivial files).
  - Checks: ruff, ruff format --check, ty, pytest; `alembic upgrade head` on an empty DB; `alembic check` (or autogenerate) reports no drift; downgrade/upgrade round trip.

## Delivery

Forecast: ~500–800 authored lines. Strategy `ask-on-risk`; chain strategy stacked-to-main (reused). If over budget, split models vs migration/tests into two commits/PRs.

## Progress

- 2026-09-29: worktree, branch and feature document created.
