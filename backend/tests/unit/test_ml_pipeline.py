"""Tests for `ml.pipeline.run_pipeline` with fake stages (VIS-REQ-029)."""

from __future__ import annotations

import threading
import time

import pytest

from ml.pipeline import run_pipeline


def test_results_match_sequential_and_keep_order() -> None:
    items = list(range(12))

    def prepare(x: int) -> int:
        time.sleep(0.01 * (x % 3))  # out-of-order completion on the pool
        return x * 2

    out = list(run_pipeline(items, prepare, lambda p: p + 1, lambda p, r: (p, r)))
    assert out == [(x * 2, x * 2 + 1) for x in items]


def test_empty_input_yields_nothing() -> None:
    assert list(run_pipeline([], str, str, lambda p, r: p)) == []


def test_execute_is_never_concurrent_and_runs_on_caller_thread() -> None:
    active = 0
    max_active = 0
    threads: set[int] = set()
    lock = threading.Lock()

    def execute(p: int) -> int:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
            threads.add(threading.get_ident())
        time.sleep(0.005)
        with lock:
            active -= 1
        return p

    list(run_pipeline(range(8), lambda x: x, execute, lambda p, r: r))
    assert max_active == 1
    assert threads == {threading.get_ident()}


def test_prepare_and_finish_overlap_execute() -> None:
    events: list[str] = []
    lock = threading.Lock()

    def log(name: str) -> None:
        with lock:
            events.append(name)

    def prepare(x: int) -> int:
        log(f"prep{x}")
        return x

    def execute(p: int) -> int:
        log(f"exec{p}")
        time.sleep(0.05)
        return p

    def finish(p: int, r: int) -> int:
        log(f"fin{p}")
        return r

    list(run_pipeline(range(3), prepare, execute, finish, lookahead=2))
    # The next photo is prepared while the current one executes.
    assert events.index("prep1") < events.index("exec0") + 2
    assert events.index("prep2") < events.index("fin1")


def test_items_are_consumed_lazily_within_lookahead() -> None:
    pulled: list[int] = []

    def source():
        for i in range(10):
            pulled.append(i)
            yield i

    gen = run_pipeline(source(), lambda x: x, lambda p: p, lambda p, r: r, lookahead=2)
    assert next(gen) == 0
    assert len(pulled) <= 4  # bounded read-ahead, not the whole input
    gen.close()


def test_stage_exception_propagates() -> None:
    def execute(p: int) -> int:
        if p == 2:
            raise RuntimeError("boom")
        return p

    got: list[int] = []
    with pytest.raises(RuntimeError, match="boom"):
        for value in run_pipeline(range(5), lambda x: x, execute, lambda p, r: r):
            got.append(value)
    assert got == [0]  # the failure surfaces one item ahead of the consumer


def test_lookahead_must_be_positive() -> None:
    with pytest.raises(ValueError, match="lookahead"):
        list(run_pipeline([1], str, str, lambda p, r: p, lookahead=0))
