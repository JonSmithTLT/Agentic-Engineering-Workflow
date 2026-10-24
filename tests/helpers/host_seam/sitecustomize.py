"""Test-only: give this child process the synthetic host a test chose (``tests/helpers/group_host.py``).

A test puts this directory on a child's ``PYTHONPATH`` together with ``AEW_TEST_HOST_GROUPS`` (and, optionally,
``AEW_TEST_CREDENTIALS``); without them it does nothing. It is code a test injects into its own child, which any process
of the same account can already do, so it opens no route: nothing in ``src/`` reads those variables.
"""

import os
import sys

_HOST = os.environ.get("AEW_TEST_HOST_GROUPS")
_CREDS = os.environ.get("AEW_TEST_CREDENTIALS")
if _HOST or _CREDS:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        import group_host

        group_host.install_in_child(_HOST, _CREDS)
    finally:
        sys.path.pop(0)
