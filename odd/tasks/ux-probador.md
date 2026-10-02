# UX "Probador" — layout, images, simpler Revisión, visual identity, garment-only cutout

Feature branch `feat/ux-probador` (worktree `~/pachapp-worktrees/ux-probador`), from `main` `b6cfcdb`.

## Objective

Make the app feel finished and quick to use before A15: images that look sharp and sized sensibly, a
Revisión screen that asks only what matters, one coherent visual identity, and cutouts that contain only
the garment.

## Problem (owner's manual test, 2026-09-30, confirmed with Playwright screenshots)

- Web layout: the horizontal filter chip rows stretch to ~260 px tall; the wardrobe grid spans the full
  window (3 columns on desktop), so each card is ~600 px and a small thumbnail is upscaled and blurry.
- Detalle/Revisión show the cutout at full width with no height limit; on desktop the image fills the
  screen and the editor is below the fold.
- Revisión expands every field with every option (7 categories, 20 colours, ...): too much to review.
- The UI is "rústica": default system type, no palette, inconsistent spacing.
- BiRefNet removes the background but keeps the person: neck, arms and trousers under a T-shirt stay in
  the cutout, and they contaminate colour extraction (trousers counted as "negro 27 %").
- The owner's test photo was 417x300 px: low-resolution sources need a warning.

## Scope (owner decisions)

- 2026-09-30: all four areas in this round: layout + images, simplified Revisión, visual style, garment-only
  cutout.
- 2026-09-30: visual direction **"Probador"** (fitting room): stone background, light "plinth" surfaces for
  garments, olive accent, brass details; Fraunces for titles, Manrope for text.
- 2026-09-30: P'achapp is **personal use only**, so non-commercial model licences (SegFormer clothes) are
  acceptable for U5; evaluate SegFormer against `u2net_cloth_seg` on the eval photos and keep the best.

## Design plan (frontend-design skill)

- Subject: a personal wardrobe; audience: the owner, on phone first and desktop web second; primary job:
  see my clothes at a glance and fix the AI's guesses fast.
- Colour tokens: stone `#E9EAE6` (app background), plinth `#FBFBF9` (garment surfaces, cards), olive
  `#4B5B3C` (primary action, selection), brass `#B08D57` (needs-review marks, highlights; used sparingly),
  charcoal `#2B2B2B` (text), plus derived muted text `#6B6E68`, hairline `#D9DAD5`, error `#A3362B`.
- Type: Fraunces (screen titles, garment name) and Manrope (everything else) via `@expo-google-fonts`;
  scale 12 / 14 / 16 / 20 / 28 / 36, sentence case, no all-caps labels.
- Layout: content max width ~1100 on web, centred; grid columns from a minimum card width (~168 dp):
  2 on phones, 4-6 on desktop; garments sit on plinth tiles with generous inner padding and no heavy
  shadows; hierarchy by type and spacing, not by boxes.
- One memorable element: the garment on its plinth (large, calm, well lit); everything else stays quiet.
- Quality floor: responsive to 360 px, visible focus, reduced motion respected, contrast AA.

## Tasks

- [x] **U0 (A)** Theme foundation: `src/theme` tokens (colours, type scale, spacing, radii), load Fraunces +
  Manrope (`@expo-google-fonts/*`, `expo-font`), apply to the stack header and tab bar. Done when: fonts load
  on web and native, typecheck/tests pass, screenshots show the new header/tab bar.
- [x] **U1 (A)** Layout: fix the stretched horizontal chip rows; centred max-width container on web;
  responsive grid columns from a minimum card width; plinth-style `GarmentCard`. Done when: phone and
  desktop screenshots of Armario show compact chips and sensibly sized cards.
- [x] **U2 (A+B)** Images: `expo-image` everywhere (card, Detalle, Revisión, upload item) with `contain`,
  caching and a soft placeholder; never render beyond a sensible size (hero image max ~45 % of viewport
  height and ~520 px wide); backend `thumb_px` default 400 -> 640; Añadir warns when a photo's long side is
  < 800 px. Done when: screenshots show sharp, bounded images; backend/app tests pass.
- [x] **U3 (A)** Revisión simplified: fields needing review expanded and marked; others collapsed to one-line
  summaries that expand on tap; colour palette behind "Cambiar colores"; sticky "Revisión terminada".
  Done when: UI-REQ-021 / UI-SCN-003/003b still hold (tests), and a phone screenshot fits the needed
  edits on the first screen.
- [ ] **R1** Review follow-ups from `review-1692a7017081f0e7` (U0-U2, approved + acknowledged): unit test for `gridColumns` (2 on phone, 4-6 desktop, floor 1); extract hero sizing into a pure helper and test caps (45 % height, 520 dp, never above intrinsic, stale-uri guard); test the low-res note on the failed-upload/retry path; listen to reduce-motion changes in `useImageTransition`; optional thumbnail backfill (regenerate existing 400 px thumbs at 640 px). From `review-ffc90d8b6bf946ae` (U3) — **done** (`413ce76`, `3fa04c3`): an unsaved free-text edit (Subcategoría, Material) is lost when the user taps "Revisión terminada" (now outside the ScrollView, `keyboardShouldPersistTaps="handled"`) or another row header while the field is focused — commit pending text before `finish()` / before collapsing, with a test.
- [ ] **D1 (A)** Revisión design + a11y fixes from the 2026-10-01 `design-critique` / `accessibility-review` pass (screenshots `pw/after/u3-*.png`). Contrast: `muted` #6B6E68 on `stone` is 4.28:1 (< 4.5) for the 12 px "Revisar" marks, hints and row labels -> darken `muted` (or use it only on plinth, 5.0:1); text-input and chip borders (`hairline`) are 1.16-1.36:1 against their background (WCAG 1.4.11 needs 3:1) -> a darker field border; brass review bar 2.56:1 (acceptable only because "Revisar" text also marks it). A11y: hero image has no `accessibilityLabel` (1.1.1); inline save errors are not announced (add `accessibilityLiveRegion="polite"` / `role="alert"`); chip / formality / palette targets are 36 dp and the "Cambiar colores" link 32 dp (raise to 44, or 48 on Android); visible keyboard focus on web unverified (check with Tab). Usability: drop the redundant per-field "Revisar" tag plus the "Pendiente de revisión" pill (the brass bar and "Por revisar" already say it) or replace the pill with a count ("3 por revisar"); add suggestion chips to Subcategoría (from the zero-shot category, like Material's) so fixing it is a tap, not typing; label the formality scale ends on the chips themselves ("1 Informal ... 5 Formal"); in the colour palette list the current colours first and show their order (dominant first); desktop: two columns (image left, sticky; fields right, ~560 px max) instead of 1100 px-wide inputs; header shows the garment (category) instead of only "Revisión"; phone hero could drop to ~30 % of the height so the fields start higher. Load `frontend-design` + `ux-copy` while implementing; re-run critique + a11y on new screenshots before closing.
- [ ] **U4 (A)** Apply the identity to the remaining screens (Añadir, Detalle, Ajustes, Hoy/Historial/
  Favoritos placeholders, empty/loading/error states) and copy pass (sentence case, plain verbs).
- [ ] **U5 (B/ML)** Garment-only cutout: parser mask (candidate SegFormer b3 clothes, fallback rembg
  `u2net_cloth_seg`) intersected with the BiRefNet matte; class set from the zero-shot category (or largest
  clothing region); skip parsing when no person is present; colours from the eroded garment mask; fallback to
  today's matte + `needs_review` when the garment mask is too small. Evaluate on the eval sets (visual pass
  rate, colour proxy, latency, VRAM) before wiring into the worker. Licence decided (personal use).
- [ ] **U6** Visual QA pass: Playwright screenshots (phone 390x844 and desktop 1440x900) of every screen,
  compared with the "before" set; fix what looks off.

## Research notes (U5, 2026-09-30, web research, unbenchmarked)

- `u2net_cloth_seg` (rembg): upper/lower/full classes, MIT weights (levindabhi/cloth-segmentation), cheapest
  to integrate; coarse, no shoes/accessories.
- SegFormer clothes (mattmdjaga b2, sayeed99 b3): 18 ATR classes incl. upper-clothes, pants, skirt, dress,
  shoes, bag, scarf, belt, hat, arms/legs/face; mIoU ~0.69; licence ambiguous (NVIDIA SegFormer code is
  non-commercial).
- FASHN parser (SegFormer-B4) and Sapiens: better fashion classes but non-commercial licences; Sapiens is
  heavy.
- Prompted GroundingDINO/Florence-2 + SAM2: flexible but 2-3 models, over latency/VRAM budget.
- Evidence gaps: no latency/VRAM measured on this GPU, ONNX export under ORT 1.30/CUDA 13 unchecked, no
  quality comparison on our eval photos.

## Constraints

- Keep existing requirement coverage (UI-REQ-*, UI-SCN-*); tests change with behaviour, never deleted to pass.
- UI copy Spanish; code, comments, tests and docs English.
- ~400 authored lines per task is a planning heuristic only.

## TDD

Mode: off (no project/session TDD configuration). Runner: backend `uv run pytest`; app `npm test` (jest).
Ordinary checks per task: ruff, ruff format, `ty check src`, pytest; prettier, eslint, tsc, jest; plus
Playwright screenshots for UI tasks.

## Delivery

Forecast ~2,500-3,500 authored lines -> over budget. Strategy `ask-on-risk` with the owner's cached chain
strategy **stacked-to-main** (used for Hito A and T3). Slices ~ one task per PR.

## Routes

- U0-U4: delegated writer (2+ non-trivial files each), one writer at a time in this worktree.
- U5: research done by a delegated read-only worker; evaluation + implementation delegated after the
  licence decision.

## Progress

- 2026-09-30: before-screenshots taken with Playwright against the owner's running stack (phone + desktop,
  all screens); plugins installed at the owner's request: playwright, frontend-design, context7 (user scope);
  Chromium headless shell downloaded (no missing system libs).
- 2026-09-30: U0/U1 implementation (writer, unverified by parent): `src/theme` tokens + Fraunces/Manrope via `useFonts` in the root layout, themed stack header and tab bar, `ContentContainer` (max 1100), wardrobe grid columns from min card width 168, compact non-growing chip rows, plinth `GarmentCard`, olive `Chip`; screenshots in scratchpad `pw/after/u0u1-*.png`.
- 2026-09-30: parent verified U0 `5bb730b` and U1 `d9fdf8a` alone (prettier, eslint, tsc, jest 74/74) and looked at the writer's screenshots (compact chips; 6 columns desktop, 2 phone; plinth tiles; Fraunces header). Review of b6cfcdb..d9fdf8a granted by the owner but START refused (`invalid_request`: untracked files appeared from the in-flight U2 writer); no review record created; will review U0-U2 together after U2 is committed.
- 2026-10-01: U2 implementation (writer, unverified by parent): backend `thumb_px` 400 -> 640 (settings, .env.example, spec 01, test); app `GarmentImage`/`HeroImage` on expo-image (`contain`, memory-disk cache, reduced-motion-aware cross-fade, plinth placeholder) in card, Detalle and Revisión; hero capped at 45 % window height and 520 dp via pure `fitWithin` (no upscaling past intrinsic size, unit-tested); low-resolution (< 800 px long side) note on the Añadir upload item with jest test; visual QA on throwaway stack with u2netp cutouts (BiRefNet on CPU was OOM-killed, GPU left to the owner's worker); screenshots in scratchpad `pw/after/u2-*.png`.
- 2026-10-01: U2 committed as `19f564c` (backend thumb_px 640; pytest 456) and `35ed871` (app images; jest 79/79), each verified alone by the parent; writer screenshots in scratchpad pw/after/u2-*.png (cutouts there came from u2netp on CPU because the owner's worker held the GPU). Review `review-1692a7017081f0e7` over b6cfcdb..35ed871 granted, approved and acknowledged; advisories recorded as R1. Checkpoint requested by the owner: U3 writer (simplified Revisión, uncommitted in this worktree) and the U5 segmentation evaluation spike (outside the repo, scratchpad/seg-eval) were still running.
- 2026-10-01 (checkpoint, agents stopped at the owner's request):
  - U3 writer stopped mid-task. Its uncommitted work stays in this worktree (`app/app/review/[id].tsx`, `app/src/components/GarmentImage.tsx`, `app/tests/review.test.tsx`; +624/-277) and is backed up as `~/pachapp-worktrees/_wip/u3-review-wip.patch`. State when stopped: `tsc` clean and `tests/review.test.tsx` 20/20 pass; full jest, lint, prettier and the Playwright screenshots were NOT done. Its throwaway API/Expo (:8096/:8095) were killed and `~/pachapp-data-uxqa` deleted.
  - U5 evaluation spike stopped in stage 1 (BiRefNet alphas computed for 62 of 66 eval photos, saved as `.npy` in `scratchpad/seg-eval/out`; scripts `run.py`, `stage1.py`, `sheets.py` there). No contact sheets or u2net_cloth_seg/SegFormer results yet. The run kept getting OOM-killed (exit 137): WSL has ~8 GB RAM and the owner's API/worker/Expo were running. Re-run with the owner's stack stopped (GPU and RAM free). The scratchpad may not survive a reboot; if it is gone, relaunch the spike from scratch.
- 2026-10-01 (resume): U3 writer relaunched from the partial state in this worktree (route: delegated direct, writer trigger). The U5 scratchpad (`seg-eval`) did not survive the reboot: the spike must be relaunched from scratch once U3 is done (RAM/GPU free; owner stack not running at resume).
- 2026-10-01: U3 committed as `1148206` (writer: partial work already matched the task, no code changes; prettier/eslint/tsc clean, jest 84/84; parent spot check: review.test 20/20 and phone screenshot `pw/after/u3-phone.png` shows the four needed fields expanded with brass marks, palette behind "Cambiar colores", sticky "Revisión terminada" on the first screen). QA garment seeded in SQLite on a throwaway stack. Review assess (base `35ed871`, committed only): medium, 897 lines, `slice_budget_reached` -> review due; consent asked.
- 2026-10-01: review `review-ffc90d8b6bf946ae` over 35ed871..1148206 (U3, medium, 1 lens: reliability) granted by the owner, approved and acknowledged (authority burned; reviewed boundary now `1148206`). One advisory WARNING (unsaved free-text lost on done/row switch) added to R1.
- 2026-10-01: R1 U3 item fixed. Writer (delegated) committed `413ce76` (flush pending text before `finish()` and on row switch; 4 tests). Parent found a gap: a single flush ref kept only the last-rendered field, so with Subcategoría and Material both open a chip save could drop the other field's text; fixed inline in `3fa04c3` (set of flushers + test). Checks: prettier/eslint/tsc clean, jest 89/89. One run of "shows loading, then an error with retry, and a 404 state" failed once and passed in 3 reruns (flaky, unrelated). Assess base `1148206`: medium, 115 lines, `under_budget` -> pending in slice (no review yet; boundary stays `1148206`).

- 2026-10-01: owner asked that every frontend task loads the design skills (frontend-design, ux-copy, design-critique, accessibility-review; superdesign only with confirmation). Ran `design-critique` + `accessibility-review` on the U3 Revisión screenshots; findings recorded as D1. Contrast computed from `src/theme/colors.ts`.
- 2026-10-01: dev speed (owner request). Measured first web load (dev server, cold cache): /mnt/d static ~204 s, ext4 static ~25 s, ext4 single ~9 s. Committed `8b2f11e` (`web.output` "single"; jest 89/89; headless render of `/` and deep link `/settings` OK, no page errors) and `f6589da` (README: keep the repo on ext4). Main checkout copied to `~/code/pachapp` (rsync without node_modules/.venv; `.git` with gentle-ai state kept), `uv sync` + `npm ci`, worktree repaired to the new repo; checks there: backend pytest 456/456, app jest 74/74 (first cold-cache run had 5 timeout failures right after pytest, rerun clean). `/mnt/d` checkout kept as backup until the owner confirms.
- 2026-10-01: owner prioritised the new redesign (`docs/redesign/`, feature `odd/tasks/rediseno.md`, branch `feat/rediseno` stacked on this branch). The redesign replaces the "Probador" palette and supersedes D1, U4 and U6; U5 (garment-only cutout) and the remaining R1 tests stay open here.
## Next step

Parked while the redesign runs. Open here: R1 (remaining tests), U5 (segmentation eval with the owner's stack stopped, then integration). D1/U4/U6 superseded by the redesign. Then stacked PRs (stacked-to-main).
