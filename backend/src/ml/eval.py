"""CLI: evaluate the zero-shot pipeline on labeled photos (08-local-vision.md
VIS-REQ-028/VIS-REQ-030, step 3 gate: >= 85 % `category` accuracy without kNN).

Usage: `python -m ml.eval [EVAL_DIR] [--no-cutout] [--limit N]` (wired up as
`make ml-eval`). `EVAL_DIR` defaults to `PACHAPP_ML_EVAL_DIR`; it holds
`*.jpg/*.jpeg/*.png` photos plus a `labels.json`:

    {"<filename>": {"category": "top", "subcategory": "t-shirt",
                    "pattern": "solid", "formality": 2}}

`null` (or a missing key) means "unlabeled" and is skipped for that attribute.
Per photo: BiRefNet cutout (an `EmptyCutoutError` falls back to the full image
and is counted) -> embed -> zero-shot. The reporting helpers are pure so they
can be unit-tested with synthetic predictions (VIS-REQ-029).
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ml.cache import configure_model_cache
from ml.zero_shot import REVIEW_ATTRIBUTES
from shared.enums import GarmentCategory, GarmentPattern
from shared.settings import get_settings

_EXTENSIONS = {".jpg", ".jpeg", ".png"}
LABELED_ATTRIBUTES = ("category", "subcategory", "pattern", "formality")


class EvalError(Exception):
    """A user-facing evaluation setup error (missing dir, bad labels)."""


@dataclass(frozen=True)
class Label:
    category: str | None = None
    subcategory: str | None = None
    pattern: str | None = None
    formality: int | None = None


@dataclass
class Prediction:
    filename: str
    category: str
    category_confidence: float
    subcategory: str
    pattern: str
    formality: int
    needs_review: bool
    low_confidence: tuple[str, ...] = ()
    cutout_s: float = 0.0
    embed_s: float = 0.0  # embed + classify
    empty_cutout: bool = False


def find_images(eval_dir: Path) -> list[Path]:
    return sorted(p for p in eval_dir.iterdir() if p.is_file() and p.suffix.lower() in _EXTENSIONS)


def parse_labels(raw: object, available_files: Sequence[str]) -> dict[str, Label]:
    """Validate a decoded `labels.json`; raises `EvalError` with a clear message."""
    if not isinstance(raw, dict):
        raise EvalError("labels.json must be a JSON object mapping filename -> labels")
    missing = sorted(set(raw) - set(available_files))
    if missing:
        raise EvalError(f"labels.json references missing files: {', '.join(missing)}")
    categories = {c.value for c in GarmentCategory}
    patterns = {p.value for p in GarmentPattern}
    out: dict[str, Label] = {}
    for name, entry in raw.items():
        if not isinstance(entry, dict):
            raise EvalError(f"{name}: labels must be an object")
        unknown = set(entry) - set(LABELED_ATTRIBUTES)
        if unknown:
            raise EvalError(f"{name}: unknown label keys: {', '.join(sorted(unknown))}")
        category = entry.get("category")
        if category is not None and category not in categories:
            raise EvalError(
                f"{name}: unknown category {category!r} (allowed: {sorted(categories)})"
            )
        pattern = entry.get("pattern")
        if pattern is not None and pattern not in patterns:
            raise EvalError(f"{name}: unknown pattern {pattern!r} (allowed: {sorted(patterns)})")
        formality = entry.get("formality")
        if formality is not None and (
            isinstance(formality, bool) or not isinstance(formality, int) or not 1 <= formality <= 5
        ):
            raise EvalError(f"{name}: formality must be an integer 1-5, got {formality!r}")
        sub = entry.get("subcategory")
        if sub is not None and not isinstance(sub, str):
            raise EvalError(f"{name}: subcategory must be a string, got {sub!r}")
        out[name] = Label(category, sub, pattern, formality)
    return out


def load_labels(eval_dir: Path, images: Sequence[Path]) -> dict[str, Label]:
    if not eval_dir.is_dir():
        raise EvalError(f"Eval directory not found: {eval_dir}")
    labels_path = eval_dir / "labels.json"
    if not labels_path.is_file():
        raise EvalError(f"labels.json not found in {eval_dir}")
    try:
        raw = json.loads(labels_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvalError(f"labels.json is not valid JSON: {exc}") from exc
    return parse_labels(raw, [p.name for p in images])


def _true_value(label: Label, attribute: str) -> str | int | None:
    return getattr(label, attribute)


def _pred_value(pred: Prediction, attribute: str) -> str | int:
    return getattr(pred, attribute)


def accuracy(
    labels: dict[str, Label], preds: Sequence[Prediction], attribute: str, *, tolerance: int = 0
) -> tuple[int, int]:
    """`(correct, labeled_total)` for `attribute`. Strings compare case-insensitively;
    integers (formality) are correct when `|pred - true| <= tolerance`."""
    correct = total = 0
    for pred in preds:
        label = labels.get(pred.filename)
        truth = _true_value(label, attribute) if label else None
        if truth is None:
            continue
        total += 1
        got = _pred_value(pred, attribute)
        if isinstance(truth, int) and isinstance(got, int):
            correct += abs(got - truth) <= tolerance
        else:
            correct += str(got).lower() == str(truth).lower()
    return correct, total


def confusion_matrix(
    labels: dict[str, Label], preds: Sequence[Prediction], classes: Sequence[str]
) -> list[list[int]]:
    """Rows = true category, cols = predicted, over `classes`; predictions
    outside `classes` are ignored (callers pass every category present)."""
    index = {c: i for i, c in enumerate(classes)}
    matrix = [[0] * len(classes) for _ in classes]
    for pred in preds:
        label = labels.get(pred.filename)
        if label is None or label.category is None:
            continue
        if label.category in index and pred.category in index:
            matrix[index[label.category]][index[pred.category]] += 1
    return matrix


def format_confusion(matrix: list[list[int]], classes: Sequence[str]) -> str:
    width = max([len(c) for c in classes] + [5])
    header = " " * width + " | " + " ".join(c.rjust(width) for c in classes)
    lines = [header, "-" * len(header)]
    for cls, row in zip(classes, matrix, strict=True):
        lines.append(cls.ljust(width) + " | " + " ".join(str(n).rjust(width) for n in row))
    return "\n".join(lines)


def timing_stats(values: Sequence[float]) -> tuple[float, float]:
    """`(mean, median)` in the same unit, excluding the first sample (warm-up);
    `(0, 0)` when there is nothing left."""
    rest = list(values[1:])
    if not rest:
        return 0.0, 0.0
    return statistics.fmean(rest), statistics.median(rest)


def misclassified(labels: dict[str, Label], preds: Sequence[Prediction]) -> list[str]:
    lines = []
    for pred in preds:
        label = labels.get(pred.filename)
        if label and label.category is not None and label.category != pred.category:
            lines.append(
                f"{pred.filename}: {label.category} -> {pred.category} "
                f"(confidence {pred.category_confidence:.2f})"
            )
    return lines


def format_report(
    labels: dict[str, Label], preds: Sequence[Prediction], *, cutout_enabled: bool = True
) -> str:
    out = [f"Photos evaluated: {len(preds)} ({len(labels)} labeled)", "", "Accuracy per attribute:"]
    for attr in LABELED_ATTRIBUTES:
        correct, total = accuracy(labels, preds, attr)
        pct = f"{100 * correct / total:.1f} %" if total else "n/a"
        extra = ""
        if attr == "formality":
            c1, t1 = accuracy(labels, preds, attr, tolerance=1)
            extra = f"  (within +-1: {100 * c1 / t1:.1f} %)" if t1 else ""
        out.append(f"  {attr:<12} {pct:>8}  ({correct}/{total}){extra}")

    present = {
        x
        for pred in preds
        for x in (
            pred.category,
            labels[pred.filename].category if pred.filename in labels else None,
        )
        if x
    }
    classes = [c.value for c in GarmentCategory if c.value in present]
    out += ["", "Category confusion matrix (rows = true, cols = predicted):"]
    out.append(format_confusion(confusion_matrix(labels, preds, classes), classes))

    n = len(preds)
    review = sum(p.needs_review for p in preds)
    out += [
        "",
        f"needs_review: {review}/{n} ({100 * review / n:.1f} %)" if n else "needs_review: n/a",
    ]

    by_attr = {a: sum(a in p.low_confidence for p in preds) for a in REVIEW_ATTRIBUTES}
    out.append(
        "  low-confidence by attribute: " + ", ".join(f"{a} {c}" for a, c in by_attr.items())
    )

    cut_mean, cut_med = timing_stats([p.cutout_s for p in preds])
    emb_mean, emb_med = timing_stats([p.embed_s for p in preds])
    tot_mean, tot_med = timing_stats([p.cutout_s + p.embed_s for p in preds])
    out += ["", "Time per garment (excluding first / warm-up), seconds:"]
    out.append(f"  cutout:         mean {cut_mean:.3f}  median {cut_med:.3f}")
    out.append(f"  embed+classify: mean {emb_mean:.3f}  median {emb_med:.3f}")
    out.append(f"  total:          mean {tot_mean:.3f}  median {tot_med:.3f}")
    if not cutout_enabled:
        out.append("  (cutout disabled: --no-cutout)")

    out.append(f"Empty cutouts (fell back to full image): {sum(p.empty_cutout for p in preds)}")
    wrong = misclassified(labels, preds)
    out += ["", f"Misclassified category ({len(wrong)}):"]
    out += [f"  {line}" for line in wrong] or ["  none"]
    return "\n".join(out)


def _evaluate(
    images: Sequence[Path], *, use_cutout: bool, settings
) -> list[Prediction]:  # pragma: no cover - needs real models
    from PIL import Image

    from ml.background import BiRefNetRemover, EmptyCutoutError
    from ml.registry import get_embedder
    from ml.zero_shot import ZeroShotClassifier

    embedder = get_embedder(settings)
    classifier = ZeroShotClassifier(embedder, margin_threshold=settings.ml_margin_threshold)
    remover = BiRefNetRemover(settings) if use_cutout else None
    preds = []
    for path in images:
        with Image.open(path) as opened:
            img = opened.copy()
        empty = False
        t0 = time.perf_counter()
        if remover is not None:
            try:
                img = remover.remove(img)
            except EmptyCutoutError:
                empty = True
        t1 = time.perf_counter()
        result = classifier.classify(embedder.embed_image(img))
        t2 = time.perf_counter()
        p = result.predictions
        formality = p["formality"].value
        assert isinstance(formality, int)
        preds.append(
            Prediction(
                filename=path.name,
                category=str(p["category"].value),
                category_confidence=p["category"].confidence,
                subcategory=str(p["subcategory"].value),
                pattern=str(p["pattern"].value),
                formality=formality,
                needs_review=result.needs_review or empty,
                low_confidence=tuple(result.low_confidence),
                cutout_s=t1 - t0,
                embed_s=t2 - t1,
                empty_cutout=empty,
            )
        )
        print(f"[{len(preds)}/{len(images)}] {path.name}: {preds[-1].category}", flush=True)
    return preds


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ml.eval", description=__doc__)
    parser.add_argument("eval_dir", nargs="?", type=Path, default=None)
    parser.add_argument("--no-cutout", action="store_true", help="skip background removal")
    parser.add_argument("--limit", type=int, default=None, help="evaluate only the first N photos")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING)
    settings = get_settings()
    eval_dir = args.eval_dir or settings.ml_eval_dir
    assert eval_dir is not None and settings.ml_cache_dir is not None
    eval_dir = Path(eval_dir).expanduser()

    try:
        images = find_images(eval_dir) if eval_dir.is_dir() else []
        labels = load_labels(eval_dir, images)
    except EvalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.limit is not None:
        images = images[: args.limit]
        labels = {k: v for k, v in labels.items() if k in {p.name for p in images}}
    if not images:
        print(f"error: no photos (*.jpg, *.jpeg, *.png) in {eval_dir}", file=sys.stderr)
        return 1

    configure_model_cache(settings.ml_cache_dir)
    preds = _evaluate(images, use_cutout=not args.no_cutout, settings=settings)
    print()
    print(format_report(labels, preds, cutout_enabled=not args.no_cutout))
    return 0


if __name__ == "__main__":
    sys.exit(main())
