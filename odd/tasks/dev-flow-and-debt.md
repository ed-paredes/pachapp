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

- [ ] **D1** `make dev` (web) and `make dev-phone` (LAN, `.env.lan`): start API + worker + Expo in one command,
  prefix and colour their logs, stop all three on Ctrl-C; `dev-phone` first runs a preflight that checks the API
  and Metro answer on the LAN IP from `.env.lan` and, when they do not, prints the exact admin PowerShell fix
  (network profile Private, portproxy reset/re-add with the WSL IP, `Restart-Service iphlpsvc`); then prints the
  `exp://<ip>:8081` URL (and a QR if Expo prints one). README section updated.
- [ ] **D2** R1 from `ux-probador.md`: unit test for `gridColumns`; extract the hero sizing into a pure helper
  and test its caps; test the low-res note on the failed-upload/retry path; `useImageTransition` listens to
  reduce-motion changes; plus any other R1 item that still applies (check the current code).
- [ ] **D3** Task docs: mark `ux-probador.md` D1/U4/U6 as superseded by the redesign and U5 as done in
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

## Next step

D1, D2, D3 with one writer.
