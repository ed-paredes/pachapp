"""Ordered three-stage pipeline for batch throughput (08-local-vision.md,
VIS-REQ-026 context). Pure stdlib, no torch/onnxruntime, so it is unit-testable
with fake stages (VIS-REQ-029).

    prepare (thread pool) -> execute (caller thread, strictly serial) -> finish (thread pool)

While `execute` (the GPU) works on item N, `prepare` (decode, resize, normalize)
of the next `lookahead` items and `finish` (mask post-processing, compositing)
of item N-1 run on worker threads. `execute` never runs concurrently with
itself, so GPU memory use stays that of a single inference (VIS-REQ-025).
Results come back in input order; per-item results are identical to running the
three stages sequentially.

Error policy (per-item isolation): an `Exception` raised by any stage for item N
is yielded, as the exception object, in item N's position and the pipeline keeps
going with the remaining items, so a corrupt upload never loses the results of
its neighbours (callers `isinstance`-check each result, like they do for
`EmptyCutoutError`). Only `BaseException`s (e.g. `KeyboardInterrupt`) and errors
from the `items` iterable itself abort the run.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor


def _resolved[V](value: V) -> Future[V]:
    future: Future[V] = Future()
    future.set_result(value)
    return future


def run_pipeline[T, P, R, Out](
    items: Iterable[T],
    prepare: Callable[[T], P],
    execute: Callable[[P], R],
    finish: Callable[[P, R], Out],
    *,
    lookahead: int = 2,
) -> Iterator[Out | Exception]:
    """Yield `finish(p, execute(p))` for `p = prepare(item)` of each item, in order;
    an `Exception` from any stage is yielded in place of that item's result.

    `items` is consumed lazily from the caller thread, at most `lookahead`
    items ahead of the one being executed.
    """
    if lookahead < 1:
        raise ValueError("lookahead must be >= 1")
    source = iter(items)
    preparing: deque[Future[P]] = deque()
    finishing: deque[Future[Out | Exception]] = deque()

    def guarded_finish(prepared: P, raw: R) -> Out | Exception:
        try:
            return finish(prepared, raw)
        except Exception as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="ml-pipeline") as pool:

        def top_up() -> None:
            while len(preparing) < lookahead:
                try:
                    item = next(source)
                except StopIteration:
                    return
                preparing.append(pool.submit(prepare, item))

        top_up()
        while preparing:
            try:
                prepared = preparing.popleft().result()
            except Exception as exc:
                top_up()
                finishing.append(_resolved(exc))
            else:
                top_up()
                try:
                    raw = execute(prepared)
                except Exception as exc:
                    finishing.append(_resolved(exc))
                else:
                    finishing.append(pool.submit(guarded_finish, prepared, raw))
            while len(finishing) > 1:
                yield finishing.popleft().result()
        while finishing:
            yield finishing.popleft().result()
