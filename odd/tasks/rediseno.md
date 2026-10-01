# Rediseño — new visual system from the owner's mockup

Feature branch `feat/rediseno` (worktree `~/pachapp-worktrees/rediseno`), stacked on `feat/ux-probador` `04aaac5`.
Source material (owner, 2026-10-01): `docs/redesign/` — `prompt.md` (rules and phases), `diseño.md` (design
system spec), `maqueta.html` (navigable mockup: visual reference), `tokens.js` (token proposal + `tint()`).
The prompt names them `DISENO.md` / `tokens.ts`; same files.

## Objective

Redesign the app's presentation after the mockup: warm linen surfaces, Fraunces + Manrope, garments as real
cutouts on a tint of their own colour, a floating pill tab bar, one primary action per screen, two columns
from 880 px — on web and on phones.

## Rules (from `docs/redesign/prompt.md`)

1. Presentation only: no changes to data logic, TanStack Query hooks, API client or generated types. Data the
   API does not provide is hidden or prepared behind an optional prop, never invented (list below).
2. Merge `tokens.js` into `src/theme` keeping its structure and names; no second theme; Manrope stays.
3. Base components per `diseño.md` §3, typed, `StyleSheet`; no UI libraries or Tailwind. New deps allowed only:
   `expo-linear-gradient`, `expo-blur`, `react-native-reanimated` (already installed), via `npx expo install`.
4. Garments are the real cutouts (`expo-image`, `contentFit="contain"`) on `tint(dominant colour)`.
5. Web and phone: two columns from 880 px; wardrobe grid columns from `useWindowDimensions`.
6. A11y: `accessibilityRole` + `accessibilityLabel` on icon-only buttons, touch targets >= 44 px, legible contrast.
7. UI copy in Spanish, as in the mockup.
8. Each phase: `tsc`, ESLint, tests pass; tests broken by copy/structure changes are updated without losing
   coverage; compare the web build with the mockup.

## Owner decisions

- 2026-10-01: redesign prioritised over UX Probador (D1/U4/U6 superseded there; U5 and R1 stay there).
- 2026-10-01: run all phases and report at the end (no stop between phases).
- 2026-10-01 (parent defaults, owner did not object): icons from the existing `IconSymbol` (expo-symbols), no
  `@expo/vector-icons` (not in the allowed deps); darker text/border variants where the palette fails AA
  (`ink3` 2.51:1 on bg, accent text 4.37:1, warn on warnSoft 3.52:1, ok on okSoft 4.13:1, `line` borders
  1.22:1) — backgrounds unchanged; radial gradients real on web, linear approximation on native.
- Every UI task loads `frontend-design` + `ux-copy` while building, and `design-critique` +
  `accessibility-review` on screenshots before closing (owner, 2026-10-01).

## Behaviour kept where the mockup conflicts (rule 1 + specs `docs/specs/07-app-ui.md`)

- Armario default filter stays active + laundry; review stays reachable (banner replaces the filter chip).
- Añadir keeps per-photo progress, "Revisar" per photo, and the first-time capture-tips panel (UI-REQ-020)
  restyled as the "Consejo" card; no batch "Añadir N prendas".
- Detalle keeps processing / failed / retry / delete-confirmation states; "Editar" goes to Revisión.
- Tab a11y labels ("Hoy, tab, 1 of 4"...) and the "Abrir ajustes" header button stay (UI-REQ-002/003, tests).

## Mockup data the API does not provide (hide or optional prop)

- Outfit engine (planned, not implemented): look of the day, look name, match %, "why" reasons, "Otra
  sugerencia", "Me lo pongo", "Otras opciones", "Crear outfit con esta prenda".
- History (planned, not implemented): calendar, KPIs + trends, "Sugerir". Derivable now: most used
  (`sort=wear_count`), forgotten (`last_worn_at`).
- Missing: weather, cost per use (no price), text search (no `q`), garment name (composed from
  subcategory/category + colour + material), garment favourites, multi-garment detection / staging, avatar.

## Tasks

- [x] **P1** Theme merge + base components (`src/components/ui/`) + `FloatingTabBar` + tab header; deps
  `expo-linear-gradient`, `expo-blur`. Route: delegated writer (writer trigger: 20+ files).
- [x] **P2** Armario + Detalle. Route: delegated writer.
- [x] **P3** Hoy (presentational components behind optional props; empty state). Route: delegated writer.
- [x] **P4** Añadir (upload zone, steps, tips card, processing on the existing per-photo polling). Route:
  delegated writer.
- [x] **P5** Historial (derivable lists + empty state), then Revisión and Ajustes with the same system.
  Route: delegated writer.
- [ ] **P6** Final visual QA (phone 390x844, desktop 1440x900, every screen vs mockup), critique + a11y,
  fixes; open list of mockup items not shown.

## Checks

TDD: off (no project/session TDD configuration). Runner: app `npm test` (jest). Per phase in `app/`:
`npx prettier --check .`, `npm run lint`, `npm run typecheck`, `npm test`; Playwright screenshots against the
QA stack.

QA stack (throwaway, outside the repo): env `.env.uxqa` (gitignored) -> data `~/pachapp-data-uxqa`, API
`:8096` (`make run ENV_FILE=.env.uxqa`), Expo web `:8095`; 18 garments from
`~/pachapp-data/eval/public-garments` processed by the worker (BiRefNet), attributes set by PATCH (the worker
does not classify yet: A15): 15 active, 2 laundry, 1 archived, 5 needs_review.

## Delivery

Forecast ~4,000-6,000 authored lines -> over budget; `ask-on-risk` with the owner's cached chain strategy
**stacked-to-main**; slices ~ one phase per PR, stacked on `feat/ux-probador`. Native review: assessed per
work-unit commit; consent prompts are batched for the owner at the end (owner asked not to be interrupted).

## Progress

- 2026-10-01: material copied to `docs/redesign/`; mapping (delegated explorer) of mockup, code and API done;
  plan shown to the owner; worktree + QA stack ready.

- 2026-10-01: P1 done (writer): `d6cb70f` tokens merged (aliases re-pointed; AA text variants `ink3Text` #6F665B, `accentText` #A24D2A, `okText`, `infoText`, `warnText` #7F5614, `lineStrong` #8C8377, ratios asserted in `tests/theme.test.ts`; radii sm 12/md 18/lg 28; spacing xl 20/xxl 28/screen 16; max width 1120; TWO_COLUMNS 880; MIN_CARD_WIDTH 190; shadows; `tint()`; Fraunces 400 + italic), `c4ead5f` base components in `src/components/ui/` (+ ToastProvider, `useReducedMotion`), `ab9e2be` FloatingTabBar + AppHeader (expo-blur, expo-linear-gradient installed). prettier/lint/tsc clean, jest 134/134. Notes for P2-P5: redesign 34 dp title is `textStyles.pageTitle` (existing `title` kept); tab scenes get a temporary `sceneStyle.paddingBottom` in `(tabs)/_layout.tsx` -> remove per screen when it moves to `Screen`; `GarmentImage`/`HeroImage` take optional `tintColor`; brass badge now warnSoft + warnText; jest uses the worklets resolver. Parent spot check: tabs-layout test passes; screenshots `pw/redesign/p1-*` match the mockup header and floating bar. Review assess (base `3fa04c3`, committed only): medium, 2,922 lines incl. ux-probador tail + docs, review due -> consent batched for the owner at the end.
- 2026-10-01: P2 done (writer): `bd19c2f` Armario (eyebrow totals, category FilterChips + status Segmented with counters via `useGarments` page_size 1, review Banner replaces the filter chip: 1 pending -> `/review/[id]`, several -> removable "Solo pendientes de revisión" filter; default active+laundry kept with no segment highlighted; 4:5 tinted cards with state pills, composed name `src/lib/garment-name.ts`, wear count, ColorDots; "+ Añadir prenda" tile; "Nada por aquí"), `41d7d90` Detalle (`GarmentHero` radial gradient on web / linear on native, two columns >= 880 with sticky hero on web, StatRow, Atributos card with AddChip, action tiles, toasts; `formatLastWorn`). prettier/lint/tsc clean, jest 163/163 (one unreproduced wardrobe flake on the first run). Hidden for lack of data: search, favourites, "Crear outfit", "Más usadas". Parent check (screenshots `pw/redesign/p2-*` + a11y props): matches the mockup; follow-ups to P3: FilterChip/Segmented minHeight 40 -> 44, status Segmented clipped at 390 px. QA cutouts keep part of the photo background (eval photos + BiRefNet-lite; U5 territory) -> consider cleaner product photos from `clothing-dataset-small` in P6.
- 2026-10-01: P3 done (writer): `79c1842` look components in `src/components/today/` (LookCanvas, LookWhyCard, AltLookCard/AltLooksList, WeatherPill, TipCard; fixtures only in tests), `472d30f` Hoy (real es-ES date, greeting, redesigned empty state keeping the UI-REQ-005 copy, laundry tip from `status=laundry`, usage tip via `wardrobeUsage()` on one `sort=wear_count` page of 200, hidden at 0 %; connection point `const proposal = undefined` in `app/(tabs)/index.tsx`), `e9caf0f` P2 follow-ups (44 px chips/segments, status control fits 360/390 px). prettier/lint/tsc clean, jest 191/191. Parent check: preview with real cutouts (`pw/redesign/p3-preview-*`, throwaway route deleted) matches the mockup composition. Deviations: mockup collage instead of UI-REQ-009 vertical stack; accessories as thumbnails (UI-REQ-010); "Cambiar solo esta pieza" (UI-REQ-011) not built — revisit with the engine. Owner question for the end: with garments but no engine, "Aún no tienes suficientes prendas…" (UI-REQ-005) is misleading.
- 2026-10-01: P4 done (writer): `f629a55` Añadir (truthful subtitle; UploadZone with "Hacer foto"/"Galería"; numbered steps + Consejo card; capture tips first-time expanded card + help button kept (UI-REQ-020); per-photo cards with local preview, state pill, gradient ProgressBar from real job progress (indeterminate only while uploading), ScanLine while analysing (static under reduced motion), done = cutout on tint + composed name + category + ColorDots + category confidence when present + "Revisar"; retry/dismiss and low-res note kept). prettier/lint/tsc clean, jest 197/197. Omitted: drag-and-drop (no upload path), batch "Descartar / Añadir N prendas" (no staging/multi-garment), "N de M listas" (needs data-flow change). Deviation to report to the owner: `useUploadQueue` gained an additive `previewUri` field (4 lines, presentation only). Done cards call `useGarment` once per finished item. QA: 4 temporary garments uploaded and deleted (set back to 18). Parent check: `pw/redesign/p4-*` match the mockup layout. Copy follow-up for P5: step 1 suggests "en percha", but hangers end up in the cutout -> recommend a flat surface.
- 2026-10-01: P5 done (writer): `dc48a4d` Historial (KPIs "% del armario usado" + "Prendas sin estrenar" from `wardrobeUsage()`; "Las que más usas" from the cached 200-page; "Dales otra oportunidad" never-worn first then worn >= 30 days ago; UI-REQ-007 empty copy kept; `MonthCalendar`, `KpiCard.trend`, `RankCard.onSuggest` wait for the history API; tab-bar padding stopgap removed), `970b8d3` Revisión restyle (behaviour unchanged incl. flushers; two columns with sticky hero; shared `StateShell` also used by Detalle), `a6fbb2e` Ajustes restyle (`Screen standalone`), `3d7c2f3` capture copy asks for a flat surface (spec UI-REQ-020 still says "colgada en percha"). prettier/lint/tsc clean, jest 213/213; parent reran the full suite 3x: 213/213 each (writer saw one unidentified flake twice). Parent critique for P6: plural colour agreement in `garmentName` ("Bermudas gris" -> "grises"); Historial shows "0 %" while Hoy hides it -> make consistent; a lone Historial list should take the full width on desktop; Revisión seasons still Chips (SeasonPicker 38 px < 44) and formality as chips.
## Next step

P6 (final visual QA, critique + a11y, fixes, gap list).
