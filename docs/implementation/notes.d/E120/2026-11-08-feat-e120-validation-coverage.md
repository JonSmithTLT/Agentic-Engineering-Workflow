First slice: a failing worker check returns a diagnostic-first excerpt with a reserved 20-line tail, bounded to
80 lines and 25 KiB of serialized JSON including its envelope. The byte budget is half of OpenCode's 50 KiB output
cut, leaving room for other response fields; it counts ASCII escaping, including non-ASCII text. Short rows are served
first so unused byte shares reach longer diagnostics, up to the 1,000-character cap and remaining byte share; displayed
rows remain in file order. Line numbers count
file newlines. Omitted-line, omitted-anchor and truncated-line counts and a runtime notice disclose the selection's
limits. Recognised error-class lines are anchors; a middle failure behind too many false anchors and a long summary
can still be missed. The excerpt is labelled as check-output data, not instructions, and uses the result channel's
scrub for AEW's credential form before truncation. Full logs and sealed evidence are unchanged. The absolute full-log
path is explicitly for the shell: the harness read tool may refuse it. Filesystem probes prove the shell-equivalent
route on both supported platforms, not a real harness read-tool grant. No harness permission is widened.

Harness status and terminal wait results list requested but unavailable skills beside missing tools, with the reason
from the run's delivered contract (including failed copies), not a fresh plan against today's install. Names pass only
in a bounded skill-id form; invalid names read `not shown` without dropping the missing entry. Missing skills remain
advisory: they do not change run outcomes, gates or next actions.

Coverage disclosure remains a second slice. This is partial delivery of the validation-disclosure requirement: the
project's affected-test consumers and CI-tool inventory have no generic product source today. The second slice will
record observed facts and explicit unknowns separately; the actual unrun-consumer and CI-tool lists remain owed until
a project-owned source is available. No claim is made here that the coverage part or the register row is closed.
