# App skeleton (spec 07)

Locator: `odd/tasks/app-skeleton.md` · Engram mirror: `odd/app-skeleton/tasks`
Branch: `feat/app-skeleton` (from `main` `525e8fb`), worktree `~/pachapp-worktrees/app-skeleton`. Runs in parallel with `feat/ml-1-registry` and `feat/phase-1-data-model` (user approved isolated worktrees, 2026-09-29).

## Objective

Navigation and screen shells of `docs/specs/07-app-ui.md` so later features plug in real data: bottom tabs Hoy, Armario, Añadir, Historial (UI-REQ-002/003); stack screens Revisión, Detalle de prenda, Favoritos, Ajustes; shared loading/empty/error-with-retry components (UI-REQ-004/007/008); TanStack Query provider and a typed API client wired to `EXPO_PUBLIC_API_BASE_URL` and the generated `schema.ts` (07 "Uso del cliente de API vía TanStack Query"); the capture-tips panel on Añadir (UI-REQ-020) with local "seen" persistence.

## Constraints

- No real endpoints yet beyond `/health`: screens show empty/placeholder states; no fake data presented as real.
- Spanish UI copy; English code/comments. Only `app/` changes.
- Web uses the same tabs (UI-REQ-003 default).

## TDD

Mode: off. Runner: `npm test` (jest-expo). Ordinary functional checks.

## Tasks

- [ ] **T1 — Navigation, screen shells, state components, API client + Query provider, tests.** Route: delegated direct (writer trigger).
  - Checks: `npm run format:check`, `lint`, `typecheck`, `test`; `expo export --platform web`.

## Delivery

Forecast: ~400–700 authored lines (lockfile excluded). Strategy `ask-on-risk`; stacked-to-main.

## Progress

- 2026-09-29: worktree, branch and feature document created.
