E120 closes the validation disclosure work after E243's second slice merged in [#570](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/pull/570).
The existing worker bridge returns bounded excerpts from failed checks. Harness status and wait report the skills a
run requested and could not receive, using the recorded delivery facts. [Worker evidence](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/pull/397) ·
[Harness disclosure](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/pull/408)

The closeout test adopts a synthetic project's selector and CI inventory. A validation with a fixed-scope check
names its selected lane without a completed consuming check and its declared Ruff CI tool without a configured covering check.
Both are known gaps.
After a later adoption, the same pinned facts remain in the validation record, status, Lead-readable output and
integrated completion. The undeclared case gives each inventory its own reason and leaves unknown inventories out
of the gap totals. Both cases pass the same acceptance path. The project owns evidence about individual tests within
a consuming check. [Shared coverage record](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/pull/416)

For first use, the operator reviews the [Quickstart](../../../guides/quickstart.md#declare-project-ci-coverage)
declaration, applies it to `.aew/policy/checks.yaml`, and runs `aew manifest adopt` at their terminal. The operator's real
validation and sign-off are the remaining SYS-19 actions. AEW's own CI lane runner and the other E243 follow-ons retain
their existing scope.
