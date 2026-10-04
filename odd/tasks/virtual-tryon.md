# Virtual try-on ("Verlo puesto") with CatVTON

## Objective

Show an outfit worn on a neutral model, generated locally with CatVTON on the worker GPU, as an on-demand,
asynchronous extra view next to the collage on Hoy (`docs/specs/09-virtual-tryon.md`).

## Status

Spec stored in the repo with integration notes (§12) on 2026-10-04. Not started. Owner decision 2026-10-04:
prepare the repo and do U5 (`odd/tasks/u5-garment-cutout.md`) first so the try-on gets clean garment images.

## Key constraints (from §12)

- RTX 2060 6 GB (fp16); the worker already holds BiRefNet + SigLIP (5.7 of 6 GB measured) -> unload before
  CatVTON, reload after.
- WSL RAM ~7 GB: the spike runs with API, worker and Expo stopped and measures peak RAM and VRAM.
- Own `tryon_renders` table and states; uploads keep priority in the worker.
- Licence CC BY-NC-SA 4.0: personal use only; CatVTON code as an external pinned dependency.

## Tasks (spec §10)

- [ ] **V0** Spike + report (§4, plus peak RAM, current vs clean cutouts) -> stop for the owner's validation.
- [ ] **V1** Mannequin + precomputed masks + `CatVTONEngine` + GPU memory management.
- [ ] **V2** Service, cache, `tryon_renders` + migration, worker integration, endpoints, backend tests,
  `make gen-client`.
- [ ] **V3** App: "Verlo puesto", polling, Collage | Puesto, states, offline storage of renders, tests.
- [ ] **V4** Polish: copy, cache cleanup, docs (licence note in the backend README).

## Next step

After U5: V0 spike with the stack stopped.
