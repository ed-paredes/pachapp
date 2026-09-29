"""Zero-shot tests with synthetic embeddings (VIS-REQ-029): no model, no network."""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from ml.taxonomy import TAXONOMY
from ml.zero_shot import (
    ZeroShotClassifier,
    ensemble_embedding,
    formality_from_probs,
    is_low_confidence,
    l2_normalize,
    softmax_probs,
    style_tags_from_sims,
    top_two,
)

DIM = 64


def _vec(key: str) -> np.ndarray:
    seed = int.from_bytes(hashlib.sha256(key.encode()).digest()[:4], "big")
    return l2_normalize(np.random.default_rng(seed).normal(size=DIM))


class FakeEmbedder:
    """Deterministic text embeddings: every template of one prompt maps near the
    prompt's own random direction, so ensembles stay separable."""

    def __init__(self) -> None:
        self.calls = 0

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        self.calls += 1
        rows = []
        for t in texts:
            core = t.removeprefix("a photo of ").removesuffix(
                ", product photo on a plain background"
            )
            rows.append(l2_normalize(_vec(core) + 0.05 * _vec(t)))
        return np.stack(rows)


@pytest.fixture(scope="module")
def clf() -> ZeroShotClassifier:
    return ZeroShotClassifier(FakeEmbedder())


def test_ensemble_mean_is_normalized() -> None:
    e = ensemble_embedding(np.stack([_vec("a"), _vec("b"), _vec("c")]))
    assert e.shape == (DIM,)
    assert np.linalg.norm(e) == pytest.approx(1.0, abs=1e-5)


def test_label_embeddings_are_unit_rows(clf: ZeroShotClassifier) -> None:
    for attr in TAXONOMY:
        norms = np.linalg.norm(clf.label_embeddings(attr), axis=1)
        assert norms == pytest.approx(np.ones(len(TAXONOMY[attr])), abs=1e-5)


def test_softmax_probs_sum_to_one_and_rank() -> None:
    labels = np.stack([_vec("x"), _vec("y")])
    p = softmax_probs(_vec("x"), labels)
    assert p.sum() == pytest.approx(1.0)
    assert p[0] > p[1]


def test_clear_winner_no_review(clf: ZeroShotClassifier) -> None:
    img = clf.label_embeddings("category")[0]  # "top" is the first taxonomy key
    result = clf.classify(img)
    cat = result.predictions["category"]
    assert cat.value == "top"
    assert cat.source == "zero_shot"
    assert cat.confidence > 0.9
    assert "category" not in result.low_confidence


def test_near_tie_triggers_margin_rule() -> None:
    probs = np.array([0.5, 0.42, 0.08])
    assert top_two(probs)[0] == 0
    # top1 0.5 < 0.7 anyway; isolate the margin rule with a low review threshold
    assert is_low_confidence(probs, needs_review_threshold=0.4, margin_threshold=0.15)
    assert not is_low_confidence(np.array([0.6, 0.3, 0.1]), 0.4, 0.15)


def test_low_top1_triggers_review() -> None:
    probs = np.array([0.6, 0.1, 0.1, 0.1, 0.1])
    assert is_low_confidence(probs, needs_review_threshold=0.7, margin_threshold=0.15)
    assert not is_low_confidence(np.array([0.9, 0.05, 0.05]), 0.7, 0.15)


def test_ambiguous_image_flags_review(clf: ZeroShotClassifier) -> None:
    labels = clf.label_embeddings("category")
    img = l2_normalize(labels[0] + labels[1])  # halfway between top and bottom
    result = clf.classify(img)
    assert result.needs_review
    assert "category" in result.low_confidence


def test_formality_weighted_mean_rounding_and_confidence() -> None:
    v, c = formality_from_probs(np.array([0, 0, 1.0, 0, 0]), [1, 2, 3, 4, 5])
    assert (v, c) == (3, pytest.approx(1.0))
    v, c = formality_from_probs(np.array([0.5, 0, 0, 0, 0.5]), [1, 2, 3, 4, 5])
    assert v == 3
    assert c == pytest.approx(0.0)  # std = 2
    v, _ = formality_from_probs(np.array([0.4, 0.6, 0, 0, 0]), [1, 2, 3, 4, 5])
    assert v == 2  # mean 1.6
    v, _ = formality_from_probs(np.array([0.5, 0.5, 0, 0, 0]), [1, 2, 3, 4, 5])
    assert v == 2  # 1.5 rounds half-up
    v, _ = formality_from_probs(np.array([0, 0, 0, 0, 1.0]), [1, 2, 3, 4, 5])
    assert v == 5


def test_style_tags_threshold_and_max_three() -> None:
    tags = ["casual", "classic", "street", "minimal", "sport"]
    sims = np.array([0.30, 0.25, 0.20, 0.15, 0.02])
    selected, conf = style_tags_from_sims(sims, tags)
    assert selected == ["casual", "classic", "street"]  # 4th passes but max 3
    assert 0.5 < conf <= 1.0
    none, conf = style_tags_from_sims(np.full(5, 0.0), tags)
    assert none == []
    assert conf > 0.9
    only_one, _ = style_tags_from_sims(np.array([0.3, 0.0, 0.0, 0.0, 0.0]), tags)
    assert only_one == ["casual"]


def test_subcategory_from_winning_prompt(clf: ZeroShotClassifier) -> None:
    prompts, embs = clf._category_prompts["bottom"]
    img = embs[prompts.index("chinos")]
    result = clf.classify(img)
    assert result.predictions["category"].value == "bottom"
    assert result.predictions["subcategory"].value == "chinos"


def test_prediction_shapes(clf: ZeroShotClassifier) -> None:
    result = clf.classify(_vec("random image"))
    assert set(result.predictions) == {
        "category",
        "subcategory",
        "pattern",
        "material",
        "formality",
        "style_tags",
    }
    assert isinstance(result.predictions["formality"].value, int)
    assert 1 <= result.predictions["formality"].value <= 5
    assert isinstance(result.predictions["style_tags"].value, list)


def test_text_embeddings_computed_once_at_construction() -> None:
    emb = FakeEmbedder()
    c = ZeroShotClassifier(emb)
    calls = emb.calls
    c.classify(_vec("q"))
    c.classify(_vec("r"))
    assert emb.calls == calls
    assert c.prompt_count > 0
