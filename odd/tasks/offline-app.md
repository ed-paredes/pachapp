# Offline app (read-only, Android) — hybrid cache

## Objective

Let the owner open the Android app and look at the wardrobe without the backend stack running (no API, no
worker, no Metro): the native app keeps the last data and images it received; the web app keeps reading from
the API as today.

## Problem / why

Today every screen reads from the local FastAPI backend and the phone loads the JS from Metro through Expo Go,
so looking at the wardrobe needs `make run`, `make run-worker` (heavy, GPU) and `make run-ui`. The owner wants
to browse it (and outfits, once the engine exists) away from the PC. R1 research
(`odd/tasks/review-follow-ups.md`, 2026-10-04): a persisted TanStack cache does not cut requests but is the
base for offline reads; images are plain `/images/...` paths served by the backend.

## Scope (owner decisions, 2026-10-04)

- Hybrid: persistence and offline UX on native only (`Platform.OS !== 'web'`); web unchanged (always reads
  the API, nothing persisted).
- Read-only offline: browse Armario, Detalle, Hoy, Historial from the saved data; upload, edit, wear/laundry
  and other mutations are disabled with an explanation while the backend is unreachable. No offline write
  queue.
- Android standalone build (APK with the JS bundle embedded) compiled locally; the owner has Android Studio
  (SDK on Windows: `C:\Users\edpar\AppData\Local\Android\Sdk`; WSL has JDK 17, no Linux SDK). Route for the
  build (Linux SDK in WSL vs build from Windows) to be decided at O4.
- Outfits: the outfit engine does not exist yet; it is out of scope here. When it is built, its results must
  be persistable the same way.

Out: offline writes, the R1 request-reduction options (narrow refresh, staleTime, counts endpoint), U5,
outfit engine, iOS.

## Tasks

- [x] **O1** Persisted query cache, native only. `@tanstack/react-query-persist-client` +
  `@tanstack/query-async-storage-persister` (versions matching `@tanstack/react-query` ^5.104) over
  `@react-native-async-storage/async-storage` (already a dependency). `PersistQueryClientProvider` on native,
  plain provider on web. maxAge ~30 days, `gcTime` >= maxAge for persisted queries, `buster` tied to the app
  version/schema. Persist garment lists (incl. infinite), garment details, settings and the Historial/Hoy
  lists; never jobs or in-flight processing state. When the backend is reachable on native, sync the whole
  wardrobe once per app start (all list pages + details, bounded concurrency) so unopened garments work
  offline. Jest: AsyncStorage mock; tests that web never persists and native restores.
- [x] **O2** Offline images, native only: garment thumbnails and cutouts stored on disk (expo-image disk cache
  policy + prefetch during the O1 sync, or expo-file-system download if the cache is not reliable); images
  render from disk with the backend down.
- [x] **O3** Offline UX, native only (UI task: frontend-design + ux-copy; critique + a11y on screenshots).
  Detect "backend unreachable" (network error, not HTTP errors); show a calm banner with the last sync time
  (e.g. "Sin conexión con tu armario · mostrando lo guardado el 4 oct"); disable mutations (upload, edit,
  wear, laundry, archive, delete, settings) with an explanation; cached data is never replaced by full-screen
  errors; recover automatically when the backend answers again.
- [x] **O5** Hardening from the O1+O2 and O3 reviews (all non-blocking, recorded 2026-10-04):
  (a) `http-client.ts` native GET timeout drops the caller's abort signal (React Query cancellation no longer
  aborts) and a caller abort is reported as unreachable -> combine signals, ignore caller aborts in
  reachability; (b) `isNetworkError` returns true for any non-ApiError -> only fetch TypeError / timeout abort,
  with tests; (c) persisted queries restored with status `error` -> check every screen shows data first after a
  save/restore round trip (or persist as success), with a round-trip test; (d) persisted cache grows without
  bound (gcTime Infinity, one key) -> prune details of garments no longer in the synced lists and one-off
  filter lists at sync time, guard/report failed writes; (e) sync filters must match the screens' query keys ->
  share the filter constants with the screens or add a test that renders Armario/Hoy/Historial from synced
  data with the API failing; (f) WardrobeSyncer foreground re-sync only after a failed run -> tests incl.
  cleanup; (g) buster test waits a fixed 50 ms -> wait for restore to finish; (h) web "never persists" test can
  catch a throttled write from earlier native tests -> isolate timers/persister; (i) Detalle delete
  confirmation can still send offline -> re-check at confirm or close it when going offline; (j) sync
  single-flight shared across QueryClient instances -> key it by client (suggestion).
- [x] **O4** Android standalone build: `app.json` Android config (package id, name, icon), API base URL baked
  at build time (`EXPO_PUBLIC_API_BASE_URL`, LAN IP), cleartext HTTP allowed for the LAN API
  (`expo-build-properties` `usesCleartextTraffic` or a network security config), release build with the
  bundle embedded, documented build/install steps (README). Owner installs and tests with the stack stopped.

## Acceptance criteria

- Native app opened with the API stopped shows Armario, Detalle, Hoy and Historial from the last sync, with
  images, plus the offline banner; mutations disabled with an explanation.
- With the API back, the banner clears and data refreshes without restarting.
- Web behaves exactly as before (tests prove nothing is persisted on web).
- All app checks clean; new behaviour covered by tests.

## TDD / checks

TDD: off (no project/session TDD configuration). Runner: app `npm test` (jest). Per task in `app/`:
`npx prettier --check .`, `npm run lint`, `npm run typecheck`, `npm test`. O3: screenshots + critique/a11y.
O4: a release build that installs and runs on the owner's phone (owner verifies).

## Delivery

Forecast ~500-700 authored lines (O1-O3 ~400-550 with tests, O4 ~50-150 config + docs) -> over the ~400
budget. Strategy `ask-on-risk` with the owner's cached chain strategy **stacked-to-main**: one PR per reviewed
slice (O1+O2, then O3, then O4) on branch `feat/offline-app` from `main` `c57d9cd`.

## Routes

- O1-O3: delegated writer (2+ non-trivial files each), one writer at a time, one commit per task.
- O4: delegated writer (script + config + Makefile + README; 4+ files). Build run by the parent via `make android-apk`.

## Progress

- 2026-10-04: scope agreed with the owner (hybrid, read-only, Android APK compiled locally). Feature document
  created.

- 2026-10-04: O1 `66238d4`, O2 `15ce70f`, O3 `16950b4` (delegated writer). O1: native-only
  `PersistQueryClientProvider` over AsyncStorage (`@tanstack/react-query-persist-client` and
  `@tanstack/query-async-storage-persister` ^5.104.1), maxAge 30 days, buster = app version + schema, persisted
  families garment lists/details/settings/sync stamp with `gcTime: Infinity` (30 days overflows the JS timer and
  collected restored queries at once), splash held while restoring; sync after restore (5 Armario infinite lists,
  counters, review banner, category counts, Hoy/Historial lists, settings, every detail; 4 concurrent;
  single-flight; stamp only on full success). O2: one `GARMENT_IMAGE_CACHE_POLICY = 'memory-disk'`; the sync
  prefetches missing thumbs/cutouts (`getCachePathAsync` + `Image.prefetch(..., 'disk')`, batches of 20). O3:
  reachability at the HTTP layer (any response = online; rejected fetch or 15 s GET timeout = offline;
  `GET /health` ping every 15 s and on foreground while offline; recover refetches and resyncs); banner "Sin
  conexión con tu armario. Mostrando lo guardado <fecha>." announced once; mutations disabled with "Podrás hacer
  cambios cuando vuelva la conexión." (Detalle actions, Revisión, Ajustes, Añadir); data wins over errors on Hoy,
  Ajustes, Armario; persist any query with data (a status-based predicate dropped data after an offline
  refetch). Checks: prettier/lint/typecheck clean; jest 281 -> 291 -> 315/315; many RED probes (several first
  passed vacuously and the assertions were fixed). Screenshots (web with a temporary uncommitted flag + mock API):
  scratchpad `pw/offline/`; reviewed against critique/a11y criteria by the writer (formal skill passes not run).
  Parent spot check: jest 315/315; `/health` exists (backend `main.py:57`); screenshots read back.
  Authored lines ~1,900 (O1 ~760, O2 ~228, O3 ~925), well over the ~400 heuristic; review in slices.
  Open (owner): sync frequency / manual "sync now"; ping and timeout 15 s; copy; queued uploads not disabled
  offline; never-visited filter combinations not synced. Left: disabled secondary Button nearly invisible
  (shared style); note not linked to disabled buttons (no hint prop). Risks to verify on the phone: Hermes
  `new Request(request, { signal })`, SafeArea override under the native stack, expo-image cache APIs on Android,
  AsyncStorage ~2 MB row limit (single key; ~600+ garments would need a chunked persister), image cache eviction,
  image URLs tied to the LAN IP.

- 2026-10-04: O4 (delegated writer) `cddb159`: `android.package` `com.edparedes.pachapp`, `expo-build-properties`
  `usesCleartextTraffic`, `scripts/build-android.ps1` (robocopy mirror to `%LOCALAPPDATA%\pachapp-android`, hash
  stamps for `npm ci` and `prebuild --clean`, JDK 17+ check, `-Install` via adb), `make android-apk`, README
  section. Parent build runs fixed in `2d30eb6`: npm.ps1 breaks under StrictMode (use `npm.cmd`/`npx.cmd`); UNC
  current directory for cmd.exe (start in `$env:TEMP`); Gradle `OutOfMemoryError: Metaspace` building four ABIs
  (now `-Xmx3g`, Metaspace 1g, `--max-workers=2`, `arm64-v8a` only via `-Abis`); a stale daemon from the OOM run
  locked `R.jar` (parent stopped the leftover Gradle/Kotlin daemons; Android Studio was not running). Fourth run:
  APK built, `pachapp-1.0.0-20261004-1412.apk` 43 MB. Not yet installed on the phone.
- 2026-10-04: native reviews: O1+O2 `c57d9cd..15ce70f` `review-e4db09458c68c040` and O3 `15ce70f..7616bf5`
  `review-dc8ec5ab9817c603`, both owner granted, reliability, approved and acknowledged (burned) in a detached
  review worktree `~/code/pachapp-worktrees/review-o1o2`. Their non-blocking findings -> task O5. Stacked PRs
  opened: #38 `offline/01-cache-images` -> main, #39 `offline/02-offline-ux` -> #38.

- 2026-10-04: owner phone test (APK installed by the owner): with the API running, a new photo stayed "en cola"
  until the worker was started (expected); after syncing, API + worker + Expo stopped, app closed and reopened:
  owner reports it works perfectly (saved wardrobe, images and offline UX). Recovery when the API comes back not
  yet tested on the phone.

- 2026-10-04: O5 (delegated writer) `3fc81a5` (a, b: caller abort joined to the native GET timeout by a manual
  combiner, no `AbortSignal.any`; caller aborts never mark offline; `RequestTimeoutError`; `isNetworkError` =
  TypeError or timeout), `ec75d43` (c: persister settles restored/saved queries to success; d: prune details of
  garments not synced and unsynced lists after a successful sync, keep observed queries, lean retry without
  details on a failed write, never throws; e: `src/lib/wardrobe-filters.ts` shared by screens and sync +
  integration test rendering Armario/Hoy/Historial/Detalle from synced data with the API down; f: syncer
  foreground tests; j: single-flight per QueryClient), `cdabc14` (g: buster test waits for restore; h: web test
  uses a web-only marker; i: Detalle closes/disables delete confirmation offline). Checks: prettier/lint/
  typecheck clean; jest 329 -> 345 -> 346/346; offline suites 5 runs 62/62; RED probes per item (several first
  passed vacuously and were tightened). Screen audit: every screen already data-first. Parent spot check: jest
  346/346. Owner-visible: lists browsed under one-off filters are pruned after the next successful sync.
  To re-check on the next APK: combined abort signal on Hermes (pull-to-refresh / leaving a screen must not mark
  offline), delete confirmation closing offline, recovery banner.

## Next step

Native review of the O4+O5 slice (`7616bf5..HEAD`), mark #40 ready, rebuild the APK for the phone re-check,
merge #38, #39, #40 in order (owner's call).
