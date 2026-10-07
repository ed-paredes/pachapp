# Single entry point for local development (D16). Every target runs from the
# repo root. See docs/specs/01-dev-tooling.md.
#
# Settings come from a dotenv file at the repo root, `.env` by default:
#   make run ENV_FILE=.env.test

SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV_FILE ?= .env

# Precedence for PACHAPP_*/EXPO_PUBLIC_* settings: command line > shell
# environment > ENV_FILE > Makefile defaults (matches pydantic-settings:
# process env beats its dotenv). A command-line assignment is already immune
# to a plain assignment (only `override` could replace it), but the plain
# assignments loaded by `-include` below WOULD shadow a shell-exported
# variable with the dotenv value, and Make would then export that dotenv
# value to recipes -- the opposite of what we want. So snapshot the
# shell-environment-origin PACHAPP_*/EXPO_PUBLIC_* variables before the
# include and restore them after.
_ENV_PRESERVE_NAMES := $(strip $(foreach v,$(.VARIABLES),$(if $(filter environment,$(origin $(v))),$(if $(filter-out PACHAPP_ENV_FILE,$(filter PACHAPP_% EXPO_PUBLIC_%,$(v))),$(v)))))
$(foreach v,$(_ENV_PRESERVE_NAMES),$(eval _ENV_STASH_$(v) := $(value $(v))))

# The backend reads this path (shared/settings.py). The Makefile also includes
# the file so host, port and the app's API URL are available here.
# PACHAPP_ENV_FILE is deliberately excluded from the preserve/restore above:
# ENV_FILE stays authoritative even if PACHAPP_ENV_FILE is also exported in
# the shell.
export PACHAPP_ENV_FILE := $(abspath $(ENV_FILE))
-include $(ENV_FILE)

# Restore the shell-environment values that -include just shadowed. As with
# any environment variable in Make, a `$` inside a value is expanded.
$(foreach v,$(_ENV_PRESERVE_NAMES),$(eval export $(v) := $(value _ENV_STASH_$(v))))

PACHAPP_API_HOST ?= 0.0.0.0
PACHAPP_API_PORT ?= 8000

BACKEND := cd backend &&
APP := cd app &&
NPM := npm --prefix app

.PHONY: help install check-node run run-worker run-ui test lint fmt fmt-check \
	typecheck migrate migrate-new gen-client ml-preload ml-cutouts ml-eval ml-cutout-eval backfill-ai recut-garments \
	tryon-setup tryon-masks tryon-spike android-apk

help: ## List targets
	@grep -hE '^[a-z-]+:.*## ' $(firstword $(MAKEFILE_LIST)) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

# Node must be the WSL install (nvm), never the Windows one under /mnt/c.
check-node:
	@node_bin=$$(command -v node || true); \
	if [[ -z "$$node_bin" || "$$node_bin" == /mnt/* ]]; then \
		echo "error: Node.js from WSL not found (got '$$node_bin'). Install it with nvm." >&2; \
		exit 1; \
	fi

install: check-node ## Install backend and app dependencies
	$(BACKEND) uv sync
	$(APP) npm install

run: ## Start the API (uvicorn, auto-reload)
	$(BACKEND) uv run uvicorn api.main:app --reload \
		--host $(PACHAPP_API_HOST) --port $(PACHAPP_API_PORT)

run-worker: ## Start the processing worker
	$(BACKEND) uv run python -m worker.main

run-ui: check-node ## Start the Expo dev server (web on :8081)
	@if [[ -z "$(EXPO_PUBLIC_API_BASE_URL)" ]]; then \
		echo "error: EXPO_PUBLIC_API_BASE_URL is empty or unset; set it in $(ENV_FILE) (or export it in the shell)." >&2; \
		exit 1; \
	fi
	$(APP) EXPO_PUBLIC_API_BASE_URL="$(EXPO_PUBLIC_API_BASE_URL)" npx expo start

test: check-node ## Run backend and app tests
	$(BACKEND) uv run pytest
	$(NPM) test

lint: check-node ## Lint backend and app
	$(BACKEND) uv run ruff check .
	$(NPM) run lint

fmt: check-node ## Format backend and app in place
	$(BACKEND) uv run ruff format .
	$(NPM) run format

fmt-check: check-node ## Check formatting without writing
	$(BACKEND) uv run ruff format --check .
	$(NPM) run format:check

typecheck: check-node ## Type-check backend (ty) and app (tsc)
	$(BACKEND) uv run ty check src
	$(NPM) run typecheck

migrate: ## Apply database migrations
	$(BACKEND) uv run alembic upgrade head

migrate-new: ## Create a migration: make migrate-new name="add garment"
	@if [[ -z "$(name)" ]]; then echo 'usage: make migrate-new name="<message>"' >&2; exit 1; fi
	$(BACKEND) uv run alembic revision --autogenerate -m "$(name)"

# Exports the schema in-process, so no running API is needed. Dummy LLM/ML
# values satisfy Settings; they never reach a provider or load a model.
gen-client: check-node ## Regenerate app/src/api-client/schema.ts from OpenAPI
	@tmp=$$(mktemp --suffix=.json); trap 'rm -f "$$tmp"' EXIT; \
	cd backend && PACHAPP_ENV_FILE=/dev/null PACHAPP_LLM_PROVIDER=gen-client \
		PACHAPP_LLM_MODEL_ID=gen-client PACHAPP_LLM_API_KEY=gen-client \
		PACHAPP_ML_EMBED_REVISION=gen-client \
		uv run python -m api.export_openapi "$$tmp" && \
	cd ../app && npx openapi-typescript "$$tmp" -o src/api-client/schema.ts

ml-preload: ## Download and validate the vision models
	$(BACKEND) uv run python -m ml.preload

ml-cutouts: ## Write BiRefNet cutouts of the eval photos for inspection
	$(BACKEND) uv run python -m ml.cutout_preview

ml-eval: ## Evaluate zero-shot accuracy on labeled eval photos (EVAL_DIR=... to override)
	$(BACKEND) uv run python -m ml.eval $(EVAL_DIR)

# Stop the API, worker and Expo first: loads several models one after another (U5).
# CUTOUT_EVAL_ARGS e.g. "DIR1 DIR2 --out /tmp/x --methods birefnet,birefnet+fashn --mask-modes subtract"
# Methods: birefnet, birefnet+{segformer-b3,segformer-b2,u2net-cloth,fashn,schp-atr,schp-lip};
# mask modes: intersect, subtract (default both, one report column per method x mode).
ml-cutout-eval: ## Compare garment-only cutout methods (CUTOUT_EVAL_ARGS="DIR... --out OUT [--methods M,..] [--mask-modes intersect,subtract] [--worn-only]")
	$(BACKEND) uv run python -m ml.cutout_eval $(CUTOUT_EVAL_ARGS)

# Virtual try-on spike (V0, docs/specs/09-virtual-tryon.md §4, §12). CatVTON is
# CC BY-NC-SA 4.0 (personal use only) and not a pip package: it is cloned at a pinned
# commit outside the repo. Its own venv only builds the mannequin masks (DensePose +
# SCHP). Its README's Python 3.9 no longer resolves: requirements.txt takes diffusers
# from git main (needs Python >= 3.10, too new for its torch 2.4) and peft>=0.17 needs
# a newer accelerate than its pin, so diffusers/accelerate are overridden to versions
# that import with torch 2.4 (checked 2026-10-05). The spike runs in the backend venv, where
# diffusers/accelerate are locked dependencies since V1a.
# Stop the API, worker and Expo before tryon-masks/tryon-spike (§12.2: RAM/VRAM).
TRYON_CATVTON_DIR ?= $(HOME)/pachapp-data/vendor/CatVTON
TRYON_CATVTON_COMMIT := 7818397f25613beedb3d861a34769f607cfcf3b1
TRYON_HF_HOME ?= $(or $(PACHAPP_ML_CACHE_DIR),$(if $(PACHAPP_DATA_DIR),$(PACHAPP_DATA_DIR)/models),$(HOME)/pachapp-data/models)

tryon-setup: ## Clone CatVTON (pinned) and create its venv for the mask builder
	@if [[ ! -d "$(TRYON_CATVTON_DIR)/.git" ]]; then \
		git clone https://github.com/Zheng-Chong/CatVTON.git "$(TRYON_CATVTON_DIR)"; fi
	git -C "$(TRYON_CATVTON_DIR)" fetch --quiet origin
	git -C "$(TRYON_CATVTON_DIR)" checkout --quiet $(TRYON_CATVTON_COMMIT)
	cd "$(TRYON_CATVTON_DIR)" && uv venv --allow-existing --python 3.10 .venv && \
		printf 'diffusers==0.30.3\naccelerate==1.2.1\n' > .venv/overrides.txt && \
		uv pip install --python .venv -r requirements.txt --override .venv/overrides.txt

tryon-masks: ## Precompute a mannequin's CatVTON masks (MANNEQUIN=dir with person.png)
	@if [[ -z "$(MANNEQUIN)" ]]; then echo 'usage: make tryon-masks MANNEQUIN=<dir>' >&2; exit 1; fi
	HF_HOME=$(TRYON_HF_HOME) "$(TRYON_CATVTON_DIR)/.venv/bin/python" \
		backend/scripts/tryon_build_masks.py --catvton-dir "$(TRYON_CATVTON_DIR)" $(MANNEQUIN)

# TRYON_SPIKE_ARGS e.g. "--mannequin M1 --mannequin M2 --garments G1 --configs C,D --seeds 42,7 --out X"
# (--cases adds `overall` for dresses; D = 768x1024/20 is opt-in; the report is checkpointed per set)
tryon-spike: ## Measure CatVTON on the GPU (TRYON_SPIKE_ARGS="--mannequin D --garments D --out D [--configs A,B,C,D] [--cases ..,overall] [--seeds 42,7]")
	$(BACKEND) uv run python -m ml.tryon_spike \
		--catvton-dir "$(TRYON_CATVTON_DIR)" $(TRYON_SPIKE_ARGS)

# Stop the worker first: backfill and worker would share the GPU (VIS-REQ-025).
backfill-ai: ## Fill AI attributes and embeddings of existing garments (stop the worker first)
	$(BACKEND) uv run python -m worker.backfill

# Stop the worker first (VIS-REQ-025). Flags: make recut-garments RECUT_ARGS="--dry-run".
recut-garments: ## Re-cut existing garments with the garment-only cutout (stop the worker first)
	$(BACKEND) uv run python -m worker.recut $(RECUT_ARGS)

# Runs on Windows (Android Studio, Node and the SDK live there); see README.
# Pass flags with: make android-apk ANDROID_ARGS="-Install"
android-apk: ## Build the Android release APK on Windows (scripts/build-android.ps1)
	powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$$(wslpath -w scripts/build-android.ps1)" $(ANDROID_ARGS)
