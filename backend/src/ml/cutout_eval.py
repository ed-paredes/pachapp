"""CLI: compare garment-only cutout methods on real photos (U5a, 08-local-vision.md).

Usage: `python -m ml.cutout_eval [PHOTO_DIR ...] --out OUT_DIR [--methods M,...]
[--mask-modes intersect,subtract] [--worn-only] [--sheet-size N]` (wired up as
`make ml-cutout-eval`). Without directories it uses `PACHAPP_ML_EVAL_DIR`.
Methods (default: all):

    birefnet                 today's BiRefNet matte (the baseline, always run first)
    birefnet+segformer-b3    matte combined with SegFormer b3 clothes classes
    birefnet+segformer-b2    ... SegFormer b2 clothes
    birefnet+u2net-cloth     ... rembg u2net_cloth_seg
    birefnet+fashn           ... FASHN Human Parser (SegFormer-B4, 18 classes)
    birefnet+schp-atr        ... SCHP, ATR checkpoint (18 classes, pure-PyTorch network)
    birefnet+schp-lip        ... SCHP, LIP checkpoint (20 classes)

Every parser method runs once per photo and is combined with the matte in each of the
`--mask-modes` (default both): "intersect" keeps only the garment's own parser classes,
"subtract" removes body (and, with a `labels.json` category, other-garment) classes from
the matte and fills enclosed holes (see `ml.garment_parse`). Each method x mode gets its
own column, folder (`birefnet+fashn.subtract/`) and contact-sheet cell; the parser's
latency parts are measured once and shared by its modes (the per-mode latency adds that
mode's combine step), and so are its VRAM / torch peak / RSS.

Per image and method it writes the cutout PNG, the warm per-image latency (model load
and the first image excluded) and the dominant colours of the eroded cutout; per method
the peak VRAM and peak RSS. It also writes contact sheets and `report.md`.

Models are loaded one method at a time and freed before the next; images run serially
(VIS-REQ-025). The BiRefNet mattes are cached as PNG files in `OUT_DIR/_mattes` so the
parser phases never need BiRefNet loaded. A `labels.json` next to the photos (the
`ml.eval` format) supplies the garment category; otherwise the largest clothing region
is kept. Exit codes: 0 ok, 1 setup error.
"""

from __future__ import annotations

import argparse
import gc
import json
import logging
import shutil
import statistics
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from PIL import Image, ImageDraw

from ml.background import (
    OPACITY_THRESHOLD,
    EmptyCutoutError,
    _to_rgb,
    crop_to_foreground,
)
from ml.garment_parse import (
    MASK_MODES,
    GarmentParser,
    ParseResult,
    cut_garment,
    erode_alpha,
    person_present,
)
from worker.colors import extract_colors

logger = logging.getLogger(__name__)

_EXTENSIONS = {".jpg", ".jpeg", ".png"}
BASELINE = "birefnet"
PARSER_KEYS = ("segformer-b3", "segformer-b2", "u2net-cloth", "fashn", "schp-atr", "schp-lip")
ALL_METHODS = (BASELINE, *(f"{BASELINE}+{k}" for k in PARSER_KEYS))
THUMB_PX = 256


class EvalSetupError(Exception):
    """A user-facing setup error (bad method, no photos, nothing worn)."""


class Matter(Protocol):
    def matte(self, rgb: Image.Image) -> Image.Image:
        """Full-size RGBA of `rgb` with the BiRefNet alpha (not cropped)."""
        ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class Photo:
    path: Path
    key: str  # unique across input dirs, used for output names
    category: str | None = None


@dataclass
class Row:
    key: str
    ms: float
    colors: str  # "negro 55%, gris 30%"
    top_color: str | None
    fallback: bool = False
    empty: bool = False
    ratio: float = 0.0
    out_file: str | None = None


@dataclass
class MethodResult:
    method: str  # report label: "birefnet" or "birefnet+<parser>.<mode>"
    mode: str | None = None
    rows: dict[str, Row] = field(default_factory=dict)
    peak_vram_mib: float | None = None
    peak_rss_mib: float = 0.0
    torch_peak_mib: float | None = None
    revision: str | None = None


# --- pure helpers ---------------------------------------------------------------------


def parse_methods(raw: str | None) -> list[str]:
    """Validate a comma-separated method list; the baseline is always included, first."""
    if not raw:
        return list(ALL_METHODS)
    chosen = [m.strip() for m in raw.split(",") if m.strip()]
    unknown = [m for m in chosen if m not in ALL_METHODS]
    if unknown:
        raise EvalSetupError(f"unknown method(s) {', '.join(unknown)}; choose from {ALL_METHODS}")
    return [BASELINE, *[m for m in dict.fromkeys(chosen) if m != BASELINE]]


def parse_mask_modes(raw: str | None) -> list[str]:
    """Validate a comma-separated mask-mode list (default: all), order preserved."""
    if not raw:
        return list(MASK_MODES)
    chosen = list(dict.fromkeys(m.strip() for m in raw.split(",") if m.strip()))
    unknown = [m for m in chosen if m not in MASK_MODES]
    if unknown or not chosen:
        raise EvalSetupError(f"unknown mask mode(s) {', '.join(unknown)}; choose from {MASK_MODES}")
    return chosen


def parser_key(method: str) -> str:
    return method.split("+", 1)[1]


def result_label(method: str, mode: str) -> str:
    return f"{method}.{mode}"


def collect_photos(dirs: Sequence[Path]) -> list[Photo]:
    """Photos of every directory, with the category from an optional `labels.json`."""
    photos: list[Photo] = []
    for directory in dirs:
        if not directory.is_dir():
            raise EvalSetupError(f"photo directory not found: {directory}")
        categories: dict[str, str | None] = {}
        labels_file = directory / "labels.json"
        if labels_file.is_file():
            raw = json.loads(labels_file.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                categories = {
                    name: (entry or {}).get("category") if isinstance(entry, dict) else None
                    for name, entry in raw.items()
                }
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix.lower() in _EXTENSIONS:
                key = f"{directory.name}__{path.name}"
                photos.append(Photo(path, key, categories.get(path.name)))
    if not photos:
        raise EvalSetupError("no .jpg/.jpeg/.png photos found")
    return photos


def format_colors(rgba: Image.Image) -> tuple[str, str | None]:
    """Dominant colours of the eroded cutout as ("negro 55%, gris 30%", "negro")."""
    entries = extract_colors(erode_alpha(rgba)).colors.root
    if not entries:
        return "-", None
    return ", ".join(f"{e.name} {e.proportion:.0%}" for e in entries), entries[0].name


def warm_latencies(rows: Sequence[Row]) -> list[float]:
    """Latencies excluding the first image (it pays CUDA/ORT warm-up) and empty masks."""
    return [r.ms for r in list(rows)[1:] if not r.empty]


def percentile(values: Sequence[float], q: float) -> float:
    return float(np.percentile(values, q)) if values else float("nan")


def colour_changed(base: Row | None, other: Row | None) -> bool:
    return bool(base and other and base.top_color != other.top_color)


# --- resource meters ------------------------------------------------------------------


def current_rss_mib() -> float:
    """Resident set size of this process in MiB (Linux /proc; 0 elsewhere)."""
    try:
        pages = int(Path("/proc/self/statm").read_text().split()[1])
    except (OSError, ValueError, IndexError):
        return 0.0
    import os

    return pages * os.sysconf("SC_PAGE_SIZE") / 1024**2


def gpu_used_mib() -> float | None:
    """GPU memory in use according to nvidia-smi (covers onnxruntime, which torch
    cannot see); None when unavailable."""
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


def _torch_cuda_ready() -> bool:
    """True when torch is already imported and has a CUDA device (never imports it)."""
    torch = sys.modules.get("torch")
    return bool(torch is not None and torch.cuda.is_available())


class Meter:
    """Peak RSS and peak GPU memory (nvidia-smi sampling) of one method run."""

    def __init__(self) -> None:
        self.torch_ready = _torch_cuda_ready()
        if self.torch_ready:
            import torch

            torch.cuda.reset_peak_memory_stats()
        self.peak_rss = current_rss_mib()
        self.baseline_gpu = gpu_used_mib()
        self.peak_gpu = self.baseline_gpu

    def sample(self) -> None:
        self.peak_rss = max(self.peak_rss, current_rss_mib())
        used = gpu_used_mib()
        if used is not None:
            self.peak_gpu = used if self.peak_gpu is None else max(self.peak_gpu, used)

    @property
    def vram_mib(self) -> float | None:
        return self.peak_gpu

    @property
    def torch_peak_mib(self) -> float | None:
        """`torch.cuda.max_memory_allocated` (torch tensors only; None without torch+CUDA)."""
        if not self.torch_ready:
            return None
        import torch

        return torch.cuda.max_memory_allocated() / 1024**2


# --- real BiRefNet matter --------------------------------------------------------------


class BiRefNetMatter:
    """Full-size BiRefNet matte via the same prepare/infer math as the worker."""

    def __init__(self, settings: Any) -> None:
        from ml.background import BiRefNetRemover

        self._remover = BiRefNetRemover(settings)

    def matte(self, rgb: Image.Image) -> Image.Image:
        from ml.background import birefnet_mask

        prepared = self._remover.prepare(rgb)
        raw = self._remover.infer(prepared)
        out = prepared.rgb.convert("RGBA")
        if prepared.feed is None:
            out.putalpha(raw.convert("RGBA").getchannel("A"))
        else:
            out.putalpha(birefnet_mask(raw, prepared.rgb.size))
        return out

    def close(self) -> None:
        from ml import registry

        registry.reset_registry()
        _release()


def _release() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:  # pragma: no cover
        pass


# --- evaluation -----------------------------------------------------------------------


def _load_rgb(path: Path) -> Image.Image:
    with Image.open(path) as opened:
        return _to_rgb(opened.copy())


def _save_cutout(rgba: Image.Image, out_dir: Path, method: str, key: str) -> str:
    folder = out_dir / method
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{key}.png"
    try:
        crop_to_foreground(rgba).save(folder / name)
    except EmptyCutoutError:
        rgba.save(folder / name)
    return f"{method}/{name}"


def _rgba_from_matte(rgb: Image.Image, matte_file: Path) -> Image.Image:
    rgba = rgb.convert("RGBA")
    with Image.open(matte_file) as alpha:
        rgba.putalpha(alpha.convert("L"))
    return rgba


def run_baseline(
    photos: Sequence[Photo], out_dir: Path, matter: Matter, mattes_dir: Path
) -> MethodResult:
    """BiRefNet over every photo: cutout PNG, latency, colours and the cached alpha."""
    mattes_dir.mkdir(parents=True, exist_ok=True)
    result = MethodResult(BASELINE)
    meter = Meter()
    for photo in photos:
        rgb = _load_rgb(photo.path)
        start = time.perf_counter()
        rgba = matter.matte(rgb)
        ms = (time.perf_counter() - start) * 1000
        rgba.getchannel("A").save(mattes_dir / f"{photo.key}.png")
        coverage = float((np.asarray(rgba.getchannel("A")) > OPACITY_THRESHOLD).mean())
        colors, top = format_colors(rgba)
        result.rows[photo.key] = Row(
            photo.key,
            ms,
            colors,
            top,
            empty=coverage == 0.0,
            ratio=coverage,
            out_file=_save_cutout(rgba, out_dir, BASELINE, photo.key),
        )
        meter.sample()
    result.peak_rss_mib, result.peak_vram_mib = meter.peak_rss, meter.vram_mib
    result.torch_peak_mib = meter.torch_peak_mib
    return result


def filter_worn(photos: Sequence[Photo], parser: GarmentParser) -> tuple[list[Photo], list[Photo]]:
    """(worn, skipped): photos where `parser` detects a person. Serial."""
    worn: list[Photo] = []
    skipped: list[Photo] = []
    for photo in photos:
        result: ParseResult = parser.parse(_load_rgb(photo.path))
        (worn if person_present(result) else skipped).append(photo)
    return worn, skipped


def run_parser_method(
    method: str,
    photos: Sequence[Photo],
    out_dir: Path,
    parser: GarmentParser,
    mattes_dir: Path,
    baseline: MethodResult,
    modes: Sequence[str] = MASK_MODES,
) -> list[MethodResult]:
    """Parser + cached matte per photo, one result per mask mode (parsed once per photo).

    Latency per mode = baseline matte time + parse + that mode's combine step.
    """
    results = {mode: MethodResult(result_label(method, mode), mode) for mode in modes}
    meter = Meter()
    for photo in photos:
        rgb = _load_rgb(photo.path)
        matte = _rgba_from_matte(rgb, mattes_dir / f"{photo.key}.png")
        start = time.perf_counter()
        parsed = parser.parse(rgb)
        parse_ms = (time.perf_counter() - start) * 1000
        for mode, result in results.items():
            start = time.perf_counter()
            cut = cut_garment(matte, parsed, photo.category, mode=mode)
            ms = parse_ms + (time.perf_counter() - start) * 1000 + baseline.rows[photo.key].ms
            colors, top = format_colors(cut.rgba)
            result.rows[photo.key] = Row(
                photo.key,
                ms,
                colors,
                top,
                fallback=cut.fallback,
                ratio=cut.garment_ratio,
                out_file=_save_cutout(cut.rgba, out_dir, result.method, photo.key),
            )
        meter.sample()
    for result in results.values():
        result.peak_rss_mib, result.peak_vram_mib = meter.peak_rss, meter.vram_mib
        result.torch_peak_mib = meter.torch_peak_mib
        result.revision = getattr(parser, "revision", None)
    return list(results.values())


def evaluate(
    photos: Sequence[Photo],
    methods: Sequence[str],
    out_dir: Path,
    *,
    matter_factory: Callable[[], Matter],
    parser_factory: Callable[[str], GarmentParser],
    worn_only: bool = False,
    mask_modes: Sequence[str] = MASK_MODES,
) -> tuple[list[Photo], list[Photo], list[MethodResult]]:
    """Run `methods` over `photos`; returns (evaluated, skipped as not worn, results).

    Each parser method yields one result per entry of `mask_modes`.

    `--worn-only` filters once with the first parser method's parser, before anything
    else, so every method sees the same photos. The baseline runs next (and its
    models are freed) so the parser phases only need the cached mattes.
    """
    parser_methods = [m for m in methods if m != BASELINE]
    skipped: list[Photo] = []
    selected = list(photos)
    if worn_only:
        if not parser_methods:
            raise EvalSetupError("--worn-only needs at least one parser method")
        parser = parser_factory(parser_key(parser_methods[0]))
        try:
            selected, skipped = filter_worn(photos, parser)
        finally:
            parser.close()
        if not selected:
            raise EvalSetupError("--worn-only: no photo with a person was found")

    mattes_dir = out_dir / "_mattes"
    matter = matter_factory()
    try:
        baseline = run_baseline(selected, out_dir, matter, mattes_dir)
    finally:
        matter.close()
    results = [baseline]
    for method in parser_methods:
        parser = parser_factory(parser_key(method))
        try:
            results += run_parser_method(
                method, selected, out_dir, parser, mattes_dir, baseline, mask_modes
            )
        finally:
            parser.close()
            _release()
    shutil.rmtree(mattes_dir, ignore_errors=True)
    return selected, skipped, results


# --- output ---------------------------------------------------------------------------


def _thumb(img: Image.Image, label: str) -> Image.Image:
    """`img` fitted into a THUMB_PX cell over grey (so cutouts show their edges)."""
    cell = Image.new("RGB", (THUMB_PX, THUMB_PX + 16), (200, 200, 200))
    fitted = img.convert("RGBA")
    fitted.thumbnail((THUMB_PX, THUMB_PX))
    cell.paste(fitted, ((THUMB_PX - fitted.width) // 2, 16), fitted)
    ImageDraw.Draw(cell).text((3, 2), label[:40], fill=(0, 0, 0))
    return cell


def write_contact_sheets(
    photos: Sequence[Photo],
    results: Sequence[MethodResult],
    out_dir: Path,
    per_sheet: int,
) -> list[Path]:
    """Grids of `per_sheet` rows: original | one column per method."""
    sheets: list[Path] = []
    cell_h = THUMB_PX + 16
    for number, start in enumerate(range(0, len(photos), per_sheet), start=1):
        chunk = photos[start : start + per_sheet]
        columns = 1 + len(results)
        sheet = Image.new("RGB", (columns * THUMB_PX, len(chunk) * cell_h), (255, 255, 255))
        for row, photo in enumerate(chunk):
            cells = [_thumb(_load_rgb(photo.path), photo.key)]
            for result in results:
                out_file = result.rows[photo.key].out_file or ""
                with Image.open(out_dir / out_file) as cutout:
                    cells.append(_thumb(cutout.copy(), result.method))
            for column, cell in enumerate(cells):
                sheet.paste(cell, (column * THUMB_PX, row * cell_h))
        path = out_dir / f"contact_{number:02d}.jpg"
        sheet.save(path, quality=88)
        sheets.append(path)
    return sheets


def _fmt(value: float | None, unit: str = "") -> str:
    return "n/a" if value is None or value != value else f"{value:.0f}{unit}"


def format_report(
    photos: Sequence[Photo],
    skipped: Sequence[Photo],
    results: Sequence[MethodResult],
    sheets: Sequence[Path],
    *,
    device: str,
) -> str:
    """Markdown report: per-method table, then per-image colours with changes flagged."""
    lines = [
        "# Garment cutout evaluation",
        "",
        f"device: {device}; photos: {len(photos)}; skipped (no person): {len(skipped)}",
        "Latency is warm (first image and model load excluded); parser methods include the "
        "BiRefNet matte time. Peak VRAM = nvidia-smi total used while the method ran "
        "(includes other processes), torch peak = tensors "
        "allocated by torch (n/a for onnxruntime), peak RSS = this process.",
        "",
        "| method | revision | median ms | p95 ms | fallbacks | peak VRAM MiB "
        "| torch peak MiB | peak RSS MiB |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        warm = warm_latencies(list(r.rows.values()))
        fallbacks = sum(row.fallback for row in r.rows.values())
        median = statistics.median(warm) if warm else None
        lines.append(
            f"| {r.method} | {r.revision or '-'} | {_fmt(median)} | {_fmt(percentile(warm, 95))}"
            f" | {fallbacks}/{len(r.rows)} | {_fmt(r.peak_vram_mib)}"
            f" | {_fmt(r.torch_peak_mib)} | {_fmt(r.peak_rss_mib)} |"
        )
    lines += [
        "",
        "## Colours per photo",
        "",
        "A star marks a changed dominant colour vs birefnet.",
        "",
    ]
    header = ["photo", "category", *[r.method for r in results]]
    lines += ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    base = results[0]
    for photo in photos:
        cells = [photo.key, photo.category or "?"]
        for r in results:
            row = r.rows[photo.key]
            mark = " *" if r is not base and colour_changed(base.rows[photo.key], row) else ""
            flag = " (fallback)" if row.fallback else ""
            cells.append(f"{row.colors}{mark}{flag}")
        lines.append("| " + " | ".join(cells) + " |")
    if skipped:
        lines += ["", "## Skipped (no person detected)", ""] + [f"- {p.key}" for p in skipped]
    if sheets:
        lines += ["", "## Contact sheets", ""] + [f"- {s.name}" for s in sheets]
    return "\n".join(lines) + "\n"


# --- CLI ------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ml.cutout_eval", description=__doc__)
    parser.add_argument("photo_dirs", nargs="*", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="output directory")
    parser.add_argument("--methods", default=None, help=f"comma list of {ALL_METHODS}")
    parser.add_argument(
        "--mask-modes",
        default=None,
        help=f"comma list of {MASK_MODES} (default: both; one column per method x mode)",
    )
    parser.add_argument("--worn-only", action="store_true", help="keep only photos with a person")
    parser.add_argument("--sheet-size", type=int, default=6, help="rows per contact sheet")
    parser.add_argument("--limit", type=int, default=None, help="evaluate only the first N photos")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)
    from ml.cache import configure_model_cache
    from shared.settings import _reject_mnt_path, get_settings

    settings = get_settings()
    assert settings.ml_cache_dir is not None and settings.ml_eval_dir is not None
    try:
        methods = parse_methods(args.methods)
        mask_modes = parse_mask_modes(args.mask_modes)
        dirs = [d.expanduser() for d in args.photo_dirs] or [settings.ml_eval_dir]
        photos = collect_photos(dirs)
        if args.limit:
            photos = photos[: args.limit]
        out_dir = args.out.expanduser()
        _reject_mnt_path(out_dir, env_var="--out")
        out_dir.mkdir(parents=True, exist_ok=True)

        configure_model_cache(settings.ml_cache_dir)  # before rembg/transformers (VIS-REQ-008)
        from ml.device import resolve_device
        from ml.garment_parse import build_parser

        device = resolve_device(settings.ml_device)
        evaluated, skipped, results = evaluate(
            photos,
            methods,
            out_dir,
            matter_factory=lambda: BiRefNetMatter(settings),
            parser_factory=lambda key: build_parser(key, settings, device),
            worn_only=args.worn_only,
            mask_modes=mask_modes,
        )
    except EvalSetupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    sheets = write_contact_sheets(evaluated, results, out_dir, max(1, args.sheet_size))
    report = format_report(evaluated, skipped, results, sheets, device=device)
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"written to: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
