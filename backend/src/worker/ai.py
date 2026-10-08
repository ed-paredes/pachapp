"""Shared logic of the `ai_attributes`/`embedding` steps and the backfill
(08-local-vision.md step 4, VIS-REQ-002/013..019).

Models are built lazily (`LazyModels`): the embedder is the process-wide
`ml.registry.get_embedder` and the zero-shot classifier is built once on top of
it. Tests inject fakes through a factory, so nothing here loads a model at
import time and the API process never imports this module (VIS-REQ-005).

User ownership: a field is never overwritten when `ai_confidence[field].source
== "user"`, when an `ai_correction` row exists for it, or when its column holds
a value that has no `ai_confidence` entry (typed by hand, e.g. in Revision,
before any AI value existed).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import numpy as np
from PIL import Image
from sqlmodel import Session, col, select

from ml.device import free_gpu_memory
from ml.zero_shot import REVIEW_TRIGGER_ATTRIBUTES, ZeroShotResult
from shared import storage
from shared.enums import ConfidenceSource, GarmentCategory, GarmentPattern
from shared.models import AiCorrection, Garment, Setting
from shared.settings import Settings

# Garment columns the zero-shot classifier fills (VIS-REQ-019 keys).
AI_FIELDS = ("category", "subcategory", "pattern", "material", "formality", "style_tags")

# Used only when the singleton `setting` row was never seeded.
DEFAULT_NEEDS_REVIEW_THRESHOLD = 0.7


class ImageEmbedder(Protocol):
    dim: int
    model_id: str

    def embed_image(self, img: Image.Image) -> np.ndarray: ...


class Classifier(Protocol):
    def classify(
        self, img_emb: np.ndarray, *, needs_review_threshold: float | None = None
    ) -> ZeroShotResult: ...


@dataclass
class AiModels:
    embedder: ImageEmbedder
    classifier: Classifier
    # Drops whatever process-wide state the models live in (production: the
    # `ml.registry` embedder); `LazyModels.unload` calls it. Fakes need none.
    release: Callable[[], object] | None = None


ModelsFactory = Callable[[], AiModels]


def production_models_factory(settings: Settings) -> ModelsFactory:
    """Factory of the real SigLIP embedder + zero-shot classifier; `ml.registry`
    (torch, open_clip) is imported only when the factory is called."""

    def build() -> AiModels:
        from ml.registry import get_embedder, unload_embedder
        from ml.zero_shot import ZeroShotClassifier

        embedder = get_embedder(settings)
        classifier = ZeroShotClassifier(embedder, margin_threshold=settings.ml_margin_threshold)
        return AiModels(embedder=embedder, classifier=classifier, release=unload_embedder)

    return build


class LazyModels:
    """Builds the models on first `get()` and reuses them (one set per process)."""

    def __init__(self, factory: ModelsFactory) -> None:
        self._factory = factory
        self._models: AiModels | None = None
        self._lock = threading.Lock()

    def get(self) -> AiModels:
        with self._lock:
            if self._models is None:
                self._models = self._factory()
            return self._models

    def unload(self) -> bool:
        """Drop the models and free GPU memory; the next `get()` rebuilds them.
        Returns whether any were loaded."""
        with self._lock:
            models, self._models = self._models, None
        was_loaded = models is not None
        if models is not None and models.release is not None:
            models.release()
        del models  # the last reference must go before the cache is emptied
        free_gpu_memory()
        return was_loaded


def load_garment_image(settings: Settings, garment: Garment) -> Image.Image:
    """The stored cutout if there is one, else the original; fully decoded."""
    assert settings.images_root is not None
    relative = garment.img_cutout or garment.img_original
    with Image.open(storage.resolve_path(settings.images_root, relative)) as opened:
        opened.load()
        return opened.copy()


def needs_review_threshold(session: Session) -> float:
    setting = session.get(Setting, 1)
    return setting.needs_review_threshold if setting else DEFAULT_NEEDS_REVIEW_THRESHOLD


def user_owned_fields(session: Session, garment: Garment) -> set[str]:
    """AI fields that must not be overwritten (see module docstring)."""
    confidence = garment.ai_confidence or {}
    corrected = set(
        session.exec(
            select(col(AiCorrection.field)).where(col(AiCorrection.garment_id) == garment.id)
        ).all()
    )
    owned: set[str] = set()
    for name in AI_FIELDS:
        entry = confidence.get(name)
        if entry is not None:
            if entry.get("source") == ConfidenceSource.user.value or name in corrected:
                owned.add(name)
        elif getattr(garment, name) is not None or name in corrected:
            owned.add(name)
    return owned


def apply_classification(garment: Garment, result: ZeroShotResult, fields: set[str]) -> list[str]:
    """Write the predicted `fields` and their `ai_confidence` entries (other
    entries, e.g. user ones, are kept). Raises `needs_review` only when a field
    this call wrote is a low-confidence trigger attribute (VIS-REQ-016) and the
    owner has not already reviewed the garment (`user_verified`: filling an empty
    field must not send it back to review, owner decision 2026-10-04); it is
    never cleared. Returns the fields written, in `AI_FIELDS` order."""
    if "category" not in fields:
        # The subcategory prediction belongs to the *predicted* category; do not
        # attach it to a category this call did not write (e.g. user-set).
        fields = fields - {"subcategory"}
    confidence = dict(garment.ai_confidence or {})
    written: list[str] = []
    for name in AI_FIELDS:
        pred = result.predictions.get(name)
        if name not in fields or pred is None:
            continue
        value: Any = pred.value
        if name == "category":
            garment.category = GarmentCategory(value)
        elif name == "pattern":
            garment.pattern = GarmentPattern(value)
        elif name == "style_tags":
            garment.style_tags = list(value)
        else:
            setattr(garment, name, value)
        confidence[name] = pred.model_dump(mode="json")
        written.append(name)
    if written:
        garment.ai_confidence = confidence
        if not garment.user_verified and any(
            a in REVIEW_TRIGGER_ATTRIBUTES and a in written for a in result.low_confidence
        ):
            garment.needs_review = True
        garment.updated_at = datetime.now(UTC)
    return written


def apply_embedding(garment: Garment, vector: np.ndarray, embedder: ImageEmbedder) -> None:
    garment.embedding = np.asarray(vector, dtype=np.float32).tobytes()
    garment.embedding_model = embedder.model_id
    garment.embedding_dim = embedder.dim
    garment.updated_at = datetime.now(UTC)
