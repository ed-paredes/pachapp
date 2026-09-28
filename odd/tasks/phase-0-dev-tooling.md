# Phase 0 — Dev tooling and monorepo scaffold

Locator: `odd/tasks/phase-0-dev-tooling.md` · Engram mirror: `odd/phase-0-dev-tooling/tasks`
Branches (stacked-to-main): `feat/phase-0-1-backend` (T1) → `feat/phase-0-2-app` (T2) → `feat/phase-0-3-makefile` (T3)

## Objective

Implement "Fase 0: base del proyecto" as mapped in `docs/specs/00-index.md`: the monorepo, backend and app tooling, root `Makefile`, and settings/`.env`, as specified in `docs/specs/01-dev-tooling.md` (D0, D13, D14, D15, D16). Docker Compose and login are out of scope (deferred).

## Problem / why

Every later spec (02–07) assumes this structure and these commands exist. Without it there is no place to put the data model, API, worker, engine or app.

## Scope

- `backend/`: single `uv` project, Python 3.12, packages `api`, `worker`, `engine`, `shared`; `alembic/`; `tests/unit`, `tests/contract`.
- `shared.settings`: `pydantic-settings` `Settings` with every key from the spec table; fail fast on missing secrets (DEV-REQ-011) and on `PACHAPP_DATA_DIR` under `/mnt/*` (DEV-REQ-014, DEV-SCN-004).
- `api.main`: FastAPI app with `CORSMiddleware` per DEV-REQ-012 and a health endpoint.
- `worker.main`: polling-loop stub (no job logic yet — phase 1).
- `app/`: Expo + TypeScript + Expo Router, `strict: true`, eslint, prettier, jest-expo + Testing Library, `src/api-client/` placeholder.
- Root `Makefile` with every target in the spec table, runnable from the repo root; `.env.example`; README quick start.

## Constraints

- No I/O in `engine` (DEV-REQ-002).
- No versioned default for secrets.
- No heavy ML dependencies yet (rembg, open_clip, scikit-learn belong to phases 1–2).
- Toolchain: uv 0.6.8, Python 3.12.9 (uv-managed), Node 22.23.3 via nvm (installed 2026-09-28 at the user's choice; Windows npm on PATH must not be used).

## TDD

Mode: off. Source: no project/session TDD configuration found and none requested. Runners: `uv run pytest` (backend), `npm test` / jest-expo (app). Ordinary functional checks apply.

## Tasks

- [x] **T1 — Backend scaffold.** Route: delegated direct (writer trigger: 10+ non-trivial files). pyproject + uv.lock, four packages, Settings with guards, FastAPI app + CORS + health, worker stub, alembic init, ruff/ty/pytest config, unit tests for settings guards and CORS.
  - Checks: `uv run ruff check`, `uv run ruff format --check`, `uv run ty check src`, `uv run pytest`.
  - Evidence (2026-09-28): uv sync ok; ruff check pass; ruff format --check pass; ty check src pass; pytest 14 passed (1 Starlette TestClient deprecation warning); `/mnt/d` data dir fails fast with the D14 message. Parent spot check re-ran pytest (14 passed) and ty (pass). ~667 authored lines (over the 400 heuristic; scaffold plus tests, not split artificially).
  - Notes: `EXPO_PUBLIC_API_BASE_URL` intentionally not in backend `Settings` (app-only, T2). OpenAPI offline export: `uv run python -m api.export_openapi [path]` (for T3).
  - Commit: `7f70aa9`. Review: assessed medium (`slice_budget_reached`), consent granted, 1 lens (reliability) → approved, acknowledged (lineage review-56e47b45f0245643, authority burned). Reviewed boundary advances to `7f70aa9`.
- [x] **T1b — Fix non-blocking review findings from T1.** Route: delegated direct (settings, worker, tests). In scope because they are gaps against DEV-REQ-011 / DEV-REQ-014 already authorized in T1:
  - R3-empty-secret-accepted: reject empty `llm_provider` / `llm_api_key` (DEV-REQ-011).
  - R3-mnt-guard-bypass: apply the `/mnt` guard to explicit `db_path` and `images_root` too (D14).
  - R3-poll-interval-unbounded: `worker_poll_interval_ms` (and other numeric settings where meaningful) must be > 0.
  - R3-test-suite-nonhermetic: tests must not read the developer's repo-root `.env`; clear the `get_settings` cache between tests.
  - R3-export-openapi-untested: test `export_openapi_json` (valid JSON, contains `/health`, creates parent dirs).
  - Checks: same as T1.
  - Evidence (2026-09-28): ruff format --check pass; ruff check pass; ty check src pass; pytest 34 passed. Parent replaced the writer's hermeticity test, which wrote a hostile `.env` into the repo root on every run, with a non-destructive check plus a tmp_path `.env` test. `PACHAPP_ENV_FILE` is a test-only override, not user-facing (keep it out of `.env.example`).
  - Commit: `2f8f6b9`. Review: assessed medium, `review_due=false` (`under_budget`, 245 lines since boundary `7f70aa9`) — pending in the slice until a later commit reaches the budget.
- [x] **T2 — App scaffold.** Route: delegated direct (writer trigger). Expo TS + Expo Router, strict tsconfig, eslint/prettier/jest configs, npm scripts `lint`, `format`, `typecheck`, `test`, one smoke test.
  - Checks: `npm run lint`, `npm run typecheck`, `npm test`.
  - Evidence (2026-09-28, re-verified from scratch on resume with nvm Node 22.23.3): format:check pass; lint exit 0; typecheck exit 0; jest 2 suites / 3 tests passed; `expo export --platform web` ok (index, _sitemap, +not-found).
  - Commit: `3d3f802` (30 files; ~16k lines are `package-lock.json`). `app/LICENSE` (Expo template MIT, copyright 650 Industries) left untracked: deleting it was blocked by the permission classifier — user to delete it.
  - Review: assessed medium (`slice_budget_reached`, reason `configuration_change` on `app/.claude/settings.json`), range `7f70aa9..3d3f802`, untracked files excluded. Consent granted; 1 lens (reliability) → approved, acknowledged (lineage review-123d0f2e030cd1a2, authority burned). Reviewed boundary advances to `3d3f802`. Advisory findings (non-blocking): R3-jest-alias-mapping-unproven — refuted by evidence (the `@/` alias test runs and passes); R3-generic-toplevel-package-names — risk accepted by the user, package-resolution test added in T3 at the user's choice; R3-numeric-bounds-partially-tested — user chose not to add now.
  - Manual check: user ran the UI (`make run-ui`) and confirmed the home screen renders correctly (2026-09-28).
- [x] **T3 — Makefile, .env.example, README.** Route: inline (mechanical, already understood; Makefile + .env.example + README). All spec targets; `gen-client` exports OpenAPI without a running server (resolves the open question in 01-dev-tooling.md). Also: user asked (2026-09-28) for a repo-root `.env.test` with dummy values and data dir `~/pachapp-data-test`, loaded via `PACHAPP_ENV_FILE=../.env.test` (so `PACHAPP_ENV_FILE` is now user-facing). The file is gitignored by `.env.*`; README must document it and the Makefile run targets should accept `ENV_FILE=.env.test`.
  - Checks: `make lint`, `make fmt`, `make typecheck`, `make test` exit 0; `make gen-client` writes `app/src/api-client/schema.ts`.
  - Decisions (2026-09-28, user): commit the user's `settings.py` change (missing env file → RuntimeError) plus the test adaptation in this slice; update spec 01 `gen-client` row and close its open question; add a package-resolution test (review follow-up).
  - Evidence so far (branch `feat/phase-0-3-makefile` created from `3d3f802`): with nvm Node, `make lint`, `make typecheck`, `make fmt-check`, `make test` (pytest 34 passed, jest 3 passed) all exit 0; `make gen-client` exit 0 and wrote `schema.ts` (tsc and eslint pass on it). Prettier flagged the generated file → added `src/api-client/schema.ts` to `app/.prettierignore`; format:check passes.
  - Route for README + spec + test: delegated direct (long-session backstop fired). Writer report `done`: ruff check/format pass, ty pass, pytest 38 passed (34 + 4 package-resolution cases), app format:check pass, README targets table matches `make help`. Parent spot check: pytest 38 passed; read back README, spec diff and test; fixed README ("shared (settings)", no models yet).
  - Commits: `88b2fe9` (user's settings.py change + test adaptation); Makefile/.env.example/README/spec/schema.ts/package test in `99f445a`.
  - Review: assessed medium (`configuration_change` on `.env.example`), 11 paths / 384 lines since `3d3f802`, `review_due=false` (`under_budget`) — pending in the slice; boundary stays `3d3f802`.
  - Still manual/unverified: D13 phone/LAN check. `make install` from a clean clone: deferred by the user (2026-09-28), not needed for now.

## Acceptance criteria

From 01-dev-tooling.md: `make install` works from a clean clone; `make lint/fmt/typecheck/test` exit 0; `make gen-client` produces types that compile. The end-to-end LAN/mobile check (D13) needs the user's phone and Windows `.wslconfig` and is a manual check.

## Delivery

Forecast: ~600–800 authored changed lines (lockfiles and generated files excluded) — over the ~400-line budget. Strategy: `ask-on-risk`; chain strategy chosen by the user: `stacked-to-main` (2026-09-28). One PR per task slice, each based on the previous slice.

| Slice | Branch | Commits |
| --- | --- | --- |
| 1 | `feat/phase-0-1-backend` | T1 `7f70aa9`, T1b `2f8f6b9`, rename `a7e511c` |
| 2 | `feat/phase-0-2-app` | T2 `3d3f802` |
| 3 | `feat/phase-0-3-makefile` | settings `88b2fe9`, T3 (see T3) |

## Progress

- 2026-09-28: branch created, Node 22 installed via nvm, feature document created.
- 2026-09-28: delivery strategy stacked-to-main chosen; T1 delegated to a writer.
- 2026-09-28: user chose to drop the `pachapp_` prefix: backend packages are now top-level `api`, `worker`, `engine`, `shared` (user accepted the name-collision risk over a `pachapp.*` namespace). Commit `a7e511c` on slice 1 (made in a separate worktree while T2 ran); slice 2 fast-forwarded. Checks: ruff, ty, pytest 34 passed, uvicorn `/health` 200, worker start/stop, OpenAPI export.
- 2026-09-28: shell fixes outside the repo: `~/.local/bin` added to PATH in `~/.zshrc` (uv was missing in zsh); `vactivate` function added to `~/.zshrc`.

## Checkpoint 2026-09-28 (end of day) — resume here

Checked-out branch: `feat/phase-0-2-app` (= slice 1 tip `a7e511c`, no own commits yet). Nothing below is committed.

Uncommitted working tree:
- `app/` (untracked) — T2 writer output. The writer was stopped at the user's request while doing its final re-verification pass (it had just edited a README); no report was received. On resume: re-verify from scratch (Node from nvm on PATH): `npm run format:check`, `lint`, `typecheck`, `test`, web export. Then commit on `feat/phase-0-2-app`.
- `Makefile`, `.env.example` (untracked) — T3, written inline. Commit on a new `feat/phase-0-3-makefile` created after the T2 commit.
- `backend/src/shared/settings.py` — **user's own change** (not made by the agent): `get_settings()` raises if the env file is missing. Confirm with the user before committing it and decide its slice (probably slice 3 together with the Makefile).
- `backend/tests/unit/conftest.py`, `test_settings.py` — agent changes: tests force `PACHAPP_ENV_FILE=os.devnull` (exists and is empty, compatible with the user's check) and clear ambient `PACHAPP_*` vars at collection time (the Makefile exports `PACHAPP_ENV_FILE`). pytest 34 passed. Goes with the settings change.
- `SPEC-ML.md` (untracked, repo root) — **user's file**, not touched.
- `.env.test` (gitignored) — dummy values plus `EXPO_PUBLIC_API_BASE_URL=http://localhost:8000`. It vanished once during the T2 run (cause unknown) and was recreated.

T3 verification so far (backend halves only; the shell used had no nvm Node on PATH, so the app halves were blocked by `check-node` as designed):
- `make help` lists all targets; `make lint`, `make typecheck`, `make fmt-check`, `make test` — backend part passes (ruff, ty, 16 files formatted, 34 passed).
- `make run ENV_FILE=.env.test PACHAPP_API_PORT=8766` → `/health` 200; `make run ENV_FILE=.env.missing` → RuntimeError "Missing .env file"; `make run-worker ENV_FILE=.env.test` starts and stops cleanly; `make migrate ENV_FILE=.env.test` created `~/pachapp-data-test/db/pachapp.sqlite3`.
- Pending: app halves of lint/typecheck/fmt-check/test, `make gen-client` (needs T2 + `openapi-typescript`), `make install`, `make run-ui`.

Still to do for T3: README (quick start, targets, `ENV_FILE=.env.test`, WSL/Node notes). Also update docs/specs/01-dev-tooling.md `gen-client` row (now exports offline) if the user agrees.

Review state: boundary `3d3f802` (covers slice 1 + slice 2). Run `gentle-ai review assess --base-ref 3d3f802 --committed-only` (plus `--untracked-scope=exclude --expected-untracked-inventory=<digest>` while untracked files exist) after each new commit.

Environment note: the user had uvicorn servers on :8000, two of them still running the old `pachapp_api.main` module (broken after the rename).

## Next step

1. ~~Verify and commit T2~~ done (`3d3f802`), review approved. 2. ~~Ask the user about their `settings.py` change~~ → slice 3. 3. ~~Finish T3~~ done (`88b2fe9`, `99f445a`; review pending under budget). 4. ~~Push~~ done 2026-09-28 (user authorized): all three branches on `origin`. PRs not created — `gh` is not installed; PR bodies prepared (Chain Context per `chained-pr`), user opens them via compare links. Slice 1 is 957 authored lines → `size:exception` requested in its PR body (one slicing pass leaves the scaffold commit at ~667). 5. Optional: D13 phone check (user). `make install` clean-clone check deferred by the user.
