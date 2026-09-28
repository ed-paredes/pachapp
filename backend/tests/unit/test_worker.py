from __future__ import annotations

import threading
import time
from pathlib import Path

from shared.settings import Settings
from worker.main import run


def _fast_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "pachapp-data",
        llm_provider="anthropic",
        llm_model_id="claude-sonnet-5-20260101",
        llm_api_key="test-secret-key",
        worker_poll_interval_ms=10,
    )


def test_run_stops_promptly_when_stop_event_set(tmp_path: Path) -> None:
    stop_event = threading.Event()
    thread = threading.Thread(target=run, args=(stop_event, _fast_settings(tmp_path)))
    thread.start()

    time.sleep(0.05)
    assert thread.is_alive()

    stop_event.set()
    thread.join(timeout=1)

    assert not thread.is_alive()


def test_run_returns_immediately_if_stop_event_already_set(tmp_path: Path) -> None:
    stop_event = threading.Event()
    stop_event.set()

    start = time.monotonic()
    run(stop_event, _fast_settings(tmp_path))
    elapsed = time.monotonic() - start

    assert elapsed < 0.5
