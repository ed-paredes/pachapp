# Quick dev flow for web and phone, plus small test debt

## Objective

One command to run the whole stack for testing on the web and on the phone, and close the small open debt
(R1 review follow-ups from `ux-probador`, stale task boxes).

## Problem / why

Testing on the phone needs three terminals, the right `ENV_FILE`, `REACT_NATIVE_PACKAGER_HOSTNAME` and the
Windows portproxy, and nothing tells you when the phone cannot reach the API (after a Windows reboot the
portproxy and the network profile reset). The owner asked (2026-10-12) for a flow to test the app quickly.
`ux-probador.md` still shows R1 open and D1/U4/U5/U6 open although they were superseded or done elsewhere.

## Scope and constraints

- Make targets only call existing commands (`make run`, `run-worker`, `run-ui`); no new services.
- WSL only; never `wsl --shutdown`; Windows admin steps stay manual (documented, not run).
- No change to app behaviour except where R1 asks for it (reduce-motion listener).

## Tasks

- [x] **D1** `make dev` (web) and `make dev-phone` (LAN, `.env.lan`): start API + worker + Expo in one command,
  prefix and colour their logs, stop all three on Ctrl-C; `dev-phone` first runs a preflight that checks the API
  and Metro answer on the LAN IP from `.env.lan` and, when they do not, prints the exact admin PowerShell fix
  (network profile Private, portproxy reset/re-add with the WSL IP, `Restart-Service iphlpsvc`); then prints the
  `exp://<ip>:8081` URL (and a QR if Expo prints one). README section updated.
- [x] **D2** R1 from `ux-probador.md`: unit test for `gridColumns`; extract the hero sizing into a pure helper
  and test its caps; test the low-res note on the failed-upload/retry path; `useImageTransition` listens to
  reduce-motion changes; plus any other R1 item that still applies (check the current code).
- [x] **D3** Task docs: mark `ux-probador.md` D1/U4/U6 as superseded by the redesign and U5 as done in
  `u5-garment-cutout.md` (#46/#47), R1 done after D2.

## Acceptance criteria

- `make dev-phone` with the stack stopped starts everything and prints the Expo Go URL, or a clear fix when the
  phone cannot reach the PC; Ctrl-C leaves no process behind.
- App checks clean: `cd app && npm run format:check && npm run typecheck && npm run lint && npm test`.

## Route and checks

TDD mode: off (no project/session TDD configuration). Runners: `cd app && npm test`; `make` targets checked by
running them. Route: one delegated writer (D1 touches Makefile + script + README, D2 several app files).
Delivery: one PR, a commit per task.

## Progress

- 2026-10-12: owner started testing on the web and the phone with the real data. Before the writer the parent
  backed up the DB (`pachapp.sqlite3.bak-pre-tryon`), ran `make migrate` (`c4e8f21a6d93`), enabled the try-on
  in `.env`/`.env.lan` and started the stack with `ENV_FILE=.env.lan`.
- D1 b8b6517 (+ c86dc82): `scripts/dev.sh` + `make dev`, `make dev-phone`, `make dev-phone-check` (LAN preflight
  on `<ip>:<api port>/health` and Metro `/status`; on failure the admin PowerShell fix with the live WSL IP), an
  optional `EXPO_PORT` on `run-ui`, README "Quick start for testing". `make dev-phone-check
  LAN_ENV_FILE=<main checkout>/.env.lan` against the running stack: "Phone ready … exp://192.168.1.41:8081".
  Start/stop verified with stub servers on spare ports; real SIGINT checked by reading only.
- D2 a723274: `gridColumns` edge tests (the floor is 2, not 1), `heroImageBox` pure helper + 8 tests, low-res
  note test on the retry path, `useImageTransition` follows live reduce-motion changes; optional thumbnail
  backfill dropped (not worth a migration). App checks clean; jest 467.
- D3 b5c2fe5: `ux-probador.md` D1/U4/U6 superseded, U5 done (#46/#47), R1 done.
- Native review (high, granted, 4 lenses): one deterministic CRITICAL finding, `scripts/dev.sh` committed as
  100644 while the Makefile ran it directly (`core.fileMode` is false in this clone) -> correction c86dc82 (run it
  through `bash`, track it as 100755). Targeted validation then failed twice with `invalid_request` (the
  in-process validator cannot inspect the frozen trees): Gentle AI defect, occurrence added to
  Gentleman-Programming/gentle-ai#5334. Owner chose "report and continue"; the captured decline answer was
  refused as `stale_target_identity` (it belongs to the pre-correction candidate), so lineage
  review-846032b6e46a6892 stays open at `targeted_validation_inconclusive_recapture_required` with no receipt.
  Delivery follows ordinary repository policy.

## Next step

PR. The owner keeps testing the try-on, ingestion (A14), AI attributes (T4) and Hoy (E4).
