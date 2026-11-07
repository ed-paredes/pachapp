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

Or all three at once: see [Quick start for testing](#quick-start-for-testing).

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
| `dev`         | Run API + worker + Expo together with prefixed logs       |
| `dev-phone`   | `dev` with `.env.lan` and a phone reachability check      |
| `dev-phone-check` | Only the phone reachability check                     |
| `test`        | Run backend and app tests                                 |
| `lint`        | Lint backend and app                                      |
| `fmt`         | Format backend and app in place                           |
| `fmt-check`   | Check formatting without writing                          |
| `typecheck`   | Type-check backend (ty) and app (tsc)                     |
| `migrate`     | Apply database migrations                                 |
| `migrate-new` | Create a migration: `make migrate-new name="add garment"` |
| `gen-client`  | Regenerate `app/src/api-client/schema.ts` from OpenAPI    |
| `ml-preload`  | Download and validate the vision models                   |
| `recut-garments` | Re-cut existing garments with the garment-only cutout  |
| `android-apk` | Build the Android release APK on Windows                  |

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
`cpu`/`mps`. Preload also fetches the FASHN garment parser at the revision pinned in
`PACHAPP_ML_PARSE_FASHN_REVISION`.

### Re-cutting existing garments

Garments uploaded before the garment-only cutout (U5) keep their old BiRefNet cutout until you
re-cut them. With the API, worker and Expo **stopped** (the GPU is shared):

```bash
make recut-garments RECUT_ARGS="--dry-run"                 # count only; loads no model
make recut-garments RECUT_ARGS="--out ~/pachapp-data/eval-results/recut"   # real run + contact sheets
```

Other flags: `--limit N`, `--ids ID...`. It re-cuts the cutout and thumbnail (atomically, the
old file stays until the new one is complete), the colours, the embedding and any still-empty
AI attribute; it never overwrites user-corrected colours or user-owned attributes, keeps the
old cutout when there is no person or the garment mask is too small (the latter raises
`needs_review`), and marks each garment (`garment.cutout_method`) so a second run does nothing.
Run `make migrate` first. It refuses to run with `PACHAPP_ML_GARMENT_PARSE=false`.

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

## Quick start for testing

One terminal runs the API, the worker and Expo, with their logs prefixed
`[api]`, `[worker]` and `[ui]`. Ctrl-C stops all three; if one of them exits,
the others are stopped too.

```bash
make dev              # web: http://localhost:8081 (settings from .env, or ENV_FILE=...)
make dev-phone        # same, on the LAN with .env.lan, plus a phone reachability check
make dev-phone-check  # only the check, against a stack that is already running
```

`make dev-phone` needs a gitignored `.env.lan` at the repo root with the PC's
LAN IP, for example:

```bash
PACHAPP_API_HOST=0.0.0.0
EXPO_PUBLIC_API_BASE_URL=http://192.168.1.41:8000
PACHAPP_CORS_ORIGINS=["http://localhost:8081","http://192.168.1.41:8081"]
```

It starts Expo with `REACT_NATIVE_PACKAGER_HOSTNAME` set to that IP. Once the
API and Metro answer on localhost, it requests `http://<ip>:8000/health` and
`http://<ip>:8081`. When both answer it prints `exp://<ip>:8081`: in Expo Go
choose "Enter URL manually" and type it (or scan the QR Expo prints). The
phone and the PC must be on the same Wi-Fi.

**When the check fails**, the stack keeps running (the web still works) and the
script prints the fix with the current WSL IP filled in. It is the usual
state after a Windows reboot (WSL runs in NAT mode; Windows forwards 8000 and
8081 to WSL with `netsh interface portproxy`, and the network profile goes
back to Public). In an administrator PowerShell:

```powershell
Set-NetConnectionProfile -InterfaceAlias "Ethernet 3" -NetworkCategory Private
netsh interface portproxy reset
netsh interface portproxy add v4tov4 listenaddress=<LAN IP> listenport=8000 connectaddress=<WSL IP> connectport=8000
netsh interface portproxy add v4tov4 listenaddress=<LAN IP> listenport=8081 connectaddress=<WSL IP> connectport=8081
Restart-Service iphlpsvc
netstat -ano | Select-String "<LAN IP>:80"
```

(`<WSL IP>` is `hostname -I | awk '{print $1}'` in WSL.) Then run
`make dev-phone-check`. Also needed once: an inbound firewall rule for 8000 and
8081 on the Private profile. Do not use `wsl --shutdown`.

`make run-ui` takes an optional `EXPO_PORT` (default: Expo's 8081).

### Alternative: mirrored networking

Instead of the portproxy, Windows `.wslconfig` can set
`networkingMode=mirrored`, with a firewall rule allowing inbound `8000`/`8081`.
Either way `EXPO_PUBLIC_API_BASE_URL` must be the PC's LAN IP and that origin
must be in `PACHAPP_CORS_ORIGINS`. See `docs/specs/01-dev-tooling.md` for the
full checklist and fallbacks.

## Android app (offline viewing)

A standalone release APK lets you browse the wardrobe from the phone without
the stack running: the app is read-only offline and shows the data (and images)
from its last sync. Mutations need the API.

Prerequisites (Windows side, not WSL): Android Studio (provides the JDK and the
SDK) and Node.js. Plug the phone in over USB with USB debugging enabled to
install.

```bash
make android-apk                          # build only
make android-apk ANDROID_ARGS="-Install"  # build and `adb install -r` on the phone
make android-apk ANDROID_ARGS="-ApiUrl http://192.168.1.50:8000"
make android-apk ANDROID_ARGS="-Clean"    # wipe the work dir, prebuild from scratch
```

The target calls `scripts/build-android.ps1` through `powershell.exe`; run that
script directly from PowerShell with the same flags if you prefer. It mirrors
`app/` into `%LOCALAPPDATA%\pachapp-android`, runs `expo prebuild` and Gradle
there, and leaves `pachapp-<version>-<timestamp>.apk` plus `pachapp-latest.apk`
in that folder.

- The API URL is baked into the bundle at build time. By default it is
  `EXPO_PUBLIC_API_BASE_URL` from the root `.env.lan`. When the PC's LAN IP
  changes, rebuild with `-ApiUrl`; cached images are downloaded again.
- Cleartext HTTP is enabled so the app can reach the LAN API.
- The release APK is signed with the debug keystore (Expo template default),
  which is fine for personal use.
- The first build downloads Gradle and missing SDK/NDK pieces and is slow;
  later builds reuse the work dir and are much faster.

## App design

The app's look follows the redesign in [`docs/redesign/`](docs/redesign/) (design system spec, navigable mockup and token proposal). Theme tokens (colours, type, radii, spacing, `tint()`) live in `app/src/theme`; the base components built on them (buttons, chips, cards, floating tab bar, ...) live in `app/src/components/ui`. Screens only compose these, so a visual change starts in one of those two places.

## Manual testing

A step-by-step manual testing guide for Hito A (upload a photo, see the garment in the wardrobe), in Spanish, lives in [`docs/manual-testing/hito-a.md`](docs/manual-testing/hito-a.md). It covers setup, the three processes, curl smoke tests, every app screen and the failure cases.

## License

P'achapp's source code is released under the [MIT License](LICENSE). Third-party models, ML code and the try-on mannequin assets keep their own licences, and several of them are non-commercial (CatVTON, its DensePose/SCHP weights, the FASHN human parser): see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) before any commercial use.
