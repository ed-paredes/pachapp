"""The server's notion of "today", in one place so tests can pin it."""

from __future__ import annotations

from datetime import date


def local_today() -> date:
    """The server's local calendar date (default `date` of the wear log)."""
    return date.today()
