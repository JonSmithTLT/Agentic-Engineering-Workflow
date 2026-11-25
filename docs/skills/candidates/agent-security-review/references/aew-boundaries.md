# AEW boundaries for agent review

Read only for an AEW invocation. Resolve current role, context and tool contracts from the supplied pack; this reference is a navigation aid, not a capability manifest.

- **Role and output:** inspect the invocation's archetype/card, path restrictions, permitted evidence and output destination. A Security Reviewer specialty supplies expertise inside its role. It does not grant Lead operations, source mutation or broader lookup.
- **Tools:** use the tool descriptions and schemas actually exposed to this invocation. If permitted discovery is present, expand only the operations needed for the review. Separate catalog membership, profile exposure, authorization for these arguments and execution. Never invent a capability-discovery command from a design proposal.
- **Custody and effects:** the adopted worker-tool delivery design routes typed requests through a supervisor bridge with credentials supervisor-side. Verify the supplied implementation's actual path. Check request identity, arguments, downstream guards and effect ownership; do not ask a worker to obtain a supervisor credential. A native shell/browser/file tool needs its own boundary assessment: it may reach an effect outside the typed path.
- **Knowledge and handoffs:** inspect provenance and instruction/data separation across retrieval, tools, memory and worker handbacks. Preserve canonical objectives, plans, diffs, checks and findings needed for the role. Do not seek current implementer private reasoning to make a reviewer better informed; the adopted independence rule excludes it by default. A worker claiming success does not turn its prose into authoritative evidence.
- **Evidence:** pin the evaluated snapshot and relevant configuration. Return findings through the assigned evidence format and private destination where required. Neither a tool response nor this review changes AEW workflow state.

When reviewing another project's agent under AEW, inspect that project's agent boundaries too; AEW's own custody model does not automatically describe the target.

Maintained anchors to recheck in this repository: [role/card decision](../../../../implementation/adr/0006-role-archetypes-and-cards.md), [worker tool delivery and independence](../../../../design/decisions-2026-10-09-knowledge-tool-delivery-and-reviewer-independence.md), and [snapshot identity](../../../../implementation/adr/0002-evaluated-snapshot-fingerprint.md). If packaged elsewhere, the context owner supplies current equivalents; missing documents do not authorize assumed semantics.

## Threat-model gate

For AEW itself, apply the operator's 2026-10-19 ruling as relayed in the review supplied for this revision: steered agents and AEW code bugs are in scope; independently malicious code already running as the operator is out. The original dated ruling file was not located during this update; the invocation's maintained threat-model record remains the authoritative source to recheck. This is a scoped summary, not a new security contract.

For each chain identify how the attacker obtains the first controlled input and each required capability. An injected document steering a worker through an exposed shell or typed tool remains in scope. A scenario that starts by assuming an unrelated hostile same-user process can patch the supervisor is outside this model unless the assignment explicitly broadens it. AEW implementation bugs reachable from supported inputs remain in scope; do not dismiss them merely because processes share a user. If a chain requires crossing between these models, state the missing assumption rather than silently borrowing the stronger attacker. Other target projects supply their own threat models.
