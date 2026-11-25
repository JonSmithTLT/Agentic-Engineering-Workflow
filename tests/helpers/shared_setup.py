"""Expensive test setup built once per process and shared, never once per test module (register E363).

The suite's duplication is kept to what is required or beneficial (the operator, 2026-11-24): a fresh repository for
a test that mutates it, parallel shards, independence that proves something. Anything else a test module would build
and keep for itself (a parsed source tree, a rendered document, a loaded schema) is built here once per process and
shared, read-only, by every module that reads it. #553 found the cost of the alternative: twelve modules each kept a
parse of ``src/aew`` in a module global, 12.1 M tracked objects (2.4 GB) in one serial process.

:func:`once` is that owner. It is ``functools.cache``, plus a record of what each first build kept, which the module
heap guard (``module_heap.py``) credits to the shared setup rather than to the test module that happened to ask first.
A consumer must not mutate what it is given; where the value is mutable, the owner hands out a copy (as
``reference_render.rendered`` does) or the consumer only reads.
"""

from __future__ import annotations

import functools
import gc
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

# What each shared build kept, in allocated memory blocks (``sys.getallocatedblocks``), by owner. Only the outermost
# build of a nesting is recorded, so a build that asks for another shared value is not counted twice.
_BUILT: dict[str, int] = {}
_depth = 0
# A build's garbage is collected before its cost is recorded, but only when the build looks big enough to matter: a
# full collection walks the whole heap, and most shared values are small.
_COLLECT_ABOVE = 50_000


def blocks() -> int:
    """The process's allocated memory blocks: a cheap reading (it walks the allocator's arenas, not the objects), so it
    can be taken around every module and every shared build."""
    return sys.getallocatedblocks()


@contextmanager
def building(owner: str) -> Iterator[None]:
    """Record what the enclosed build keeps as shared setup, owned by ``owner``. The guard's own hook for
    session-scoped fixtures uses it too: a session fixture is shared once per session by definition."""
    global _depth
    _depth += 1
    before = blocks()
    try:
        yield
    finally:
        _depth -= 1
        if _depth == 0:
            kept = blocks() - before
            if kept > _COLLECT_ABOVE:
                gc.collect()
                kept = blocks() - before
            _BUILT[owner] = _BUILT.get(owner, 0) + max(kept, 0)


def once(fn: Callable[P, R]) -> Callable[P, R]:
    """``functools.cache`` for expensive shared test setup: built on first use in each process, then the same object
    for every caller. Its first build of each argument tuple is recorded as shared (:func:`building`)."""
    cached = functools.cache(fn)
    owner = f"{fn.__module__}.{fn.__qualname__}"
    built: set[object] = set()

    @functools.wraps(fn)
    def shared(*args: P.args, **kwargs: P.kwargs) -> R:
        key = (args, tuple(sorted(kwargs.items())))
        if key in built:
            return cached(*args, **kwargs)
        with building(owner):
            value = cached(*args, **kwargs)
        built.add(key)
        return value

    def cache_clear() -> None:
        cached.cache_clear()
        built.clear()  # the next build is recorded again, as a build
        # and the cleared builds' credit goes with them: what is no longer held is no longer shared, so a clear and a
        # rebuild never leave a module an allowance the size of the first build (review of #559, n1)
        _BUILT.pop(owner, None)

    shared.cache_clear = cache_clear  # type: ignore[attr-defined]
    shared.cache_info = cached.cache_info  # type: ignore[attr-defined]
    return shared


def credited() -> int:
    """Every block shared setup has kept so far in this process."""
    return sum(_BUILT.values())


def owners() -> dict[str, int]:
    """What each shared owner has kept so far in this process, by owner: the breakdown of :func:`credited`, which the
    guard subtracts, for a test (or a reader of a guard failure) to see what was credited and to whom."""
    return dict(_BUILT)
