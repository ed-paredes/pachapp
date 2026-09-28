# P'achapp

## Layout

| Path | What |
| --- | --- |
| `backend/` | `uv` project, Python 3.12. Packages: `api` (FastAPI), `worker` (polling loop), `engine` (pure functions, no I/O), `shared` (settings). |
| `app/` | Expo + TypeScript client (Expo Router), targeting iOS/Android (Expo Go) and web. |
| `docs/` | Specs (`docs/specs/`) and C4 architecture (`docs/architecture/c4.md`). |

Full toolchain spec: `docs/specs/01-dev-tooling.md`.

## Prerequisites

- WSL2 (Ubuntu), with `uv` and Node 22 installed **inside WSL** via `nvm`.
  - `make` refuses to run app/UI targets against the Windows Node/npm under
    `/mnt/c` (`check-node`) — always run `make` from a WSL shell with `nvm`'s
    Node on `PATH`.
- The repo itself can live under `/mnt/d` (or anywhere Windows-visible), but
  `PACHAPP_DATA_DIR` (the SQLite DB + images) must resolve to a path on the
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

| Target | Description |
| --- | --- |
| `install` | Install backend and app dependencies |
| `run` | Start the API (uvicorn, auto-reload) |
| `run-worker` | Start the processing worker |
| `run-ui` | Start the Expo dev server (web on :8081) |
| `test` | Run backend and app tests |
| `lint` | Lint backend and app |
| `fmt` | Format backend and app in place |
| `fmt-check` | Check formatting without writing |
| `typecheck` | Type-check backend (ty) and app (tsc) |
| `migrate` | Apply database migrations |
| `migrate-new` | Create a migration: `make migrate-new name="add garment"` |
| `gen-client` | Regenerate `app/src/api-client/schema.ts` from OpenAPI |

## `make gen-client`

Exports the OpenAPI schema in-process (no running API needed) and runs
`openapi-typescript` against it, writing `app/src/api-client/schema.ts`. That
file is committed (DEV-REQ-010) and excluded from Prettier.

## Phone / LAN access (manual)

To open the app on a phone via Expo Go, the phone needs to reach the API
running in WSL (D13). This typically means:

- Windows `.wslconfig` set to `networkingMode=mirrored`, with a firewall rule
  allowing inbound `8000`/`8081`.
- `EXPO_PUBLIC_API_BASE_URL` set to the PC's LAN IP (e.g.
  `http://192.168.1.10:8000`), and that LAN origin added to
  `PACHAPP_CORS_ORIGINS`.

See `docs/specs/01-dev-tooling.md` for the full checklist and fallbacks.
