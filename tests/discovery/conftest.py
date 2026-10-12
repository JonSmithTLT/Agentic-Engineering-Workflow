"""The discovery lane starts with its identity check (spec v3.4 §5, J2): a mismatch aborts the run before anything
is judged."""

from __future__ import annotations

from pathlib import Path

import pytest
from discovery import identity

CHECKOUT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session", autouse=True)
def the_aew_under_test_is_this_checkout() -> None:
    import aew

    found = identity.problems(aew.__file__, aew.__version__, CHECKOUT / "src", CHECKOUT / "pyproject.toml")
    if found:
        pytest.exit("discovery lane aborted, identity check failed: " + "; ".join(found), returncode=3)
