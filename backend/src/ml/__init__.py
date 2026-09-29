"""Local vision package for pachapp: BiRefNet cutout, SigLIP embedding/zero-shot.

Used only by `worker` (VIS-REQ-004): `api` MUST NOT import `ml`, directly or
transitively, so the vision models are never loaded in the API process (see
`backend/tests/unit/test_api_ml_boundary.py`, VIS-REQ-005).

This module MUST stay import-cheap: it must not import torch, open_clip, or
rembg at import time. Those heavy imports live inside `ml.registry` and are
only touched on first use (lazy loading), so `import ml` (and anything that
transitively imports this package) never pulls the vision stack in.
"""

from __future__ import annotations
