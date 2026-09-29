"""Eval reporting/parsing tests with synthetic predictions (VIS-REQ-029/030)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from PIL import Image

import ml.eval as ml_eval
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
from shared.settings import Settings


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
    preds = [dataclasses.replace(p) for p in PREDS]
    preds[0] = dataclasses.replace(preds[0], empty_cutout=True)
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


def test_report_labels_pipelined_cutout_time_distinctly() -> None:
    sequential = format_report(LABELS, PREDS)
    pipelined = format_report(LABELS, PREDS, pipelined=True)
    assert "cutout wait (pipelined):" not in sequential
    assert "cutout wait (pipelined):" in pipelined
    assert "not comparable with a sequential report" in pipelined


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"a.jpg": {"category": ["top"]}}, "category must be a string"),
        ({"a.jpg": {"pattern": {"x": 1}}}, "pattern must be a string"),
    ],
)
def test_parse_labels_rejects_unhashable_values(raw: object, message: str) -> None:
    with pytest.raises(EvalError, match=message):
        parse_labels(raw, ["a.jpg"])


# --- main() control flow (the evaluate function is faked; no models) ---------------


@pytest.fixture
def cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Run `ml.eval.main` with fake settings and a fake `_evaluate`; returns
    `(run, calls)` where `calls` records the photos each evaluation received."""
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        data_dir=tmp_path / "data",
        ml_embed_revision="test-revision",
    )
    monkeypatch.setattr(ml_eval, "get_settings", lambda: settings)
    monkeypatch.setattr(ml_eval, "configure_model_cache", lambda _dir: None)
    calls: list[dict] = []

    def fake_evaluate(images, *, use_cutout, pipeline, settings):
        calls.append({"names": [p.name for p in images], "cutout": use_cutout, "pipe": pipeline})
        return [_pred(p.name, "top") for p in images]

    monkeypatch.setattr(ml_eval, "_evaluate", fake_evaluate)
    return ml_eval.main, calls


def _make_dir(root: Path, names: list[str], labels: object | None) -> Path:
    root.mkdir()
    for name in names:
        Image.new("RGB", (4, 4)).save(root / name)
    if labels is not None:
        (root / "labels.json").write_text(json.dumps(labels), encoding="utf-8")
    return root


def test_main_missing_dir_exits_1(cli, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run, calls = cli
    assert run([str(tmp_path / "nope")]) == 1
    assert "error: Eval directory not found" in capsys.readouterr().err
    assert calls == []


def test_main_missing_labels_exits_1(
    cli, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run, calls = cli
    d = _make_dir(tmp_path / "d", ["a.png"], None)
    assert run([str(d)]) == 1
    assert "error: labels.json not found" in capsys.readouterr().err
    assert calls == []


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"{not json", "not valid JSON"),
        (b"\xff\xfe\x00garbage", "not valid UTF-8"),
        (b"[]", "must be a JSON object"),
        (b'{"a.png": {"category": ["top"]}}', "category must be a string"),
    ],
)
def test_main_invalid_labels_exits_1(
    cli, tmp_path: Path, capsys: pytest.CaptureFixture[str], content: bytes, message: str
) -> None:
    run, calls = cli
    d = _make_dir(tmp_path / "d", ["a.png"], None)
    (d / "labels.json").write_bytes(content)
    assert run([str(d)]) == 1
    assert message in capsys.readouterr().err
    assert calls == []


def test_main_no_photos_exits_1(cli, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run, calls = cli
    d = _make_dir(tmp_path / "d", [], {})
    assert run([str(d)]) == 1
    assert "error: no photos" in capsys.readouterr().err
    assert calls == []


def test_main_limit_filters_photos_and_labels(
    cli, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run, calls = cli
    labels = {n: {"category": "top"} for n in ("a.png", "b.png", "c.png")}
    d = _make_dir(tmp_path / "d", list(labels), labels)
    assert run([str(d), "--limit", "2", "--no-cutout", "--pipeline"]) == 0
    assert calls == [{"names": ["a.png", "b.png"], "cutout": False, "pipe": True}]
    assert "Photos evaluated: 2 (2 labeled)" in capsys.readouterr().out


@pytest.mark.parametrize("value", ["0", "-3", "x"])
def test_main_rejects_non_positive_limit(
    cli, tmp_path: Path, capsys: pytest.CaptureFixture[str], value: str
) -> None:
    run, calls = cli
    d = _make_dir(tmp_path / "d", ["a.png"], {})
    with pytest.raises(SystemExit) as exc:
        run([str(d), "--limit", value])
    assert exc.value.code == 2
    assert "--limit" in capsys.readouterr().err
    assert calls == []


def test_main_without_gate_exits_0_even_with_low_accuracy(cli, tmp_path: Path) -> None:
    run, _ = cli
    d = _make_dir(tmp_path / "d", ["a.png"], {"a.png": {"category": "bottom"}})
    assert run([str(d)]) == 0  # predicted "top", labeled "bottom": no gate -> exit 0


def test_main_gate_passes(cli, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run, _ = cli
    d = _make_dir(
        tmp_path / "d", ["a.png", "b.png"], {n: {"category": "top"} for n in ("a.png", "b.png")}
    )
    assert run([str(d), "--min-category-accuracy", "0.85"]) == 0
    assert "gate passed: category accuracy 100.0 %" in capsys.readouterr().out


def test_main_gate_fails_after_printing_report(
    cli, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run, _ = cli
    labels = {"a.png": {"category": "top"}, "b.png": {"category": "bottom"}}
    d = _make_dir(tmp_path / "d", list(labels), labels)
    assert run([str(d), "--min-category-accuracy", "0.85"]) == 2
    captured = capsys.readouterr()
    assert "Accuracy per attribute" in captured.out
    assert "gate failed: category accuracy 50.0 % is below the required 85.0 %" in captured.err


def test_main_gate_without_category_labels_fails(cli, tmp_path: Path) -> None:
    run, _ = cli
    d = _make_dir(tmp_path / "d", ["a.png"], {})
    assert run([str(d), "--min-category-accuracy", "0.5"]) == 2


@pytest.mark.parametrize("value", ["1.5", "-0.1", "abc"])
def test_main_rejects_invalid_gate_value(cli, tmp_path: Path, value: str) -> None:
    run, _ = cli
    d = _make_dir(tmp_path / "d", ["a.png"], {})
    with pytest.raises(SystemExit) as exc:
        run([str(d), "--min-category-accuracy", value])
    assert exc.value.code == 2


def test_main_without_any_eval_dir_exits_1(
    cli, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run, calls = cli
    settings = ml_eval.get_settings()
    monkeypatch.setattr(settings, "ml_eval_dir", None)
    assert run([]) == 1
    assert "error: no eval directory" in capsys.readouterr().err
    assert calls == []
