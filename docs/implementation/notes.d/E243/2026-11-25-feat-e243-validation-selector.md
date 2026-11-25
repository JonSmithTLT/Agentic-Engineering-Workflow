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

### Review follow-ons

- **m2, selector diagnostics.** Validation selector processes are recorded under their own context kind. A failed
  selector records its reason and, when applicable, its exit code. A follow-up on E243 should retain bounded, redacted
  diagnostics for the operator, using the existing access rules for check logs. Decide retention and the treatment
  of selector-controlled output and host-local command arguments before copying diagnostics into durable evidence.
- **m4, recovery after an unknown.** Revision 2 reuses the immutable observation for the same snapshot, selector and
  changed paths, including a timeout or a failed start. The check still receives the full-scope marker. An E243
  follow-up needs an adopted attempt and citation contract before a later execution can recover that selection.
- **m5, policy classification.** Revision 2 classifies the declaration as operational and leaves legality and check
  definition digests unchanged. The published observation identifies its pinned selector. An E243 follow-up should
  take the effect of selector edits on selection-consuming checks to the designer before changing what becomes stale.
