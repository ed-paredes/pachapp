"""FastAPI application entrypoint for pachapp.

`uvicorn api.main:app` imports the module-level `app` below, which is
built eagerly via `create_app()` so misconfiguration (e.g. an invalid
`.env`/environment) fails fast with a clear error instead of starting a
half-working server.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.errors import register_error_handlers
from shared.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application. Pass `settings` explicitly in tests."""
    settings = settings or get_settings()

    app = FastAPI(title="pachapp API")
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

    return app


app = create_app()
