# Virtual try-on ("Verlo puesto") with CatVTON

## Objective

Show an outfit worn on a neutral model, generated locally with CatVTON on the worker GPU, as an on-demand,
asynchronous extra view next to the collage on Hoy (`docs/specs/09-virtual-tryon.md`).

## Status

Spec stored in the repo with integration notes (§12) on 2026-10-04. Owner decision 2026-10-04: do U5
(`odd/tasks/u5-garment-cutout.md`) first so the try-on gets clean garment images. 2026-10-05: owner started
V0 assuming U5 done (U5a in review); V0a tooling done, V0b (real run) pending.

## Key constraints (from §12)

- RTX 2060 6 GB (fp16); the worker already holds BiRefNet + SigLIP (5.7 of 6 GB measured) -> unload before
  CatVTON, reload after.
- WSL RAM ~7 GB: the spike runs with API, worker and Expo stopped and measures peak RAM and VRAM.
- Own `tryon_renders` table and states; uploads keep priority in the worker.
- Licence CC BY-NC-SA 4.0: personal use only; CatVTON code as an external pinned dependency.

## Tasks (spec §10)

- [ ] **V0** Spike + report (§4, plus peak RAM, current vs clean cutouts) -> stop for the owner's validation.
  - [x] **V0a** Tooling: `ml/tryon_spike.py` + `make tryon-setup|tryon-masks|tryon-spike`,
    `backend/scripts/tryon_build_masks.py`; unit tests with a fake dresser.
  - [ ] **V0b** Run on the RTX 2060 with the stack stopped -> report -> owner validates (§4 criterion).
- [ ] **V1** Mannequin + precomputed masks + `CatVTONEngine` + GPU memory management.
- [ ] **V2** Service, cache, `tryon_renders` + migration, worker integration, endpoints, backend tests,
  `make gen-client`.
- [ ] **V3** App: "Verlo puesto", polling, Collage | Puesto, states, offline storage of renders, tests.
- [ ] **V4** Polish: copy, cache cleanup, docs (licence note in the backend README).

## Research notes (2026-10-05, reading CatVTON at `7818397f`)

- `CatVTONPipeline` (`model/pipeline.py`) is not a diffusers `DiffusionPipeline`: no
  `enable_model_cpu_offload`, no step callback. Per-step progress works by wrapping
  `noise_scheduler.step` (keeping its signature: the pipeline inspects it for `eta`/`generator`).
- Models: base `booksforcharlie/stable-diffusion-inpainting` (runwayml's repo was deleted), attention
  weights `zhengchong/CatVTON` `mix-48k-1024` (trained at 768x1024), VAE `stabilityai/sd-vae-ft-mse`
  hard-coded and unpinnable without patching. Upstream defaults: 50 steps, guidance 2.5, bf16 (we use fp16).
- Weights are small in fp16 (SD 1.5 inpainting UNet ~1.7 GB + VAE ~0.2 GB): CPU offload would save little;
  the spike measures without it and §5.5's `TRYON_CPU_OFFLOAD=true` default waits for V0b numbers.
- The SD safety checker is skipped (VRAM, and it can swap a mannequin for NSFW.jpg).
- Masks: app.py blurs the AutoMasker mask (`blur_factor=9`) and the pipeline binarises it at 0.5. The
  AutoMasker also offers `inner`/`outer` (layering, §5.3); `tryon-masks` saves all five types.
- Install: the README's Python 3.9 + `requirements.txt` no longer resolves (diffusers from git main needs
  Python >= 3.10 and is too new for its torch 2.4; `peft>=0.17` needs a newer accelerate). `tryon-setup`
  uses Python 3.10 with diffusers 0.30.3 + accelerate 1.2.1 overrides (AutoMasker imports checked).
- The pipeline also imports and runs in the backend venv (torch 2.14, transformers 5, diffusers 0.40,
  accelerate 1.15): checked with tiny random UNet/VAE on CPU through `CatVTONDresser` + `run_spike`
  (3 cases, chained outfit pass). No real weights or GPU were available in that session (Hugging Face
  and the PyTorch index blocked), so V0b is the first real run.

## Progress

- 2026-10-05: V0a (cloud session): spike tooling. Configs A 576x768/30, B 384x512/30, C 576x768/20;
  cases upper, lower, outfit (lower then upper, chained); several `--mannequin` and `--garments` folders
  (e.g. current cutouts vs U5 clean cutouts vs original photos). Records per pass time, torch peak, median
  ms/step, OOM (recorded, run continues), blank output (fp16 NaN guard); per run model load time,
  nvidia-smi peak, peak RSS; writes images, contact sheets and `tryon_spike_report.md` with the §4
  criterion. Weights go to `PACHAPP_ML_CACHE_DIR` (HF_HOME) instead of §5.5's `TRYON_WEIGHTS_DIR`.
  diffusers/accelerate come in with `uv run --with` (uv.lock untouched; V1 adds them for real). Checks:
  ruff, format, ty clean; pytest 644 (17 new).

- 2026-10-06: V0b first real run (parent, owner away; stack stopped). Branch rebased on main after U5
  (#46/#47, Makefile conflicts resolved, pytest 724). `make tryon-setup` OK (pinned CatVTON, py3.10 venv);
  `make tryon-masks` OK on a **provisional** mannequin built from an owner screenshot (cropped at the thighs,
  personal use, only to measure; not a V1 mannequin, §5.1 choice still open); garments = two U5 cutouts
  (brown tee, beige trousers). `make tryon-spike` without code changes: model load 273 s (first download
  included), peak RSS 4995 MiB, nvidia-smi peak 4907 MiB, torch peak 2859 MiB (A/C) / 2457 MiB (B); no OOM, no
  blank output. Outfit (2 chained passes): A 576x768/30 = 35.8 s (~570 ms/step), B 384x512/30 = 15.2 s,
  C 576x768/20 = 24.6 s; all meet the §4 criterion (<= 90 s). Quality by eye: A and C dress both garments
  convincingly (C close to A); B loses the colour (tee turns white) and garbles the trousers. Results in
  `~/pachapp-data/eval-results/tryon-v0b-2026-10-06/`. VAE `sd-vae-ft-mse` still unpinned (upstream
  hard-codes it). Pending owner: validate quality, choose the mannequin (§5.1), choose A vs C.

## Next step

Owner decisions to close V0 (setup, masks and the measuring run already work; see the 2026-10-06 entry):

1. Look at `~/pachapp-data/eval-results/tryon-v0b-2026-10-06/contact_provisional-m1_u5-cutouts.jpg` and decide
   whether the quality is good enough (A or C; B is not).
2. Choose the mannequin (§5.1: neutral human model vs mannequin): a folder with `person.png` (front, full body,
   3:4, licence-compatible) and `meta.json`; then `make tryon-masks MANNEQUIN=<dir>` and re-run
   `make tryon-spike TRYON_SPIKE_ARGS="--mannequin <dir> --garments ~/pachapp-data/tryon/garments/u5-cutouts
   --out ..."` with the stack stopped.
3. With V0 validated: V1 (`CatVTONEngine`, GPU memory management next to BiRefNet + FASHN + SigLIP).
