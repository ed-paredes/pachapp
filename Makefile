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
	typecheck migrate migrate-new gen-client ml-preload ml-cutouts ml-eval backfill-ai

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

# Stop the worker first: backfill and worker would share the GPU (VIS-REQ-025).
backfill-ai: ## Fill AI attributes and embeddings of existing garments (stop the worker first)
	$(BACKEND) uv run python -m worker.backfill
