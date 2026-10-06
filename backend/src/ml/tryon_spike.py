"""CLI: virtual try-on spike with CatVTON (V0, 09-virtual-tryon.md §4 and §12).

Usage (wired up as `make tryon-spike`; stop the API, worker and Expo first, §12.2):

    python -m ml.tryon_spike --catvton-dir DIR --mannequin DIR [--mannequin DIR]
        --garments DIR [--garments DIR] --out OUT_DIR
        [--configs A,B,C] [--cases upper,lower,outfit] [--base-revision SHA]
        [--attn-revision SHA]

- `--catvton-dir`: a clone of `Zheng-Chong/CatVTON` at the commit pinned in the
  Makefile (CC BY-NC-SA 4.0, kept outside the repo, §12.6). Its pipeline is imported
  from there; it needs `diffusers` and `accelerate`, which `make tryon-spike` adds with
  `uv run --with` so the backend lock is untouched until V1 decides.
- `--mannequin DIR`: `person.png|jpg` plus `mask_upper.png`, `mask_lower.png` (and
  optionally `mask_overall.png`), made once with `make tryon-masks` (§5.1) or painted
  by hand (white = area to repaint). The folder name is the mannequin id.
- `--garments DIR`: `upper.*` and/or `lower.*` (a cutout PNG with alpha or a photo).
  Pass one folder per input variant to compare, e.g. today's cutouts vs U5 clean
  cutouts vs original photos (§5.4, §12.4). The folder name is the set id.

Configurations (§4): A 576x768/30 steps, B 384x512/30, C 576x768/20. Cases: `upper`
(one pass), `lower` (one pass), `outfit` (lower then upper, the second pass dresses the
output of the first with the mannequin's mask, §5.3).

Per pass it records the time, the torch peak VRAM (`max_memory_allocated`), the time per
diffusion step (counted through the scheduler, which also proves a per-step progress
callback is possible, §6.3) and out-of-memory errors (recorded, then the run goes on).
Per run: model load time, nvidia-smi peak VRAM (all processes), peak RSS of this
process. It writes every image, one contact sheet per mannequin and garment set, and
`tryon_spike_report.md` with the §4 criterion (no OOM, outfit of 2 garments <= 90 s);
quality is the owner's call. Exit codes: 0 ok, 1 setup error.

Pure helpers are unit-tested with a fake dresser and tiny images (VIS-REQ-029); the
CatVTON loader is never imported in tests.
"""

from __future__ import annotations

import argparse
import functools
import gc
import logging
import resource
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

logger = logging.getLogger(__name__)

BASE_MODEL = "booksforcharlie/stable-diffusion-inpainting"  # CatVTON README / app.py default
ATTN_MODEL = "zhengchong/CatVTON"
ATTN_VERSION = "mix"  # app.py default, loads the "mix-48k-1024" attention weights
ATTN_SUBFOLDER = "mix-48k-1024"
GUIDANCE = 2.5  # app.py / pipeline default, matches §5.5
SEED = 42
# app.py blurs the AutoMasker mask with VaeImageProcessor.blur(blur_factor=9) before
# inference; the pipeline then binarises it at 0.5.
MASK_BLUR = 9
# §4 acceptance: an outfit of 2 garments in <= 90 s, without running out of memory.
OUTFIT_BUDGET_S = 90.0
# Margin (share of the longest side) kept around a cutout before CatVTON pads it.
GARMENT_MARGIN = 0.05
# Output with a near-flat colour (std below this, 0-255 scale): fp16 NaNs decode to black.
BLANK_STD = 2.0

_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
MASK_TYPES = ("upper", "lower", "overall")
THUMB_PX = 192


class SpikeSetupError(Exception):
    """A user-facing setup error (bad option, missing file)."""


@dataclass(frozen=True)
class Config:
    name: str
    width: int
    height: int
    steps: int


CONFIGS: dict[str, Config] = {
    "A": Config("A", 576, 768, 30),
    "B": Config("B", 384, 512, 30),
    "C": Config("C", 576, 768, 20),
}

# Case -> passes as (garment slot, CatVTON mask/cloth type), in dressing order (§5.3).
CASES: dict[str, tuple[tuple[str, str], ...]] = {
    "upper": (("upper", "upper"),),
    "lower": (("lower", "lower"),),
    "outfit": (("lower", "lower"), ("upper", "upper")),
}


@dataclass(frozen=True)
class Mannequin:
    id: str
    person: Path
    masks: dict[str, Path]


@dataclass(frozen=True)
class GarmentSet:
    id: str
    garments: dict[str, Path]  # slot ("upper" / "lower") -> image


@dataclass
class PassResult:
    slot: str
    seconds: float
    torch_peak_mib: float | None
    step_ms: float | None  # median time per diffusion step
    steps_seen: int
    oom: bool = False
    blank: bool = False


@dataclass
class CaseResult:
    mannequin: str
    garment_set: str
    config: str
    case: str
    passes: list[PassResult] = field(default_factory=list)
    out_file: str | None = None
    skipped: str | None = None  # reason when the case could not run

    @property
    def seconds(self) -> float:
        return sum(p.seconds for p in self.passes)

    @property
    def oom(self) -> bool:
        return any(p.oom for p in self.passes)

    @property
    def blank(self) -> bool:
        return any(p.blank for p in self.passes)

    @property
    def torch_peak_mib(self) -> float | None:
        peaks = [p.torch_peak_mib for p in self.passes if p.torch_peak_mib is not None]
        return max(peaks) if peaks else None


@dataclass
class RunInfo:
    device: str
    dtype: str
    load_seconds: float
    revisions: dict[str, str | None]
    peak_rss_mib: float = 0.0
    peak_vram_mib: float | None = None


class Dresser(Protocol):
    def dress(
        self,
        person: Image.Image,
        garment: Image.Image,
        mask: Image.Image,
        *,
        config: Config,
        on_step: Callable[[], None],
    ) -> Image.Image:
        """One CatVTON pass at `config`'s size; calls `on_step` after each diffusion step."""
        ...

    def peak_mib(self) -> float | None:
        """Peak torch allocation since the last `reset_peak` (None without CUDA)."""
        ...

    def reset_peak(self) -> None: ...

    def is_oom(self, exc: BaseException) -> bool:
        """True when `exc` is an out-of-memory error (the pass is recorded, not raised)."""
        ...

    def free(self) -> None:
        """Release cached GPU memory (after an OOM)."""
        ...


# --- pure helpers ---------------------------------------------------------------------


def parse_choice(raw: str | None, allowed: Sequence[str], what: str) -> list[str]:
    """Validate a comma-separated list against `allowed` (all of them when empty)."""
    if not raw:
        return list(allowed)
    chosen = list(dict.fromkeys(c.strip() for c in raw.split(",") if c.strip()))
    unknown = [c for c in chosen if c not in allowed]
    if unknown or not chosen:
        raise SpikeSetupError(f"unknown {what} {', '.join(unknown)}; choose from {list(allowed)}")
    return chosen


def _find_image(directory: Path, stem: str) -> Path | None:
    for ext in _IMAGE_EXTENSIONS:
        path = directory / f"{stem}{ext}"
        if path.is_file():
            return path
    return None


def load_mannequin(directory: Path) -> Mannequin:
    if not directory.is_dir():
        raise SpikeSetupError(f"mannequin directory not found: {directory}")
    person = _find_image(directory, "person")
    if person is None:
        raise SpikeSetupError(f"{directory}: missing person.png/.jpg")
    masks = {t: directory / f"mask_{t}.png" for t in MASK_TYPES}
    masks = {t: p for t, p in masks.items() if p.is_file()}
    if not masks:
        raise SpikeSetupError(
            f"{directory}: no mask_upper/lower/overall.png; run `make tryon-masks` or paint them"
        )
    return Mannequin(directory.name, person, masks)


def load_garment_set(directory: Path) -> GarmentSet:
    if not directory.is_dir():
        raise SpikeSetupError(f"garment directory not found: {directory}")
    garments = {s: p for s in ("upper", "lower") if (p := _find_image(directory, s)) is not None}
    if not garments:
        raise SpikeSetupError(f"{directory}: needs upper.* and/or lower.* (png/jpg/webp)")
    return GarmentSet(directory.name, garments)


def missing_inputs(case: str, mannequin: Mannequin, garments: GarmentSet) -> str | None:
    """Why `case` cannot run with these inputs, or None when it can."""
    for slot, mask_type in CASES[case]:
        if slot not in garments.garments:
            return f"no {slot} garment in {garments.id}"
        if mask_type not in mannequin.masks:
            return f"no mask_{mask_type}.png for {mannequin.id}"
    return None


def fit_crop(image: Image.Image, size: tuple[int, int], resample: int) -> Image.Image:
    """Centre-crop to `size`'s aspect ratio, then resize (CatVTON `resize_and_crop` math)."""
    w, h = image.size
    target_w, target_h = size
    if w / h < target_w / target_h:
        new_w, new_h = w, w * target_h // target_w
    else:
        new_w, new_h = h * target_w // target_h, h
    left, top = (w - new_w) // 2, (h - new_h) // 2
    return image.crop((left, top, left + new_w, top + new_h)).resize(size, resample)


def prepare_person(image: Image.Image, config: Config) -> Image.Image:
    return fit_crop(image.convert("RGB"), (config.width, config.height), Image.Resampling.LANCZOS)


def prepare_mask(mask: Image.Image, config: Config, blur: int = MASK_BLUR) -> Image.Image:
    """Mask at the working size, binarised then blurred like CatVTON's app.py."""
    fitted = fit_crop(mask.convert("L"), (config.width, config.height), Image.Resampling.NEAREST)
    binary = fitted.point(lambda v: 255 if v >= 128 else 0)
    return binary.filter(ImageFilter.GaussianBlur(blur)) if blur > 0 else binary


def prepare_garment(image: Image.Image, margin: float = GARMENT_MARGIN) -> Image.Image:
    """RGB garment input: a cutout is cropped to its opaque area (plus `margin`) and
    composited on white (§5.4); a photo without transparency is returned as is.
    CatVTON then pads it to the working size with white (`resize_and_padding`)."""
    if image.mode not in ("RGBA", "LA", "P"):
        return image.convert("RGB")
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    if alpha.getextrema()[0] == 255:  # fully opaque: a photo stored as PNG
        return rgba.convert("RGB")
    box = alpha.point(lambda a: 255 if a > 0 else 0).getbbox()
    if box is None:
        raise SpikeSetupError("garment cutout is fully transparent")
    rgba = rgba.crop(box)
    pad = round(max(rgba.size) * margin)
    canvas = Image.new("RGB", (rgba.width + 2 * pad, rgba.height + 2 * pad), (255, 255, 255))
    canvas.paste(rgba, (pad, pad), rgba)
    return canvas


def is_blank(image: Image.Image, threshold: float = BLANK_STD) -> bool:
    return float(np.asarray(image.convert("L"), dtype=np.float32).std()) < threshold


def meets_criterion(
    results: Sequence[CaseResult], budget_s: float = OUTFIT_BUDGET_S
) -> bool | None:
    """§4 for one configuration: every outfit case without OOM, blank output or overrun.
    None when no outfit case ran (nothing to judge)."""
    outfits = [r for r in results if r.case == "outfit" and r.skipped is None]
    if not outfits:
        return None
    return all(not r.oom and not r.blank and r.seconds <= budget_s for r in outfits)


# --- resource meters ------------------------------------------------------------------


def peak_rss_mib() -> float:
    """Peak resident set size of this process (Linux reports ru_maxrss in KiB)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def gpu_used_mib() -> float | None:
    """GPU memory in use according to nvidia-smi (all processes); None when unavailable."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout
        return float(out.strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


# --- the spike ------------------------------------------------------------------------


def _open(path: Path) -> Image.Image:
    with Image.open(path) as opened:
        opened.load()
        return opened.copy()


def run_case(
    dresser: Dresser,
    mannequin: Mannequin,
    garments: GarmentSet,
    config: Config,
    case: str,
    out_dir: Path,
    *,
    sample_gpu: Callable[[], None] = lambda: None,
) -> CaseResult:
    """Dress the mannequin pass by pass; stops at the first OOM (recorded, not raised)."""
    result = CaseResult(mannequin.id, garments.id, config.name, case)
    reason = missing_inputs(case, mannequin, garments)
    if reason is not None:
        result.skipped = reason
        return result

    person = prepare_person(_open(mannequin.person), config)
    for slot, mask_type in CASES[case]:
        garment = prepare_garment(_open(garments.garments[slot]))
        mask = prepare_mask(_open(mannequin.masks[mask_type]), config)
        step_times: list[float] = []
        last = [time.perf_counter()]

        def on_step(step_times: list[float] = step_times, last: list[float] = last) -> None:
            now = time.perf_counter()
            step_times.append((now - last[0]) * 1000)
            last[0] = now

        dresser.reset_peak()
        start = time.perf_counter()
        last[0] = start
        try:
            person = dresser.dress(person, garment, mask, config=config, on_step=on_step)
        except Exception as exc:
            if not dresser.is_oom(exc):
                raise
            logger.warning(
                "OOM: %s %s %s %s/%s", mannequin.id, garments.id, config.name, case, slot
            )
            dresser.free()
            result.passes.append(
                PassResult(slot, time.perf_counter() - start, dresser.peak_mib(), None, 0, oom=True)
            )
            return result
        seconds = time.perf_counter() - start
        sample_gpu()
        # The first "step" also pays the VAE encodings; the median hides it.
        step_ms = float(np.median(step_times)) if step_times else None
        result.passes.append(
            PassResult(
                slot,
                seconds,
                dresser.peak_mib(),
                step_ms,
                len(step_times),
                blank=is_blank(person),
            )
        )

    rel = Path(mannequin.id) / garments.id / f"{config.name}_{case}.png"
    (out_dir / rel).parent.mkdir(parents=True, exist_ok=True)
    person.save(out_dir / rel)
    result.out_file = rel.as_posix()
    return result


def run_spike(
    dresser: Dresser,
    mannequins: Sequence[Mannequin],
    garment_sets: Sequence[GarmentSet],
    configs: Sequence[Config],
    cases: Sequence[str],
    out_dir: Path,
    *,
    sample_gpu: Callable[[], None] = lambda: None,
) -> list[CaseResult]:
    """Every mannequin x garment set x configuration x case, serially (VIS-REQ-025)."""
    results: list[CaseResult] = []
    for mannequin in mannequins:
        for garments in garment_sets:
            for config in configs:
                for case in cases:
                    logger.info("%s / %s / %s / %s", mannequin.id, garments.id, config.name, case)
                    results.append(
                        run_case(
                            dresser,
                            mannequin,
                            garments,
                            config,
                            case,
                            out_dir,
                            sample_gpu=sample_gpu,
                        )
                    )
    return results


# --- output ---------------------------------------------------------------------------


def _cell(img: Image.Image | None, label: str) -> Image.Image:
    cell = Image.new("RGB", (THUMB_PX, THUMB_PX * 4 // 3 + 16), (230, 230, 230))
    if img is not None:
        fitted = img.convert("RGB")
        fitted.thumbnail((THUMB_PX, THUMB_PX * 4 // 3))
        cell.paste(fitted, ((THUMB_PX - fitted.width) // 2, 16))
    ImageDraw.Draw(cell).text((3, 2), label[:30], fill=(0, 0, 0))
    return cell


def write_contact_sheets(
    mannequins: Sequence[Mannequin],
    garment_sets: Sequence[GarmentSet],
    configs: Sequence[Config],
    cases: Sequence[str],
    results: Sequence[CaseResult],
    out_dir: Path,
) -> list[Path]:
    """One sheet per mannequin x garment set: inputs row, then a row per configuration."""
    by_key = {(r.mannequin, r.garment_set, r.config, r.case): r for r in results}
    sheets: list[Path] = []
    for mannequin in mannequins:
        for garments in garment_sets:
            inputs = [_cell(_open(mannequin.person), mannequin.id)]
            inputs += [
                _cell(prepare_garment(_open(path)), f"{garments.id}/{slot}")
                for slot, path in garments.garments.items()
            ]
            rows = [inputs]
            for config in configs:
                row = []
                for case in cases:
                    r = by_key.get((mannequin.id, garments.id, config.name, case))
                    image = _open(out_dir / r.out_file) if r and r.out_file else None
                    status = "" if image else (" OOM" if r and r.oom else " -")
                    row.append(_cell(image, f"{config.name} {case}{status}"))
                rows.append(row)
            columns = max(len(r) for r in rows)
            cell_w, cell_h = rows[0][0].size
            sheet = Image.new("RGB", (columns * cell_w, len(rows) * cell_h), (255, 255, 255))
            for y, row in enumerate(rows):
                for x, cell in enumerate(row):
                    sheet.paste(cell, (x * cell_w, y * cell_h))
            path = out_dir / f"contact_{mannequin.id}_{garments.id}.jpg"
            sheet.save(path, quality=88)
            sheets.append(path)
    return sheets


def _fmt(value: float | None, digits: int = 0) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def format_report(
    results: Sequence[CaseResult],
    configs: Sequence[Config],
    info: RunInfo,
    sheets: Sequence[Path],
) -> str:
    lines = [
        "# Try-on spike report (CatVTON)",
        "",
        f"device: {info.device}; dtype: {info.dtype}; model load: {info.load_seconds:.1f} s; "
        f"peak RSS: {_fmt(info.peak_rss_mib)} MiB; peak VRAM (nvidia-smi, all processes): "
        f"{_fmt(info.peak_vram_mib)} MiB",
        "revisions: " + ", ".join(f"{k}={v or 'unpinned'}" for k, v in info.revisions.items()),
        "",
        f"Criterion (§4): every outfit (2 passes) without OOM or blank output in <= "
        f"{OUTFIT_BUDGET_S:.0f} s. Quality is the owner's call (contact sheets).",
        "",
        "| config | size | steps | outfit max s | criterion |",
        "|---|---|---|---|---|",
    ]
    for config in configs:
        mine = [r for r in results if r.config == config.name]
        outfit_s = [r.seconds for r in mine if r.case == "outfit" and r.passes]
        verdict = {True: "meets", False: "fails", None: "n/a (no outfit case)"}
        lines.append(
            f"| {config.name} | {config.width}x{config.height} | {config.steps} "
            f"| {_fmt(max(outfit_s) if outfit_s else None, 1)} "
            f"| {verdict[meets_criterion(mine)]} |"
        )
    lines += [
        "",
        "## Runs",
        "",
        "| mannequin | garments | config | case | total s | per pass s | ms/step "
        "| torch peak MiB | notes |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        if r.skipped:
            lines.append(
                f"| {r.mannequin} | {r.garment_set} | {r.config} | {r.case} "
                f"| - | - | - | - | skipped: {r.skipped} |"
            )
            continue
        per_pass = " + ".join(f"{p.seconds:.1f}" for p in r.passes)
        step_ms = " / ".join(_fmt(p.step_ms) for p in r.passes)
        notes = ", ".join(n for n, on in (("OOM", r.oom), ("blank output", r.blank)) if on)
        lines.append(
            f"| {r.mannequin} | {r.garment_set} | {r.config} | {r.case} | {r.seconds:.1f} "
            f"| {per_pass} | {step_ms} | {_fmt(r.torch_peak_mib)} | {notes or '-'} |"
        )
    if sheets:
        lines += ["", "## Contact sheets", ""] + [f"- {s.name}" for s in sheets]
    return "\n".join(lines) + "\n"


# --- real CatVTON dresser (not loaded in tests) ------------------------------------------


class CatVTONDresser:  # pragma: no cover - needs torch, CatVTON and its weights
    """Wraps an already-built `CatVTONPipeline` (or a compatible object).

    The pipeline is not a diffusers `DiffusionPipeline`: it has no
    `enable_model_cpu_offload` or callbacks. Progress is counted by wrapping its
    scheduler's `step`, which runs once per diffusion step.
    """

    def __init__(self, pipeline: Any, device: str) -> None:
        self.pipeline = pipeline
        self.device = device
        self._on_step: Callable[[], None] | None = None
        scheduler = pipeline.noise_scheduler
        original_step = scheduler.step

        # `wraps` keeps the signature: the pipeline inspects `step` for `eta`/`generator`.
        @functools.wraps(original_step)
        def counted_step(*args: Any, **kwargs: Any) -> Any:
            out = original_step(*args, **kwargs)
            if self._on_step is not None:
                self._on_step()
            return out

        scheduler.step = counted_step

    @classmethod
    def load(
        cls,
        catvton_dir: Path,
        *,
        device: str,
        fp16: bool,
        base_revision: str | None,
        attn_revision: str | None,
    ) -> tuple[CatVTONDresser, dict[str, str | None]]:
        import torch
        from huggingface_hub import snapshot_download

        if str(catvton_dir) not in sys.path:
            sys.path.insert(0, str(catvton_dir))
        from model.pipeline import CatVTONPipeline  # ty: ignore[unresolved-import]

        # Only what CatVTONPipeline loads from the base repo (no .ckpt, text encoder,
        # safety checker or VAE: the VAE comes from sd-vae-ft-mse).
        base_path = snapshot_download(
            BASE_MODEL, revision=base_revision, allow_patterns=["scheduler/*", "unet/*"]
        )
        attn_path = snapshot_download(
            ATTN_MODEL, revision=attn_revision, allow_patterns=[f"{ATTN_SUBFOLDER}/*"]
        )
        pipeline = CatVTONPipeline(
            base_ckpt=base_path,
            attn_ckpt=attn_path,
            attn_ckpt_version=ATTN_VERSION,
            # Turing (RTX 20xx) has no fast bf16: fp16 on CUDA (§5.5, §12).
            weight_dtype=torch.float16 if fp16 else torch.float32,
            device=device,
            # The SD safety checker costs VRAM and may swap a mannequin for NSFW.jpg.
            skip_safety_check=True,
            use_tf32=False,
        )
        revisions = {
            BASE_MODEL: Path(base_path).name,  # snapshot folder = resolved commit
            ATTN_MODEL: Path(attn_path).name,
            "stabilityai/sd-vae-ft-mse": None,  # hard-coded in CatVTONPipeline, latest
        }
        return cls(pipeline, device), revisions

    def dress(
        self,
        person: Image.Image,
        garment: Image.Image,
        mask: Image.Image,
        *,
        config: Config,
        on_step: Callable[[], None],
    ) -> Image.Image:
        import torch

        generator = torch.Generator(device=self.device).manual_seed(SEED)
        self._on_step = on_step
        try:
            return self.pipeline(
                image=person,
                condition_image=garment,
                mask=mask,
                num_inference_steps=config.steps,
                guidance_scale=GUIDANCE,
                width=config.width,
                height=config.height,
                generator=generator,
            )[0]
        finally:
            self._on_step = None

    def _cuda(self) -> Any:
        import torch

        return torch.cuda if self.device == "cuda" and torch.cuda.is_available() else None

    def peak_mib(self) -> float | None:
        cuda = self._cuda()
        return cuda.max_memory_allocated() / 1024**2 if cuda else None

    def reset_peak(self) -> None:
        cuda = self._cuda()
        if cuda:
            cuda.reset_peak_memory_stats()

    def is_oom(self, exc: BaseException) -> bool:
        import torch

        return isinstance(exc, torch.cuda.OutOfMemoryError)

    def free(self) -> None:
        gc.collect()
        cuda = self._cuda()
        if cuda:
            cuda.empty_cache()


# --- CLI ------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ml.tryon_spike", description=__doc__)
    parser.add_argument("--catvton-dir", type=Path, required=True)
    parser.add_argument("--mannequin", type=Path, action="append", required=True)
    parser.add_argument("--garments", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--configs", default=None, help=f"comma list of {list(CONFIGS)}")
    parser.add_argument("--cases", default=None, help=f"comma list of {list(CASES)}")
    parser.add_argument("--base-revision", default=None, help=f"commit of {BASE_MODEL}")
    parser.add_argument("--attn-revision", default=None, help=f"commit of {ATTN_MODEL}")
    parser.add_argument("--fp32", action="store_true", help="fp32 weights (default fp16 on GPU)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)
    from shared.settings import _reject_mnt_path, get_settings

    try:
        configs = [CONFIGS[c] for c in parse_choice(args.configs, list(CONFIGS), "config")]
        cases = parse_choice(args.cases, list(CASES), "case")
        mannequins = [load_mannequin(d.expanduser()) for d in args.mannequin]
        garment_sets = [load_garment_set(d.expanduser()) for d in args.garments]
        catvton_dir = args.catvton_dir.expanduser()
        if not (catvton_dir / "model" / "pipeline.py").is_file():
            raise SpikeSetupError(f"not a CatVTON clone: {catvton_dir} (run `make tryon-setup`)")
        out_dir = args.out.expanduser()
        _reject_mnt_path(out_dir, env_var="--out")
        out_dir.mkdir(parents=True, exist_ok=True)
    except SpikeSetupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    settings = get_settings()
    assert settings.ml_cache_dir is not None
    from ml.cache import configure_model_cache

    configure_model_cache(settings.ml_cache_dir)  # before huggingface_hub (VIS-REQ-008)
    from ml.device import resolve_device

    device = resolve_device(settings.ml_device)
    if device != "cuda":
        logger.warning("running on %s: timings will not be representative", device)
    fp16 = device == "cuda" and not args.fp32

    vram_peak: list[float] = []

    def sample_gpu() -> None:
        used = gpu_used_mib()
        if used is not None:
            vram_peak.append(used)

    start = time.perf_counter()
    dresser, revisions = CatVTONDresser.load(
        catvton_dir,
        device=device,
        fp16=fp16,
        base_revision=args.base_revision,
        attn_revision=args.attn_revision,
    )
    load_seconds = time.perf_counter() - start
    sample_gpu()

    results = run_spike(
        dresser, mannequins, garment_sets, configs, cases, out_dir, sample_gpu=sample_gpu
    )
    info = RunInfo(
        device=device,
        dtype="fp16" if fp16 else "fp32",
        load_seconds=load_seconds,
        revisions=revisions,
        peak_rss_mib=peak_rss_mib(),
        peak_vram_mib=max(vram_peak) if vram_peak else None,
    )
    sheets = write_contact_sheets(mannequins, garment_sets, configs, cases, results, out_dir)
    report = format_report(results, configs, info, sheets)
    (out_dir / "tryon_spike_report.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"written to: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
