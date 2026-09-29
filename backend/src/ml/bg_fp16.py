"""fp16 copy of the background-removal model (08-local-vision.md, VIS-REQ-026).

fp32 BiRefNet at 1024 px needs more than the ~5.5 GB of free VRAM on the 6 GB
reference GPU, so the driver spills to system memory and a cutout takes
seconds. An fp16 copy of the lite model runs in ~0.7 s with masks that match
fp32 (IoU >= 0.9998). The conversion happens once, at `make ml-preload`, and
is stored next to rembg's fp32 file inside `PACHAPP_ML_CACHE_DIR`.

`should_use_fp16` and `fp16_path` are pure; `onnx`/`onnxconverter_common` are
imported inside `ensure_fp16_model` so importing this module stays cheap.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

FP16_SUFFIX = ".fp16"


def should_use_fp16(device: str, *, fp16_enabled: bool) -> bool:
    """fp16 only when the flag is on and the resolved device is `cuda`;
    cpu/mps keep the original fp32 model (fp16 is slower or unsupported there)."""
    return fp16_enabled and device == "cuda"


def fp16_path(fp32_path: Path) -> Path:
    """Location of the fp16 copy: `<name>.onnx` -> `<name>.fp16.onnx`, in the
    same directory as rembg's fp32 file."""
    return fp32_path.with_name(f"{fp32_path.stem}{FP16_SUFFIX}{fp32_path.suffix}")


def model_precision(model_file: Path) -> str:
    """`fp16` for a file produced by `fp16_path`, else `fp32`."""
    return "fp16" if model_file.stem.endswith(FP16_SUFFIX) else "fp32"


def _is_fresh(dst: Path, src: Path) -> bool:
    return dst.is_file() and dst.stat().st_size > 0 and dst.stat().st_mtime >= src.stat().st_mtime


def ensure_fp16_model(src: Path, dst: Path) -> Path:
    """Convert `src` (fp32 ONNX) to fp16 at `dst`, once.

    Skipped when `dst` exists, is non-empty and is not older than `src`.
    Graph inputs/outputs stay float32 (`keep_io_types=True`), so rembg's
    pre/post-processing is unchanged. The write is atomic: a temp file in the
    same directory, then `os.replace`. Returns `dst`.
    """
    if _is_fresh(dst, src):
        return dst

    import onnx
    from onnxconverter_common import float16

    logger.info("Converting %s to fp16 at %s (one-time, may take a minute)", src, dst)
    model = float16.convert_float_to_float16(onnx.load(str(src)), keep_io_types=True)

    tmp = dst.with_name(f"{dst.name}.tmp.{os.getpid()}")
    try:
        # External data only when the protobuf would exceed its 2 GB limit.
        onnx.save(model, str(tmp), save_as_external_data=model.ByteSize() > 1_900_000_000)
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)
    return dst
