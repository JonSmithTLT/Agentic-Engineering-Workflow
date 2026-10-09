# Designer rulings of 2026-10-09: worker tool delivery and reviewer independence (F21)

**Status:** Decision record, governing. **Adopted** by the designer on 2026-10-09, the day the operator adopted the
knowledge system ([adoption decision](decisions-2026-10-09-knowledge-system-adoption.md)). The two rulings answer
questions the lead developer raised while preparing F21's implementation-readiness package (adoption decision §8): how
knowledge lookup reaches a worker, and what a reviewer or verifier may look up about the Ticket under review. §1 is the
rulings as given; §2 says where they are filed and how they meet the adopted designs.

## 1. The rulings, recorded as given

**Worker tool delivery.** The question: how knowledge, map and helper operations reach a worker inside its sandbox.

> **APPROVE.** This is already the intended `aew-run` architecture: the worker sees typed tools, requests go through
> the supervisor bridge, and credentials remain supervisor-side. Knowledge/map/helper operations extend that mechanism
> rather than create another worker credential surface.

**Reviewer independence.** The lead developer had proposed excluding all records of the Ticket under review from
reviewer and verifier lookup.

> **REVISE.** AEW defines independence as fresh/bounded context with the implementer reasoning transcript excluded; the
> verifier explicitly needs unresolved review findings and relevant canonical evidence, so blanket same-Ticket hiding
> would destroy legitimate rework/verification context. The rule: hide current implementer reasoning/private working
> state by default; preserve canonical objective, plan, diff, check results, findings, failures and whatever the role
> actually requires; broader historical prose from that Ticket can require explicit investigation mode.

## 2. Filing (lead developer)

- **Ledger:** KDR-01 to KDR-05.
- **Worker tool delivery** is register F15.3's `aew-run` role server: typed tools inside the sandbox through a thin
  client, requests through the supervisor bridge, credentials supervisor-side (typed Lead surface v0.2 §6, ledger
  TLS-23). F15.3 already names `aew-knowledge` as a separate capability *namespace* over the shared transport; this
  ruling fixes that the namespace, and any map or helper namespace after it, adds tools to the same bridge and custody,
  never a second credential, socket or authority path for the worker. Which tools a role sees stays F13's and the role
  matrix's question (adoption decision §2, §8 item 4).
- **Reviewer independence** bounds the default role shape of the adoption decision §2 for the reviewer and verifier
  roles. It is an input to F21's concrete request-mode and role matrix (§8 item 4): by default a reviewer's or
  verifier's lookup about the Ticket under review excludes the current implementer's reasoning and private working
  state and keeps the canonical records the role needs; broader historical prose from that Ticket is reached through
  an explicit investigation mode where the role holds one. Request modes stay query intent, never authority (adoption
  decision §2), so asking for investigation mode does not widen what a role may see.
- Neither ruling changes WC/KC text. The second applies the Workflow Contract's context independence to lookup: a
  reviewer gets "a fresh or deliberately bounded context" and judges the change against the requirement, plan, diff
  and actual test output, without the implementer's conversational history (WC §4.2, "Independent review"; WC §5.6,
  context independence).
