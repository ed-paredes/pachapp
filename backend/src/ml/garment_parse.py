"""Human parsing for garment-only cutouts (U5, 08-local-vision.md).

BiRefNet keeps every foreground object, so a worn garment comes out with the arms,
face and trousers attached. A human-parsing model labels each pixel (upper-clothes,
pants, face, ...); intersecting the garment's classes with the BiRefNet alpha leaves
only the garment.

Two layers, like `ml.background`:

- Pure helpers (class sets per app category, person test, mask intersection, erosion,
  small-mask fallback) work on numpy arrays / PIL images and are unit-tested with
  synthetic data (VIS-REQ-029).
- `GarmentParser` implementations load their weights lazily (never at import) and are
  device-aware. Callers MUST call `ml.cache.configure_model_cache` first (VIS-REQ-008)
  and run one inference at a time (VIS-REQ-025).

Class names are normalised to lower snake case (`Upper-clothes` -> `upper_clothes`);
the SegFormer ATR vocabulary comes from the model config, the U2Net-cloth one is
`upper` / `lower` / `full`.
"""

from __future__ import annotations

import gc
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

import numpy as np
from PIL import Image, ImageFilter

from ml.background import OPACITY_THRESHOLD

if TYPE_CHECKING:
    from shared.settings import Settings

logger = logging.getLogger(__name__)

SEGFORMER_B3_MODEL = "sayeed99/segformer_b3_clothes"
SEGFORMER_B2_MODEL = "mattmdjaga/segformer_b2_clothes"
U2NET_CLOTH_MODEL = "u2net_cloth_seg"

# Share of the image (default, tunable) below which the garment mask is considered
# unusable and the BiRefNet matte is kept as is (+ `needs_review`).
MIN_GARMENT_RATIO = 0.01
# Share of the image (default, tunable) that must be face/hair/limb pixels (or, for
# parsers without those classes, any clothing) for a person to count as present.
MIN_PERSON_RATIO = 0.02
# Erosion radius in pixels (default, tunable) applied before sampling colours, so
# the blurry matte edge does not leak skin / background tones into the palette.
COLOR_ERODE_PX = 4

BACKGROUND = "background"
PERSON_CLASSES = frozenset(
    {"hair", "face", "left_arm", "right_arm", "left_leg", "right_leg", "sunglasses"}
)
_SEGFORMER_CLOTHING = frozenset(
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
    }
)
_U2NET_CLOTHING = frozenset({"upper", "lower", "full"})

# App category (`shared.enums.GarmentCategory`) -> class names per parser vocabulary.
CATEGORY_CLASSES: dict[str, frozenset[str]] = {
    "top": frozenset({"upper_clothes", "upper"}),
    "mid_layer": frozenset({"upper_clothes", "upper"}),
    "outerwear": frozenset({"upper_clothes", "upper"}),
    "bottom": frozenset({"pants", "skirt", "lower"}),
    "one_piece": frozenset({"dress", "full"}),
    "shoes": frozenset({"left_shoe", "right_shoe"}),
    "accessory": frozenset({"bag", "scarf", "belt", "hat", "sunglasses"}),
}


def normalize_label(name: str) -> str:
    return name.strip().lower().replace("-", "_").replace(" ", "_")


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
        return {n for n in self.names.values() if n in _SEGFORMER_CLOTHING | _U2NET_CLOTHING}


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


def person_present(result: ParseResult, min_ratio: float = MIN_PERSON_RATIO) -> bool:
    """True when face/hair/arm/leg pixels cover at least `min_ratio` of the image.

    Parsers without person classes (U2Net-cloth) fall back to "any clothing".
    """
    total = result.labels.size
    if total == 0:
        return False
    present = PERSON_CLASSES & set(result.names.values())
    classes = present or result.clothing_names()
    return float(result.mask_for(classes).sum()) / total >= min_ratio


def largest_clothing_class(result: ParseResult) -> frozenset[str]:
    """The single clothing class covering the most pixels (empty if none)."""
    best: tuple[int, str] | None = None
    for class_id, name in result.names.items():
        if name not in _SEGFORMER_CLOTHING | _U2NET_CLOTHING:
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
    classes: frozenset[str]


def cut_garment(
    matte_rgba: Image.Image,
    result: ParseResult,
    category: str | None,
    *,
    min_ratio: float = MIN_GARMENT_RATIO,
) -> GarmentCutout:
    """Garment-only cutout: parser classes for `category` intersected with the matte.

    The ratio is measured on the intersection (garment pixels that BiRefNet also kept),
    so a parser hit outside the matte does not count. Below `min_ratio` the matte is
    returned unchanged with `fallback=True`.
    """
    classes = garment_classes(result, category)
    mask = result.mask_for(classes)
    matte_alpha = np.asarray(matte_rgba.getchannel("A")) > OPACITY_THRESHOLD
    ratio = mask_ratio(mask & matte_alpha)
    if ratio < min_ratio:
        return GarmentCutout(matte_rgba.convert("RGBA"), True, ratio, classes)
    return GarmentCutout(intersect_alpha(matte_rgba, mask), False, ratio, classes)


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
    """SegFormer clothes parser (18 ATR classes) from Hugging Face `transformers`.

    fp16 on CUDA only; logits are upsampled to the input size before the argmax.
    """

    def __init__(
        self,
        model_id: str,
        *,
        revision: str | None = None,
        device: str = "cpu",
        fp16: bool = True,
        short_name: str | None = None,
    ) -> None:
        self.model_id = model_id
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
        self._names = {int(i): normalize_label(n) for i, n in id2label.items()}
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
    """Parser for a method key: `segformer-b3`, `segformer-b2` or `u2net-cloth`."""
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
    raise ValueError(f"unknown parser {key!r}")
