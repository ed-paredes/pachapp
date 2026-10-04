"""`embedding` step (08-local-vision.md step 4, VIS-REQ-002).

Persists the image embedding computed by `ai_attributes` (`ctx.data["embedding"]`,
no second inference; computed here when the step runs without it) as float32
bytes, with `embedding_model` (`id@revision`) and `embedding_dim` read from the
loaded model. Re-running writes the same values.
"""

from __future__ import annotations

from shared.models import Garment
from worker.ai import LazyModels, apply_embedding
from worker.runner import PermanentStepError, Step, StepContext
from worker.steps.ai_attributes import MSG_AI, image_embedding


def make_embedding_step(models: LazyModels) -> Step:
    def embedding_step(ctx: StepContext) -> None:
        loaded = models.get()
        vector = image_embedding(ctx, loaded)
        with ctx.session_factory() as session:
            garment = session.get(Garment, ctx.garment_id)
            if garment is None:
                raise PermanentStepError(
                    f"garment {ctx.garment_id} disappeared", user_message=MSG_AI
                )
            apply_embedding(garment, vector, loaded.embedder)
            session.add(garment)
            session.commit()

    return embedding_step
