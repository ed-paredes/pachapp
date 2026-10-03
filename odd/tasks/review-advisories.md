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
- [ ] **V2** Historial: query errors show an error state with retry (not an empty wardrobe); Hoy and Historial
      recompute `now` (date, greeting, relative labels) across midnight / on app focus; tests.
- [ ] **V3** Armario counters and review banner refresh on pull-to-refresh; FloatingTabBar skips hidden routes;
      UploadItem done card: no duplicated file name while `useGarment` loads/fails, and the error is surfaced;
      tests.
- [ ] **V4** Test gaps: Hoy "absence" tests wait for queries to settle before asserting absence; Segmented
      narrow branch; GarmentImage tint branch; Añadir two-column tips branch; WebFocusRing mount effect. Docs:
      SPA deep-link hosting fallback (static host must rewrite unknown paths to `index.html`).

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

## Next step

V2 (Historial error state + stale `now`).
