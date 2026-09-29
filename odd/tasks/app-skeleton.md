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

- [x] **T1 — Navigation, screen shells, state components, API client + Query provider, tests.** Route: delegated direct (writer trigger).
  - Checks: `npm run format:check`, `lint`, `typecheck`, `test`; `expo export --platform web`.

## Delivery

Forecast: ~400–700 authored lines (lockfile excluded). Strategy `ask-on-risk`; stacked-to-main.

## Progress

- 2026-09-29: worktree, branch and feature document created.

## Checkpoint 2026-09-29 — resume here

Writer for T1 stopped at the user's request (checkpoint) right after lint/format/typecheck came back clean, before running the test suite. No final report; nothing committed. Uncommitted: tabs `app/app/(tabs)/`, stack screens (`favorites`, `garments/`, `review/`, `settings`), `jest.setup.js`, api-client (`http-client.ts`, `query-client.ts`), components (CaptureTipsPanel, EmptyState, ErrorState, IconSymbol, LoadingState), hooks (`useCaptureTipsSeen`, `useHealth`), `src/lib/`, 6 new tests; `app/app/index.tsx` deleted (moved into tabs); package.json/lock changed.

Known issue (found by the data-model writer): a clean `npm install` fails with a peer conflict — `typescript ~6.0.3` vs `openapi-typescript@7.13.0` peer `^5.x`. Affects `make install` from a clean clone (also on `main`). Fix here or in a small separate PR.

On resume: re-verify (`npm run format:check`, `lint`, `typecheck`, `test`, web export), review the diff and dependency choices, commit, PR.

## Resume 2026-09-29 — verification and commits

- Re-verify found 4 failing tests in 3 suites (format/lint/typecheck/web export were clean). Fixed by a delegated writer: `tabs-layout` and `add-capture-tips` did not await RNTL 14's async `renderRouter`/`fireEvent.press`; `settings` exposed an app bug — `openapi-fetch` captured `globalThis.fetch` at client creation, so the client now resolves fetch per request (`http-client.ts`). Jest "worker failed to exit" fixed (test QueryClient `gcTime: 0` + cleanup). Remaining noise: one act(...) console warning from react-query in the settings suite (non-failing).
- Checks (feature branch head): `format:check`, `lint`, `typecheck` exit 0; `npm run test` 8 suites / 12 tests passed; `expo export --platform web` ok.
- Work-unit commits (each typechecks and passes its tests on its own):
  - `50a1f2e` feat(app): typed API client, query provider, test setup (~118 lines + lockfile) — 2 suites / 3 tests
  - `1e50689` feat(app): loading/empty/error state components (~182) — 3 suites / 5 tests
  - `f811ccc` feat(app): tab navigation and screen shells (~772) — 8 suites / 12 tests
- New deps: `@tanstack/react-query`, `openapi-fetch`, `@react-native-async-storage/async-storage`.
- Clean `npm install` peer conflict (typescript ~6.0.3 vs openapi-typescript 7.13 peer ^5) still open — separate small PR.

## Next step

Review assessment for the slice(s), then push + stacked PRs (user decision).
