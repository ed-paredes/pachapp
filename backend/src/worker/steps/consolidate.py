"""`consolidate` step (03-garment-ingestion.md "Reglas de needs_review", D19, DAT-REQ-002/018).

`needs_review` becomes true when `color_confidence < setting.color_review_threshold`
or the cutout soft-failed (ING-SCN-005). It is only ever raised here, never
cleared: only "Revisión terminada" (API-REQ-019) sets it back to false.

Seam for 08 step 4 (A15): the AI-dependent triggers (`ai_confidence` below
`needs_review_threshold`, top-1/top-2 margin, exhausted local-classifier retry) are
added to `_review_triggers` once `ai_attributes` exists.
"""

from __future__ import annotations

from datetime import UTC, datetime

from shared.models import Garment, Setting
from worker.runner import PermanentStepError, StepContext

MSG_CONSOLIDATE = "No se pudo finalizar la prenda. Inténtalo de nuevo."

# Used only when the singleton `setting` row was never seeded.
DEFAULT_COLOR_REVIEW_THRESHOLD = 0.7


def _review_triggers(
    ctx: StepContext, garment: Garment, color_review_threshold: float
) -> list[str]:
    reasons: list[str] = []
    # A missing confidence means the colour step produced nothing usable.
    if garment.color_confidence is None or garment.color_confidence < color_review_threshold:
        reasons.append("low_color_confidence")
    if ctx.data.get("cutout_soft_failure"):
        reasons.append("cutout_soft_failure")
    # 08 step 4 seam: ai_confidence / margin / classifier-retry triggers go here.
    return reasons


def consolidate_step(ctx: StepContext) -> None:
    with ctx.session_factory() as session:
        garment = session.get(Garment, ctx.garment_id)
        if garment is None:
            raise PermanentStepError(
                f"garment {ctx.garment_id} disappeared", user_message=MSG_CONSOLIDATE
            )
        setting = session.get(Setting, 1)
        threshold = setting.color_review_threshold if setting else DEFAULT_COLOR_REVIEW_THRESHOLD
        if _review_triggers(ctx, garment, threshold):
            garment.needs_review = True  # never set back to False here (D19)
        garment.updated_at = datetime.now(UTC)
        session.add(garment)
        session.commit()
