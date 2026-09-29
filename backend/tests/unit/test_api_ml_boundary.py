"""Guards VIS-REQ-004/VIS-REQ-005: `api` must never import `ml`, directly or
transitively -- the vision models (BiRefNet, SigLIP, and the optional LLM
fallback client) load only in the worker process, never in the API process.
"""

from __future__ import annotations

import os
import subprocess
import sys

_FORBIDDEN_MODULES = ("ml", "torch", "open_clip", "rembg")


def test_api_main_never_imports_ml() -> None:
    """Import `api.main` in a fresh subprocess and assert that none of the
    vision stack ends up in `sys.modules`. A subprocess-level `sys.modules`
    check catches a transitive import (e.g. some future `api` module quietly
    depending on `ml`) that a source-level grep/AST scan of
    `backend/src/api/` alone could miss.
    """
    probe = (
        "import sys\n"
        "import api.main\n"
        f"forbidden = {_FORBIDDEN_MODULES!r}\n"
        "loaded = [name for name in forbidden if name in sys.modules]\n"
        "assert not loaded, f'api.main pulled in forbidden module(s): {loaded}'\n"
    )

    # A fresh, minimal env: just enough for Settings() to succeed
    # (PACHAPP_ML_EMBED_REVISION has no default, VIS-REQ-002; the vision LLM
    # fallback stays off by default so no PACHAPP_LLM_* vars are needed).
    env = os.environ.copy()
    env["PACHAPP_ENV_FILE"] = os.devnull
    env["PACHAPP_ML_EMBED_REVISION"] = "test-boundary-revision"

    result = subprocess.run(
        [sys.executable, "-c", probe],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
