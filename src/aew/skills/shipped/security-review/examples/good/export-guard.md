# Good example

Synthetic good: an export endpoint authenticates a session and calls `export_for_member(session.user, project_id)`. Inspect the helper. If it checks current membership for that same project before returning bytes, reject the missing route-local check as a finding. If its contract is absent, retain the unresolved guard rather than inventing bypass behavior. If it checks membership in any project, not this one, the cross-project export is the finding.
