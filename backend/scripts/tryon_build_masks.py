"""Precompute the CatVTON masks of a mannequin, once (09-virtual-tryon.md §5.1).

Runs in CatVTON's own environment (`make tryon-setup` creates it), not in the backend
venv: its AutoMasker needs DensePose (vendored detectron2) and SCHP. Wired up as
`make tryon-masks MANNEQUIN=DIR`.

    python tryon_build_masks.py --catvton-dir DIR MANNEQUIN_DIR [--device cuda]

`MANNEQUIN_DIR` holds `person.png|jpg` (front, full body, 3:4). The person is
centre-cropped to 768x1024 (CatVTON's training size, as its app.py does) and saved
as `person.png`; the masks `mask_{upper,lower,overall,inner,outer}.png` (white = area
to repaint) and `mask_preview.jpg` are written next to it. The DensePose and SCHP
weights come from the `zhengchong/CatVTON` Hugging Face repo (into `HF_HOME`).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

MASK_TYPES = ("upper", "lower", "overall", "inner", "outer")
SIZE = (768, 1024)
ATTN_MODEL = "zhengchong/CatVTON"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mannequin_dir", type=Path)
    parser.add_argument("--catvton-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--revision", default=None, help=f"commit of {ATTN_MODEL}")
    args = parser.parse_args(argv)

    directory = args.mannequin_dir.expanduser()
    sources = [p for p in (directory / "person.png", directory / "person.jpg") if p.is_file()]
    if not sources:
        print(f"error: {directory}: missing person.png/.jpg", file=sys.stderr)
        return 1

    sys.path.insert(0, str(args.catvton_dir.expanduser()))
    from huggingface_hub import snapshot_download
    from model.cloth_masker import AutoMasker  # type: ignore[import-not-found]
    from PIL import Image
    from utils import resize_and_crop  # type: ignore[import-not-found]

    weights = Path(
        snapshot_download(
            ATTN_MODEL, revision=args.revision, allow_patterns=["DensePose/*", "SCHP/*"]
        )
    )
    masker = AutoMasker(
        densepose_ckpt=str(weights / "DensePose"),
        schp_ckpt=str(weights / "SCHP"),
        device=args.device,
    )
    with Image.open(sources[0]) as opened:
        person = resize_and_crop(opened.convert("RGB"), SIZE)
    person.save(directory / "person.png")

    parsed = masker.preprocess_image(person)  # DensePose + SCHP once, every part reuses it
    previews = []
    for part in MASK_TYPES:
        mask = masker.cloth_agnostic_mask(
            parsed["densepose"], parsed["schp_lip"], parsed["schp_atr"], part=part
        )
        mask.save(directory / f"mask_{part}.png")
        tinted = Image.composite(Image.new("RGB", SIZE, (200, 60, 40)), person, mask.convert("L"))
        previews.append(Image.blend(person, tinted, 0.6).resize((SIZE[0] // 3, SIZE[1] // 3)))

    sheet = Image.new("RGB", (previews[0].width * len(previews), previews[0].height), "white")
    for i, preview in enumerate(previews):
        sheet.paste(preview, (i * preview.width, 0))
    sheet.save(directory / "mask_preview.jpg", quality=88)
    print(f"masks written to {directory} (weights {weights.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
