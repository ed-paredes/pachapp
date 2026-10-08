"""In-memory `TryOnEngine` for tests and the service layer (no torch, no GPU)."""

from __future__ import annotations

from collections.abc import Callable

from PIL import Image

from tryon.engine import TryOnError, TryOnParams, prepare_garment_input
from tryon.images import prepare_mask, prepare_person


class FakeTryOnEngine:
    """Paints the masked area with the garment's mean colour; records its calls."""

    def __init__(self, *, error: TryOnError | None = None) -> None:
        self.error = error  # raised by every `dress` when set
        self.calls: list[TryOnParams] = []
        self.unloads = 0
        self.idle = False  # makes `unload_if_idle` unload, like an engine past its idle limit
        self.loaded = False

    def dress(
        self,
        person: Image.Image,
        garment: Image.Image,
        mask: Image.Image,
        *,
        params: TryOnParams,
        on_step: Callable[[], None] | None = None,
        on_retry: Callable[[], None] | None = None,
    ) -> Image.Image:
        garment_rgb = prepare_garment_input(garment)
        self.calls.append(params)
        self.loaded = True
        if self.error is not None:
            raise self.error
        size = (params.width, params.height)
        base = prepare_person(person, size)
        colour = garment_rgb.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
        assert isinstance(colour, tuple)
        base.paste(Image.new("RGB", size, colour), mask=prepare_mask(mask, size, blur=0))
        for _ in range(params.steps):
            if on_step is not None:
                on_step()
        return base

    def unload(self) -> None:
        self.unloads += 1
        self.loaded = False

    def unload_if_idle(self) -> bool:
        if not (self.idle and self.loaded):
            return False
        self.unload()
        return True
