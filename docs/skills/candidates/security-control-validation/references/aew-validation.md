# AEW validation context

The public [I6 profile, revision 3](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/blob/8a1ed7b291fe7a6d4592696248226bde157426a4/docs/contracts/A-39/I6-PROFILE.md)
records the operator's October 19, 2026 scope. Steered agents and AEW bugs are
in scope. Independently malicious code already running as the operator is
outside this model. The October 24, 2026 decision on contained-agent reachability
is reflected in the public [KP position](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/blob/8a1ed7b291fe7a6d4592696248226bde157426a4/docs/contracts/A-57/KP-POSITION.md),
[CAPR position](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/blob/8a1ed7b291fe7a6d4592696248226bde157426a4/docs/contracts/A-38/CAPR-POSITION.md)
and [review guide §10](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/blob/8a1ed7b291fe7a6d4592696248226bde157426a4/docs/implementation/review-guide.md).

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
