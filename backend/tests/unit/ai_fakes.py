"""Offline fakes for the `ai_attributes`/`embedding` steps and the backfill
(VIS-REQ-029): synthetic text/image embeddings, no model and no network."""

from __future__ import annotations

import hashlib

import numpy as np
from PIL import Image

from ml.zero_shot import ZeroShotClassifier, l2_normalize
from worker.ai import AiModels

DIM = 64
MODEL_ID = "fake/embedder@rev-1"


def _vec(key: str) -> np.ndarray:
    seed = int.from_bytes(hashlib.sha256(key.encode()).digest()[:4], "big")
    return l2_normalize(np.random.default_rng(seed).normal(size=DIM))


class FakeTextEmbedder:
    def embed_texts(self, texts: list[str]) -> np.ndarray:
        rows = []
        for t in texts:
            core = t.removeprefix("a photo of ").removesuffix(
                ", product photo on a plain background"
            )
            rows.append(l2_normalize(_vec(core) + 0.05 * _vec(t)))
        return np.stack(rows)


class FakeImageEmbedder:
    """`embed_image` returns `vector` (or raises `error`) and records its inputs."""

    def __init__(self, vector: np.ndarray, model_id: str = MODEL_ID) -> None:
        self.vector = vector
        self.model_id = model_id
        self.dim = int(vector.shape[0])
        self.error: Exception | None = None
        self.images: list[Image.Image] = []

    def embed_image(self, img: Image.Image) -> np.ndarray:
        self.images.append(img)
        if self.error is not None:
            raise self.error
        return self.vector


_CLASSIFIER = ZeroShotClassifier(FakeTextEmbedder())


def vector_for(
    *,
    category: str | tuple[str, str] = "top",
    pattern: str | tuple[str, str] = "solid",
    material: str | tuple[str, str] = "algodón",
    formality: int | tuple[int, int] = 2,
    weights: dict[str, float] | None = None,
) -> np.ndarray:
    """An image embedding that the fake classifier maps to the given labels. A
    pair of values blends two labels, which makes that attribute less certain;
    `weights` scales an attribute's share (default 1)."""

    def label(attr: str, values: list, wanted) -> np.ndarray:
        embs = _CLASSIFIER.label_embeddings(attr)
        wanted = wanted if isinstance(wanted, tuple) else (wanted,)
        return sum(embs[values.index(v)] for v in wanted) / len(wanted)

    values = _CLASSIFIER._values
    w = weights or {}
    parts = [
        w.get("category", 1) * label("category", values["category"], category),
        w.get("pattern", 1) * label("pattern", values["pattern"], pattern),
        w.get("material", 1) * label("material", values["material"], material),
        w.get("formality", 1) * label("formality", values["formality"], formality),
    ]
    return l2_normalize(sum(parts))


def make_models(vector: np.ndarray | None = None, **classifier_kwargs) -> AiModels:
    """Fake embedder + the real zero-shot classifier over fake text embeddings;
    `classifier_kwargs` (e.g. `margin_threshold`) build a dedicated classifier."""
    embedder = FakeImageEmbedder(vector if vector is not None else vector_for())
    classifier = (
        ZeroShotClassifier(FakeTextEmbedder(), **classifier_kwargs)
        if classifier_kwargs
        else _CLASSIFIER
    )
    return AiModels(embedder=embedder, classifier=classifier)
