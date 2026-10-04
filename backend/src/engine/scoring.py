"""Vectorised hard filters and score components over sets of garments.

A "set" is a row of an `(N, M)` integer matrix of garment indices, padded with
-1, so one call scores every candidate of a stage at once (D1). The scalar
reading of each formula is in docs/specs/05-outfit-engine.md.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from engine import constants as C
from engine.context import (
    CH_COSINE,
    CH_COSINE_OK,
    CH_JACCARD,
    CH_JACCARD_OK,
    CH_PREFERENCE,
    CH_WORN_TOGETHER,
    Context,
)

Array = NDArray[Any]

_BIG = 1 << 14  # above any colour id (int16)


class SetView:
    """A batch of garment sets (`(N, M)` indices, -1 padded) with the lookups
    the filters and the scores share computed once."""

    def __init__(self, ctx: Context, idx: Array) -> None:
        self.ctx = ctx
        self.idx = idx
        self.present = idx >= 0
        self.safe = np.maximum(idx, 0)
        keys = np.sort(np.where(self.present, ctx.ckey[self.safe], 0), axis=1)
        # distinct non-neutral clothing colours, and the lowest / highest id
        self.color_count = (keys[:, :1] > 0).sum(axis=1) + (
            (keys[:, 1:] > 0) & (keys[:, 1:] != keys[:, :-1])
        ).sum(axis=1)
        lowest = np.where(keys > 0, keys, _BIG).min(axis=1)
        self.color_lo = np.where(lowest == _BIG, 0, lowest)
        self.color_hi = keys[:, -1]

    def subset(self, mask: Array) -> SetView:
        view = object.__new__(SetView)
        view.ctx = self.ctx
        for name in ("idx", "present", "safe", "color_count", "color_lo", "color_hi"):
            setattr(view, name, getattr(self, name)[mask])
        return view


def valid_mask(view: SetView) -> Array:
    """ENG-REQ-003 (formality spread), ENG-REQ-007 (<= 2 non-neutral colours
    among clothing) and ENG-REQ-008 (no two accessories of one subtype)."""
    ctx, present, safe = view.ctx, view.present, view.safe
    f = ctx.formality[safe]
    spread = np.where(present, f, -np.inf).max(axis=1) - np.where(present, f, np.inf).min(axis=1)
    ok = (spread <= C.MAX_FORMALITY_SPREAD + 1e-9) & (view.color_count <= C.MAX_NON_NEUTRAL_COLORS)
    sub = np.sort(np.where(present, ctx.subcat[safe], -1), axis=1)
    ok &= ~((sub[:, 1:] >= 0) & (sub[:, 1:] == sub[:, :-1])).any(axis=1)
    return ok


def _hue_level(delta: Array) -> Array:
    return np.where(
        delta <= C.HUE_ANALOGOUS_MAX_DEG,
        C.HUE_SCORE_ANALOGOUS,
        np.where(
            delta >= C.HUE_COMPLEMENTARY_MIN_DEG, C.HUE_SCORE_COMPLEMENTARY, C.HUE_SCORE_OTHER
        ),
    )


def color_score(view: SetView) -> Array:
    ctx = view.ctx
    # The hue of a colour is that of the first garment in the set wearing it.
    keys = np.where(view.present, ctx.ckey[view.safe], 0)
    rows = np.arange(len(keys))
    hue_lo = ctx.ghue[view.safe[rows, (keys == view.color_lo[:, None]).argmax(axis=1)]]
    hue_hi = ctx.ghue[view.safe[rows, (keys == view.color_hi[:, None]).argmax(axis=1)]]
    delta = np.abs(hue_lo - hue_hi)
    delta = np.minimum(delta, 360.0 - delta)
    base = np.where(view.color_count <= 1, C.COLOR_SCORE_FEW_COLORS, _hue_level(delta))
    loud = (ctx.loud[view.safe] & view.present).sum(axis=1)
    penalty = np.where(loud >= C.LOUD_PATTERN_MIN_COUNT, C.LOUD_PATTERN_PENALTY, 0.0)
    return np.clip(base - penalty, 0.0, 1.0)


def components(view: SetView) -> Array:
    """`(N, 4)` array: color, style, novelty, preference, each in [0, 1]."""
    ctx, present, safe = view.ctx, view.present, view.safe
    n_rows, width = present.shape
    size = present.sum(axis=1).astype(float)

    # Pair channels summed over every present pair of the set.
    n = len(ctx.garments)
    flat = ctx.pair.reshape(n * n, -1)
    totals = np.zeros((n_rows, flat.shape[1]))
    for a in range(width):
        for b in range(a + 1, width):
            both = (present[:, a] & present[:, b])[:, None]
            totals += np.take(flat, safe[:, a] * n + safe[:, b], axis=0) * both

    # C_style: mean of the available terms (formality variance, tag Jaccard,
    # embedding cosine). A term with no usable pair is skipped.
    f = ctx.formality[safe]
    mean_f = (f * present).sum(axis=1) / size
    var_f = (((f - mean_f[:, None]) ** 2) * present).sum(axis=1) / size
    terms = [1.0 - np.clip(var_f / C.FORMALITY_VARIANCE_NORM, 0.0, 1.0)]
    have = [np.ones(n_rows)]
    for value, ok in ((CH_JACCARD, CH_JACCARD_OK), (CH_COSINE, CH_COSINE_OK)):
        pairs = totals[:, ok]
        usable = pairs > 0
        terms.append(np.where(usable, totals[:, value] / np.where(usable, pairs, 1.0), 0.0))
        have.append(usable.astype(float))
    style = sum(t * h for t, h in zip(terms, have, strict=True)) / sum(have)

    # C_novelty: mean per-garment novelty - pair penalty + capped forgotten bonus.
    novelty = (ctx.item_novelty[safe] * present).sum(axis=1) / size
    novelty -= np.where(totals[:, CH_WORN_TOGETHER] > 0, C.PAIR_PENALTY, 0.0)
    bonus = (ctx.forgotten[safe] * present).sum(axis=1) * C.FORGOTTEN_BONUS
    novelty = np.clip(novelty + np.minimum(bonus, C.FORGOTTEN_BONUS_CAP), 0.0, 1.0)

    # C_preference: 0.5 with no feedback, tanh of the net liked-minus-disliked.
    preference = C.PREFERENCE_NEUTRAL + 0.5 * np.tanh(
        totals[:, CH_PREFERENCE] / C.PREFERENCE_TANH_SCALE
    )

    return np.stack([color_score(view), style, novelty, preference], axis=1)


def total_score(ctx: Context, comps: Array) -> Array:
    """S = w_color*C_color + w_style*C_style + w_novelty*C_novelty + w_pref*C_pref."""
    return comps @ ctx.weights
