"""SCHP network, pre/post-processing and parser wiring without weights (VIS-REQ-029)."""

from __future__ import annotations

import numpy as np
import pytest
import torch
from PIL import Image

from ml import schp
from ml.garment_parse import SegformerClothesParser, build_parser
from shared.settings import Settings


def test_abn_uses_abs_weight_plus_eps_and_leaky_relu() -> None:
    abn = schp.ABN(2)
    x = torch.tensor([[[[1.0]], [[-1.0]]]])  # running stats 0/1, so y ~= x * |weight|
    with torch.no_grad():
        abn.weight.copy_(torch.tensor([-2.0, 1.0]))
        out = abn(x)
        plain = schp.ABN(2, activation=False)(x)
    assert out[0, 0, 0, 0] == pytest.approx(2.0, abs=1e-3)
    assert out[0, 1, 0, 0] == pytest.approx(-0.01, abs=1e-3)  # leaky slope 0.01
    assert plain[0, 1, 0, 0] == pytest.approx(-1.0, abs=1e-3)


def test_network_matches_checkpoint_layout_and_output_shape() -> None:
    net = schp.SchpNet(18).eval()
    keys = set(net.state_dict())
    for expected in (
        "conv1.weight",
        "bn1.running_var",
        "layer1.0.downsample.1.weight",
        "layer3.22.conv3.weight",
        "context_encoding.stages.0.1.weight",
        "context_encoding.stages.3.2.running_mean",
        "context_encoding.bottleneck.1.bias",
        "edge.conv4.bias",
        "edge.conv5.weight",
        "decoder.conv3.3.weight",
        "decoder.conv4.bias",
        "fushion.0.weight",
        "fushion.1.weight",
        "fushion.3.bias",
    ):
        assert expected in keys
    assert not any(k.endswith("num_batches_tracked") for k in keys)
    with torch.no_grad():
        out = net(torch.zeros(1, 3, 64, 64))
    assert out.shape == (1, 18, 16, 16)  # 1/4 of the input, one logit map per class


def test_schp_input_pads_to_square_and_normalises_bgr() -> None:
    rgb = Image.new("RGB", (4, 2), (255, 0, 0))  # red, landscape
    arr = schp.schp_input(rgb, 8)
    assert arr.shape == (3, 8, 8) and arr.dtype == np.float32
    black = (0 - np.asarray(schp.BGR_MEAN)) / np.asarray(schp.BGR_STD)
    assert arr[0, 0, 0] == pytest.approx(black[0], abs=1e-5)  # padding row is black
    # centre pixel is red: BGR order puts red in channel 2
    assert arr[2, 4, 4] == pytest.approx((1 - schp.BGR_MEAN[2]) / schp.BGR_STD[2], abs=1e-5)
    assert arr[0, 4, 4] == pytest.approx(black[0], abs=1e-5)


def test_labels_from_logits_crops_padding_and_resizes_to_photo() -> None:
    # 8 x 8 logits, 3 classes; a 4 x 2 photo occupies rows 2..5 of the square
    logits = torch.zeros(1, 3, 8, 8)
    logits[0, 1, :, :4] = 5.0  # left half -> class 1
    logits[0, 2, :, 4:] = 5.0  # right half -> class 2
    labels = schp.labels_from_logits(logits, 4, 2)
    assert labels.shape == (2, 4) and labels.dtype == np.uint8
    assert labels[:, :2].tolist() == [[1, 1], [1, 1]] and labels[:, 2:].tolist() == [[2, 2], [2, 2]]


def test_labels_from_logits_caps_work_size_but_keeps_photo_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(schp, "MAX_LABEL_SIDE", 4)
    logits = torch.zeros(1, 2, 8, 8)
    logits[0, 1] = 1.0
    labels = schp.labels_from_logits(logits, 16, 8)
    assert labels.shape == (8, 16) and set(np.unique(labels)) == {1}


def test_schp_parser_vocabulary_and_pin_requirement() -> None:
    parser = schp.SchpParser("atr", revision=None)
    assert parser.name == "schp-atr" and parser._names[4] == "upper_clothes"
    with pytest.raises(ValueError, match="PACHAPP_ML_PARSE_SCHP_REVISION"):
        parser._checkpoint()
    with pytest.raises(ValueError, match="unknown SCHP variant"):
        schp.SchpParser("pascal", revision="x")


def test_sha256_of(tmp_path) -> None:  # noqa: ANN001
    f = tmp_path / "x.bin"
    f.write_bytes(b"abc")
    assert schp.sha256_of(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_build_parser_fashn_and_schp_use_pinned_settings(tmp_path) -> None:  # noqa: ANN001
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        data_dir=tmp_path / "d",
        ml_embed_revision="r",
        ml_parse_fashn_revision="a" * 40,
        ml_parse_schp_revision="b" * 40,
    )
    fashn = build_parser("fashn", settings, "cpu")
    assert isinstance(fashn, SegformerClothesParser)
    assert fashn.model_id == "fashn-ai/fashn-human-parser" and fashn.revision == "a" * 40
    lip = build_parser("schp-lip", settings, "cpu")
    assert lip.name == "schp-lip" and lip.revision == "b" * 40
    with pytest.raises(ValueError, match="unknown parser"):
        build_parser("nope", settings, "cpu")


def test_moving_schp_revision_is_rejected(tmp_path) -> None:  # noqa: ANN001
    with pytest.raises(ValueError, match="PACHAPP_ML_PARSE_SCHP_REVISION"):
        Settings(
            _env_file=None,  # type: ignore[call-arg]
            data_dir=tmp_path / "d",
            ml_embed_revision="r",
            ml_parse_schp_revision="main",
        )
