"""Root's administration writes into the service's own state: every file and directory it makes there is handed to the
account that owns the state directory, the service's dynamic UID (G3-05, G3-09).

``set-pin`` and ``rotate-key`` run as root. At the service's next start, systemd's ``StateDirectory=`` set-up does not
descend into a directory whose top level the dynamic UID already owns, so a file root leaves behind would stay root's,
and the service, with no capabilities, could not read it (review of #269, M1). Run as anyone else, as the tests and the
service itself run, the files are already the caller's and nothing is changed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def hand_to_service(state_dir: Path, *paths: Path) -> None:
    """Chowns each path to the state directory's owner when root is the caller; otherwise does nothing."""
    if sys.platform == "win32":
        return
    if os.geteuid() != 0:
        return
    st = state_dir.stat()
    for p in paths:
        os.chown(p, st.st_uid, st.st_gid)
