"""Hand the GPU to CatVTON: unload the worker's resident models first (§6.4, §12).

BiRefNet, FASHN and SigLIP leave the 6 GB card nearly full (5.7 GB measured), so the
try-on service calls `release_resident_models` before CatVTON loads; each of them reloads
lazily on its next use. Nothing here is wired into the worker loop yet.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

from ml.device import free_gpu_memory

if TYPE_CHECKING:
    from worker.ai import LazyModels
    from worker.steps.cutout import CutoutEngine

logger = logging.getLogger(__name__)


def resident_unloaders(cutout: CutoutEngine, models: LazyModels) -> list[Callable[[], object]]:
    """The unload hooks of the worker's models: FASHN (and the remover wrapper), BiRefNet's
    process-wide session, and SigLIP."""
    from ml import registry

    return [cutout.unload, registry.unload_background_remover, models.unload]


def release_resident_models(unloaders: Iterable[Callable[[], object]]) -> int:
    """Run every unloader, then empty the CUDA cache once. A failing unloader is logged
    and does not stop the rest (CatVTON still needs the others' memory); returns how many
    failed."""
    failed = 0
    for unload in unloaders:
        try:
            unload()
        except Exception:  # noqa: BLE001 - keep releasing the remaining models
            failed += 1
            logger.exception("could not unload %r", unload)
    free_gpu_memory()
    return failed
