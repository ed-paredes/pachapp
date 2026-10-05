"""SCHP (Self-Correction for Human Parsing) inference, pure PyTorch (U5b2).

SCHP is not in `transformers`, and its reference code needs the compiled
`inplace_abn` CUDA extension. This module re-implements the inference path only:

- The network (ResNet-101 + PSP context encoding + edge branch + decoder + fusion) is
  the `AugmentCE2P` definition of the original repo, with `InPlaceABNSync` replaced by
  `ABN` below (batch norm in eval mode + leaky ReLU, same maths, no compiled code).
  Parameter names match the official checkpoints, so they load with `strict=True`.
- Pre/post-processing follows `simple_extractor.py` (BGR input, the repo's mean/std,
  person box = whole image padded to the model's aspect ratio) without OpenCV.

Attribution: network structure and constants derive from
https://github.com/GoGoDuck912/Self-Correction-Human-Parsing (MIT, Copyright (c) 2020
Peike Li), as repackaged for inference by https://github.com/Zheng-Chong/CatVTON, whose
Hugging Face repo `zhengchong/CatVTON` hosts the checkpoints loaded here (those files
carry CC BY-NC-SA 4.0 there; non-commercial, like the other parsers in the evaluation).

MIT licence notice of the original code:

    Permission is hereby granted, free of charge, to any person obtaining a copy of this
    software and associated documentation files (the "Software"), to deal in the
    Software without restriction, including without limitation the rights to use, copy,
    modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
    and to permit persons to whom the Software is furnished to do so, subject to the
    following conditions: The above copyright notice and this permission notice shall be
    included in all copies or substantial portions of the Software. THE SOFTWARE IS
    PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.

Importing this module imports torch; `ml.garment_parse.build_parser` imports it lazily.
Checkpoints are downloaded once into the Hugging Face cache (configure it with
`ml.cache.configure_model_cache` first, VIS-REQ-008) at a pinned revision and verified
against the sha256 below before they are unpickled.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image
from torch import nn
from torch.nn import functional

from ml.garment_parse import ParseResult, _free_gpu, normalize_label

logger = logging.getLogger(__name__)

SCHP_REPO = "zhengchong/CatVTON"

# variant -> (file in the repo, sha256, input size, label list). Labels and sizes are
# the `dataset_settings` of the SCHP repo.
SCHP_VARIANTS: dict[str, dict[str, Any]] = {
    "atr": {
        "file": "SCHP/exp-schp-201908301523-atr.pth",
        "sha256": "e9d7c91ce3b4e7133df56b599fc817b533e3439c5e8d282a59126d2fda339a2a",
        "input_size": 512,
        "labels": [
            "Background",
            "Hat",
            "Hair",
            "Sunglasses",
            "Upper-clothes",
            "Skirt",
            "Pants",
            "Dress",
            "Belt",
            "Left-shoe",
            "Right-shoe",
            "Face",
            "Left-leg",
            "Right-leg",
            "Left-arm",
            "Right-arm",
            "Bag",
            "Scarf",
        ],
    },
    "lip": {
        "file": "SCHP/exp-schp-201908261155-lip.pth",
        "sha256": "24fa3254ceeb74c8435458994a64b522fb439a3635b7b86ff470457e0413da00",
        "input_size": 473,
        "labels": [
            "Background",
            "Hat",
            "Hair",
            "Glove",
            "Sunglasses",
            "Upper-clothes",
            "Dress",
            "Coat",
            "Socks",
            "Pants",
            "Jumpsuits",
            "Scarf",
            "Skirt",
            "Face",
            "Left-arm",
            "Right-arm",
            "Left-leg",
            "Right-leg",
            "Left-shoe",
            "Right-shoe",
        ],
    },
}
# SCHP feeds BGR images scaled to [0, 1] and normalised with these (BGR-ordered) values.
BGR_MEAN = (0.406, 0.456, 0.485)
BGR_STD = (0.225, 0.224, 0.229)
# Logits are argmax-ed at most this many pixels on the long side, then the label map is
# resized (nearest) to the photo: avoids a classes x H x W float tensor for 12 MP photos.
MAX_LABEL_SIDE = 1024


# --- network (inference only) --------------------------------------------------------


class ABN(nn.Module):
    """Batch norm (running statistics) + optional leaky ReLU: `InPlaceABNSync` at inference.

    As in the compiled op, the scale is `abs(weight) + eps`.
    """

    def __init__(self, num_features: int, eps: float = 1e-5, activation: bool = True) -> None:
        super().__init__()
        self.eps = eps
        self.activation = activation
        self.weight = nn.Parameter(torch.ones(num_features))
        self.bias = nn.Parameter(torch.zeros(num_features))
        self.running_mean: torch.Tensor
        self.running_var: torch.Tensor
        self.register_buffer("running_mean", torch.zeros(num_features))
        self.register_buffer("running_var", torch.ones(num_features))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = functional.batch_norm(
            x,
            self.running_mean,
            self.running_var,
            self.weight.abs() + self.eps,
            self.bias,
            training=False,
            eps=self.eps,
        )
        return functional.leaky_relu(x, 0.01) if self.activation else x


def _conv(cin: int, cout: int, k: int = 1, *, bias: bool = False, dilation: int = 1) -> nn.Conv2d:
    padding = dilation * (k // 2)
    return nn.Conv2d(cin, cout, k, padding=padding, dilation=dilation, bias=bias)


class Bottleneck(nn.Module):
    expansion = 4

    def __init__(
        self,
        inplanes: int,
        planes: int,
        stride: int = 1,
        dilation: int = 1,
        downsample: nn.Module | None = None,
        multi_grid: int = 1,
    ) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(inplanes, planes, 1, bias=False)
        self.bn1 = ABN(planes, activation=False)
        self.conv2 = nn.Conv2d(
            planes,
            planes,
            3,
            stride=stride,
            padding=dilation * multi_grid,
            dilation=dilation * multi_grid,
            bias=False,
        )
        self.bn2 = ABN(planes, activation=False)
        self.conv3 = nn.Conv2d(planes, planes * 4, 1, bias=False)
        self.bn3 = ABN(planes * 4, activation=False)
        self.downsample = downsample

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = functional.relu(self.bn1(self.conv1(x)))
        out = functional.relu(self.bn2(self.conv2(out)))
        out = self.bn3(self.conv3(out))
        residual = x if self.downsample is None else self.downsample(x)
        return functional.relu(out + residual)


class PSPModule(nn.Module):
    def __init__(
        self, features: int, out_features: int = 512, sizes: tuple[int, ...] = (1, 2, 3, 6)
    ) -> None:
        super().__init__()
        self.stages = nn.ModuleList(
            nn.Sequential(
                nn.AdaptiveAvgPool2d((s, s)), _conv(features, out_features), ABN(out_features)
            )
            for s in sizes
        )
        self.bottleneck = nn.Sequential(
            _conv(features + len(sizes) * out_features, out_features, 3), ABN(out_features)
        )

    def forward(self, feats: torch.Tensor) -> torch.Tensor:
        h, w = feats.shape[2:]
        priors = [
            functional.interpolate(stage(feats), size=(h, w), mode="bilinear", align_corners=True)
            for stage in self.stages
        ]
        return self.bottleneck(torch.cat([*priors, feats], 1))


class EdgeModule(nn.Module):
    def __init__(self, in_fea: tuple[int, int, int] = (256, 512, 1024), mid_fea: int = 256) -> None:
        super().__init__()
        self.conv1 = nn.Sequential(_conv(in_fea[0], mid_fea), ABN(mid_fea))
        self.conv2 = nn.Sequential(_conv(in_fea[1], mid_fea), ABN(mid_fea))
        self.conv3 = nn.Sequential(_conv(in_fea[2], mid_fea), ABN(mid_fea))
        self.conv4 = _conv(mid_fea, 2, 3, bias=True)
        self.conv5 = _conv(6, 2, 1, bias=True)

    def forward(
        self, x1: torch.Tensor, x2: torch.Tensor, x3: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        h, w = x1.shape[2:]
        fea1, fea2, fea3 = self.conv1(x1), self.conv2(x2), self.conv3(x3)
        edge1, edge2, edge3 = self.conv4(fea1), self.conv4(fea2), self.conv4(fea3)

        def up(t: torch.Tensor) -> torch.Tensor:
            return functional.interpolate(t, size=(h, w), mode="bilinear", align_corners=True)

        edge = self.conv5(torch.cat([edge1, up(edge2), up(edge3)], dim=1))
        return edge, torch.cat([fea1, up(fea2), up(fea3)], dim=1)


class DecoderModule(nn.Module):
    def __init__(self, num_classes: int) -> None:
        super().__init__()
        self.conv1 = nn.Sequential(_conv(512, 256), ABN(256))
        self.conv2 = nn.Sequential(_conv(256, 48), ABN(48))
        self.conv3 = nn.Sequential(_conv(304, 256), ABN(256), _conv(256, 256), ABN(256))
        self.conv4 = _conv(256, num_classes, 1, bias=True)

    def forward(self, xt: torch.Tensor, xl: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h, w = xl.shape[2:]
        xt = functional.interpolate(
            self.conv1(xt), size=(h, w), mode="bilinear", align_corners=True
        )
        x = self.conv3(torch.cat([xt, self.conv2(xl)], dim=1))
        return self.conv4(x), x


class SchpNet(nn.Module):
    """`AugmentCE2P` ResNet-101 (the architecture of every released SCHP checkpoint)."""

    def __init__(self, num_classes: int, layers: tuple[int, int, int, int] = (3, 4, 23, 3)) -> None:
        super().__init__()
        self.inplanes = 128
        self.conv1 = nn.Conv2d(3, 64, 3, stride=2, padding=1, bias=False)
        self.bn1 = ABN(64, activation=False)
        self.conv2 = nn.Conv2d(64, 64, 3, padding=1, bias=False)
        self.bn2 = ABN(64, activation=False)
        self.conv3 = nn.Conv2d(64, 128, 3, padding=1, bias=False)
        self.bn3 = ABN(128, activation=False)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)
        self.layer1 = self._make_layer(64, layers[0])
        self.layer2 = self._make_layer(128, layers[1], stride=2)
        self.layer3 = self._make_layer(256, layers[2], stride=2)
        self.layer4 = self._make_layer(512, layers[3], dilation=2, multi_grid=(1, 1, 1))
        self.context_encoding = PSPModule(2048, 512)
        self.edge = EdgeModule()
        self.decoder = DecoderModule(num_classes)
        self.fushion = nn.Sequential(  # (sic) the checkpoints use this spelling
            _conv(1024, 256),
            ABN(256),
            nn.Dropout2d(0.1),
            _conv(256, num_classes, 1, bias=True),
        )

    def _make_layer(
        self,
        planes: int,
        blocks: int,
        stride: int = 1,
        dilation: int = 1,
        multi_grid: tuple[int, ...] | int = 1,
    ) -> nn.Sequential:
        downsample = None
        if stride != 1 or self.inplanes != planes * Bottleneck.expansion:
            downsample = nn.Sequential(
                nn.Conv2d(self.inplanes, planes * 4, 1, stride=stride, bias=False),
                ABN(planes * 4, activation=False),
            )

        def grid(index: int) -> int:
            return multi_grid[index % len(multi_grid)] if isinstance(multi_grid, tuple) else 1

        layers = [Bottleneck(self.inplanes, planes, stride, dilation, downsample, grid(0))]
        self.inplanes = planes * Bottleneck.expansion
        layers += [
            Bottleneck(self.inplanes, planes, dilation=dilation, multi_grid=grid(i))
            for i in range(1, blocks)
        ]
        return nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Fusion-branch logits (B x classes x H/4 x W/4), the ones SCHP evaluates."""
        x = functional.relu(self.bn1(self.conv1(x)))
        x = functional.relu(self.bn2(self.conv2(x)))
        x = functional.relu(self.bn3(self.conv3(x)))
        x2 = self.layer1(self.maxpool(x))
        x3 = self.layer2(x2)
        x4 = self.layer3(x3)
        x5 = self.layer4(x4)
        _, parsing_fea = self.decoder(self.context_encoding(x5), x2)
        _, edge_fea = self.edge(x2, x3, x4)
        return self.fushion(torch.cat([parsing_fea, edge_fea], dim=1))


# --- pre/post-processing (pure numpy / torch, unit-tested) ----------------------------


def square_geometry(width: int, height: int) -> tuple[int, int, int]:
    """(side, left, top): the black square that holds a width x height image centred."""
    side = max(width, height)
    return side, (side - width) // 2, (side - height) // 2


def schp_input(rgb: Image.Image, size: int) -> np.ndarray:
    """Normalised BGR CHW float32 array (3 x size x size) for the network.

    The photo is centred on a black square (SCHP's whole-image person box scaled to the
    model's square aspect ratio) and resized bilinearly; mean/std are the repo's.
    """
    side, left, top = square_geometry(rgb.width, rgb.height)
    canvas = Image.new("RGB", (side, side), (0, 0, 0))
    canvas.paste(rgb.convert("RGB"), (left, top))
    arr = np.asarray(canvas.resize((size, size), Image.Resampling.BILINEAR), dtype=np.float32)
    bgr = arr[..., ::-1] / 255.0
    mean = np.asarray(BGR_MEAN, dtype=np.float32)
    std = np.asarray(BGR_STD, dtype=np.float32)
    return np.ascontiguousarray(((bgr - mean) / std).transpose(2, 0, 1), dtype=np.float32)


def labels_from_logits(logits: torch.Tensor, width: int, height: int) -> np.ndarray:
    """Per-pixel class ids (height x width, uint8) from square model logits (1 x C x S x S).

    The caller upsamples the network output to the square input size; here the padding is
    cropped away, the logits are resized to the photo (long side capped at `MAX_LABEL_SIDE`),
    argmax-ed, and the label map is resized (nearest) to the exact photo size.
    """
    size = logits.shape[-1]
    side, left, top = square_geometry(width, height)
    scale = size / side
    x0, x1 = round(left * scale), max(round((left + width) * scale), round(left * scale) + 1)
    y0, y1 = round(top * scale), max(round((top + height) * scale), round(top * scale) + 1)
    crop = logits[:, :, y0:y1, x0:x1].float()
    shrink = min(1.0, MAX_LABEL_SIDE / max(width, height))
    target = (max(1, round(height * shrink)), max(1, round(width * shrink)))
    resized = functional.interpolate(crop, size=target, mode="bilinear", align_corners=True)
    labels = resized.argmax(dim=1)[0].to("cpu").numpy().astype(np.uint8)
    if labels.shape != (height, width):
        image = Image.fromarray(labels, mode="L").resize((width, height), Image.Resampling.NEAREST)
        labels = np.asarray(image, dtype=np.uint8)
    return labels


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --- parser ---------------------------------------------------------------------------


class SchpParser:
    """SCHP human parser (`atr`: 18 classes, 512 px; `lip`: 20 classes, 473 px)."""

    def __init__(self, variant: str, *, revision: str | None, device: str = "cpu") -> None:
        if variant not in SCHP_VARIANTS:
            raise ValueError(
                f"unknown SCHP variant {variant!r}; choose from {tuple(SCHP_VARIANTS)}"
            )
        self.variant = variant
        self.name = f"schp-{variant}"
        self.revision = revision
        self.device = device
        self._spec = SCHP_VARIANTS[variant]
        self._names = {i: normalize_label(n) for i, n in enumerate(self._spec["labels"])}
        self._model: SchpNet | None = None

    def _checkpoint(self) -> Path:
        if not self.revision:
            raise ValueError(
                f"{self.name} needs a pinned revision of {SCHP_REPO}: set "
                "PACHAPP_ML_PARSE_SCHP_REVISION to a commit hash."
            )
        from huggingface_hub import hf_hub_download

        path = Path(
            hf_hub_download(repo_id=SCHP_REPO, filename=self._spec["file"], revision=self.revision)
        )
        found = sha256_of(path)
        if found != self._spec["sha256"]:
            raise RuntimeError(
                f"{path} sha256 {found} does not match the expected {self._spec['sha256']}; "
                "refusing to unpickle it."
            )
        return path

    def _load(self) -> SchpNet:
        if self._model is not None:
            return self._model
        path = self._checkpoint()
        logger.info("Loading %s (revision=%s) on %s", self.name, self.revision, self.device)
        # The sha256 above pins the file, so a full unpickle is safe (the checkpoint also
        # stores non-tensor training metadata that `weights_only=True` rejects).
        state = torch.load(path, map_location="cpu", weights_only=False)["state_dict"]
        state = {k.removeprefix("module."): v for k, v in state.items()}
        model = SchpNet(len(self._spec["labels"]))
        model.load_state_dict(state, strict=True)
        self._model = model.to(self.device).eval()
        return self._model

    def parse(self, rgb: Image.Image) -> ParseResult:  # pragma: no cover - needs weights
        model = self._load()
        size = self._spec["input_size"]
        batch = torch.from_numpy(schp_input(rgb, size)).unsqueeze(0).to(self.device)
        with torch.no_grad():
            logits = model(batch)
            logits = functional.interpolate(
                logits, size=(size, size), mode="bilinear", align_corners=True
            )
            labels = labels_from_logits(logits, rgb.width, rgb.height)
        return ParseResult(labels, dict(self._names))

    def close(self) -> None:
        self._model = None
        _free_gpu()
