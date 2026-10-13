"""Cache cleanup of stale try-on renders (09-virtual-tryon.md §6.5)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel, col, create_engine

from shared.enums import JobStatus
from shared.models import TryOnRender
from tryon import cleanup
from tryon.cleanup import purge_stale_renders
from tryon.tones import SKIN_TONES

NOW = dt.datetime(2026, 10, 11, tzinfo=dt.UTC)
OLD = NOW - dt.timedelta(days=31)
RECENT = NOW - dt.timedelta(days=29)


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_engine(f"sqlite:///{tmp_path / 'db.sqlite3'}")
    SQLModel.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, class_=Session, expire_on_commit=False)


def _add(
    factory: sessionmaker[Session],
    images_root: Path,
    key: str,
    *,
    status: JobStatus = JobStatus.done,
    accessed: dt.datetime = OLD,
    with_file: bool = True,
    variants: bool = False,
) -> TryOnRender:
    render = TryOnRender(cache_key=key, mannequin_id="m1", status=status, last_accessed_at=accessed)
    if status == JobStatus.done:
        render.img_path = f"tryon/{render.id}.webp"
        if with_file:
            path = images_root / render.img_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"webp")
        if variants:
            for tone, _ in SKIN_TONES:
                (images_root / f"tryon/{render.id}_t{tone}.webp").write_bytes(b"webp")
    with factory() as session:
        session.add(render)
        session.commit()
    return render


def _exists(factory: sessionmaker[Session], render_id: str) -> bool:
    with factory() as session:
        return session.get(TryOnRender, render_id) is not None


def _purge(factory: sessionmaker[Session], root: Path, days: int = 30) -> int:
    with factory() as session:
        return purge_stale_renders(session, root, days, now=NOW)


def test_removes_stale_rows_and_files_and_keeps_recent_ones(factory, tmp_path: Path) -> None:
    stale = _add(factory, tmp_path, "stale")
    fresh = _add(factory, tmp_path, "fresh", accessed=RECENT)

    assert _purge(factory, tmp_path) == 1

    assert not _exists(factory, stale.id)
    assert stale.img_path is not None and not (tmp_path / stale.img_path).exists()
    assert _exists(factory, fresh.id)
    assert fresh.img_path is not None and (tmp_path / fresh.img_path).is_file()


def test_the_dummy_variants_go_with_the_render(factory, tmp_path: Path) -> None:
    stale = _add(factory, tmp_path, "stale", variants=True)
    fresh = _add(factory, tmp_path, "fresh", accessed=RECENT, variants=True)

    assert _purge(factory, tmp_path) == 1

    assert list((tmp_path / "tryon").glob(f"{stale.id}*")) == []
    assert len(list((tmp_path / "tryon").glob(f"{fresh.id}_t*.webp"))) == len(SKIN_TONES)


def test_stale_failed_renders_go_too(factory, tmp_path: Path) -> None:
    failed = _add(factory, tmp_path, "failed", status=JobStatus.failed)

    assert _purge(factory, tmp_path) == 1
    assert not _exists(factory, failed.id)


@pytest.mark.parametrize("status", [JobStatus.pending, JobStatus.claimed, JobStatus.running])
def test_never_removes_a_render_that_is_queued_or_in_flight(
    factory, tmp_path: Path, status: JobStatus
) -> None:
    render = _add(factory, tmp_path, "busy", status=status)

    assert _purge(factory, tmp_path) == 0
    assert _exists(factory, render.id)


def test_a_missing_file_does_not_stop_the_cleanup(factory, tmp_path: Path) -> None:
    gone = _add(factory, tmp_path, "gone", with_file=False)
    other = _add(factory, tmp_path, "other")

    assert _purge(factory, tmp_path) == 2
    assert not _exists(factory, gone.id) and not _exists(factory, other.id)


def test_zero_days_keeps_everything(factory, tmp_path: Path) -> None:
    render = _add(factory, tmp_path, "old")

    assert _purge(factory, tmp_path, days=0) == 0
    assert _exists(factory, render.id)


@pytest.mark.parametrize(
    "change",
    [{"last_accessed_at": NOW}, {"status": JobStatus.pending}],
    ids=["touched", "requeued"],
)
def test_a_row_changed_between_the_select_and_the_delete_survives_with_its_file(
    factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: dict
) -> None:
    render = _add(factory, tmp_path, "racing")
    real_delete = cleanup.delete

    def touch_then_delete(*args, **kwargs):
        # A request touches or requeues the render after the cleanup selected it as stale.
        with factory() as other:
            other.connection().execute(
                update(TryOnRender).where(col(TryOnRender.id) == render.id).values(**change)
            )
            other.commit()
        return real_delete(*args, **kwargs)

    monkeypatch.setattr(cleanup, "delete", touch_then_delete)

    assert _purge(factory, tmp_path) == 0

    assert _exists(factory, render.id)
    assert render.img_path is not None and (tmp_path / render.img_path).is_file()
