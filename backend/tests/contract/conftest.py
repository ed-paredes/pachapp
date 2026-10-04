"""Fixtures for the API contract tests: a real app on a temporary SQLite database.

Mirrors the environment setup of `tests/unit/conftest.py` (conftest files are
per directory): the test suite never reads the developer's `.env`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

for _key in [key for key in os.environ if key.startswith("PACHAPP_")]:
    del os.environ[_key]
os.environ["PACHAPP_ENV_FILE"] = os.devnull
os.environ["PACHAPP_ML_EMBED_REVISION"] = "test-collection-time-revision"

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402

from api import clock  # noqa: E402
from api.deps import get_engine  # noqa: E402
from api.main import create_app  # noqa: E402
from shared.enums import GarmentCategory, GarmentPattern, GarmentStatus  # noqa: E402
from shared.models import Garment, Setting  # noqa: E402
from shared.settings import Settings, get_settings  # noqa: E402

TODAY = date(2026, 10, 4)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    get_settings.cache_clear()
    for key in list(os.environ):
        if key.startswith("PACHAPP_"):
            monkeypatch.delenv(key, raising=False)
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _pin_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "local_today", lambda: TODAY)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None, data_dir=tmp_path / "data", ml_embed_revision="test-revision"
    )
    app = create_app(settings)
    SQLModel.metadata.create_all(get_engine(app))
    with Session(get_engine(app)) as session:  # the migration seeds this row in production
        session.add(Setting())
        session.commit()
    with TestClient(app) as test_client:
        yield test_client


def db(client: TestClient) -> Session:
    return Session(get_engine(client.app), expire_on_commit=False)  # type: ignore[arg-type]


def add_garment(
    client: TestClient,
    category: GarmentCategory,
    *,
    colour: str = "negro",
    neutral: bool = True,
    subcategory: str | None = None,
    formality: int = 3,
    status: GarmentStatus = GarmentStatus.active,
    last_worn_at: date | None = None,
    embedding: list[float] | None = None,
) -> str:
    garment = Garment(
        img_original="original/x.jpg",
        category=category,
        subcategory=subcategory,
        colors=[{"name": colour, "hex": "#111111", "lab": [40.0, 0.0, 0.0], "proportion": 1.0}],
        is_neutral=neutral,
        pattern=GarmentPattern.solid,
        formality=formality,
        style_tags=["casual"],
        status=status,
        last_worn_at=last_worn_at,
        embedding=None if embedding is None else np.array(embedding, dtype=np.float32).tobytes(),
        embedding_model=None if embedding is None else "test@1",
        embedding_dim=None if embedding is None else len(embedding),
    )
    with db(client) as session:
        session.add(garment)
        session.commit()
        return garment.id


def basic_wardrobe(client: TestClient) -> dict[str, str]:
    """Two tops, two bottoms, two shoes: enough for several outfits."""
    cat = GarmentCategory
    return {
        "t1": add_garment(client, cat.top, colour="blanco"),
        "t2": add_garment(client, cat.top, colour="gris", embedding=[1.0, 0.0, 0.0]),
        "b1": add_garment(client, cat.bottom, colour="negro", embedding=[0.9, 0.1, 0.0]),
        "b2": add_garment(client, cat.bottom, colour="denim"),
        "s1": add_garment(client, cat.shoes, colour="negro"),
        "s2": add_garment(client, cat.shoes, colour="blanco"),
    }


def days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)
