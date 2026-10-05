"""Human parsing for garment-only cutouts (U5, 08-local-vision.md).

BiRefNet keeps every foreground object, so a worn garment comes out with the arms,
face and trousers attached. A human-parsing model labels each pixel (upper-clothes,
pants, face, ...). Two ways to combine that map with the BiRefNet alpha:

- "intersect": keep only the garment's own classes (largest clothing region, or the
  category's class set) inside the matte. Precise, but a garment partly labelled as
  another class loses those parts.
- "subtract": start from the matte and remove only what is clearly not the garment
  (body/person classes, plus other garment groups when the category is known), then
  fill holes enclosed by what remains. Forgiving of mislabelled garment parts.

Two layers, like `ml.background`:

- Pure helpers (class sets per app category, person test, mask intersection, erosion,
  small-mask fallback) work on numpy arrays / PIL images and are unit-tested with
  synthetic data (VIS-REQ-029).
- `GarmentParser` implementations load their weights lazily (never at import) and are
  device-aware. Callers MUST call `ml.cache.configure_model_cache` first (VIS-REQ-008)
  and run one inference at a time (VIS-REQ-025).

Class names are normalised to lower snake case (`Upper-clothes` -> `upper_clothes`)
into one shared vocabulary: the SegFormer/SCHP ATR names come from the model config,
FASHN's `top`/`glasses` are aliased to `upper_clothes`/`sunglasses` (its `arms`,
`legs`, `hands`, `feet`, `torso`, `jewelry` stay as they are), SCHP-LIP adds `coat`,
`jumpsuits`, `socks`, `glove`, and U2Net-cloth is `upper` / `lower` / `full`.
"""

from __future__ import annotations

import gc
import logging
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any, Protocol

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

from ml.background import OPACITY_THRESHOLD

if TYPE_CHECKING:
    from shared.settings import Settings

logger = logging.getLogger(__name__)

SEGFORMER_B3_MODEL = "sayeed99/segformer_b3_clothes"
SEGFORMER_B2_MODEL = "mattmdjaga/segformer_b2_clothes"
FASHN_MODEL = "fashn-ai/fashn-human-parser"
U2NET_CLOTH_MODEL = "u2net_cloth_seg"

MASK_MODES = ("intersect", "subtract")

# Share of the image (default, tunable) below which the garment mask is considered
# unusable and the BiRefNet matte is kept as is (+ `needs_review`).
MIN_GARMENT_RATIO = 0.01
# A person counts as present only with real body evidence (see `person_present`):
# face pixels >= MIN_FACE_RATIO of the image, or arm/hand/leg pixels >= MIN_PERSON_RATIO.
# Hair and any skin-like class alone are not enough (round 1 of U5b: flat-lay sandals and
# skin-toned insoles were "persons"). Both values are defaults, tunable.
MIN_FACE_RATIO = 0.005
MIN_PERSON_RATIO = 0.05
# Erosion radius in pixels (default, tunable) applied before sampling colours, so
# the blurry matte edge does not leak skin / background tones into the palette.
COLOR_ERODE_PX = 4

BACKGROUND = "background"
# Body / person pixels (never part of a garment). Includes the FASHN-only region names.
BODY_CLASSES = frozenset(
    {
        "hair",
        "face",
        "left_arm",
        "right_arm",
        "left_leg",
        "right_leg",
        "arms",
        "legs",
        "hands",
        "torso",
        "neck",
        "sunglasses",
        "jewelry",
    }
)
FACE_CLASSES = frozenset({"face"})
LIMB_CLASSES = frozenset(
    {"left_arm", "right_arm", "left_leg", "right_leg", "arms", "legs", "hands"}
)
# FASHN label -> shared vocabulary (everything else keeps its own normalised name).
FASHN_ALIASES = {"top": "upper_clothes", "glasses": "sunglasses"}
# Clothing / carried-item class names of the ATR-style vocabularies (SegFormer b2/b3, FASHN
# after aliasing, SCHP). `CLOTHING_CLASSES` adds U2Net-cloth's three coarse classes.
_ATR_CLOTHING = frozenset(
    {
        "hat",
        "upper_clothes",
        "skirt",
        "pants",
        "dress",
        "belt",
        "left_shoe",
        "right_shoe",
        "bag",
        "scarf",
        # SCHP-LIP extras
        "coat",
        "jumpsuits",
        "socks",
        "glove",
    }
)
_U2NET_CLOTHING = frozenset({"upper", "lower", "full"})
CLOTHING_CLASSES = _ATR_CLOTHING | _U2NET_CLOTHING

# App category (`shared.enums.GarmentCategory`) -> class names per parser vocabulary.
CATEGORY_CLASSES: dict[str, frozenset[str]] = {
    "top": frozenset({"upper_clothes", "upper"}),
    "mid_layer": frozenset({"upper_clothes", "coat", "upper"}),
    "outerwear": frozenset({"upper_clothes", "coat", "upper"}),
    "bottom": frozenset({"pants", "skirt", "lower"}),
    "one_piece": frozenset({"dress", "jumpsuits", "full"}),
    # FASHN has no shoe class; its `feet` region is the closest thing.
    "shoes": frozenset({"left_shoe", "right_shoe", "feet"}),
    "accessory": frozenset({"bag", "scarf", "belt", "hat", "sunglasses", "glove"}),
}

# Subtract mode, category known: clearly-other garment groups removed on top of the body.
_UPPER_GROUP = frozenset({"upper_clothes", "coat", "upper"})
_LOWER_GROUP = frozenset({"pants", "skirt", "lower"})
_FOOTWEAR = frozenset({"left_shoe", "right_shoe", "feet", "socks"})
_CARRIED = frozenset({"hat", "bag", "scarf"})
_UPPER_CATEGORIES = frozenset({"top", "mid_layer", "outerwear"})
OTHER_GARMENT_CLASSES: dict[str, frozenset[str]] = {
    **{c: _LOWER_GROUP | _FOOTWEAR | _CARRIED | {"belt"} for c in _UPPER_CATEGORIES},
    "bottom": _UPPER_GROUP | _FOOTWEAR | _CARRIED,
    "one_piece": _FOOTWEAR | {"hat", "bag"},
}


def normalize_label(name: str, aliases: dict[str, str] | None = None) -> str:
    """Lower snake case, then mapped through `aliases` (parser-specific renames)."""
    normalized = name.strip().lower().replace("-", "_").replace(" ", "_")
    return (aliases or {}).get(normalized, normalized)


@dataclass
class ParseResult:
    """Per-pixel class ids (H x W, uint8) and the id -> normalised name vocabulary."""

    labels: np.ndarray
    names: dict[int, str]

    def mask_for(self, classes: frozenset[str] | set[str]) -> np.ndarray:
        """Boolean (H x W) mask of the pixels labelled with any of `classes`."""
        ids = [i for i, n in self.names.items() if n in classes]
        return np.isin(self.labels, ids) if ids else np.zeros(self.labels.shape, dtype=bool)

    def clothing_names(self) -> set[str]:
        return {n for n in self.names.values() if n in CLOTHING_CLASSES}


class GarmentParser(Protocol):
    name: str
    revision: str | None  # resolved model revision, for the report

    def parse(self, rgb: Image.Image) -> ParseResult:
        """Label every pixel of an RGB image (labels at the image's own size)."""
        ...

    def close(self) -> None:
        """Release weights and GPU memory."""
        ...


# --- pure helpers -------------------------------------------------------------------


def person_present(
    result: ParseResult,
    min_ratio: float = MIN_PERSON_RATIO,
    min_face_ratio: float = MIN_FACE_RATIO,
) -> bool:
    """True when the parse shows real body evidence: face pixels cover at least
    `min_face_ratio` of the image, or arm/hand/leg pixels cover at least `min_ratio`.

    Hair, torso, neck, jewelry and sunglasses never count on their own, so a flat-lay
    product photo (sandals, insoles, a dark garment labelled as hair) is not a person.
    Parsers without person classes (U2Net-cloth) fall back to "any clothing" at
    `min_ratio`.
    """
    total = result.labels.size
    if total == 0:
        return False
    names = set(result.names.values())
    if not (FACE_CLASSES | LIMB_CLASSES) & names:
        return float(result.mask_for(result.clothing_names()).sum()) / total >= min_ratio
    face = float(result.mask_for(FACE_CLASSES).sum()) / total
    limbs = float(result.mask_for(LIMB_CLASSES).sum()) / total
    return face >= min_face_ratio or limbs >= min_ratio


def largest_clothing_class(result: ParseResult) -> frozenset[str]:
    """The single clothing class covering the most pixels (empty if none)."""
    best: tuple[int, str] | None = None
    for class_id, name in result.names.items():
        if name not in CLOTHING_CLASSES:
            continue
        count = int((result.labels == class_id).sum())
        if count > 0 and (best is None or count > best[0]):
            best = (count, name)
    return frozenset() if best is None else frozenset({best[1]})


def garment_classes(result: ParseResult, category: str | None) -> frozenset[str]:
    """Class set to keep for `category`; the largest clothing region when the
    category is unknown (not yet classified) or has no class in this vocabulary."""
    wanted = CATEGORY_CLASSES.get(category or "", frozenset()) & set(result.names.values())
    if wanted:
        return wanted
    return largest_clothing_class(result)


def garment_mask(result: ParseResult, category: str | None) -> np.ndarray:
    """Boolean mask of the garment's parser classes."""
    return result.mask_for(garment_classes(result, category))


def mask_ratio(mask: np.ndarray) -> float:
    return float(mask.sum()) / mask.size if mask.size else 0.0


def intersect_alpha(rgba: Image.Image, mask: np.ndarray) -> Image.Image:
    """RGBA with alpha = original alpha where `mask` holds, else 0 (same size)."""
    if mask.shape != (rgba.height, rgba.width):
        raise ValueError(f"mask {mask.shape} does not match image {(rgba.height, rgba.width)}")
    out = np.array(rgba.convert("RGBA"))
    out[..., 3] = np.where(mask, out[..., 3], 0)
    return Image.fromarray(out, mode="RGBA")


def erode_alpha(rgba: Image.Image, radius: int = COLOR_ERODE_PX) -> Image.Image:
    """Copy of `rgba` whose opaque region is eroded by `radius` pixels (colour sampling)."""
    rgba = rgba.convert("RGBA")
    if radius <= 0:
        return rgba
    binary = rgba.getchannel("A").point(lambda a: 255 if a > OPACITY_THRESHOLD else 0)
    eroded = binary.filter(ImageFilter.MinFilter(2 * radius + 1))
    out = rgba.copy()
    out.putalpha(eroded)
    return out


@dataclass
class GarmentCutout:
    rgba: Image.Image  # full-size, alpha restricted to the garment (or the matte on fallback)
    fallback: bool  # garment mask too small -> matte kept, caller flags `needs_review`
    garment_ratio: float
    classes: frozenset[str]  # classes kept ("intersect") or removed ("subtract")
    mode: str = "intersect"
    review: bool = False  # a worn/carried item may have been unselected -> `needs_review`


def removed_classes(
    result: ParseResult, category: str | None, *, body_only: bool = False
) -> frozenset[str]:
    """Classes subtract mode removes from the matte, in this parser's vocabulary.

    Always the body/person classes; with a known category also the clearly-other garment
    groups (see `OTHER_GARMENT_CLASSES`). `shoes` is the exception: only shoes are kept,
    so every other labelled class is removed. `body_only` removes just the body classes
    whatever the category (the worker's rule for footwear and accessories).
    """
    present = set(result.names.values()) - {BACKGROUND}
    if body_only:
        return frozenset(BODY_CLASSES & present)
    if category == "shoes":
        return frozenset(present - CATEGORY_CLASSES["shoes"])
    removed = BODY_CLASSES | OTHER_GARMENT_CLASSES.get(category or "", frozenset())
    return frozenset(removed & present)


def subtract_garment(
    matte_alpha: np.ndarray, removed: np.ndarray, *, opacity: int = OPACITY_THRESHOLD
) -> tuple[np.ndarray, np.ndarray]:
    """Alpha (uint8) of the matte minus `removed`, with enclosed holes filled.

    A hole is a region fully surrounded by the remaining garment (a matte gap, an
    unlabelled patch, a mislabelled garment part that is not body). Pixels that were
    removed as body/other-garment stay removed. Returns (new alpha, kept mask).
    """
    remaining = (matte_alpha > opacity) & ~removed
    holes = ndimage.binary_fill_holes(remaining) & ~remaining & ~removed
    alpha = np.where(removed, 0, matte_alpha).astype(np.uint8)
    alpha[holes & (alpha <= opacity)] = 255
    return alpha, remaining | holes


def fill_garment_holes(
    mask: np.ndarray, matte_alpha: np.ndarray, body: np.ndarray, *, opacity: int = OPACITY_THRESHOLD
) -> np.ndarray:
    """`mask` plus the matte pixels fully enclosed by it that are not body (a part of the
    garment labelled as a sibling class, e.g. a pocket or a stripe)."""
    holes = ndimage.binary_fill_holes(mask) & ~mask & (matte_alpha > opacity) & ~body
    return mask | holes


# Categories cut by removing only the body (FASHN has no shoe class and accessories are
# too small and varied for a class group); every other category intersects with its group.
SUBTRACT_CATEGORIES = frozenset({"shoes", "accessory"})


# Unknown category: a footwear / bag / accessory group the largest-clothing rule did not
# select but that covers at least this share of the matte is kept (subtract, body only) and
# flagged for review instead of being cut away silently.
MIN_UNSELECTED_ITEM_RATIO = 0.10
_FOOTWEAR_ITEMS = CATEGORY_CLASSES["shoes"]
_CARRIED_ITEMS = CATEGORY_CLASSES["accessory"] - BODY_CLASSES


def _group_pixels(result: ParseResult, classes: frozenset[str], matte: np.ndarray) -> int:
    return int((result.mask_for(classes) & matte).sum())


def _cut_unknown_category(
    matte_rgba: Image.Image, result: ParseResult, min_ratio: float
) -> GarmentCutout:
    """Category not classified yet: pick the largest of the clothing, footwear and
    carried-item groups; items are cut by subtracting the body, and an item group that
    lost to clothing but is substantial is kept too, with `review` set."""
    matte = np.asarray(matte_rgba.getchannel("A")) > OPACITY_THRESHOLD
    garments = CLOTHING_CLASSES - _FOOTWEAR_ITEMS - _CARRIED_ITEMS
    counts = {n: int((result.labels == i).sum()) for i, n in result.names.items() if n in garments}
    clothing_px = max(counts.values(), default=0)
    top_item = max(
        _group_pixels(result, group, matte) for group in (_FOOTWEAR_ITEMS, _CARRIED_ITEMS)
    )
    subtract = partial(
        cut_garment, matte_rgba, result, None, mode="subtract", min_ratio=min_ratio, body_only=True
    )
    if top_item > clothing_px:
        return subtract()
    if top_item >= MIN_UNSELECTED_ITEM_RATIO * max(int(matte.sum()), 1):
        cut = subtract()
        cut.review = not cut.fallback
        return cut
    return cut_garment(
        matte_rgba, result, None, mode="intersect", min_ratio=min_ratio, fill_holes=True
    )


def cut_garment_by_rule(
    matte_rgba: Image.Image,
    result: ParseResult,
    category: str | None,
    *,
    min_ratio: float = MIN_GARMENT_RATIO,
) -> GarmentCutout:
    """The worker's cutout rule (owner decision 2026-10-05), for a photo with a person:

    - footwear / accessories: "subtract" body only;
    - clothing: "intersect" with the category's class group, holes filled;
    - category unknown (not classified yet): the largest of the clothing, footwear and
      carried-item groups; items subtract the body, clothing intersects with the largest
      clothing region (holes filled) unless a substantial item group would be lost
      (`MIN_UNSELECTED_ITEM_RATIO`), which keeps it and sets `review`.

    Falls back to the unchanged matte (`fallback=True`) when the garment mask is too small.
    """
    if category in SUBTRACT_CATEGORIES:
        return cut_garment(
            matte_rgba, result, category, mode="subtract", min_ratio=min_ratio, body_only=True
        )
    if category is None:
        return _cut_unknown_category(matte_rgba, result, min_ratio)
    return cut_garment(
        matte_rgba, result, category, mode="intersect", min_ratio=min_ratio, fill_holes=True
    )


def cut_garment(
    matte_rgba: Image.Image,
    result: ParseResult,
    category: str | None,
    *,
    mode: str = "intersect",
    min_ratio: float = MIN_GARMENT_RATIO,
    fill_holes: bool = False,
    body_only: bool = False,
) -> GarmentCutout:
    """Garment-only cutout of the matte, by `mode` (`MASK_MODES`).

    "intersect": parser classes for `category` intersected with the matte. "subtract":
    the matte minus body (and other-garment) classes, enclosed holes filled; for
    `shoes` it keeps only shoe pixels. The ratio is measured on the pixels kept (inside
    the matte for "intersect"), so a parser hit outside the matte does not count. Below
    `min_ratio` the matte is returned unchanged with `fallback=True`. `fill_holes` (intersect
    only) also keeps matte pixels fully enclosed by the garment mask that are not body, so a
    garment labelled across sibling classes stays whole; `body_only` (subtract only) removes
    just the body classes.
    """
    if mode not in MASK_MODES:
        raise ValueError(f"unknown mask mode {mode!r}; choose from {MASK_MODES}")
    matte_alpha = np.asarray(matte_rgba.getchannel("A"))
    if mode == "intersect":
        classes = garment_classes(result, category)
        mask = result.mask_for(classes)
        if fill_holes:
            mask = fill_garment_holes(mask, matte_alpha, result.mask_for(BODY_CLASSES))
        ratio = mask_ratio(mask & (matte_alpha > OPACITY_THRESHOLD))
        if ratio >= min_ratio:
            return GarmentCutout(intersect_alpha(matte_rgba, mask), False, ratio, classes, mode)
    else:
        classes = removed_classes(result, category, body_only=body_only)
        alpha, kept = subtract_garment(matte_alpha, result.mask_for(classes))
        ratio = mask_ratio(kept)
        if ratio >= min_ratio:
            out = matte_rgba.convert("RGBA")
            out.putalpha(Image.fromarray(alpha, mode="L"))
            return GarmentCutout(out, False, ratio, classes, mode)
    return GarmentCutout(matte_rgba.convert("RGBA"), True, ratio, classes, mode)


# --- implementations (lazy, not loaded in tests) -------------------------------------


def _free_gpu() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:  # pragma: no cover
        pass


class SegformerClothesParser:
    """SegFormer-family parser from Hugging Face `transformers` (ATR b2/b3, FASHN B4).

    The image processor comes from the repo, so each model keeps its own input size and
    normalisation (FASHN: 384x576). fp16 on CUDA only; logits are upsampled to the input
    size before the argmax.
    """

    def __init__(
        self,
        model_id: str,
        *,
        revision: str | None = None,
        device: str = "cpu",
        fp16: bool = True,
        short_name: str | None = None,
        aliases: dict[str, str] | None = None,
    ) -> None:
        self.model_id = model_id
        self.aliases = aliases
        self.revision = revision
        self.device = device
        self.fp16 = fp16 and device == "cuda"
        self.name = short_name or model_id
        self._model: Any = None
        self._processor: Any = None
        self._names: dict[int, str] = {}

    def _load(self) -> None:
        if self._model is not None:
            return
        from transformers import AutoImageProcessor, SegformerForSemanticSegmentation

        pin = self.revision or "main"  # unpinned eval runs record the loaded commit below
        logger.info("Loading %s (revision=%s) on %s", self.model_id, pin, self.device)
        self._processor = AutoImageProcessor.from_pretrained(self.model_id, revision=pin)
        model: Any = SegformerForSemanticSegmentation.from_pretrained(self.model_id, revision=pin)
        id2label: dict[Any, str] = model.config.id2label
        self._names = {int(i): normalize_label(n, self.aliases) for i, n in id2label.items()}
        if self.fp16:
            model = model.half()
        self._model = model.to(self.device).eval()
        if self.revision is None:  # report what was actually loaded
            self.revision = getattr(model.config, "_commit_hash", None)

    def parse(self, rgb: Image.Image) -> ParseResult:  # pragma: no cover - needs weights
        import torch
        import torch.nn.functional as functional

        self._load()
        inputs = self._processor(images=rgb, return_tensors="pt")
        pixel_values = inputs["pixel_values"].to(self.device)
        if self.fp16:
            pixel_values = pixel_values.half()
        with torch.no_grad():
            logits = self._model(pixel_values=pixel_values).logits
            logits = functional.interpolate(
                logits.float(), size=(rgb.height, rgb.width), mode="bilinear", align_corners=False
            )
            labels = logits.argmax(dim=1)[0].to("cpu").numpy().astype(np.uint8)
        return ParseResult(labels, dict(self._names))

    def close(self) -> None:
        self._model = None
        self._processor = None
        _free_gpu()


class U2NetClothParser:
    """rembg `u2net_cloth_seg`: upper / lower / full-body clothing masks (onnxruntime)."""

    name = "u2net-cloth"
    revision: str | None = None  # rembg downloads a fixed, checksummed file

    def __init__(self, *, device: str = "cpu") -> None:
        self.device = device
        self._session: Any = None

    def _load(self) -> Any:
        if self._session is None:
            from rembg import new_session

            from ml.device import check_session_providers, onnxruntime_providers

            session = new_session(U2NET_CLOTH_MODEL, providers=onnxruntime_providers(self.device))
            check_session_providers(self.device, session.inner_session.get_providers())
            self._session = session
        return self._session

    def parse(self, rgb: Image.Image) -> ParseResult:  # pragma: no cover - needs weights
        session = self._load()
        upper, lower, full = session.predict(rgb)
        labels = np.zeros((rgb.height, rgb.width), dtype=np.uint8)
        for class_id, mask in ((3, full), (2, lower), (1, upper)):
            labels[np.asarray(mask) > 127] = class_id
        return ParseResult(labels, {0: BACKGROUND, 1: "upper", 2: "lower", 3: "full"})

    def close(self) -> None:
        self._session = None
        _free_gpu()


def build_parser(key: str, settings: Settings, device: str) -> GarmentParser:
    """Parser for a method key: `segformer-b3`, `segformer-b2`, `u2net-cloth`, `fashn`,
    `schp-atr` or `schp-lip`."""
    if key == "segformer-b3":
        return SegformerClothesParser(
            SEGFORMER_B3_MODEL,
            revision=settings.ml_parse_b3_revision,
            device=device,
            short_name=key,
        )
    if key == "segformer-b2":
        return SegformerClothesParser(
            SEGFORMER_B2_MODEL,
            revision=settings.ml_parse_b2_revision,
            device=device,
            short_name=key,
        )
    if key == "u2net-cloth":
        return U2NetClothParser(device=device)
    if key == "fashn":
        return SegformerClothesParser(
            FASHN_MODEL,
            revision=settings.ml_parse_fashn_revision,
            device=device,
            short_name=key,
            aliases=FASHN_ALIASES,
        )
    if key in ("schp-atr", "schp-lip"):
        from ml.schp import SchpParser  # imports torch: only when this parser is used

        return SchpParser(
            key.removeprefix("schp-"), revision=settings.ml_parse_schp_revision, device=device
        )
    raise ValueError(f"unknown parser {key!r}")
