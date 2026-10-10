# Designer rulings of 2026-10-09: worker tool delivery and reviewer independence (F21)

**Status:** Decision record, governing. **Adopted** by the designer on 2026-10-09, the day the operator adopted the
knowledge system ([adoption decision](decisions-2026-10-09-knowledge-system-adoption.md)). The two rulings answer
questions the lead developer raised while preparing F21's implementation-readiness package (adoption decision §8): how
knowledge lookup reaches a worker, and what a reviewer or verifier may look up about the Ticket under review. §1 is the
rulings as given; §2 says where they are filed and how they meet the adopted designs.

## 1. The rulings, recorded as given

The two questions: how knowledge, map and helper operations reach a worker inside its sandbox; and the lead
developer's proposal to exclude all records of the Ticket under review from reviewer and verifier lookup. The
designer's reply, relayed by the operator, opened "On Opus's two points:" and continued:

> * Worker tool delivery: APPROVE. This is actually already the intended `aew-run` architecture: the worker sees typed tools, requests go through the supervisor bridge, and credentials remain supervisor-side. Knowledge/map/helper operations should extend that mechanism rather than create another worker credential surface.
> * Reviewer independence: REVISE. I would not exclude all records belonging to the Ticket under review. AEW defines independence as fresh/bounded context with the implementer reasoning transcript excluded. Meanwhile, the verifier explicitly needs unresolved review findings and relevant canonical evidence. Blanket same-Ticket hiding would destroy legitimate rework/verification context.
>
> The better rule is: hide current implementer reasoning/private working state by default; preserve canonical objective, plan, diff, check results, findings, failures, and whatever the role actually requires. Broader historical prose from that Ticket can require explicit investigation mode.

## 2. Filing (lead developer)

- **Ledger:** KDR-01 to KDR-05.
- **Worker tool delivery** is register F15.3's `aew-run` role server: typed tools inside the sandbox through a thin
  client, requests through the supervisor bridge, credentials supervisor-side (typed Lead surface v0.2 §6, ledger
  TLS-23). F15.3 already names `aew-knowledge` as a separate capability *namespace* over the shared transport; the
  ruling says that knowledge, map and helper operations should extend the same bridge and custody rather than create
  another worker credential surface. The lead developer reads that, with F15.3's custody rule, as no second credential
  for the worker (KDR-02). Which tools a role sees stays F13's and the role matrix's question (adoption decision §2,
  §8 item 4).
- **Reviewer independence** bounds the default role shape of the adoption decision §2 for the reviewer and verifier
  roles. It is an input to F21's concrete request-mode and role matrix (§8 item 4): by default a reviewer's or
  verifier's lookup about the Ticket under review excludes the current implementer's reasoning and private working
  state and keeps the canonical objective, plan, diff, check results, findings, failures and whatever the role
  actually requires; broader historical prose from that Ticket can require an explicit investigation mode, which the
  role matrix settles. Request modes stay query intent, never authority (adoption decision §2).
- Neither ruling changes WC/KC text. The second applies the Workflow Contract's context independence to lookup: a
  reviewer gets "a fresh or deliberately bounded context" and judges the change against the requirement, plan, diff
  and actual test output, without the implementer's conversational history (WC §4.2, "Independent review"; WC §5.6,
  context independence).
