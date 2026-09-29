"""FastAPI application entrypoint for pachapp.

`uvicorn api.main:app` imports the module-level `app` below, which is
built eagerly via `create_app()` so misconfiguration (e.g. an invalid
`.env`/environment) fails fast with a clear error instead of starting a
half-working server.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.errors import register_error_handlers
from api.routers import garment_edit, garment_lifecycle, garments, jobs
from api.routers import settings as settings_router
from shared.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application. Pass `settings` explicitly in tests."""
    settings = settings or get_settings()

    assert settings.images_root is not None
    images_root = settings.images_root

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # API-REQ-016: make sure the static root exists before serving.
        images_root.mkdir(parents=True, exist_ok=True)
        yield
        engine = getattr(app.state, "engine", None)
        if engine is not None:
            engine.dispose()

    app = FastAPI(title="pachapp API", lifespan=lifespan)
    app.state.settings = settings
    register_error_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(garments.router)
    app.include_router(garment_edit.router)
    app.include_router(garment_lifecycle.router)
    app.include_router(jobs.router)
    app.include_router(settings_router.router)

    # API-REQ-016: serves the relative paths stored on `garment`. `check_dir`
    # is off because the directory is created at startup, not at import.
    app.mount("/images", StaticFiles(directory=images_root, check_dir=False), name="images")

    return app


app = create_app()
