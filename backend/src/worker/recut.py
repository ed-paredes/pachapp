"""Re-cut of existing garments with the garment-only cutout (U5d, 08-local-vision.md VIS-REQ-032).

    make recut-garments         # uv run python -m worker.recut [--dry-run] [--limit N] [--ids ...]

Garments uploaded before U5c were cut with the plain BiRefNet matte, so a worn photo still
carries skin and the other clothes. For every garment with an original photo this re-runs the
same rule the worker `cutout` step applies (`worker.steps.cutout.CutoutEngine`: BiRefNet matte
+ FASHN parser, using the garment's stored category when there is one) and, only when that
produced a new garment-only cutout, refreshes what depends on it:

- `cutout/{id}.png` and `thumb/{id}.webp`, each written atomically (the previous file stays in
  place until the complete new one replaces it, so a crash never loses a cutout);
- the colour palette, from the cutout eroded like the worker does (`colors`, `is_neutral`,
  `color_confidence`), unless the user corrected the colours (`ai_correction` row);
- the SigLIP embedding of the new cutout, and the AI attributes that are still empty and not
  user-owned, with the same rules as `make backfill-ai` (`worker.ai.user_owned_fields`).
  Existing attribute values are never recomputed: the backfill does not do that for a model
  change either (that is `reembed`, step 6), so category, pattern, ... stay as they are.

No person in the photo (or an empty matte) keeps the old cutout untouched. A garment mask below
1 % of the image, or a parser failure, also keeps it; the first raises `needs_review`, the
second is counted as an error and retried by the next run. A garment the owner already
reviewed (`user_verified`) is never sent back to review (same rule as the backfill).

Idempotent and convergent: `garment.cutout_method` records the method/version
(`cutout_method_id`); garments already carrying it are skipped, so a second run does nothing.
Uploads made after U5c are not marked (their category was unknown at cut time), so the next
run re-cuts them once with the category the AI found. The cutout itself is not tracked as
user-editable: there is no API to replace it.

Run it with the worker STOPPED (VIS-REQ-025): everything runs serially on the GPU. As a cheap
guard, garments with a pending/claimed/running job are skipped. `--dry-run` loads no model and
writes nothing; it lists how many garments a real run would visit. `--out DIR` writes
before/after contact sheets (original | old cutout | new cutout).
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, col, select

from ml.cache import configure_model_cache
from ml.cutout_eval import THUMB_PX, fit_cell
from ml.zero_shot import ZeroShotResult
from shared import storage
from shared.corrections import has_color_correction
from shared.db import create_db_engine, create_session_factory
from shared.enums import JobStatus
from shared.models import Garment, Job
from shared.settings import Settings, get_settings
from worker.ai import (
    AI_FIELDS,
    ImageEmbedder,
    LazyModels,
    apply_classification,
    apply_embedding,
    needs_review_threshold,
    production_models_factory,
    user_owned_fields,
)
from worker.colors import ColorResult, extract_colors
from worker.runner import StepContext
from worker.steps.cutout import (
    REVIEW_MASK_TOO_SMALL,
    REVIEW_PARSER_FAILED,
    CutoutEngine,
    production_parser_factory,
    production_remover_factory,
    write_cutout_files,
)
from worker.steps.preprocess import preprocess_step

logger = logging.getLogger(__name__)

# Bump when the cutout rule changes in a way existing cutouts should be redone for.
RULE_VERSION = 1
SHEET_ROWS = 10
_BUSY = (JobStatus.pending, JobStatus.claimed, JobStatus.running)


def cutout_method_id(settings: Settings) -> str:
    """Marker stored in `garment.cutout_method` once a garment was re-cut with this method."""
    revision = settings.ml_parse_fashn_revision or "main"
    return f"{settings.ml_bg_model}+fashn@{revision}#rule{RULE_VERSION}"


@dataclass
class Counts:
    recut: int = 0  # new garment-only cutout written
    unchanged: int = 0  # no person / empty matte: old cutout kept
    small_mask: int = 0  # garment mask too small: old cutout kept, needs_review raised
    flagged: int = 0  # re-cut, but an unselected worn/carried item was kept: needs_review
    colors_kept: int = 0  # user-corrected colours left alone
    skipped_done: int = 0  # already carry the current cutout method
    skipped_busy: int = 0  # open job: the worker owns the garment
    errors: int = 0
    would_recut: int = 0  # dry run only
    failures: list[str] = field(default_factory=list)


@dataclass
class SheetRow:
    garment_id: str
    cells: list[Image.Image]


class SheetWriter:
    """Contact sheets (original | old cutout | new cutout), flushed every `SHEET_ROWS` rows."""

    def __init__(self, out_dir: Path | None) -> None:
        self.out_dir = out_dir
        self.rows: list[SheetRow] = []
        self.paths: list[Path] = []

    def add(
        self, garment_id: str, original: Image.Image, old: Image.Image | None, new: Image.Image
    ) -> None:
        if self.out_dir is None:
            return
        blank = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        self.rows.append(
            SheetRow(
                garment_id,
                [
                    fit_cell(original, garment_id[:8]),
                    fit_cell(old if old is not None else blank, "old"),
                    fit_cell(new, "new"),
                ],
            )
        )
        if len(self.rows) >= SHEET_ROWS:
            self.flush()

    def flush(self) -> None:
        if self.out_dir is None or not self.rows:
            return
        self.out_dir.mkdir(parents=True, exist_ok=True)
        cell_h = THUMB_PX + 16
        sheet = Image.new("RGB", (3 * THUMB_PX, len(self.rows) * cell_h), (255, 255, 255))
        for row, entry in enumerate(self.rows):
            for column, cell in enumerate(entry.cells):
                sheet.paste(cell, (column * THUMB_PX, row * cell_h))
        path = self.out_dir / f"recut_{len(self.paths) + 1:02d}.jpg"
        sheet.save(path, quality=88)
        self.paths.append(path)
        self.rows = []


def _pending_ids(
    session: Session, method: str, only: Sequence[str] | None, counts: Counts
) -> list[str]:
    busy = set(session.exec(select(col(Job.garment_id)).where(col(Job.status).in_(_BUSY))).all())
    wanted = set(only) if only else None
    ids: list[str] = []
    seen: set[str] = set()
    for garment in session.exec(select(Garment).order_by(col(Garment.created_at))).all():
        if wanted is not None and garment.id not in wanted:
            continue
        seen.add(garment.id)
        if garment.cutout_method == method:
            counts.skipped_done += 1
        elif garment.id in busy:
            logger.info("garment %s has an open job, skipping", garment.id)
            counts.skipped_busy += 1
        else:
            ids.append(garment.id)
    for unknown in sorted((wanted or set()) - seen):
        logger.warning("garment %s not found", unknown)
    return ids


def _load(settings: Settings, relative: str | None) -> Image.Image | None:
    assert settings.images_root is not None
    if not relative:
        return None
    try:
        with Image.open(storage.resolve_path(settings.images_root, relative)) as opened:
            return opened.convert("RGBA")
    except (OSError, ValueError):
        return None


def _store(
    factory: sessionmaker[Session],
    garment_id: str,
    method: str,
    counts: Counts,
    *,
    review: str | None,
    embedder: ImageEmbedder | None,
    colors: ColorResult | None,
    vector: np.ndarray | None,
    prediction: ZeroShotResult | None,
    paths: tuple[str, str] | None,
) -> None:
    """One short transaction. User edits made while the batch ran are re-checked here."""
    with factory() as session:
        garment = session.get(Garment, garment_id)
        if garment is None:  # deleted while the command ran
            return
        if paths is not None:
            garment.img_cutout, garment.img_thumb = paths
        if colors is not None:
            if has_color_correction(session, garment_id):
                counts.colors_kept += 1
            else:
                garment.colors = colors.colors.model_dump(mode="json")
                garment.is_neutral = colors.is_neutral
                garment.color_confidence = colors.confidence
        if vector is not None and embedder is not None:
            apply_embedding(garment, vector, embedder)
            if prediction is not None:
                owned = user_owned_fields(session, garment)
                missing = {n for n in AI_FIELDS if getattr(garment, n) is None} - owned
                if "category" not in missing:
                    missing.discard("subcategory")  # same rule as the backfill
                apply_classification(garment, prediction, missing)
        if review and not garment.user_verified:  # reviewed garments stay out of review
            garment.needs_review = True
        garment.cutout_method = method
        garment.updated_at = datetime.now(UTC)
        session.add(garment)
        session.commit()


def _recut_one(
    factory: sessionmaker[Session],
    settings: Settings,
    engine: CutoutEngine,
    models: LazyModels,
    method: str,
    garment_id: str,
    counts: Counts,
    sheets: SheetWriter,
) -> None:
    ctx = StepContext(
        job_id="recut", garment_id=garment_id, settings=settings, session_factory=factory
    )
    preprocess_step(ctx)
    image: Image.Image = ctx.data["image"]
    with factory() as session:
        garment = session.get(Garment, garment_id)
        if garment is None:
            return
        old_rel = garment.img_cutout
    old = _load(settings, old_rel)
    result = engine.cut(ctx, image)

    if result.review == REVIEW_PARSER_FAILED:
        raise RuntimeError("the garment parser failed; the old cutout was kept")
    if result.soft_failure or not result.parsed:
        # Nothing new to write (no person, empty matte or mask too small): keep the old
        # cutout, unless there was none, in which case the plain matte is better than nothing.
        small = result.review == REVIEW_MASK_TOO_SMALL
        paths = None
        if old is None and not result.soft_failure:
            paths = write_cutout_files(settings, garment_id, result.cutout)
        _store(
            factory,
            garment_id,
            method,
            counts,
            review=result.review if small else None,
            embedder=None,
            colors=None,
            vector=None,
            prediction=None,
            paths=paths,
        )
        if small:
            counts.small_mask += 1
            sheets.add(garment_id, image, old, result.cutout)
        else:
            counts.unchanged += 1
        return

    assert result.color_image is not None
    loaded = models.get()
    vector = loaded.embedder.embed_image(result.cutout)
    with factory() as session:
        threshold = needs_review_threshold(session)
    prediction = loaded.classifier.classify(vector, needs_review_threshold=threshold)
    colors = extract_colors(result.color_image)
    paths = write_cutout_files(settings, garment_id, result.cutout)  # old files kept until here
    _store(
        factory,
        garment_id,
        method,
        counts,
        review=result.review,
        embedder=loaded.embedder,
        colors=colors,
        vector=vector,
        prediction=prediction,
        paths=paths,
    )
    counts.recut += 1
    if result.review:
        counts.flagged += 1
    sheets.add(garment_id, image, old, result.cutout)


def recut(
    settings: Settings,
    factory: sessionmaker[Session],
    engine: CutoutEngine,
    models: LazyModels,
    *,
    dry_run: bool = False,
    limit: int | None = None,
    ids: Sequence[str] | None = None,
    out_dir: Path | None = None,
) -> tuple[Counts, list[Path]]:
    counts = Counts()
    method = cutout_method_id(settings)
    with factory() as session:
        pending = _pending_ids(session, method, ids, counts)
    if limit is not None:
        pending = pending[: max(limit, 0)]
    if dry_run:
        counts.would_recut = len(pending)
        return counts, []
    sheets = SheetWriter(out_dir)
    for garment_id in pending:  # serial: one garment on the GPU at a time (VIS-REQ-025)
        try:
            _recut_one(factory, settings, engine, models, method, garment_id, counts, sheets)
        except Exception as exc:  # noqa: BLE001 - one bad garment must not stop the run
            logger.error("garment %s failed: %s", garment_id, exc)
            counts.errors += 1
            counts.failures.append(f"{garment_id}: {exc}")
    sheets.flush()
    return counts, sheets.paths


def format_summary(counts: Counts, sheets: Sequence[Path], *, dry_run: bool) -> str:
    if dry_run:
        return (
            f"dry run: would_recut={counts.would_recut} already_done={counts.skipped_done} "
            f"busy={counts.skipped_busy} (no model loaded, nothing written)"
        )
    lines = [
        f"recut={counts.recut} (needs_review from an unselected item: {counts.flagged})",
        f"unchanged (no person / empty matte)={counts.unchanged}",
        f"small_mask (old cutout kept, needs_review)={counts.small_mask}",
        f"user colours kept={counts.colors_kept}",
        f"already_done={counts.skipped_done} busy={counts.skipped_busy} errors={counts.errors}",
    ]
    lines += [f"contact sheet: {path}" for path in sheets]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="worker.recut", description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    parser.add_argument("--limit", type=int, default=None, help="re-cut at most N garments")
    parser.add_argument("--ids", nargs="+", default=None, help="only these garment ids")
    parser.add_argument("--out", type=Path, default=None, help="directory for contact sheets")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    settings = get_settings()
    if not settings.ml_garment_parse:
        print(
            "PACHAPP_ML_GARMENT_PARSE is off: the re-cut needs the garment parser. "
            "Set it to true and run again.",
            file=sys.stderr,
        )
        return 2
    assert settings.ml_cache_dir is not None
    configure_model_cache(settings.ml_cache_dir)
    factory = create_session_factory(create_db_engine(settings))
    engine = CutoutEngine(production_remover_factory(settings), production_parser_factory(settings))
    models = LazyModels(production_models_factory(settings))
    counts, sheets = recut(
        settings,
        factory,
        engine,
        models,
        dry_run=args.dry_run,
        limit=args.limit,
        ids=args.ids,
        out_dir=args.out,
    )
    print(format_summary(counts, sheets, dry_run=args.dry_run))
    for line in counts.failures:
        print(f"  failed {line}", file=sys.stderr)
    return 1 if counts.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
