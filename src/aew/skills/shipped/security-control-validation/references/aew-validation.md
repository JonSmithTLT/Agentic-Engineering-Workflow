# AEW validation context

The public I6 profile, revision 3 (`docs/contracts/A-39/I6-PROFILE.md`)
records the operator's October 19, 2026 scope. Steered agents and AEW bugs are
in scope. Independently malicious code already running as the operator is
outside this model. The October 24, 2026 decision on contained-agent reachability
is reflected in the public KP position (`docs/contracts/A-57/KP-POSITION.md`),
CAPR position (`docs/contracts/A-38/CAPR-POSITION.md`)
and review guide §10 (`docs/implementation/review-guide.md`).

Bind validation to the invocation's adopted subject, threat model and policy.
Assess whether the actor, supported interface and applicable control are
relevant and whether the observations can demonstrate the claimed outcome.
Keep authorized evidence records separate from judgments about verification
and integration. An assignment may require more current scope evidence than a
public method reference supplies.

For evidence involving correlation, check identity, subject/configuration,
request identifiers, ordering, and collection completeness. An attempted
request, an enforcement record and a committed effect are separate stages.
Report each available stage and where data is missing. Keep findings and
restricted records in the assigned destination.

The October 24 rule covers fake operator approval, a forged owner fact,
and credential access or acting as the operator outside containment. Assess
whether the contained agent can cause the outcome on its own with what AEW
provides. The ordinary review process still covers product correctness.

The cited public repository files were consulted at revision
`8a1ed7b291fe7a6d4592696248226bde157426a4`.
