# Review advisories (redesign + UX Probador follow-ups)

## Objective

Fix the advisory findings left by the native reviews of the redesign slices (PRs #26-#33, recorded in
`odd/tasks/rediseno.md` Progress 2026-10-01/02 and 2026-10-03) so `main` carries no known UI defects or
test gaps from that work.

## Problem / why

The reviews approved every slice but flagged non-blocking defects: some are user-visible (Historial looks
like an empty wardrobe when its query fails; Armario counters stay stale after pull-to-refresh; Hoy and
Historial keep yesterday's date after midnight), others are edge cases in helpers or untested branches.

## Scope (authorized: owner chose "Avisos de revisión", 2026-10-03)

In: the advisories listed in the tasks below. Out: U5 garment-only cutout, R1/D1 Revisión work, outfit
engine, history API, A15. The native upload part type advisory stays as-is (photos are always re-encoded to
.jpg by `preparePhoto`; low risk, no task).

## Tasks

- [x] **V1** Pure helpers: `tint()` handles 3-digit hex (`#abc`); `FormalityMeter` renders safely when the
      value is NaN / missing / out of range; `isNewGarment` treats future timestamps as not new (or clamps),
      with unit tests for each.
- [x] **V2** Historial: query errors show an error state with retry (not an empty wardrobe); Hoy and Historial
      recompute `now` (date, greeting, relative labels) across midnight / on app focus; tests.
- [x] **V3** Armario counters and review banner refresh on pull-to-refresh; FloatingTabBar skips hidden routes;
      UploadItem done card: no duplicated file name while `useGarment` loads/fails, and the error is surfaced;
      tests.
- [x] **V4** Test gaps: Hoy "absence" tests wait for queries to settle before asserting absence; Segmented
      narrow branch; GarmentImage tint branch; Añadir two-column tips branch; WebFocusRing mount effect. Docs:
      SPA deep-link hosting fallback (static host must rewrite unknown paths to `index.html`). Added from
      `review-def4988555b60feb` (suggestions): `formality-meter.test.tsx` "renders nothing" cases must prove
      nothing renders (no label text / empty tree), not only no `progressbar` role; `use-now.test.ts` must prove
      the timer is cleared on unmount (reset the spy before unmount, or advance timers and expect no update).

## Acceptance criteria

Each advisory is fixed or covered by a test that fails without the fix (where behavioural); no regressions in
existing tests; copy stays es-ES and follows the redesign tone.

## Checks

TDD: off (no project/session TDD configuration). Runner: app `npm test` (jest). Per task in `app/`:
`npx prettier --check .`, `npm run lint`, `npm run typecheck`, `npm test`.

## Delivery

Branch `fix/review-advisories` from `main` `c6af071` (review boundary). Forecast ~400-600 authored lines ->
`ask-on-risk`, reusing the owner's cached chain strategy **stacked-to-main** if it goes over budget. Native
review assessed per work-unit commit (RDD on, global).

## Route per task

- V1-V4: delegated direct (one writer per task) — each touches 2+ non-trivial files and needs reading that
  prepares the write (preparation + writer triggers).

## Progress

- 2026-10-03: feature document created; branch `fix/review-advisories` at `c6af071`.
- 2026-10-03: V1 done (delegated writer) `f93f9e7`: `tint()` doubles 3-digit hex like CSS; `FormalityMeter`
  `level: number | null | undefined`, non-finite/missing renders nothing, finite values still clamped 1..5 (the
  only caller already shows the "add formalidad" prompt for falsy values); `isNewGarment` uses
  `Math.abs(now - created) <= NEW_WINDOW_MS` (small skew still new, far-future dates not). New
  `tests/is-new-garment.test.ts`. Checks: prettier/lint/typecheck clean; jest 234/234 (writer: first run 2
  failures unnamed, second green; parent spot check: `wardrobe.test.tsx` failed 1 test in two cold full runs,
  passed alone 25/25 and in two warm full runs 234/234 -> load/timing flake, pre-existing). Environment: app
  `node_modules` was missing deps after the ext4 move; writer ran `npm ci` (no tracked changes). Assess base
  `c6af071` (untracked excluded: owner's `SPEC-ML.md`, this doc): medium, 67 lines, `under_budget` -> pending in
  slice, boundary stays `c6af071`.

- 2026-10-03: V2 done (delegated writer) `4d90e09`: Historial renders the shared `ErrorState` (server message,
  "Reintentar" refetches every failed query) when any of its three queries errors with no data; loading/empty
  unchanged; no new copy. New `useNow()` (`src/hooks/useNow.ts`, pure `nextTick`) re-arms a timeout to the next
  local midnight or greeting boundary (06/12/20, matching `greeting()`) and refreshes on `AppState` 'active'
  (react-native-web maps it to `visibilitychange`); Hoy and Historial use it instead of a memoised `new Date()`.
  Tests: Historial error + retry; `use-now.test.ts` with fake timers (boundaries, month rollover, midnight, noon,
  foreground after sleep, cleanup). Checks: prettier/lint/typecheck clean; jest 239/239 (parent spot check: one
  cold run failed the known Revisión flake "shows loading, then an error with retry, and a 404 state"; rerun
  239/239, file alone 30/30; writer saw the Wardrobe flake once). Parent readback: no hooks after the early
  return. Assess base `c6af071`: medium, 296 lines (incl. this doc), `under_budget` -> pending in slice.

- 2026-10-03: V3 done (delegated writer) `be7f22d`: Armario pull-to-refresh runs
  `queryClient.refetchQueries({ queryKey: queryKeys.garments.lists(), type: 'active' })` (grid, counters and
  review banner; also mounted Hoy/Historial lists, harmless); FloatingTabBar filters routes whose flattened
  `tabBarItemStyle.display` is `'none'` (expo-router strips `href`), "N of M" counts visible tabs; UploadItem done
  card shows the file name once and, on `useGarment` error, "No se pudieron cargar los detalles de la prenda." +
  "Reintentar" (a11y "Reintentar detalles de {name}") next to "Revisar". Checks: prettier/lint/typecheck clean;
  jest 244/244 (writer and parent spot check).
- 2026-10-03: native review of slice `c6af071..be7f22d` (V1-V3 + doc, 18 files, 452 lines, medium,
  `slice_budget_reached`): untracked excluded (`--untracked-scope=exclude`, owner's `SPEC-ML.md`), owner
  granted, `review-def4988555b60feb` one lens (reliability) approved and acknowledged (burned). Two SUGGESTION
  findings folded into V4. Reviewed boundary -> `be7f22d`.

- 2026-10-03: V4 done (delegated writer) `dbf47de` tests + `c455a63` docs; no production change, no bug found.
  Hoy: `index.test.tsx` dated-greeting test now awaits the empty-state text before asserting absence (other Hoy
  absence tests already awaited or are prop-driven). New coverage: Segmented narrow (column at 390 dp, row at
  1024), `garment-image.test.tsx` (GarmentImage/HeroImage tint and plain), Añadir tips side column at 1200 dp vs
  stacked at 390, WebFocusRing (fake `document`, style tag injected once on web, nothing on iOS; file renamed to
  `.tsx`). Review suggestions: FormalityMeter "renders nothing" also checks no label text and `toJSON()` null;
  `useNow` asserts `clearTimeout` with the armed timer id on unmount and no update after 24 h. README "Hosting
  the web build" (SPA fallback to `/index.html`). Checks: prettier (app) / lint / typecheck clean; jest 253/253
  in two writer runs and the parent spot check. README is outside the app prettier scope (already failing at
  HEAD before this edit). Assess base `be7f22d`: medium, 241 lines, `under_budget`; no later commit, so this
  tests+docs slice stays unreviewed.

## Delivery plan

Feature total ~700 authored lines (> 400) -> owner's cached chain strategy **stacked-to-main**, one PR per
slice: PR 1 `c6af071..be7f22d` (V1-V3, reviewed `review-def4988555b60feb`), PR 2 `be7f22d..HEAD` (V4 + doc,
stacked on PR 1). Push and PR creation are the owner's decision.

## Next step

Owner: push + PRs (plan above), merge, then delete branches. Open follow-ups outside this feature: cold-run
jest flakes in `wardrobe.test.tsx` and `review.test.tsx`; `README.md` prettier formatting.
