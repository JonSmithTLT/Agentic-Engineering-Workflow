"""The launcher's entry (STG-03 G3-B): the arguments are checked here, before the window module imports GTK, because
PyGObject's Gtk takes its own options (``--name``, ``--class``, ``--g-fatal-warnings`` and others) out of
``sys.argv`` at import (#282 review, m5).
"""

import sys
from typing import List

from . import core


def main(argv: List[str]) -> int:
    if not core.arguments_ok(argv):
        sys.stderr.write("aew-g3-confirm takes no arguments: the PIN is typed into its window only\n")
        return 2
    from . import window  # GTK is imported only once the arguments are known to be none or --at-login

    return window.main(argv)
