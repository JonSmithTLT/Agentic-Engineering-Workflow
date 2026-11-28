**Cited, not implemented: a measurement from E375 (PR #627; review of #627, n3).** With E375's steering-on Lead
policy, the steering loop now runs the review stage itself, and C5's refused `resolve` of the loop's own stage
(RESOLVE_STAGE, refused `INVALID_ARGUMENTS`) now shows at REVIEW_PENDING in every steering-on vertical case, V1,
V2-exit and V2-kill; before E375 it showed there only in V2-kill. So the fix of C5 (this row, with E388's `resolve`
arguments) clears that refusal in all three steering-on cases, not only in V2-kill. The V-01 burn-down's C6 row
records the same in its "Still breaks" cell. This change does none of E374's work; it records what E375 measured, so
whoever builds C5 sees it.
