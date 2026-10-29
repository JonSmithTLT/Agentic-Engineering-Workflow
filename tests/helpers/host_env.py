"""No containment layout a test builds reads the host's own home (#283's CI at 59707278).

A layout's secret paths come from its launching environment (``layout._launching``): HOME, the XDG directories and the
variables that name OpenCode's files and the display's cookie. A test that builds one from the host's own values
depends on that host's home: a CI runner has no ``~/.local``, so a path left out of the real home put the test's lab,
under it, back read-only, and the runner's own XDG_CONFIG_HOME named its ``~/.config``. The guard fails such a test,
naming what came from the host; a test passes ``env=`` with a synthetic HOME, or sets or clears the variables itself
(:func:`clean_launching_env`). Every module whose tests build a layout themselves takes it (:data:`GUARDED` in its
``pytestmark``), and a test holds that so. It covers a layout built in the test's process, not one an ``aew``
subprocess builds, nor one a module reaches only through a command such as ``aew doctor``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

# Imported here, as the session starts: importing them inside a test would change the shared state some tests check.
from aew.harness.containment import layout as L
from aew.harness.opencode import login

HOST = dict(os.environ)  # as the session started, before any test's monkeypatch


def launching_names() -> tuple[str, ...]:
    """The variables a layout reads for the secret paths they name (``layout._env_masks``, ``opencode.login``)."""
    return ("HOME", "XAUTHORITY", "OPENCODE_DB", "OPENCODE_CONFIG",
            *(f"XDG_{kind.upper()}_HOME" for kind in login.XDG_DEFAULTS))


def clean_launching_env(monkeypatch: pytest.MonkeyPatch, home: str | os.PathLike[str]) -> None:
    """This process's launching environment, synthetic: ``home`` as HOME (and USERPROFILE), none of the others."""
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for name in launching_names()[1:]:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def host_env_guard() -> Iterator[None]:
    real = L._launching  # noqa: SLF001

    def launching(home, env):
        out = real(home, env)
        leaked = [n for n in launching_names() if HOST.get(n) and out.get(n) == HOST[n]]
        if leaked:
            pytest.fail(f"a containment layout was built from the host's own {', '.join(leaked)}: pass env= with a "
                        "synthetic HOME, or set the test's own (tests/helpers/host_env.py)", pytrace=False)
        return out

    # its own patch, not the test's ``monkeypatch``, whose undoing it would otherwise move to its own teardown
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(L, "_launching", launching)
        yield


GUARDED = pytest.mark.usefixtures(host_env_guard.__name__)  # for the pytestmark of a module that builds layouts
