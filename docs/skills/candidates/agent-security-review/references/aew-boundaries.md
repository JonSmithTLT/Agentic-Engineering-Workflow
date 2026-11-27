# AEW boundaries for agent review

For AEW itself, the operator's October 19, 2026 threat-model ruling is recorded
in the [I6 profile, revision 3](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/blob/8a1ed7b291fe7a6d4592696248226bde157426a4/docs/contracts/A-39/I6-PROFILE.md).
Steered agents and AEW bugs are in scope. Independently malicious code already
running as the operator is outside this model. Use the exact scope and subject
assigned by the invocation. Other projects supply their own threat model.

For the October 24, 2026 ruling on agent reachability, see the public
[KP position](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/blob/8a1ed7b291fe7a6d4592696248226bde157426a4/docs/contracts/A-57/KP-POSITION.md),
[CAPR position](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/blob/8a1ed7b291fe7a6d4592696248226bde157426a4/docs/contracts/A-38/CAPR-POSITION.md)
and [review guide §10](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/blob/8a1ed7b291fe7a6d4592696248226bde157426a4/docs/implementation/review-guide.md).
Judge whether the affected boundary is reachable by a contained agent in the
supported system using actually granted capabilities and applicable controls.
Apply the review guide's existing disposition when a finding is supported.
State each material premise and record uncertainty when evidence is missing.

For an AEW review record, cite the public contract or applicable adopted
revision alongside the inspected code and configuration. Distinguish role
assignment, host exposure, policy mediation and owned effects. Keep sensitive
facts within the assigned finding destination. This reference describes method.
