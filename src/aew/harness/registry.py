"""Harness adapter registry: built-in adapters plus operator-configured ones (``AEW_HARNESS_ADAPTERS``).

``AEW_HARNESS_ADAPTERS="name=package.module:Class;other=C:/path/adapter.py:Class"`` registers extra
adapters (the fake harness in tests, or a site adapter). It is read from the launching Lead's environment
and never passed to the agent.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys

from aew.errors import HarnessIncompatible
from aew.harness.base import HarnessAdapter

ENV = "AEW_HARNESS_ADAPTERS"
BUILTIN = {"opencode": "aew.harness.opencode.adapter:OpenCodeAdapter"}


def specs() -> dict[str, str]:
    out = dict(BUILTIN)
    for item in filter(None, (os.environ.get(ENV) or "").split(";")):
        name, _, target = item.partition("=")
        if name.strip() and target.strip():
            out[name.strip()] = target.strip()
    return out


def load(name: str) -> type[HarnessAdapter]:
    target = specs().get(name)
    if target is None:
        raise HarnessIncompatible(f"no harness adapter named {name!r}", known=sorted(specs()))
    where, _, cls_name = target.rpartition(":")
    try:
        if where.endswith(".py"):
            spec = importlib.util.spec_from_file_location(f"aew_harness_{name}", where)
            if spec is None or spec.loader is None:
                raise ImportError(where)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        else:
            module = importlib.import_module(where)
        cls = getattr(module, cls_name)
    except (ImportError, AttributeError, OSError) as exc:
        raise HarnessIncompatible(f"harness adapter {name!r} is not available: {exc}", target=target) from None
    if not (isinstance(cls, type) and issubclass(cls, HarnessAdapter)):
        raise HarnessIncompatible(f"{target} is not a HarnessAdapter")
    return cls


def check(name: str) -> None:
    """Fail before any commit when the named adapter cannot even be loaded."""
    load(name)
