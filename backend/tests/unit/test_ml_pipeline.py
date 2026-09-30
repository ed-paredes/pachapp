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
    # Each blocking wait below can only be released by a stage running on a worker
    # thread *during* an `execute`; a serialized pipeline would time out.
    prep1_done = threading.Event()
    fin0_done = threading.Event()
    overlapped: list[str] = []

    def prepare(x: int) -> int:
        if x == 1:
            prep1_done.set()
        return x

    def execute(p: int) -> int:
        if p == 0 and prep1_done.wait(timeout=5):
            overlapped.append("prepare(1) during execute(0)")
        if p == 1 and fin0_done.wait(timeout=5):
            overlapped.append("finish(0) during execute(1)")
        return p

    def finish(p: int, r: int) -> int:
        if p == 0:
            fin0_done.set()
        return r

    assert list(run_pipeline(range(3), prepare, execute, finish, lookahead=2)) == [0, 1, 2]
    assert overlapped == ["prepare(1) during execute(0)", "finish(0) during execute(1)"]


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


def test_stage_exceptions_are_isolated_per_item_and_keep_order() -> None:
    def prepare(x: int) -> int:
        if x == 2:
            raise ValueError("bad prepare 2")
        return x

    def execute(p: int) -> int:
        if p == 4:
            raise RuntimeError("bad execute 4")
        return p * 10

    def finish(p: int, r: int) -> int:
        if p == 6:
            raise KeyError("bad finish 6")
        return r

    out = list(run_pipeline(range(8), prepare, execute, finish))
    assert len(out) == 8
    assert [o for o in out if not isinstance(o, Exception)] == [0, 10, 30, 50, 70]
    assert [type(out[i]) for i in (2, 4, 6)] == [ValueError, RuntimeError, KeyError]
    assert [i for i, o in enumerate(out) if isinstance(o, Exception)] == [2, 4, 6]


def test_error_does_not_lose_the_previous_result() -> None:
    def execute(p: int) -> int:
        if p == 1:
            raise RuntimeError("boom")
        return p

    got = list(run_pipeline(range(3), lambda x: x, execute, lambda p, r: r))
    assert got[0] == 0 and isinstance(got[1], RuntimeError) and got[2] == 2


def test_base_exceptions_abort_the_run() -> None:
    def execute(p: int) -> int:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        list(run_pipeline(range(3), lambda x: x, execute, lambda p, r: r))


def test_lookahead_must_be_positive() -> None:
    with pytest.raises(ValueError, match="lookahead"):
        list(run_pipeline([1], str, str, lambda p, r: p, lookahead=0))
