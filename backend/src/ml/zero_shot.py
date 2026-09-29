"""Zero-shot attribute classification (08-local-vision.md, VIS-REQ-011..019).

No DB and no kNN yet (step 3): the final probability is `p = p_zs` (alpha = 1,
VIS-REQ-015). The math functions are pure numpy so they can be unit-tested with
synthetic embeddings (VIS-REQ-029); `ZeroShotClassifier` only needs an object
with `embed_texts` (the `GarmentEmbedder`, or a fake in tests).

Tunable defaults documented here:
- `needs_review_threshold = 0.7`: `setting.needs_review_threshold` default (02).
- `margin_threshold`: `settings.ml_margin_threshold` (0.15 default).
- `STYLE_SIGMOID_SCALE = 100`, `STYLE_SIGMOID_BIAS = 0.10`,
  `STYLE_TAG_THRESHOLD = 0.5`: per-tag probability is
  `sigmoid(scale * (cos_sim - bias))`, so with the defaults a tag is kept when
  its cosine similarity exceeds ~0.10. SigLIP image-text cosines are small
  (~0.05-0.25), hence the shifted sigmoid. VIS-REQ-018 leaves these open
  (calibrate empirically); `STYLE_MAX_TAGS = 3`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from ml.taxonomy import PROMPT_TEMPLATES, SUBCATEGORY_BY_PROMPT, TAXONOMY, expand_prompts
from shared.enums import ConfidenceSource
from shared.schemas import AttributeConfidence

LOGIT_SCALE = 100.0  # VIS-REQ-013
DEFAULT_NEEDS_REVIEW_THRESHOLD = 0.7
DEFAULT_MARGIN_THRESHOLD = 0.15
STYLE_SIGMOID_SCALE = 100.0
STYLE_SIGMOID_BIAS = 0.10
STYLE_TAG_THRESHOLD = 0.5
STYLE_MAX_TAGS = 3

# Single-label attributes checked by the low-confidence rule (VIS-REQ-016).
# `subcategory` (conditional on the chosen category, often near-tied between
# e.g. "a shirt"/"a t-shirt") and `style_tags` (multi-label) do not trigger it.
REVIEW_ATTRIBUTES = ("category", "pattern", "material", "formality")

# Subset of `REVIEW_ATTRIBUTES` that actually sets `needs_review` in iteration 1
# (user decision 2026-09-29, VIS-REQ-016): the literal rule flagged ~90 % of the
# public evaluation garments through `material`/`formality`, whose zero-shot
# probabilities are uncalibrated. Those two still report their low-confidence
# state (`ZeroShotResult.low_confidence`) but do not trigger review until kNN or
# calibration exists.
REVIEW_TRIGGER_ATTRIBUTES = ("category", "pattern")


class TextEmbedder(Protocol):
    def embed_texts(self, texts: list[str]) -> np.ndarray: ...


def l2_normalize(x: np.ndarray, axis: int = -1) -> np.ndarray:
    """L2-normalize along `axis` (float32); zero vectors stay zero."""
    x = np.asarray(x, dtype=np.float32)
    norm = np.linalg.norm(x, axis=axis, keepdims=True)
    return x / np.where(norm == 0, 1.0, norm)


def ensemble_embedding(text_embs: np.ndarray) -> np.ndarray:
    """Mean of the rows of `text_embs`, re-normalized (VIS-REQ-011)."""
    return l2_normalize(np.asarray(text_embs, dtype=np.float32).mean(axis=0))


def softmax_probs(img_emb: np.ndarray, label_embs: np.ndarray) -> np.ndarray:
    """VIS-REQ-013: softmax of `100 * (img_emb @ label_embs.T)`."""
    logits = LOGIT_SCALE * (label_embs @ img_emb)
    logits = logits - logits.max()
    exp = np.exp(logits)
    return exp / exp.sum()


def top_two(probs: np.ndarray) -> tuple[int, float, float]:
    """(index of top-1, top-1 probability, top-2 probability); top-2 is 0 when
    there is a single label."""
    order = np.argsort(probs)[::-1]
    top1 = float(probs[order[0]])
    top2 = float(probs[order[1]]) if len(order) > 1 else 0.0
    return int(order[0]), top1, top2


def is_low_confidence(
    probs: np.ndarray, needs_review_threshold: float, margin_threshold: float
) -> bool:
    """VIS-REQ-016: `top1 < needs_review_threshold or top1 - top2 < margin_threshold`."""
    _, top1, top2 = top_two(probs)
    return top1 < needs_review_threshold or (top1 - top2) < margin_threshold


def formality_from_probs(probs: np.ndarray, levels: list[int]) -> tuple[int, float]:
    """VIS-REQ-017: `(value, confidence)`.

    value = probability-weighted mean of `levels`, rounded half-up and clamped to
    [min(levels), max(levels)]. confidence = `1 - std / 2` where std is the
    probability-weighted standard deviation of the ordinal values,
    `sqrt(sum_i p_i * (v_i - mean)^2)`; for levels 1..5 std <= 2, so the
    confidence lies in [0, 1] (clipped defensively).
    """
    values = np.asarray(levels, dtype=np.float64)
    p = np.asarray(probs, dtype=np.float64)
    mean = float((p * values).sum())
    std = math.sqrt(max(0.0, float((p * (values - mean) ** 2).sum())))
    value = int(math.floor(mean + 0.5))
    value = max(min(levels), min(max(levels), value))
    return value, float(min(1.0, max(0.0, 1.0 - std / 2.0)))


def style_tags_from_sims(
    sims: np.ndarray,
    tags: list[str],
    *,
    scale: float = STYLE_SIGMOID_SCALE,
    bias: float = STYLE_SIGMOID_BIAS,
    threshold: float = STYLE_TAG_THRESHOLD,
    max_tags: int = STYLE_MAX_TAGS,
) -> tuple[list[str], float]:
    """VIS-REQ-018: per-tag sigmoid on image-text similarity.

    Returns `(selected tags by descending probability, confidence)`; confidence
    is the mean probability of the selected tags, or `1 - max(p)` when none
    passes the threshold (confident that nothing applies).
    """
    p = 1.0 / (1.0 + np.exp(-scale * (np.asarray(sims, dtype=np.float64) - bias)))
    order = [int(i) for i in np.argsort(p)[::-1] if p[i] >= threshold][:max_tags]
    if order:
        return [tags[i] for i in order], float(np.mean([p[i] for i in order]))
    return [], float(1.0 - p.max())


@dataclass
class ZeroShotResult:
    """Output of `ZeroShotClassifier.classify`; `predictions` values are the
    `garment.ai_confidence` shape (VIS-REQ-019), `source="zero_shot"`."""

    predictions: dict[str, AttributeConfidence]
    needs_review: bool  # True only when a `REVIEW_TRIGGER_ATTRIBUTES` member is low-confidence
    low_confidence: list[str] = field(default_factory=list)  # every low-confidence attribute


class ZeroShotClassifier:
    """Precomputes ensemble text embeddings once, at construction (VIS-REQ-011)."""

    def __init__(
        self,
        embedder: TextEmbedder,
        *,
        needs_review_threshold: float = DEFAULT_NEEDS_REVIEW_THRESHOLD,
        margin_threshold: float = DEFAULT_MARGIN_THRESHOLD,
        templates: list[str] | None = None,
    ) -> None:
        self.needs_review_threshold = needs_review_threshold
        self.margin_threshold = margin_threshold
        templates = PROMPT_TEMPLATES if templates is None else templates
        self.prompt_count = 0
        self._values: dict[str, list] = {}
        self._label_embs: dict[str, np.ndarray] = {}
        # category value -> (prompts, per-prompt ensemble embeddings)
        self._category_prompts: dict[str, tuple[list[str], np.ndarray]] = {}

        for attr, by_value in TAXONOMY.items():
            values = list(by_value)
            rows = []
            for value in values:
                prompts = by_value[value]
                texts = expand_prompts(prompts, templates)
                embs = np.asarray(embedder.embed_texts(texts), dtype=np.float32)
                self.prompt_count += len(texts)
                rows.append(ensemble_embedding(embs))
                if attr == "category":
                    per_prompt = embs.reshape(len(prompts), len(templates), -1)
                    self._category_prompts[value] = (
                        prompts,
                        np.stack([ensemble_embedding(g) for g in per_prompt]),
                    )
            self._values[attr] = values
            self._label_embs[attr] = np.stack(rows)

    def label_embeddings(self, attribute: str) -> np.ndarray:
        return self._label_embs[attribute]

    def classify(self, img_emb: np.ndarray) -> ZeroShotResult:
        img = l2_normalize(img_emb)
        preds: dict[str, AttributeConfidence] = {}
        low: list[str] = []

        def make(value: str | int | list[str], conf: float) -> AttributeConfidence:
            return AttributeConfidence(
                value=value,
                confidence=float(min(1.0, max(0.0, conf))),
                source=ConfidenceSource.zero_shot,
            )

        for attr in ("category", "pattern", "material"):
            probs = softmax_probs(img, self._label_embs[attr])
            idx, top1, _ = top_two(probs)
            preds[attr] = make(self._values[attr][idx], top1)
            if is_low_confidence(probs, self.needs_review_threshold, self.margin_threshold):
                low.append(attr)

        # Subcategory: winning prompt within the chosen category (VIS-REQ-012);
        # confidence = softmax probability among that category's prompts.
        category = str(preds["category"].value)
        prompts, prompt_embs = self._category_prompts[category]
        sub_probs = softmax_probs(img, prompt_embs)
        sub_idx, sub_top1, _ = top_two(sub_probs)
        preds["subcategory"] = make(SUBCATEGORY_BY_PROMPT[prompts[sub_idx]], sub_top1)

        f_probs = softmax_probs(img, self._label_embs["formality"])
        f_value, f_conf = formality_from_probs(f_probs, [int(v) for v in self._values["formality"]])
        preds["formality"] = make(f_value, f_conf)
        if f_conf < self.needs_review_threshold:
            low.append("formality")

        tags = self._values["style_tags"]
        sims = self._label_embs["style_tags"] @ img
        selected, tag_conf = style_tags_from_sims(sims, tags)
        preds["style_tags"] = make(selected, tag_conf)

        low = [a for a in REVIEW_ATTRIBUTES if a in low]
        needs_review = any(a in REVIEW_TRIGGER_ATTRIBUTES for a in low)
        return ZeroShotResult(predictions=preds, needs_review=needs_review, low_confidence=low)
