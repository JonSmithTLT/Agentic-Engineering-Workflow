PR 2 renders systems.md from the data and the register's Now list: finish soon, more to build, open questions, done,
and Not counted. It shows state totals and the limit's count with their members, derives priority without storing it,
and offers `python tools/systems.py show SYS-NN`. Both checks detect a stale page; `python tools/register.py render`
refreshes it alongside the register. SYS-48 is partly built with only PR 3 remaining, so FORMAT.md rule 1's count is
14, not the previous 13, against wip_limit 12; this PR reports it and does not enforce it.

The register's §1 wording of the count is for the Lead to reconcile with FORMAT.md rule 1; this change does not edit
that section. State read from code, wired checks, limit enforcement and stale slices remain PR 3. Serves, lanes and
requirements served are later work; a dashboard view is not placed.

Review fixes: the own-slice count now shares a line with every counted slice's text and row, not just its next
slice; concurrent completion of different slices conflicts and forces a re-render. Invalid board data refuses
register rendering without writes or a traceback, including through resolve. Systems command errors name the verb.

The operator approved adding docs/implementation/systems.md to review-guide.md §7's closed generated-page list
beside future-work.md and decisions-due.md in this PR. The guide now includes it; the operator merges this change.

Adopted lines this reverses: none.
