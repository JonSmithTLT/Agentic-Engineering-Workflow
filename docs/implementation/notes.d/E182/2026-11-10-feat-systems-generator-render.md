PR 2 renders systems.md from the data and the register's Now list: finish soon, more to build, open questions, done,
and Not counted. It shows state totals and the limit's count with their members, derives priority without storing it,
and offers `python tools/systems.py show SYS-NN`. Both checks detect a stale page; `python tools/register.py render`
refreshes it alongside the register. SYS-48 is partly built with only PR 3 remaining, so FORMAT.md rule 1's count is
14, not the previous 13, against wip_limit 12; this PR reports it and does not enforce it.

The register's §1 wording of the count is for the Lead to reconcile with FORMAT.md rule 1; this change does not edit
that section. State read from code, wired checks, limit enforcement and stale slices remain PR 3. Serves, lanes and
requirements served are later work; a dashboard view is not placed.

Adopted lines this reverses: none.
