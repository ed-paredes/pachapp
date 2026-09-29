"""Colour extraction from a garment cutout (03-garment-ingestion.md ING-REQ-010..014).

Pure numpy / scikit-learn / Pillow: no DB, no `ml`, no torch, so it is trivially
unit-testable with synthetic images.

Pipeline: opaque pixels (alpha > `ALPHA_THRESHOLD`) -> deterministic subsample ->
sRGB -> CIELAB (D65) -> KMeans (k=4, fixed seed) -> drop clusters < 10 % ->
name each cluster by the nearest palette entry (CIEDE2000) -> merge clusters that
share a name -> `Colors` (proportions descending, sum <= 1).

Defaults below are all tunable (ING-REQ-010/012/014 mark them "default, adjustable").

`color_confidence` formula (ING-REQ-014, monotonic; tune against real photos):

    Let the surviving clusters be grouped by palette name. For each pixel take its
    CIELAB distance (dE76) to the centroid of its group.

    w = sqrt(mean(d^2))                   RMS within-group spread (compactness)
    s = min pairwise centroid distance    between groups (separation; +inf if 1 group)

    compactness = 1 / (1 + (w / 20)^2)    1.0 for a flat colour, 0.5 at w = 20
    separation  = 1 - exp(-s / 25)        1.0 for a single group, ~0.63 at s = 25
    confidence  = compactness * separation, clamped to [0, 1]

Tight, well-separated groups therefore score higher than diffuse or nearly touching
ones. No opaque pixels at all -> confidence 0.0 and no colours.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from itertools import combinations

import numpy as np
from PIL import Image
from sklearn.cluster import KMeans

from shared.schemas import ColorEntry, Colors

# Alpha strictly above this counts as foreground (0-255). Same notion as
# `ml.background.OPACITY_THRESHOLD`, duplicated on purpose: this module must not import `ml`.
ALPHA_THRESHOLD = 10

KMEANS_K = 4
KMEANS_N_INIT = 10
KMEANS_SEED = 0
# ING-REQ-011: clusters below this share of the opaque pixels are dropped.
MIN_CLUSTER_PROPORTION = 0.10
# Deterministic stride subsampling keeps KMeans fast on large cutouts.
MAX_SAMPLE_PIXELS = 20_000

COMPACTNESS_SCALE = 20.0
SEPARATION_SCALE = 25.0

# ING-REQ-013.
NEUTRAL_NAMES = frozenset({"negro", "blanco", "gris", "beige", "camel", "marino", "denim"})

# Fixed palette (ING-REQ-012): Spanish name -> sRGB anchor.
PALETTE: dict[str, tuple[int, int, int]] = {
    "negro": (25, 25, 28),
    "blanco": (245, 245, 243),
    "gris": (128, 128, 128),
    "beige": (222, 205, 175),
    "camel": (193, 154, 107),  # tan
    "marino": (20, 30, 80),  # navy
    "denim": (65, 95, 145),  # mid indigo blue
    "marrón": (110, 70, 40),
    "rojo": (200, 30, 40),
    "burdeos": (110, 20, 40),  # burgundy
    "rosa": (240, 150, 180),
    "naranja": (240, 130, 30),
    "amarillo": (245, 210, 40),
    "verde": (40, 150, 70),
    "oliva": (110, 110, 40),  # olive
    "azul": (30, 90, 220),
    "celeste": (135, 200, 235),
    "morado": (120, 60, 160),
    "turquesa": (40, 190, 180),
    "caqui": (175, 165, 110),  # khaki
}

# D65 reference white for sRGB.
_WHITE_D65 = np.array([0.95047, 1.0, 1.08883])
_RGB_TO_XYZ = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ]
)


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """Convert sRGB values (0-255, shape `(..., 3)`) to CIELAB (D65)."""
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    linear = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = linear @ _RGB_TO_XYZ.T / _WHITE_D65
    eps, kappa = 216 / 24389, 24389 / 27
    f = np.where(xyz > eps, np.cbrt(xyz), (kappa * xyz + 16) / 116)
    return np.stack(
        [116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])],
        axis=-1,
    )


def ciede2000(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """CIEDE2000 colour difference (Sharma, Wu, Dalal 2005), broadcasting over `(..., 3)`."""
    lab1 = np.asarray(lab1, dtype=np.float64)
    lab2 = np.asarray(lab2, dtype=np.float64)
    l1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    l2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]

    c_bar = (np.hypot(a1, b1) + np.hypot(a2, b2)) / 2
    c_bar7 = c_bar**7
    g = 0.5 * (1 - np.sqrt(c_bar7 / (c_bar7 + 25.0**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360

    dlp = l2 - l1
    dcp = c2p - c1p
    zero_chroma = c1p * c2p == 0
    dh = h2p - h1p
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    dh = np.where(zero_chroma, 0.0, dh)
    dhp = 2 * np.sqrt(c1p * c2p) * np.sin(np.radians(dh / 2))

    l_bar = (l1 + l2) / 2
    c_bar_p = (c1p + c2p) / 2
    h_sum = h1p + h2p
    h_bar = np.where(
        zero_chroma,
        h_sum,
        np.where(
            np.abs(h1p - h2p) <= 180,
            h_sum / 2,
            np.where(h_sum < 360, (h_sum + 360) / 2, (h_sum - 360) / 2),
        ),
    )
    t = (
        1
        - 0.17 * np.cos(np.radians(h_bar - 30))
        + 0.24 * np.cos(np.radians(2 * h_bar))
        + 0.32 * np.cos(np.radians(3 * h_bar + 6))
        - 0.20 * np.cos(np.radians(4 * h_bar - 63))
    )
    d_theta = 30 * np.exp(-(((h_bar - 275) / 25) ** 2))
    c_bar_p7 = c_bar_p**7
    r_c = 2 * np.sqrt(c_bar_p7 / (c_bar_p7 + 25.0**7))
    s_l = 1 + 0.015 * (l_bar - 50) ** 2 / np.sqrt(20 + (l_bar - 50) ** 2)
    s_c = 1 + 0.045 * c_bar_p
    s_h = 1 + 0.015 * c_bar_p * t
    r_t = -np.sin(np.radians(2 * d_theta)) * r_c

    term_l = dlp / s_l
    term_c = dcp / s_c
    term_h = dhp / s_h
    return np.sqrt(term_l**2 + term_c**2 + term_h**2 + r_t * term_c * term_h)


_PALETTE_NAMES = tuple(PALETTE)
_PALETTE_LAB = srgb_to_lab(np.array(list(PALETTE.values())))


def nearest_palette_name(lab: np.ndarray) -> str:
    """Palette name with the smallest CIEDE2000 distance to `lab` (ING-REQ-012)."""
    distances = ciede2000(np.asarray(lab, dtype=np.float64)[None, :], _PALETTE_LAB)
    return _PALETTE_NAMES[int(np.argmin(distances))]


@dataclass(frozen=True)
class ColorResult:
    colors: Colors
    is_neutral: bool | None  # None when there is no colour to judge
    confidence: float  # [0, 1]


def _opaque_pixels(rgba: Image.Image) -> np.ndarray:
    arr = np.asarray(rgba.convert("RGBA"))
    return arr[arr[..., 3] > ALPHA_THRESHOLD][:, :3]


def _subsample(pixels: np.ndarray) -> np.ndarray:
    if len(pixels) <= MAX_SAMPLE_PIXELS:
        return pixels
    idx = np.linspace(0, len(pixels) - 1, MAX_SAMPLE_PIXELS).astype(np.int64)
    return pixels[idx]


def _hex(rgb: np.ndarray) -> str:
    r, g, b = (int(round(v)) for v in np.clip(rgb, 0, 255))
    return f"#{r:02x}{g:02x}{b:02x}"


def compute_confidence(lab: np.ndarray, group_ids: np.ndarray) -> float:
    """`color_confidence` from within-group spread and between-group separation."""
    if len(lab) == 0:
        return 0.0
    groups = np.unique(group_ids)
    centroids = np.stack([lab[group_ids == g].mean(axis=0) for g in groups])
    index = np.searchsorted(groups, group_ids)
    spread = float(np.sqrt(np.mean(np.sum((lab - centroids[index]) ** 2, axis=1))))
    compactness = 1.0 / (1.0 + (spread / COMPACTNESS_SCALE) ** 2)
    if len(groups) == 1:
        separation = 1.0
    else:
        nearest = min(float(np.linalg.norm(a - b)) for a, b in combinations(centroids, 2))
        separation = 1.0 - float(np.exp(-nearest / SEPARATION_SCALE))
    return float(min(1.0, max(0.0, compactness * separation)))


def extract_colors(rgba: Image.Image) -> ColorResult:
    """Dominant colours of `rgba` (ING-REQ-010..014). Never raises on empty input."""
    pixels = _subsample(_opaque_pixels(rgba))
    if len(pixels) == 0:
        return ColorResult(Colors(root=[]), None, 0.0)

    lab = srgb_to_lab(pixels)
    # Fewer distinct colours than k (e.g. a flat swatch): KMeans would warn and
    # return duplicate centres, so shrink k instead.
    k = min(KMEANS_K, len(np.unique(pixels, axis=0)))
    if k == 1:
        labels = np.zeros(len(lab), dtype=np.int64)
    else:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            labels = KMeans(
                n_clusters=k, n_init=KMEANS_N_INIT, random_state=KMEANS_SEED
            ).fit_predict(lab)

    total = len(lab)
    survivors = [
        c
        for c in np.unique(labels)
        if np.count_nonzero(labels == c) / total >= MIN_CLUSTER_PROPORTION
    ]
    if not survivors:  # unreachable with k <= 4, kept for safety
        return ColorResult(Colors(root=[]), None, 0.0)

    # Name each surviving cluster, then merge clusters with the same name.
    grouped: dict[str, list[np.ndarray]] = {}
    for c in survivors:
        mask = labels == c
        name = nearest_palette_name(lab[mask].mean(axis=0))
        grouped.setdefault(name, []).append(mask)

    entries: list[ColorEntry] = []
    group_ids = np.full(total, -1, dtype=np.int64)
    for gid, (name, masks) in enumerate(grouped.items()):
        mask = np.logical_or.reduce(masks)
        group_ids[mask] = gid
        centre = lab[mask].mean(axis=0)
        entries.append(
            ColorEntry(
                name=name,
                hex=_hex(pixels[mask].mean(axis=0)),
                lab=(
                    round(float(centre[0]), 2),
                    round(float(centre[1]), 2),
                    round(float(centre[2]), 2),
                ),
                proportion=float(np.count_nonzero(mask) / total),
            )
        )
    entries.sort(key=lambda e: e.proportion, reverse=True)

    kept = group_ids >= 0
    confidence = compute_confidence(lab[kept], group_ids[kept])
    return ColorResult(Colors(root=entries), entries[0].name in NEUTRAL_NAMES, confidence)
