**G3-B, the confirmer (2026-10-25), built from A-37 (G3 revision 7.1), the designer's hand-off and its addenda 1
and 2.** The window where the operator approves or declines a pending approval, in `g3/aew_g3_confirm/`, installed
root-owned under `/opt/aew-g3` by `g3/install.sh`. What it is:
- **The toolkit:** GTK3, through the host's own Python 3 and `python3-gobject` (Rocky 8's `platform-python`, 3.6;
  the Lead's ruling). Standard library and GTK only, never `aew` or `aew_g3`; the facts it restates are held to their
  owners by `tests/unit/test_g3_confirm.py`.
- **Launching it:** by hand only, from the desktop entry "AEW approvals" or `/usr/local/bin/aew-g3-confirm`. A
  notifier that starts it when an approval arrives is the designer's to decide; the start-up path is one call
  (`window.main`), so it can be added later.
- **What it shows (G3-03):** one row per served line, made only of the line's own fields and a fixed label, every value
  as ASCII-escaped JSON. A rendering it cannot show exactly is refused whole, and can only be declined.
- **Deciding (G3-05):** the PIN only from the window's own entry field; no arguments, environment, standard input or
  IPC. Each decision is sent once and never retried; `NOT_FOUND` after a lost reply says the approval is no longer
  pending (addendum 2 §1). Every outcome is fixed text.
- **The tests:** `tests/unit/test_g3_confirm.py` (both platforms; two static checks for Python 3.6),
  `tests/integration/test_g3_confirm_process.py` (Linux, against the real service), and
  `tests/helpers/g3_confirm_py36.py`, the run under the host's Python 3.6 that CI cannot make, recorded in the pull
  request.

**Next in the stage:** G3-D (the CLI client). The operator's trial of the confirmer, root's install and the first
approval with a real PIN, follows the merge.
