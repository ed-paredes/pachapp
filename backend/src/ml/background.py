"""Background removal (BiRefNet via `rembg`), 08-local-vision.md step 2.

`BiRefNetRemover.remove` returns an RGBA image cropped to the foreground
bounding box (03-garment-ingestion.md `cutout` step, ING-REQ-009). The pure
helpers (`alpha_coverage`, `crop_to_foreground`) are torch-free so they can be
unit-tested with synthetic PIL images (VIS-REQ-029).

Near-empty mask contract (ING-SCN-005): when the model finds (almost) no
foreground, `remove` raises `EmptyCutoutError` instead of returning a useless
crop. The worker's `cutout` step (plan step 4) MUST catch it and apply the
soft failure: fall back to the full preprocessed image as `img_cutout`, set
`needs_review=true`, and continue the pipeline rather than failing the job.

Callers MUST call `ml.cache.configure_model_cache` before the first `remove`
(VIS-REQ-008); the session comes from `ml.registry.get_background_remover`
(process-wide, lazy, VIS-REQ-004). `rembg` is imported inside `remove`.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Any, Protocol

from PIL import Image, ImageOps

from ml import registry
from ml.pipeline import run_pipeline
from shared.settings import Settings

logger = logging.getLogger(__name__)

# Alpha values strictly above this count as foreground, on the 0-255 scale
# (default, tunable). Matches the "opaque pixel" notion of ING-REQ-010.
OPACITY_THRESHOLD = 10

# Minimum fraction of pixels that must be foreground for a cutout to be
# considered usable: 0.5% of the image (default, tunable). Below this the mask
# is treated as empty (ING-SCN-005).
MIN_COVERAGE = 0.005


class EmptyCutoutError(Exception):
    """The background remover produced a near-empty mask (ING-SCN-005)."""

    def __init__(self, coverage: float, min_coverage: float = MIN_COVERAGE) -> None:
        self.coverage = coverage
        self.min_coverage = min_coverage
        super().__init__(
            f"Cutout mask is near-empty: foreground coverage {coverage:.4%} "
            f"is below the minimum {min_coverage:.4%}"
        )


# BiRefNet input normalization and size, as in rembg's `BiRefNetSessionGeneral.predict`.
_BIREFNET_MEAN = (0.485, 0.456, 0.406)
_BIREFNET_STD = (0.229, 0.224, 0.225)
_BIREFNET_SIZE = (1024, 1024)


class BackgroundRemover(Protocol):
    def remove(self, img: Image.Image) -> Image.Image:
        """Return an RGBA image cropped to the foreground bbox."""
        ...


def _foreground_mask(rgba: Image.Image, threshold: int) -> Image.Image:
    """Binary ("L", 0/255) mask of pixels whose alpha is above `threshold`."""
    return rgba.getchannel("A").point(lambda a: 255 if a > threshold else 0)


def alpha_coverage(rgba: Image.Image, threshold: int = OPACITY_THRESHOLD) -> float:
    """Fraction (0..1) of pixels whose alpha is strictly above `threshold`."""
    rgba = rgba.convert("RGBA")
    total = rgba.width * rgba.height
    if total == 0:
        return 0.0
    histogram = rgba.getchannel("A").histogram()
    opaque = sum(histogram[threshold + 1 :])
    return opaque / total


def crop_to_foreground(rgba: Image.Image, threshold: int = OPACITY_THRESHOLD) -> Image.Image:
    """Crop to the bbox of pixels with alpha above `threshold`.

    Raises `EmptyCutoutError` (coverage 0) if no pixel qualifies.
    """
    rgba = rgba.convert("RGBA")
    bbox = _foreground_mask(rgba, threshold).getbbox()
    if bbox is None:
        raise EmptyCutoutError(0.0)
    return rgba.crop(bbox)


def _to_rgb(img: Image.Image) -> Image.Image:
    """Normalize any PIL image to RGB: apply EXIF orientation if present and
    composite transparency (RGBA/LA/P with transparency) over white."""
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(background, rgba).convert("RGB")
    return img.convert("RGB")


def birefnet_mask(model_output: Any, size: tuple[int, int]) -> Image.Image:
    """Model output -> 8-bit mask at `size`: sigmoid, min-max normalization and a
    LANCZOS resize back to the input size. Same math as rembg's
    `BiRefNetSessionGeneral.predict`, so results are identical to `rembg.remove`."""
    import numpy as np

    pred = 1 / (1 + np.exp(-model_output[:, 0, :, :]))
    lo, hi = np.min(pred), np.max(pred)
    if hi == lo:  # constant output: no foreground signal; avoid 0/0 -> NaN
        return Image.new("L", size, 0)
    pred = np.squeeze((pred - lo) / (hi - lo))
    mask = Image.fromarray((pred * 255).astype("uint8"), mode="L")
    return mask.resize(size, Image.Resampling.LANCZOS)


@dataclass
class PreparedCutout:
    """Output of `BiRefNetRemover.prepare`: the RGB image and the model feed."""

    rgb: Image.Image
    feed: dict[str, Any] | None  # None -> not a fast-path session, `infer` runs rembg.remove


class BiRefNetRemover:
    """`BackgroundRemover` backed by the process-wide BiRefNet `rembg` session.

    `remove` runs `prepare` -> `infer` -> `finish`; `remove_many` runs the same
    stages pipelined (CPU pre/post-processing of neighbouring photos overlaps
    the GPU inference) with identical results. Sessions that are not rembg
    BiRefNet sessions, or whose class overrides rembg's BiRefNet `predict`,
    fall back to plain `rembg.remove`, run whole inside `infer` (so under the
    same inference lock; no CPU/GPU overlap on that path).

    Per-item errors in `remove_many` are yielded in place of that item's result
    (see `ml.pipeline`); `EmptyCutoutError` is one of them.
    """

    def __init__(self, settings: Settings, min_coverage: float = MIN_COVERAGE) -> None:
        self._settings = settings
        self._min_coverage = min_coverage
        self._infer_lock = threading.Lock()  # one inference at a time (VIS-REQ-025)

    def _is_birefnet(self, session: Any) -> bool:
        try:
            from rembg.sessions.birefnet_general import BiRefNetSessionGeneral
        except ImportError:  # pragma: no cover - rembg always ships it
            return False
        # Only rembg's own `predict` is replicated by prepare/infer/finish; a
        # subclass overriding it must keep its own pre/post-processing.
        return isinstance(session, BiRefNetSessionGeneral) and (
            type(session).predict is BiRefNetSessionGeneral.predict
        )

    def prepare(self, img: Image.Image) -> PreparedCutout:
        """Normalize to RGB and build the model input (CPU)."""
        session = registry.get_background_remover(self._settings)
        rgb = _to_rgb(img)
        if not self._is_birefnet(session):
            return PreparedCutout(rgb, None)
        feed = session.normalize(rgb, _BIREFNET_MEAN, _BIREFNET_STD, _BIREFNET_SIZE)
        return PreparedCutout(rgb, feed)

    def infer(self, prepared: PreparedCutout) -> Any:
        """Run the model (GPU); serialized by `_infer_lock`. Returns the raw model
        output, or for non-BiRefNet sessions the finished RGBA image from
        `rembg.remove` (which includes its own inference)."""
        session = registry.get_background_remover(self._settings)
        with self._infer_lock:
            if prepared.feed is None:
                from rembg import remove

                result = remove(prepared.rgb, session=session)
                if not isinstance(result, Image.Image):
                    raise TypeError(
                        f"rembg.remove returned {type(result).__name__}, expected PIL image"
                    )
                return result
            return session.inner_session.run(None, prepared.feed)[0]

    def finish(self, prepared: PreparedCutout, raw: Any) -> Image.Image:
        """Mask -> RGBA cutout cropped to the foreground bbox (CPU).

        Raises `EmptyCutoutError` when coverage is below `min_coverage`
        (ING-SCN-005); see the module docstring for the caller contract.
        """
        if prepared.feed is None:
            rgba = raw.convert("RGBA")  # `infer` already ran rembg.remove
        else:
            from rembg.bg import naive_cutout

            rgba = naive_cutout(prepared.rgb, birefnet_mask(raw, prepared.rgb.size)).convert("RGBA")
        coverage = alpha_coverage(rgba)
        if coverage < self._min_coverage:
            raise EmptyCutoutError(coverage, self._min_coverage)
        return crop_to_foreground(rgba)

    def remove(self, img: Image.Image) -> Image.Image:
        """Cut out the foreground and crop to its bbox (RGBA).

        Raises `EmptyCutoutError` when coverage is below `min_coverage`
        (ING-SCN-005); see the module docstring for the caller contract.
        """
        prepared = self.prepare(img)
        return self.finish(prepared, self.infer(prepared))

    def remove_many[T](
        self, sources: Iterable[T], load: Callable[[T], Image.Image]
    ) -> Iterator[Image.Image | Exception]:
        """Pipelined `remove` over `sources` (`load` turns a source, e.g. a path,
        into an image on a worker thread). Yields, in
        order, the cutout, or the exception for that photo (`EmptyCutoutError`,
        or e.g. a decode error for a corrupt file) while the rest still run.
        Batch throughput only: per-photo latency is unchanged."""
        registry.get_background_remover(self._settings)  # create the session up front

        def prep(source: T) -> PreparedCutout:
            return self.prepare(load(source))

        return run_pipeline(sources, prep, self.infer, self.finish)
