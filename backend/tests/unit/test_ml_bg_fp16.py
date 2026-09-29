"""Unit tests for `ml.bg_fp16` (08-local-vision.md, VIS-REQ-026/029): a tiny
synthetic ONNX graph stands in for BiRefNet; no torch, no model, no network."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import onnx
import pytest
from onnx import TensorProto, helper, numpy_helper

from ml.bg_fp16 import ensure_fp16_model, fp16_path, model_precision, should_use_fp16


@pytest.mark.parametrize(
    ("device", "enabled", "expected"),
    [
        ("cuda", True, True),
        ("cuda", False, False),
        ("cpu", True, False),
        ("mps", True, False),
        ("cpu", False, False),
    ],
)
def test_should_use_fp16(device: str, enabled: bool, expected: bool) -> None:
    assert should_use_fp16(device, fp16_enabled=enabled) is expected


def test_fp16_path_is_next_to_the_fp32_file() -> None:
    src = Path("/cache/models/birefnet-general-lite/birefnet-general-lite.onnx")

    dst = fp16_path(src)

    assert dst == Path("/cache/models/birefnet-general-lite/birefnet-general-lite.fp16.onnx")
    assert model_precision(dst) == "fp16"
    assert model_precision(src) == "fp32"


def _write_tiny_model(path: Path) -> None:
    """y = MatMul(x, W) with a float32 initializer W."""
    weight = numpy_helper.from_array(np.ones((4, 4), dtype=np.float32), name="W")
    node = helper.make_node("MatMul", ["x", "W"], ["y"])
    graph = helper.make_graph(
        [node],
        "tiny",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 4])],
        [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 4])],
        initializer=[weight],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9
    onnx.save(model, str(path))


def test_ensure_fp16_model_converts_weights_but_keeps_float32_io(tmp_path: Path) -> None:
    src = tmp_path / "m.onnx"
    _write_tiny_model(src)
    dst = fp16_path(src)

    assert ensure_fp16_model(src, dst) == dst

    converted = onnx.load(str(dst))
    assert all(i.data_type == TensorProto.FLOAT16 for i in converted.graph.initializer)
    assert converted.graph.input[0].type.tensor_type.elem_type == TensorProto.FLOAT
    assert converted.graph.output[0].type.tensor_type.elem_type == TensorProto.FLOAT
    assert [p.name for p in tmp_path.iterdir() if ".tmp" in p.name] == []


def test_ensure_fp16_model_is_idempotent(tmp_path: Path) -> None:
    src = tmp_path / "m.onnx"
    _write_tiny_model(src)
    dst = fp16_path(src)
    ensure_fp16_model(src, dst)
    os.utime(dst, (1, 4_000_000_000))  # newer than src, distinctive mtime
    before = dst.stat().st_mtime_ns

    ensure_fp16_model(src, dst)

    assert dst.stat().st_mtime_ns == before


def test_ensure_fp16_model_reconverts_empty_or_stale_output(tmp_path: Path) -> None:
    src = tmp_path / "m.onnx"
    _write_tiny_model(src)
    dst = fp16_path(src)
    dst.write_bytes(b"")

    ensure_fp16_model(src, dst)
    assert dst.stat().st_size > 0

    os.utime(dst, (1, 1))  # older than src
    ensure_fp16_model(src, dst)
    assert dst.stat().st_mtime > 1
