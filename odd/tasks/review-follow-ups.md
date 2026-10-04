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

- [x] **F1** Historial secondary-query failure notice. Compact inline error (new small component or a
  `compact` variant of `ErrorState`) with "Reintentar" in the second-chance card slot when `unworn` or `stale`
  failed with no data; retry refetches only the failed queries and is disabled while fetching. Tests: stale
  fails -> notice + Reintentar, no full-screen `error-state`; retry with success -> section appears; unworn
  fails; retrying disabled; `HistoryView` unit test for the new prop. UI task: load frontend-design + ux-copy;
  design-critique + accessibility-review on screenshots before closing.
- [x] **F2** Cold-run flakes. `review.test.tsx`: gate the mocked 500 behind a deferred promise so the spinner is
  asserted before the response settles. `wardrobe.test.tsx`: diagnose the flaky test (cold runs) and fix it
  the same way, or record the evidence if it cannot be reproduced.
- [x] **F3** Shared window-size test helper `app/tests/helpers/window.ts`, adopted by
  `garment-detail.test.tsx`, `segmented.test.tsx` and `add-capture-tips.test.tsx`; same assertions.
- [x] **F4** Docs: FloatingTabBar JSDoc + `_layout.tsx` note (hide tabs with `href: null` only); `NEW_WINDOW_MS`
  comment stating the 7-day rolling rule; `README.md` formatted with prettier.
- [x] **R1 (research, done; implementation pending owner decisions)** Persisted query cache to reduce requests on refresh/tab switches: options
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

- 2026-10-04: F3 (delegated writer) `017d767`: `app/tests/helpers/window.ts` `withWindowWidths(height, fn)`
  (spies `Dimensions.get`, restores in `finally`), adopted by garment-detail, segmented and add-capture-tips;
  assertions unchanged. RED probe: helper ignoring the width fails all 3. 41+/27-.
- 2026-10-04: F2 (delegated writer) `1165de4`: review "shows loading, then an error with retry, and a 404 state"
  and wardrobe "shows the grid skeleton while loading" gate the response behind a deferred promise. Wardrobe
  flake reproduced once in a combined cold run ("hides the 'Añadir prenda' tile under Archivadas", message not
  captured); inferred cause: the tab switch briefly shows the skeleton, so `waitFor(tile is null)` passed early;
  fix asserts card present + tile absent in one `waitFor`. Proof: review alone 10/10 cold runs; wardrobe +
  review + history 10/10 cold runs. 42+/11-.
- 2026-10-04: F1 (delegated writer) `35e4648`: new `SectionError` (card style like `RankCard`, title kept, "No se
  pudo cargar esta lista." + primary "Reintentar" 44 dp, `accessibilityRole="alert"`, label "Reintentar:
  <title>"); `HistoryView` prop `secondChanceError`; `history.tsx` `failedLists` (unworn/stale with no data and
  error), retry refetches only those, disabled while fetching; full-screen block for `active` untouched. Tests:
  notice without `error-state`, retry restores the section and repeats only the failed request, unworn
  failure, disabled while retrying, HistoryView unit tests; RED probes (prop ignored, refetch-all, retrying
  false, unworn ignored) all failed as expected. Screenshots (web build + mock API, playwright-core):
  scratchpad `pw/follow-ups/` phone 390x844 and desktop 1440x900; design-critique fixed the button contrast
  (primary ink instead of white on white); a11y: single alert announcement, focus ring visible, text ~6:1;
  screen reader not tested. Open product gap: when only one secondary list fails, the notice replaces the
  whole card, hiding the other list's items. 195+/7-.
- 2026-10-04: checks after each writer commit: prettier/lint/typecheck clean; jest 257/257, 257/257, 263/263.
  Parent spot check: jest 263/263; screenshots read back.
- 2026-10-04: R1 research (delegated, read-only). Findings: no staleTime (0) and gcTime 5 min defaults; pull-to-
  refresh refetches every active `['garments','list']` query (Armario grid, 4-6 `useTotal` counters, review
  banner, category chips, plus mounted Hoy/Historial); tab switches do not refetch; cold start ~10-13 list
  requests. Options ranked: (1) in-memory tuning (narrow the Armario refresh to grid + counters, modest
  staleTime for non-grid lists), ~15-40 lines; (2) one `GET /garments/counts` endpoint replacing 5-7
  `page_size: 1` requests, ~100-170 lines across backend + app; (3) persisted cache
  (`@tanstack/react-query-persist-client` + localStorage / AsyncStorage, already a dependency) only improves
  first paint and offline reads, does not cut requests, ~40-70 lines + 2 deps; (4) HTTP ETag/304 skipped
  (saves bytes, not requests; unreliable on native). Owner decisions: acceptable staleness window; refresh
  only Armario or the whole app; instant paint / offline wanted; new counts endpoint OK. Gaps: counts from
  code reading only; AsyncStorage limits, infinite-query persistence and persister versions unverified.

- 2026-10-04: owner kept the F1 behaviour: the notice replaces the whole second-chance card even when only one
  secondary list failed.
- 2026-10-04: native review of `df24db3..216ca7e` (16 files, 488 lines, medium, `slice_budget_reached`), owner
  granted, `review-770249cd17ec7d62` one lens (reliability) approved and acknowledged (burned). Reviewed
  boundary -> `216ca7e`. Non-blocking: WARNING partial list hidden when one list fails (= the owner decision
  above, kept; untested mixed state); SUGGESTION add tests for an unworn-only retry (repeats only the unworn
  request) and both lists failing at once (follow-up).

- 2026-10-04: review SUGGESTION done inline `07fe057` (one test file, owner asked): unworn-only retry repeats only
  `wear_count:asc`; both lists failing show one notice and the retry repeats both. RED probes (retry always
  refetches both; `failedLists` ignores unworn) failed 4 and 3 tests; reverted. Checks: prettier/lint/typecheck
  clean; jest 265/265.

## Next step

Push, open the PR and merge (owner approved 2026-10-04). Follow-up: R1 implementation once the owner answers
its decisions.
