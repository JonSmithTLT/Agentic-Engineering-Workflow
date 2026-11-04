"""AEW's per-host state, per operator account: one directory outside every project and every sandbox's writable binds.

``$XDG_DATA_HOME/aew`` (by default ``~/.local/share/aew``), or ``%LOCALAPPDATA%\\aew`` on Windows. It holds the
capability register (``capability/``, STG-15) and the register of weaker contexts (``weaker-contexts/``, G3 addendum 7,
ruling 2). Each keeps its own test override; this module owns only where the directory is.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def base_variable() -> str:
    """The environment variable that names the directory AEW's host state lives under on this platform."""
    return "LOCALAPPDATA" if sys.platform == "win32" else "XDG_DATA_HOME"


def root() -> Path:
    """This host's AEW state directory."""
    if sys.platform == "win32":
        base = os.environ.get(base_variable()) or str(Path.home() / "AppData" / "Local")
    else:  # the XDG base directory rule: a relative XDG_DATA_HOME is ignored
        xdg = os.environ.get(base_variable()) or ""
        base = xdg if os.path.isabs(xdg) else str(Path.home() / ".local" / "share")
    return Path(base) / "aew"
