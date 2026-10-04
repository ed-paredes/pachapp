# Contract tests

Black-box tests of the HTTP API against a real app on a temporary SQLite
database: request and response shapes, status codes and error envelopes.

- `test_outfits_api.py`: `POST /outfits/generate` and `POST /outfits`.
- `test_wear_log_api.py`: `POST`/`PUT`/`DELETE /wear-log` and the derived
  `wear_count` / `last_worn_at`.

The LLM JSON output contract test (D11) arrives once `engine`/`worker`
actually call an LLM provider.
