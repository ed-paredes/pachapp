"""Eval reporting/parsing tests with synthetic predictions (VIS-REQ-029/030)."""

from __future__ import annotations

import pytest

from ml.eval import (
    EvalError,
    Label,
    Prediction,
    accuracy,
    confusion_matrix,
    format_report,
    misclassified,
    parse_labels,
    timing_stats,
)


def _pred(name: str, cat: str, **kw) -> Prediction:
    base = dict(
        filename=name,
        category=cat,
        category_confidence=0.9,
        subcategory="x",
        pattern="solid",
        formality=2,
        needs_review=False,
    )
    base.update(kw)
    return Prediction(**base)  # type: ignore[arg-type]


LABELS = {
    "a.jpg": Label("top", "t-shirt", "solid", 2),
    "b.jpg": Label("bottom", None, None, 4),
    "c.jpg": Label(None, None, None, None),
    "d.jpg": Label("shoes", "boots", "solid", 3),
}
PREDS = [
    _pred("a.jpg", "top", subcategory="T-Shirt"),
    _pred("b.jpg", "top", formality=3),
    _pred("c.jpg", "top"),
    _pred("d.jpg", "shoes", formality=3, needs_review=True),
]


def test_accuracy_skips_unlabeled() -> None:
    assert accuracy(LABELS, PREDS, "category") == (2, 3)
    assert accuracy(LABELS, PREDS, "subcategory") == (1, 2)  # case-insensitive
    assert accuracy(LABELS, PREDS, "pattern") == (2, 2)
    assert accuracy(LABELS, PREDS, "formality") == (2, 3)
    assert accuracy(LABELS, PREDS, "formality", tolerance=1) == (3, 3)


def test_confusion_matrix_rows_true_cols_pred() -> None:
    classes = ["top", "bottom", "shoes"]
    assert confusion_matrix(LABELS, PREDS, classes) == [[1, 0, 0], [1, 0, 0], [0, 0, 1]]


def test_misclassified_lists_true_to_pred() -> None:
    assert misclassified(LABELS, PREDS) == ["b.jpg: bottom -> top (confidence 0.90)"]


def test_timing_stats_exclude_first() -> None:
    assert timing_stats([100.0, 1.0, 3.0]) == (2.0, 2.0)
    assert timing_stats([5.0]) == (0.0, 0.0)


def test_format_report_contains_sections() -> None:
    preds = [p for p in PREDS]
    preds[0].empty_cutout = True
    report = format_report(LABELS, preds)
    assert "category" in report and "(2/3)" in report
    assert "needs_review: 1/4 (25.0 %)" in report
    assert "Empty cutouts (fell back to full image): 1" in report
    assert "b.jpg: bottom -> top" in report
    assert "confusion matrix" in report
    assert "low-confidence by attribute" in report
    assert "(trigger attributes: category, pattern)" in report
    assert "material 0 (no review)" in report
    assert "category 0," in report


def test_parse_labels_ok() -> None:
    out = parse_labels({"a.jpg": {"category": "top", "formality": 3, "pattern": None}}, ["a.jpg"])
    assert out["a.jpg"] == Label("top", None, None, 3)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"a.jpg": {"category": "hat"}}, "unknown category 'hat'"),
        ({"a.jpg": {"pattern": "dotted"}}, "unknown pattern"),
        ({"a.jpg": {"formality": 6}}, "formality must be an integer 1-5"),
        ({"a.jpg": {"color": "red"}}, "unknown label keys"),
        ({"zzz.jpg": {"category": "top"}}, "missing files: zzz.jpg"),
        ([], "must be a JSON object"),
    ],
)
def test_parse_labels_errors(raw: object, message: str) -> None:
    with pytest.raises(EvalError, match=message):
        parse_labels(raw, ["a.jpg"])


def test_report_includes_throughput_only_when_wall_time_is_recorded() -> None:
    assert "Throughput" not in format_report(LABELS, PREDS)
    timed = [_pred(f"{i}.jpg", "top", wall_s=w) for i, w in enumerate([9.0, 0.5, 0.5, 0.5])]
    report = format_report({}, timed)
    assert "Throughput (wall, excluding first): 2.00 garments/s (0.500 s/garment)" in report
