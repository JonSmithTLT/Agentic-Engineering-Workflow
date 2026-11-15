Partial stale stages with no known fresh-call continuation now retain their stop for explicit `resolve`, only when
the continue's rechecks pass. A changed subject or blocked next step ends the intent instead of holding the unit
behind a continue already known to fail. Resume and RESOLVE_STAGE show the retained stop separately from the next
continue's assessment. Committed steps never repeat; judgment-bearing stages never retry; a retained stage continues
only through explicit Lead resolution. R5-1's existing single retry of an uncommitted non-judgment step is unchanged.

Custody registration's contract is unchanged and intentional: it accepts no caller revision, locks and checks current
custody admission, then commits against the locked session revision.
`test_registration_rechecks_revoked_custody_in_its_locked_transaction` proves revoked custody cannot register.

The publish finish was already fixed; this completes the demonstrated non-publish partial-stale remainder, including
verifier-mode publication after acceptance. Historical terminal intents are not reopened. Enumeration covers shipped
planners and tested state/card variants, not every possible interleaving or future planner. No further implementation
slice is established by this investigation; general typed exits and defect reporting belong to E233 and E138.
