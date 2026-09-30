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
- [ ] **U2 (A+B)** Images: `expo-image` everywhere (card, Detalle, Revisión, upload item) with `contain`,
  caching and a soft placeholder; never render beyond a sensible size (hero image max ~45 % of viewport
  height and ~520 px wide); backend `thumb_px` default 400 -> 640; Añadir warns when a photo's long side is
  < 800 px. Done when: screenshots show sharp, bounded images; backend/app tests pass.
- [ ] **U3 (A)** Revisión simplified: fields needing review expanded and marked; others collapsed to one-line
  summaries that expand on tap; colour palette behind "Cambiar colores"; sticky "Revisión terminada".
  Done when: UI-REQ-021 / UI-SCN-003/003b still hold (tests), and a phone screenshot fits the needed
  edits on the first screen.
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

## Next step

U0 theme foundation (delegated writer).
