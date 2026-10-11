# Pachapp backend

`uv` project (Python 3.12): `api` (FastAPI), `worker` (polling loop), `engine`, `shared`,
`ml` (local vision) and `tryon` (virtual try-on). Setup, `make` targets and the settings
table are in the [repository README](../README.md) and `.env.example`.

## Virtual try-on

Dresses a mannequin with an outfit's garment cutouts using
[CatVTON](https://github.com/Zheng-Chong/CatVTON). Design: `docs/specs/09-virtual-tryon.md`.
It is **off by default**: nothing is downloaded or loaded until you enable it.

### Enable it

1. `make tryon-setup` clones CatVTON at the pinned commit into
   `<data dir>/vendor/CatVTON` (override with `PACHAPP_TRYON_CATVTON_DIR`) and creates the
   venv used by `make tryon-masks`. CatVTON is not a pip package and is never copied into
   this repository.
2. Set `PACHAPP_TRYON_ENABLED=true` in `.env` and restart the API and the worker. The app
   reads `GET /tryon/capabilities` to show or hide the feature.
3. The model weights download from the Hugging Face Hub on the first render into
   `PACHAPP_ML_CACHE_DIR` (default `<data dir>/models`), then load from there without
   contacting the Hub. The first load also builds a one-time fp16 copy of the base UNet
   (about 1.7 GB) under `<cache dir>/tryon/`. Budget roughly 10 GB of disk for the whole cache (8.4 GB measured before the fp16 copy).
   A partly downloaded cache is completed from the Hub instead of being trusted.

### Resources

- **GPU:** built for a 6 GB card (RTX 2060, fp16, 576x768). A render peaks around 5 GB of
  VRAM, so the worker releases the upload pipeline's models before CatVTON loads and unloads
  CatVTON before an upload job runs (uploads always go first). Turing GPUs have no usable
  bf16, so only `fp16` and `fp32` are offered.
- **RAM:** the load peaks at about 5.8 GB RSS in a ~8 GB WSL. Stop Expo and other heavy
  processes while a render runs if memory is tight.
- **Out of memory:** a CUDA OOM is retried once at `PACHAPP_TRYON_OOM_RETRY_WIDTH` x
  `PACHAPP_TRYON_OOM_RETRY_HEIGHT`.

### Housekeeping

The worker deletes renders (rows and WebP files) that nobody has opened for
`PACHAPP_TRYON_CACHE_MAX_AGE_DAYS` days (default 30, `0` keeps them forever). Resubmitting a
look and reading a finished render both count as an access. It checks hourly while idle, and
only with the try-on enabled; queued and running renders are never removed.

A failed render is retried on resubmit unless the error is permanent (`invalid_garment`,
`invalid_params`, `garment_missing`, `garment_changed`, `mannequin_unavailable`,
`blank_output`). After `MAX_RENDER_ATTEMPTS` tries a new round starts only five minutes after
the last failure.

### Licence

CatVTON and its weights are released under **CC BY-NC-SA 4.0**: personal, non-commercial use
only, with share-alike. Pachapp uses it as an external, pinned dependency and does not
redistribute it. **Do not ship the try-on in a commercial product** without switching to a
model or provider with a licence that allows it. Mannequin images under `assets/tryon/`
carry their own licence in each `meta.json`.
