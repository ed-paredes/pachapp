# Third-party notices

P'achapp's own source code is MIT-licensed (see [`LICENSE`](LICENSE)). The
components below are not part of that grant: they keep their own licences.
Except where noted, they are not stored in this repository; they are installed
as dependencies, cloned outside the repo, or downloaded into the ML cache at
runtime.

Some of them are **non-commercial**. Using P'achapp with the default models is
fine for personal use, but a commercial deployment must replace or separately
license every component marked "No" below.

## Models and ML code

| Component | Used for | Licence | Commercial use | How it is used |
| --- | --- | --- | --- | --- |
| [CatVTON](https://github.com/Zheng-Chong/CatVTON) code and [`zhengchong/CatVTON`](https://huggingface.co/zhengchong/CatVTON) weights (including its `DensePose/` and `SCHP/` checkpoints) | Virtual try-on, try-on masks, SCHP garment parsing | CC BY-NC-SA 4.0 | No | External pinned clone (`make tryon-setup`); weights downloaded at runtime |
| [DensePose](https://github.com/facebookresearch/detectron2/tree/main/projects/DensePose) (detectron2) code | Mannequin masks, via CatVTON's bundled copy | Apache 2.0 | Yes | Inside the external CatVTON clone |
| [Self-Correction-Human-Parsing](https://github.com/GoGoDuck912/Self-Correction-Human-Parsing) code | SCHP network definition | MIT, Copyright (c) 2020 Peike Li | Yes | Re-implemented in `backend/src/ml/schp.py`, which carries the original MIT notice |
| [`booksforcharlie/stable-diffusion-inpainting`](https://huggingface.co/booksforcharlie/stable-diffusion-inpainting) (Stable Diffusion 1.5 inpainting) | Try-on base model | CreativeML OpenRAIL-M | Yes, subject to the licence's use restrictions | Downloaded at runtime |
| [`fashn-ai/fashn-human-parser`](https://huggingface.co/fashn-ai/fashn-human-parser) (SegFormer-B4) | Garment-only cutout | NVIDIA SegFormer source licence | No | Downloaded at runtime |
| `birefnet-general-lite` / `birefnet-general` via [rembg](https://github.com/danielgatis/rembg) | Background removal (default) | MIT | Yes | Downloaded at runtime |
| `RMBG-2.0` | Background removal (opt-in only, `PACHAPP_ML_BG_MODEL=rmbg-2.0`) | Non-commercial | No | Downloaded at runtime only when enabled |
| [`Marqo/marqo-fashionSigLIP`](https://huggingface.co/Marqo/marqo-fashionSigLIP) via open_clip | Embeddings and zero-shot tags | Apache 2.0 | Yes | Downloaded at runtime |

The local-vision rows follow `docs/specs/08-local-vision.md`; the try-on rows
follow `docs/specs/09-virtual-tryon.md` and the upstream pages linked above.
Check each upstream page for the current terms before redistributing or
deploying commercially.

## Files in this repository

| Path | Licence |
| --- | --- |
| `assets/tryon/mannequins/*/person.png` | [Pexels License](https://www.pexels.com/license/); source URL in each `meta.json` |
| `assets/tryon/mannequins/*/mask_*.png` | Derived from the CatVTON DensePose and SCHP weights; treated as CC BY-NC-SA 4.0 (non-commercial, share-alike) |

## Package dependencies

npm (`app/package.json`) and Python (`backend/pyproject.toml`) dependencies
keep their own licences, listed in each package's metadata.
