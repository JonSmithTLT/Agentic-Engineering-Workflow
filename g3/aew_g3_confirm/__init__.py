"""AEW's G3 confirmer (STG-03, G3-B): the operator's approval window, under A-37 (G3 revision 7.1).

The operator runs it on their own desktop, as their own account and outside every sandbox. It lists the pending
approvals the service serves on ``confirm.sock``, shows each one's rendering exactly as served (G3-03), and sends one
decision: Decline, or Approve with the PIN typed into its own window (G3-05).

It runs under the host's own Python 3 with its GTK3 bindings (Rocky 8: ``/usr/libexec/platform-python``, 3.6, and
``python3-gobject``), so this package is written for Python 3.6 and the standard library. It never imports ``aew`` or
``aew_g3``: the facts it restates are held to their owners there by ``tests/unit/test_g3_confirm.py``. Only
``window.py`` imports GTK; ``core.py`` holds everything the tests can reach.
"""
