# Review follow-ups (after review advisories)

## Objective

Close the leftovers of the review-advisories feature (`odd/tasks/review-advisories.md`, PRs #34/#35): the
non-blocking WARNING from `review-7b3d031a732bdc72`, the owner-deferred items, the cold-run jest flakes and the
README formatting.

## Problem / why

- Historial hides a failed secondary list ("Dales otra oportunidad") with no error and no retry; with
  `retry: false` in the query client it never self-heals, and the user cannot tell "failed" from "empty".
- `tests/review.test.tsx` "shows loading, then an error with retry, and a 404 state" races: the mocked fetch
  resolves inside render's act on cold runs, so the synchronous spinner assertion fails. `wardrobe.test.tsx`
  has a cold-run flake that is not yet identified.
- Three tests duplicate the same `Dimensions.get` spy for window-width cases.
- Two conventions are undocumented (FloatingTabBar hides only `href: null` routes; "Nueva" lasts 7 days).
- Root `README.md` fails prettier (table alignment only).

## Scope (owner decisions, 2026-10-04)

- Historial: inline notice + "Reintentar" in place of the "Dales otra oportunidad" card; retry refetches only
  the failed queries; the rest of Historial unchanged.
- Armario refresh fan-out: not changed now. Recorded as research: can a persisted cache (browser/app storage,
  e.g. react-query persistence) cut the number of requests? See R1 below.
- "Nueva" pill: unchanged; only document the 7-day rule.
- README: format it with prettier.
- FloatingTabBar: document the `href: null` convention (no `tabBarButton` detection).

Out: U5 garment-only cutout, ux-probador R1, outfit engine.

## Tasks

- [ ] **F1** Historial secondary-query failure notice. Compact inline error (new small component or a
  `compact` variant of `ErrorState`) with "Reintentar" in the second-chance card slot when `unworn` or `stale`
  failed with no data; retry refetches only the failed queries and is disabled while fetching. Tests: stale
  fails -> notice + Reintentar, no full-screen `error-state`; retry with success -> section appears; unworn
  fails; retrying disabled; `HistoryView` unit test for the new prop. UI task: load frontend-design + ux-copy;
  design-critique + accessibility-review on screenshots before closing.
- [ ] **F2** Cold-run flakes. `review.test.tsx`: gate the mocked 500 behind a deferred promise so the spinner is
  asserted before the response settles. `wardrobe.test.tsx`: diagnose the flaky test (cold runs) and fix it
  the same way, or record the evidence if it cannot be reproduced.
- [ ] **F3** Shared window-size test helper `app/tests/helpers/window.ts`, adopted by
  `garment-detail.test.tsx`, `segmented.test.tsx` and `add-capture-tips.test.tsx`; same assertions.
- [x] **F4** Docs: FloatingTabBar JSDoc + `_layout.tsx` note (hide tabs with `href: null` only); `NEW_WINDOW_MS`
  comment stating the 7-day rolling rule; `README.md` formatted with prettier.
- [ ] **R1 (research, pending)** Persisted query cache to reduce requests on refresh/tab switches: options
  (`@tanstack/query-persist-client` with localStorage on web / AsyncStorage on native, staleTime tuning,
  narrower refetch keys), trade-offs (stale data after server-side changes, storage size, image URLs), and a
  recommendation. Not implemented in this feature.

## Acceptance criteria

- F1-F4 done with their tests; no full-screen error when only a secondary list fails.
- `review.test.tsx` passes 10 cold runs in a row (jest cache cleared).
- All app checks clean.

## TDD / checks

TDD: off (no project/session TDD configuration). Runner: app `npm test` (jest). Per task in `app/`:
`npx prettier --check .`, `npm run lint`, `npm run typecheck`, `npm test`. README: `npx --prefix app prettier
--check README.md` from the repo root.

## Delivery

Forecast ~150-200 authored lines (under the ~400 budget): one branch `chore/review-follow-ups` from `main`
`df24db3`, one PR. Strategy `ask-on-risk` (owner's cached chain strategy stacked-to-main if it grows).

## Routes

- F1-F3: delegated writer (2+ non-trivial files; preparation reading belongs to the writer). Mapping done by a
  delegated explorer (7 items, 4+ files).
- F4: inline (mechanical comments + formatter).
- R1: delegated read-only research when the owner picks it up.

## Progress

- 2026-10-04: mapping by a delegated explorer; owner decisions recorded in Scope.

- 2026-10-04: F4 done inline `7eefefc` (comments in `GarmentCard.tsx`, `FloatingTabBar.tsx`, `(tabs)/_layout.tsx`;
  `README.md` formatted, table alignment only). Checks: app prettier/lint/typecheck clean; README prettier
  clean. Jest not run (comments only).

## Next step

F1-F3 with one delegated writer, one commit per task.
