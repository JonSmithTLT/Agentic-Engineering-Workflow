Two of the row's three parts are built, at `a2fd5229` (merged before this note). Every contained start clears the
Lead's own store of saved permissions and of each session's own permission rules, and refuses the start when the clear
fails (`CONTAINMENT_UNAVAILABLE`, reason `saved_permissions`). The login seed checks the `credential` table's columns
against OpenCode 2.0.18's before it inserts, and on a mismatch skips the seed: the Lead starts without that login and
is told so. The tests are in `tests/unit/test_lead_contained.py`.

Moving the Lead's server out of the shell's reach is not built. It waits on the designer's choice of mechanism, and
E118 stays open for it.
