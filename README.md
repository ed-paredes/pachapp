# P'achapp

## Layout

| Path       | What                                                                                                                                   |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `backend/` | `uv` project, Python 3.12. Packages: `api` (FastAPI), `worker` (polling loop), `engine` (pure functions, no I/O), `shared` (settings). |
| `app/`     | Expo + TypeScript client (Expo Router), targeting iOS/Android (Expo Go) and web.                                                       |
| `docs/`    | Specs (`docs/specs/`) and C4 architecture (`docs/architecture/c4.md`).                                                                 |

Full toolchain spec: `docs/specs/01-dev-tooling.md`.

## Prerequisites

- WSL2 (Ubuntu), with `uv` and Node 22 installed **inside WSL** via `nvm`.
  - `make` refuses to run app/UI targets against the Windows Node/npm under
    `/mnt/c` (`check-node`) — always run `make` from a WSL shell with `nvm`'s
    Node on `PATH`.
- Keep the repo on the WSL2 ext4 filesystem too (e.g. `~/code/pachapp`; Windows
  sees it under `\\wsl$\`). It works under `/mnt/d`, but every file read
  crosses the WSL/Windows boundary: the first web load of `make run-ui` took
  ~200 s there against ~9 s on ext4, and the worker and tests slow down the
  same way.
- `PACHAPP_DATA_DIR` (the SQLite DB + images) must resolve to a path on the
  WSL2 ext4 filesystem, e.g. `~/pachapp-data` — never under `/mnt/*`. Settings
  fail fast with an explicit error if it doesn't (D14).

## Setup

```bash
cp .env.example .env
# then fill PACHAPP_LLM_PROVIDER / PACHAPP_LLM_MODEL_ID / PACHAPP_LLM_API_KEY
make install
make migrate
```

## Run

```bash
make run        # API: http://localhost:8000/health, http://localhost:8000/docs
make run-worker # processing worker
make run-ui     # Expo dev server, web on :8081
```

### Hosting the web build

The web build is a single-page app (`web.output: "single"` in `app/app.json`):
`npx expo export --platform web` emits one `index.html` and Expo Router resolves
routes on the client. A static host must therefore rewrite unknown paths to
`/index.html` (an SPA fallback); otherwise a deep link such as `/review/<id>`
returns 404 on reload or when opened directly.

## `ENV_FILE`

Every target reads a dotenv file at the repo root, named by `ENV_FILE`
(default `.env`):

```bash
make run ENV_FILE=.env.test
```

`.env.test` is a local, gitignored file (`.env.*` in `.gitignore`) with dummy
values and a data dir like `~/pachapp-data-test`, useful for trying things out
without touching real secrets or real data.

The backend reads the dotenv path via `PACHAPP_ENV_FILE`, which the Makefile
exports (set to `$(ENV_FILE)`'s absolute path); `get_settings()` fails if that
file doesn't exist.

Precedence: command line > shell environment > `ENV_FILE` > Makefile
defaults (matches pydantic-settings: process env beats its dotenv).

## Targets

Generated from the Makefile's `## ` help comments; run `make help` for the
live list.

| Target        | Description                                               |
| ------------- | --------------------------------------------------------- |
| `install`     | Install backend and app dependencies                      |
| `run`         | Start the API (uvicorn, auto-reload)                      |
| `run-worker`  | Start the processing worker                               |
| `run-ui`      | Start the Expo dev server (web on :8081)                  |
| `test`        | Run backend and app tests                                 |
| `lint`        | Lint backend and app                                      |
| `fmt`         | Format backend and app in place                           |
| `fmt-check`   | Check formatting without writing                          |
| `typecheck`   | Type-check backend (ty) and app (tsc)                     |
| `migrate`     | Apply database migrations                                 |
| `migrate-new` | Create a migration: `make migrate-new name="add garment"` |
| `gen-client`  | Regenerate `app/src/api-client/schema.ts` from OpenAPI    |
| `ml-preload`  | Download and validate the vision models                   |

## `make gen-client`

Exports the OpenAPI schema in-process (no running API needed) and runs
`openapi-typescript` against it, writing `app/src/api-client/schema.ts`. That
file is committed (DEV-REQ-010) and excluded from Prettier.

## Vision models

`make ml-preload` downloads BiRefNet (background removal, via `rembg`) and
the pinned SigLIP embedding model (via `open_clip`) into
`PACHAPP_ML_CACHE_DIR` (default `~/pachapp-data/models`). The first run
downloads roughly 5 GB; later runs just validate the existing cache. The
default background model is `birefnet-general-lite`; on `cuda` it is converted
once to an fp16 copy (`*.fp16.onnx`, next to the fp32 file; about 40 s) so it
fits a 6 GB GPU -- disable with `PACHAPP_ML_BG_FP16=false`. Preload prints the
BG file, its precision and the warm per-image time. `torch`
is installed from the PyTorch CUDA 13.0 wheel index (`backend/pyproject.toml`),
so it needs an NVIDIA GPU and a CUDA 13 driver to actually run on `cuda` -- see
`docs/specs/08-local-vision.md` for the full settings table and fallback to
`cpu`/`mps`.

`make ml-cutouts` is the step-2 gate aid: it runs the background remover over
the photos in `PACHAPP_ML_EVAL_DIR` and writes `<name>.png` cutouts to
`~/pachapp-data/eval/cutouts`, printing per-image coverage and timing. Inspect
about 20 eval photos; at least 18 cutouts should be clean. Pass another folder
with `make ml-cutouts` after editing the target, or run
`cd backend && uv run python -m ml.cutout_preview INPUT_DIR --out OUTPUT_DIR`.

`make ml-eval` is the step-3 gate: it runs cutout -> embed -> zero-shot over the
photos in `PACHAPP_ML_EVAL_DIR` (or `make ml-eval EVAL_DIR=/path`) and prints
per-attribute accuracy, the category confusion matrix, the `needs_review`
percentage and timings. The folder holds `*.jpg/*.jpeg/*.png` plus a
`labels.json` such as
`{"a.jpg": {"category": "top", "subcategory": "t-shirt", "pattern": "solid", "formality": 2}}`
(`null` = unlabeled). The gate is at least 85 % `category` accuracy without kNN.
Direct use: `cd backend && uv run python -m ml.eval [DIR] [--no-cutout] [--limit N]`.
Add `--min-category-accuracy 0.85` to exit with code 2 (after the report) when category accuracy is below the gate.

## Phone / LAN access (manual)

To open the app on a phone via Expo Go, the phone needs to reach the API
running in WSL (D13). This typically means:

- Windows `.wslconfig` set to `networkingMode=mirrored`, with a firewall rule
  allowing inbound `8000`/`8081`.
- `EXPO_PUBLIC_API_BASE_URL` set to the PC's LAN IP (e.g.
  `http://192.168.1.10:8000`), and that LAN origin added to
  `PACHAPP_CORS_ORIGINS`.

See `docs/specs/01-dev-tooling.md` for the full checklist and fallbacks.

## App design

The app's look follows the redesign in [`docs/redesign/`](docs/redesign/) (design system spec, navigable mockup and token proposal). Theme tokens (colours, type, radii, spacing, `tint()`) live in `app/src/theme`; the base components built on them (buttons, chips, cards, floating tab bar, ...) live in `app/src/components/ui`. Screens only compose these, so a visual change starts in one of those two places.

## Manual testing

A step-by-step manual testing guide for Hito A (upload a photo, see the garment in the wardrobe), in Spanish, lives in [`docs/manual-testing/hito-a.md`](docs/manual-testing/hito-a.md). It covers setup, the three processes, curl smoke tests, every app screen and the failure cases.
