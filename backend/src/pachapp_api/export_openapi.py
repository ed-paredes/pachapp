"""Export the API's OpenAPI schema as JSON, without starting a server.

Used by `make gen-client` (see T3) to feed `openapi-typescript`. Requires
valid (dummy is fine) LLM settings env vars, since `create_app()` builds the
full app via `pachapp_shared.settings.get_settings()`.

Usage:
    uv run python -m pachapp_api.export_openapi [output_path]

With no `output_path`, the schema is printed to stdout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pachapp_api.main import create_app


def export_openapi_json(output: Path | None = None) -> str:
    """Return the OpenAPI schema as a JSON string, optionally writing it to `output`."""
    app = create_app()
    text = json.dumps(app.openapi(), indent=2)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n")
    return text


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    text = export_openapi_json(output)
    if output is None:
        print(text)


if __name__ == "__main__":
    main()
