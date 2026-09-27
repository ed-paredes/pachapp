"""Worker process entrypoint for pachapp.

Phase 0 is a polling-loop stub only: no job logic yet (that arrives in
phase 1). `run()` is factored out from `main()` so the loop is testable
without touching real signal handlers.
"""

from __future__ import annotations

import logging
import signal
import threading
from types import FrameType

from pachapp_shared.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def run(stop_event: threading.Event, settings: Settings | None = None) -> None:
    """Poll until `stop_event` is set. No job logic yet (phase 1)."""
    settings = settings or get_settings()
    interval_s = settings.worker_poll_interval_ms / 1000
    logger.info("pachapp worker started (poll interval: %sms)", settings.worker_poll_interval_ms)

    while not stop_event.is_set():
        stop_event.wait(interval_s)

    logger.info("pachapp worker stopped")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    stop_event = threading.Event()

    def _handle_signal(signum: int, frame: FrameType | None) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    run(stop_event)


if __name__ == "__main__":
    main()
