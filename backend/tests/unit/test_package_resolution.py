"""Guards against a third-party distribution shadowing these generic
top-level names (review finding R3-generic-toplevel-package-names)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

# backend/tests/unit/test_package_resolution.py -> backend/src is two parents up.
_BACKEND_SRC = Path(__file__).resolve().parents[2] / "src"


@pytest.mark.parametrize("name", ["api", "worker", "engine", "shared"])
def test_top_level_package_resolves_to_backend_src(name: str) -> None:
    module = importlib.import_module(name)

    resolved = Path(module.__file__).resolve().parent
    assert resolved == _BACKEND_SRC / name
