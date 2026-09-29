"""CLI: run the background remover over a folder of photos for eyeballing.

Usage: `python -m ml.cutout_preview [INPUT_DIR] [--out OUTPUT_DIR]` (wired up
as `make ml-cutouts`). Step-2 gate aid for 08-local-vision.md: inspect the
cutouts of ~20 eval photos, at least 18 must be clean (VIS-REQ-026 timing is
reported too; the first image includes model warm-up and is flagged).
"""

from __future__ import annotations

import argparse
import logging
import statistics
import sys
import time
from pathlib import Path

from ml.cache import configure_model_cache
from shared.settings import _reject_mnt_path, get_settings

_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def _find_images(input_dir: Path) -> list[Path]:
    return sorted(p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in _EXTENSIONS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ml.cutout_preview", description=__doc__)
    parser.add_argument("input_dir", nargs="?", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None, help="output dir for <stem>.png cutouts")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    assert settings.ml_cache_dir is not None
    assert settings.ml_eval_dir is not None

    input_dir = (args.input_dir or settings.ml_eval_dir).expanduser()
    out_dir = (args.out or settings.data_dir / "eval" / "cutouts").expanduser()

    if not input_dir.is_dir():
        print(f"error: input directory not found: {input_dir}", file=sys.stderr)
        return 1
    images = _find_images(input_dir)
    if not images:
        print(f"error: no .jpg/.jpeg/.png images in {input_dir}", file=sys.stderr)
        return 1
    _reject_mnt_path(out_dir, env_var="--out")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Must run before anything below imports/uses rembg (VIS-REQ-008).
    configure_model_cache(settings.ml_cache_dir)

    from PIL import Image

    from ml.background import BiRefNetRemover, EmptyCutoutError, alpha_coverage
    from ml.device import resolve_device

    print(f"device: {resolve_device(settings.ml_device)}  model: {settings.ml_bg_model}")
    remover = BiRefNetRemover(settings)
    timings: list[float] = []
    empty: list[str] = []

    for index, path in enumerate(images):
        with Image.open(path) as opened:
            img = opened.copy()
        start = time.perf_counter()
        try:
            cutout = remover.remove(img)
        except EmptyCutoutError as exc:
            ms = (time.perf_counter() - start) * 1000
            empty.append(path.name)
            print(f"{path.name}: EMPTY mask (coverage {exc.coverage:.2%}) {ms:.0f} ms")
            continue
        ms = (time.perf_counter() - start) * 1000
        cutout.save(out_dir / f"{path.stem}.png")
        warm = " (includes warm-up)" if index == 0 else ""
        if index > 0:
            timings.append(ms)
        print(
            f"{path.name}: coverage {alpha_coverage(cutout):.2%} of bbox, "
            f"bbox {cutout.width}x{cutout.height}, {ms:.0f} ms{warm}"
        )

    print(f"\nimages: {len(images)}  empty masks: {len(empty)}")
    if empty:
        print(f"  empty: {', '.join(empty)}")
    if timings:
        print(f"median ms (excluding warm-up): {statistics.median(timings):.0f}")
    print(f"cutouts written to: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
