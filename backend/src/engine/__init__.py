"""Outfit engine package for pachapp.

This package MUST stay pure: no I/O (no database session, no HTTP client, no
filesystem access). It exists to be testable as plain functions (see D1 in
docs/architecture/c4.md). Actual outfit-generation logic arrives in phase 1.
"""
