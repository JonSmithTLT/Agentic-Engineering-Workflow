# AEW boundaries for agent review

For AEW itself, the operator's October 19, 2026 threat-model ruling is recorded
in the I6 profile, revision 3 (`docs/contracts/A-39/I6-PROFILE.md`).
Steered agents and AEW bugs are in scope. Independently malicious code already
running as the operator is outside this model. Use the exact scope and subject
assigned by the invocation. Other projects supply their own threat model.

For the October 24, 2026 ruling on agent reachability, see the public
KP position (`docs/contracts/A-57/KP-POSITION.md`),
CAPR position (`docs/contracts/A-38/CAPR-POSITION.md`)
and review guide §10 (`docs/implementation/review-guide.md`).
Judge whether the affected boundary is reachable by a contained agent in the
supported system using actually granted capabilities and applicable controls.
Apply the review guide's existing disposition when a finding is supported.
State each material premise and record uncertainty when evidence is missing.

For an AEW review record, cite the public contract or applicable adopted
revision alongside the inspected code and configuration. Distinguish role
assignment, host exposure, policy mediation and owned effects. Keep sensitive
facts within the assigned finding destination. This reference describes method.

The October 24 rule covers fake operator approval, a forged owner fact,
and credential access or acting as the operator outside containment. Assess
whether the contained agent can cause the outcome on its own with what AEW
provides. The ordinary review process still covers product correctness.

The cited public repository files were consulted at revision
`8a1ed7b291fe7a6d4592696248226bde157426a4`.
