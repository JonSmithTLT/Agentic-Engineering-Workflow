E243 PR 2 runs the adopted selector on a disposable copy of the integration candidate. The validation
records its observation by digest and keeps the complete selected list with the validation records.
Changes to the selector's declared inputs yield an explicit unknown. A check that takes the selection
file receives the selected items or the full-scope marker when selection is unknown. The coverage
record credits a finished check's observed input, while test assurance within that check is the project's
responsibility. Doctor reports a declared selector that no configured check consumes and probes it
on the authoritative commit when the operator requests `--run-checks`.

AEW's CI lane example uses the same tier decision as CI. The operator reviews the draft declaration in
the quickstart, applies it to the project's checks policy and runs `aew manifest adopt`. AEW's own
checks need a lane runner to consume that selection. The worker and verifier check paths still use
the full-scope marker, and the CI-file search remains a follow-on.
