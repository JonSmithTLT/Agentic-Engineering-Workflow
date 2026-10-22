"""An xdist worker saves its coverage at the end of its session, before it reports finished.

At teardown the controller waits 10 s for each worker to exit and then kills it (execnet's ``terminate``), and a killed
worker never runs coverage's atexit save. One of ``core``'s four workers lost its data that way, or by a crash on the
way out (2026-10-22: line coverage 93.3% to 91.7%, the gate's drop). The atexit save still runs when the worker exits
normally, into the same data file. The same shape as pytest-cov's worker plugin. Without coverage, nothing happens.
"""

from __future__ import annotations

from typing import Any


def save(session: Any) -> None:
    """``pytest_sessionfinish`` (``trylast``): in an xdist worker under coverage, save what it measured."""
    if getattr(session.config, "workerinput", None) is None:
        return
    try:
        import coverage
    except ImportError:
        return
    cov = coverage.Coverage.current()
    if cov is not None:
        cov.save()
