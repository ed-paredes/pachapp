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

- [ ] **O1** Persisted query cache, native only. `@tanstack/react-query-persist-client` +
  `@tanstack/query-async-storage-persister` (versions matching `@tanstack/react-query` ^5.104) over
  `@react-native-async-storage/async-storage` (already a dependency). `PersistQueryClientProvider` on native,
  plain provider on web. maxAge ~30 days, `gcTime` >= maxAge for persisted queries, `buster` tied to the app
  version/schema. Persist garment lists (incl. infinite), garment details, settings and the Historial/Hoy
  lists; never jobs or in-flight processing state. When the backend is reachable on native, sync the whole
  wardrobe once per app start (all list pages + details, bounded concurrency) so unopened garments work
  offline. Jest: AsyncStorage mock; tests that web never persists and native restores.
- [ ] **O2** Offline images, native only: garment thumbnails and cutouts stored on disk (expo-image disk cache
  policy + prefetch during the O1 sync, or expo-file-system download if the cache is not reliable); images
  render from disk with the backend down.
- [ ] **O3** Offline UX, native only (UI task: frontend-design + ux-copy; critique + a11y on screenshots).
  Detect "backend unreachable" (network error, not HTTP errors); show a calm banner with the last sync time
  (e.g. "Sin conexión con tu armario · mostrando lo guardado el 4 oct"); disable mutations (upload, edit,
  wear, laundry, archive, delete, settings) with an explanation; cached data is never replaced by full-screen
  errors; recover automatically when the backend answers again.
- [ ] **O4** Android standalone build: `app.json` Android config (package id, name, icon), API base URL baked
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
- O4: decided at O4 (environment setup needs owner authorization for downloads/installs).

## Progress

- 2026-10-04: scope agreed with the owner (hybrid, read-only, Android APK compiled locally). Feature document
  created.

## Next step

O1-O3 with one delegated writer.
