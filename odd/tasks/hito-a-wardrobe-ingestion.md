# Hito A — upload a photo and the garment appears in the wardrobe

Locator: `odd/tasks/hito-a-wardrobe-ingestion.md` · Engram mirror: `odd/hito-a-wardrobe-ingestion/tasks`
Worktree: `~/pachapp-worktrees/hito-a` · Base branch: `feat/hito-a` (from main `eff0114`).

## Objective

First end-to-end product flow: the user uploads a garment photo from the app, the worker processes it (preprocess → cutout → color → consolidate), and the garment shows up cut out in Armario, openable in Detalle and Revisión. Specs: 03-garment-ingestion, 04-wardrobe-api, 07-app-ui (Añadir, Armario, Detalle, Revisión, Ajustes), 02-data-model.

## Scope and constraints

- Authorized by the user on 2026-09-29 ("si no depende de T3, adelante").
- **Out of scope until T3 merges:** 08 step 4 (ai_attributes + embedding in the worker). Those two steps are registered but deferred (skipped, progress 75/90 kept monotonic). Duplicate warning (ING-REQ-024) and kNN come later.
- `api` never imports `ml` (VIS-REQ-004/005): shared image/colour code lives outside `ml` and never imports `ml.background` privates.
- `make test` never loads real models (VIS-REQ-029): the worker's cutout step takes a `BackgroundRemover` protocol; tests inject a fake.
- Shared files also touched by `feat/ml-3-zero-shot` (Makefile, README, `ml/registry.py`, `ml/background.py`, specs 03/08): avoid or keep edits small and last; no edits to top-level `conftest.py` or `settings.py` unless unavoidable.
- No new settings expected (images root, upload/thumb px, poll interval already exist).

## TDD

Mode: off (no project/session TDD configuration). Runners: `uv run pytest` (backend), `npm run test` (app). Ordinary functional checks per task.

## Defaults chosen for spec gaps (user may veto)

- **Image URLs:** API responses return stored relative paths (`cutout/{id}.png`); the app prefixes `API_BASE_URL/images/`.
- **Armario list:** app requests `status` ∈ {active, laundry} by default; archived via filter. Garments still processing (no `img_thumb`) show a placeholder card with progress.
- **Garments without AI attributes (until T3 step 4):** consolidate does not force `needs_review`; Revisión shows empty editable chips.
- **Colour palette:** fixed ~20 Spanish names with sRGB anchors in code (`negro, blanco, gris, beige, camel, marino, denim, marrón, rojo, burdeos, rosa, naranja, amarillo, verde, oliva, azul, celeste, morado, turquesa, caqui`); ΔE CIEDE2000; alpha threshold 10 (same as `ml.background.OPACITY_THRESHOLD`, duplicated as a constant, not imported); KMeans k=4, `random_state=0`; `color_confidence` = documented formula of cluster compactness and separation (tunable).
- **Colour edits:** PATCH `colors` validated against `Colors`, sets `color_confidence=1.0`, recomputes `is_neutral`; also writes `ai_correction(field="colors")` when the previous value came from the pipeline.
- **Preprocess failures:** undecodable original → `failed` without retry; I/O errors retryable once (ING-REQ-022). `attempts` counts per job.
- **Stuck jobs:** on worker start, jobs left `claimed`/`running` by a previous worker are requeued to `pending` (single worker, VIS-REQ-025).
- **`job.error`:** short user-facing Spanish message; details go to the worker log.
- **Error codes:** `GARMENT_NOT_FOUND`, `JOB_NOT_FOUND`, `INVALID_IMAGE`, `IMAGE_TOO_LARGE`, `JOB_NOT_FAILED`, `GARMENT_HAS_HISTORY`, `INVALID_WEIGHTS`.
- **Upload:** client resizes to `upload_max_px` with `expo-image-manipulator`; picker `expo-image-picker` (native) / file input (web). HEIC not supported server-side (picker returns JPEG).
- **After `done`:** Añadir shows "Revisar" per photo (invites, does not auto-navigate, so several uploads can chain). Pending jobs are kept in memory while the app runs (not persisted across restarts).
- **Retry:** re-runs the whole pipeline, overwriting images and colours unless `colors` was user-corrected.
- **Settings PATCH:** thresholds in [0,1], days ≥ 0, weights must sum to 1.0±0.01 (no auto-normalization).

## Tasks

Route per task: delegated direct (writer trigger: each task touches 2+ non-trivial files). Stacked PRs to main, one or two tasks per PR.

- [x] **A1 (B)** Imaging/storage helpers (`shared/imaging.py`, `shared/storage.py`) + error envelope (`api/errors.py`). Done when: unit tests (EXIF, decode/size validation, relative layout) pass; envelope `{"error":{code,message,details}}`; api↛ml boundary test still passes.
- [x] **A2 (B)** DB session dependency, `POST /garments` (202, ING-REQ-001..003), `GET /jobs/{id}` (ING-REQ-026), `/images` static mount (API-REQ-016); `python-multipart` if missing; regenerate client. Done when: TestClient tests with tmp DB/images root pass.
- [x] **A3 (B)** Worker runner: atomic claim (DAT-REQ-009, ING-SCN-006), lifecycle, step-at-start, retry-once, progress table, stuck-job requeue, deferred steps. Done when: tests with fake steps pass.
- [x] **A4 (B)** Steps preprocess + cutout (fake-remover tests; soft failure ING-SCN-005; cutout/thumb files, relative paths). Done when: ING-REQ-008/009, ING-SCN-005 tests pass.
- [x] **A5 (B)** Colour extraction (ING-REQ-010..014) + consolidate (colour threshold, cutout soft failure). Done when: end-to-end worker test (fake remover) pending → done with colours and `needs_review`.
- [x] **A6 (B)** `GET /garments` (filters, sort, pagination) + `GET /garments/{id}`; regenerate client. Done when: API-REQ-003..005, API-SCN-001 tests pass.
- [x] **A7a (B)** PATCH (+ `ai_correction`, user source, colours) + `POST review/complete`. Done when: API-REQ-006/007/019, API-SCN-002/002b pass.
- [ ] **A7b (B)** archive / reactivate / retry / delete. Done when: API-REQ-010..012, API-SCN-003/004 pass; client regenerated.
- [ ] **A8 (B)** `GET/PATCH /settings` (API-REQ-014/015, API-SCN-005); regenerate client.
- [ ] **A9 (A)** App data layer: `useGarments`, `useGarment`, `useJob`, `useSettings` + mutations, query keys, `imageUrl()`.
- [ ] **A10 (A)** Añadir: picker/camera, client resize, upload queue with per-photo progress polling (1 s), Reintentar, "Revisar" link.
- [ ] **A11 (A)** Armario grid: skeleton, empty, error+retry, review badge, processing placeholder, filters (category, status, needs_review).
- [ ] **A12a (A)** Revisión: cutout + editable chips, low-confidence highlight kept until "Revisión terminada" (UI-REQ-021, UI-SCN-003/003b).
- [ ] **A12b (A)** Detalle: attributes, usage, status change, invalidation (UI-REQ-016).
- [ ] **A13 (A)** Ajustes: weights, no_repeat_days, max_accessories, `INVALID_WEIGHTS` error; keep health line.
- [ ] **A14** Manual end-to-end (UI-SCN-002: 10 photos) + README section (last; small, append-only).
- (after T3 merges) **A15** 08 step 4: ai_attributes + embedding in the worker — separate follow-up.

## Delivery

Forecast: ~3,500–4,500 authored lines (lockfiles and generated `schema.ts` excluded) → over budget. Strategy `ask-on-risk` with cached chain strategy **stacked-to-main**; slices ≈ one task per PR (A1+A2, A3, A4+A5, A6, A7a, A7b+A8, A9, A10, A11, A12a, A12b, A13+A14). RDD on: assess after each work-unit commit.

## Progress

- 2026-09-29: read-only mapping of specs 03/04/07/02 vs code done; worktree + feature doc created.
- A1/A2 implementation (writer): A1 = `shared/imaging.py`, `shared/storage.py`, `api/errors.py` + tests `test_imaging.py`, `test_storage.py`, `test_api_errors.py`. A2 = `api/deps.py` (lazy engine on `app.state`, per-request session), `api/schemas.py`, `api/routers/{garments,jobs}.py`, `api/main.py` wiring (lifespan creates images root; `/images` StaticFiles), `test_api_garments.py`, `app/src/api-client/schema.ts`. Dep added: `python-multipart` (pyproject + uv.lock). Fix outside the task files: `shared/models.py` dropped `from __future__ import annotations` (relationships quoted) because instantiating ORM rows raised a SQLAlchemy mapper error. Defaults applied: Spanish messages for INVALID_IMAGE/IMAGE_TOO_LARGE; alpha flattened on white for the JPEG original.

- 2026-09-29: A1 `01e8f85`, A2 `8a9328d` (+ `python-multipart`, client regenerated). Latent main bug found and fixed first in `8684293`: `shared/models.py` Relationships were unmappable under `from __future__ import annotations` (no ORM row could be created; data model tests only used raw SQL) — regression test added. Each commit passes alone (pytest 164 / 186 / 197). Notes: upload has only the pixel cap (no byte cap); PNG alpha is flattened onto white for the JPEG original.

- A3 implementation (writer): `worker/claim.py` (`claim_next_job`: one `UPDATE job ... WHERE id = (SELECT oldest pending) AND status='pending' RETURNING`, `requeue_stuck_jobs`), `worker/runner.py` (`STEP_ORDER`/`STEP_PROGRESS`, `StepContext{job_id, garment_id, settings, session_factory, data}`, `Step = Callable[[StepContext], None]`, `RetryableStepError`/`PermanentStepError` with Spanish `user_message`, `default_steps(settings)` seam returning deferred no-ops, `run_job`), `worker/main.py::run(stop_event, settings, steps, engine)` wired, tests `tests/unit/test_worker_jobs.py`. Retry budget: one retry per job (`attempts`), unexpected exceptions count as retryable with a generic Spanish message.
- R / A4 / A5 implementation (writer): R = review follow-ups on A1/A2 (`POST /garments` is a plain `def` in the threadpool; 25 MiB `MAX_UPLOAD_BYTES` read in 1 MiB chunks -> 400 `IMAGE_TOO_LARGE`; engine creation behind a lock in `api/deps.py`; `decode_image` maps any decoder/EXIF exception to `InvalidImageError`, bomb branch tested). A4 = `worker/steps/{preprocess,cutout}.py`, `default_steps(settings, remover_factory=None)` (real steps imported lazily; remover built lazily on first job, BiRefNet in production, fake in tests); empty mask -> full image as opaque PNG cutout + `ctx.data["cutout_soft_failure"]`. A5 = `worker/colors.py` (numpy sRGB->CIELAB, CIEDE2000 checked against Sharma 2005 pairs, KMeans k=4 seed 0 n_init 10, 20-name palette, confidence = compactness x separation), `worker/steps/{color,consolidate}.py` (color persists colours/is_neutral/color_confidence; consolidate raises `needs_review` only, threshold from `setting`, default 0.7 if the row is missing). Tests: `test_worker_colors.py`, `test_worker_steps.py` (incl. end-to-end upload -> worker loop -> `GET /jobs`), plus additions to `test_api_garments.py`, `test_imaging.py`, `test_worker_jobs.py`.
- A6 / A7a implementation (writer): A6 = `GET /garments` (filters in SQL; `color`/`season` via SQLite `json_each` EXISTS so `total`/pages stay exact; `status` repeatable, default all; `sort` + `order`, NULL keys last, id tie-break; 422 on bad params) and `GET /garments/{id}` (`GarmentDetail` incl. `outfit_count`, latest `job` summary) in `api/routers/garments.py` + `api/schemas.py`; tests `test_api_garment_reads.py`. A7a = `api/routers/garment_edit.py` (PATCH + `review/complete`), `GarmentPatch` (`extra="forbid"` -> 422 for forbidden fields; `null` only allowed for `brand`/`notes`), `NEUTRAL_NAMES` moved to `shared/colors_palette.py` (+ `is_neutral()`; `worker/colors.py` imports it); tests `test_api_garment_edit.py`. Colours rule: `ai_correction(field="colors")` only when the previous value is non-null and `color_confidence` is null or < 1.0 (user edits pin it to 1.0); always sets `color_confidence=1.0` and recomputes `is_neutral`. Client regenerated.
- F / A7b / A8 implementation (writer): F = orphan release (`worker/main.py::_release_orphan` + `claim.release_orphaned_job`: best-effort, backoff `ORPHAN_RELEASE_BACKOFF_S`, requeues to pending consuming one attempt while `MAX_RETRIES` lasts, else `failed` with a generic Spanish message; `MAX_RETRIES` moved to `worker/claim.py`), poison job (`requeue_stuck_jobs` increments `attempts`, fails a job whose budget is spent, logs both counts), colours marker = absence of an `ai_correction(field="colors")` row (`shared/corrections.py::has_color_correction`, used by `garment_edit` and the worker colour step), upload byte-cap test renamed. A7b = `api/routers/garment_lifecycle.py` (archive, reactivate, retry -> `JobRead`, delete); added error code `GARMENT_PROCESSING` (409, delete while a job is `claimed`/`running`); the colour step skips writing colours/`color_confidence`/`is_neutral` when a colours correction exists. A8 = `api/routers/settings.py` (`GET`/`PATCH /settings`, models inline; weights in [0,1] and sum 1.0+-0.01 else 400 `INVALID_WEIGHTS`; explicit `null` and unknown fields -> 422; missing singleton row is created with defaults). Client regenerated.

## Next step

Review assessment for `origin/main..HEAD`, then A3 (worker runner).
