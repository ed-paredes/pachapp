# Phase 0 — Dev tooling and monorepo scaffold

Locator: `odd/tasks/phase-0-dev-tooling.md` · Engram mirror: `odd/phase-0-dev-tooling/tasks`
Branches (stacked-to-main): `feat/phase-0-1-backend` (T1) → `feat/phase-0-2-app` (T2) → `feat/phase-0-3-makefile` (T3)

## Objective

Implement "Fase 0: base del proyecto" as mapped in `docs/specs/00-index.md`: the monorepo, backend and app tooling, root `Makefile`, and settings/`.env`, as specified in `docs/specs/01-dev-tooling.md` (D0, D13, D14, D15, D16). Docker Compose and login are out of scope (deferred).

## Problem / why

Every later spec (02–07) assumes this structure and these commands exist. Without it there is no place to put the data model, API, worker, engine or app.

## Scope

- `backend/`: single `uv` project, Python 3.12, packages `pachapp_api`, `pachapp_worker`, `pachapp_engine`, `pachapp_shared`; `alembic/`; `tests/unit`, `tests/contract`.
- `pachapp_shared.settings`: `pydantic-settings` `Settings` with every key from the spec table; fail fast on missing secrets (DEV-REQ-011) and on `PACHAPP_DATA_DIR` under `/mnt/*` (DEV-REQ-014, DEV-SCN-004).
- `pachapp_api.main`: FastAPI app with `CORSMiddleware` per DEV-REQ-012 and a health endpoint.
- `pachapp_worker.main`: polling-loop stub (no job logic yet — phase 1).
- `app/`: Expo + TypeScript + Expo Router, `strict: true`, eslint, prettier, jest-expo + Testing Library, `src/api-client/` placeholder.
- Root `Makefile` with every target in the spec table, runnable from the repo root; `.env.example`; README quick start.

## Constraints

- No I/O in `pachapp_engine` (DEV-REQ-002).
- No versioned default for secrets.
- No heavy ML dependencies yet (rembg, open_clip, scikit-learn belong to phases 1–2).
- Toolchain: uv 0.6.8, Python 3.12.9 (uv-managed), Node 22.23.3 via nvm (installed 2026-09-28 at the user's choice; Windows npm on PATH must not be used).

## TDD

Mode: off. Source: no project/session TDD configuration found and none requested. Runners: `uv run pytest` (backend), `npm test` / jest-expo (app). Ordinary functional checks apply.

## Tasks

- [x] **T1 — Backend scaffold.** Route: delegated direct (writer trigger: 10+ non-trivial files). pyproject + uv.lock, four packages, Settings with guards, FastAPI app + CORS + health, worker stub, alembic init, ruff/ty/pytest config, unit tests for settings guards and CORS.
  - Checks: `uv run ruff check`, `uv run ruff format --check`, `uv run ty check src`, `uv run pytest`.
  - Evidence (2026-09-28): uv sync ok; ruff check pass; ruff format --check pass; ty check src pass; pytest 14 passed (1 Starlette TestClient deprecation warning); `/mnt/d` data dir fails fast with the D14 message. Parent spot check re-ran pytest (14 passed) and ty (pass). ~667 authored lines (over the 400 heuristic; scaffold plus tests, not split artificially).
  - Notes: `EXPO_PUBLIC_API_BASE_URL` intentionally not in backend `Settings` (app-only, T2). OpenAPI offline export: `uv run python -m pachapp_api.export_openapi [path]` (for T3).
- [ ] **T2 — App scaffold.** Route: delegated direct (writer trigger). Expo TS + Expo Router, strict tsconfig, eslint/prettier/jest configs, npm scripts `lint`, `format`, `typecheck`, `test`, one smoke test.
  - Checks: `npm run lint`, `npm run typecheck`, `npm test`.
- [ ] **T3 — Makefile, .env.example, README.** Route: to be decided (likely inline, mechanical). All spec targets; `gen-client` exports OpenAPI without a running server (resolves the open question in 01-dev-tooling.md).
  - Checks: `make lint`, `make fmt`, `make typecheck`, `make test` exit 0; `make gen-client` writes `app/src/api-client/schema.ts`.

## Acceptance criteria

From 01-dev-tooling.md: `make install` works from a clean clone; `make lint/fmt/typecheck/test` exit 0; `make gen-client` produces types that compile. The end-to-end LAN/mobile check (D13) needs the user's phone and Windows `.wslconfig` and is a manual check.

## Delivery

Forecast: ~600–800 authored changed lines (lockfiles and generated files excluded) — over the ~400-line budget. Strategy: `ask-on-risk`; chain strategy chosen by the user: `stacked-to-main` (2026-09-28). One PR per task slice, each based on the previous slice.

| Slice | Branch | Commits |
| --- | --- | --- |
| 1 | `feat/phase-0-1-backend` | T1 (pending) |
| 2 | `feat/phase-0-2-app` | T2 (pending) |
| 3 | `feat/phase-0-3-makefile` | T3 (pending) |

## Progress

- 2026-09-28: branch created, Node 22 installed via nvm, feature document created.
- 2026-09-28: delivery strategy stacked-to-main chosen; T1 delegated to a writer.

## Next step

T2 (app scaffold) on `feat/phase-0-2-app`, stacked on slice 1.
