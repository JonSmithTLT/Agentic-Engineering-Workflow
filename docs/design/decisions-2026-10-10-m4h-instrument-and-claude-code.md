# Designer decisions of 2026-10-10 (evening): the M4-H instrument, E5b, F9 and the Claude Code adapter (F25, F19, F15.2, F9, F24.2)

**Status:** Decision record, governing for what it decides. **Approved** by the designer on 2026-10-10, relayed by the
operator. Eight decisions answer the lead developer's evening brief of the same day. D1 to D3 come from planning the
M4-H instrument: F25's live usage telemetry and F19's evaluation runner, which Q7 v0.3.1 §16 makes M4-H prerequisites.
D4 was found in review of M4-E's slice E5b (F15.2, pull request 182). D5 settles a gap between the F9-A1 adoption and
M4-E's plan. D6 to D8 answer the runtime probe of Claude Code 2.1.296 (register F24.2) for a future Claude Code
adapter. §1 is the decisions as given; §2 gives the context of each; §3 says where they are filed.

The plans the brief drew on (F25's M4-H telemetry plan v4, F19's M4-H instrument plan v5 and the sequencing amendment
of the M4-E plan) are not in the repository; this record names them by register row and slice. None of the decisions
blocks work being built now; most are needed before M4-H's pre-calibration seal.

## 1. The decisions, recorded as given

The designer's text, verbatim:

```text
D1  APPROVE — F25 settlement boundary satisfies M4-H cost requirement.
D2  APPROVE — per-run operator ceremony through constrained evaluator relay.
D3  APPROVE — seal exhaustive request/attention disposition table pre-calibration.
D4  REVISE — retain only non-gating, unrequired inconclusive/not_run verification results.
D5  APPROVE — F9 coordination lane joins wait --any; no second notifier.
D6  APPROVE — Claude Code bare + relay G.
D7  CONFIRM — writable shell is compatible with source-RO + mediated mutation.
D8  APPROVE — project Claude settings fail closed unless explicitly qualified.
```

## 2. Context for each decision

The questions, the facts behind them and the lead developer's recommendation, as put in the brief. The decisions in
§1 govern; this section only explains them.

### D1. The measurement boundary for M4-H's counted cost (F25's G1)

Q7 §9.2 needs live usage the M4-H evaluator can enforce the sealed USD cap with, and EVC-14 names the cost block of the
run record. On F25's G1 the designer had leaned APPROVE on counting F25's live, settled figure for the AEW arm, the Lead
included, provided the measurement boundary was nailed down: which settled entries belong to one run, and when its
snapshot closes. F25's plan (v4 §5) now defines it:

- **Membership:** every OpenCode server started on the arm host for the run id, and all of its sessions from server
  start, relaunches included; the rule is fixed at the task's release.
- **The close:** when every source is final, or 60 s after shutdown begins, whichever is first, for every end of a
  counted run (completion, second quiescence, an operator-only halt, a refusal, either cap, an evaluator-side failure).
- **After the close:** late samples never change the figure; the settled object is frozen and hashed into F19's run
  record, with the in-flight residual stated.
- **No experiment semantics in F25:** F25 reports measured usage only; charging a cap and the stop rule are F19's,
  evaluator-side.

D1 approves: the boundary meets the designer's condition, and G1 is approved. F25's slice L7 records the ruling's
content as its own decision record, with ledger rows (prefix CMB) that amend EVC-14's cost-block source for M4-H only.
This record holds the approval itself. F25's held Lead part (the cost and usage ledger v0.2 §5.7, its item in
decisions due) is a different question and stays open.

### D2. The publication grant ceremony, once per counted AEW run (F19's G1)

M4-E binds the publication envelope and the mode raise to one project and one Lead generation, granted at the operator
endpoint through a console challenge. Each counted AEW-arm run is a fresh cold-start project, so every run needs its own
ceremony: about 164 challenges across the counted runs, and 194 to 214 with calibration. F19's plan orders each A run
as: the Lead attaches, then the raise and the grant, then a host re-check, then the first prompt. The operator answers
from the evaluator through a relay and never logs into the model's host. The relay shows the bound action verbatim,
strips terminal control sequences, and cannot answer a challenge itself (a static test proves it).

The questions were whether a challenge relayed over the evaluator's forced-command channel is an acceptable
human-intent channel under M4-E's `guarantee: dev`, or whether a campaign-scoped grant is wanted instead (new
authority, which the plan does not invent). The brief recommended the per-run ceremony, with the relay's three
properties as its conditions: the operator's time becomes the campaign's pace (an estimated 8 to 10 calendar days),
and no new authority is created. D2 approves the per-run ceremony through that constrained relay; the three properties
are binding conditions on it.

### D3. How the AEW arm's mid-run requests are answered (F19's G2)

Q7 §2.4 needs every AEW request or attention kind sorted before the seal into pre-granted, denied, or an operator-only
halt, and M4-E gives no non-operator channel for the text of a denial or a clarification. Some kinds are ambiguous: a
confirmation under Run, a high anomaly that needs a disposition, a Ticket-revision checkpoint. The brief proposed: the
lead developer drafts the table from E7's event vocabulary; a confirmation can never be pre-granted; a high anomaly
needing a disposition is an operator-only halt; the fixed texts are delivered as a user message in the Lead's session,
the channel of the first prompt; and the designer confirms the table before the pre-calibration seal. The sorting
decides whether a run continues or ends as an AEW failure, so it belongs to the designer, not to the instrument's
builder. D3 approves: the table is exhaustive and sealed before calibration.

### D4. The verification half of `requires_disposition` (M4-E, E5b)

The M4-E plan v3 §2.4 adds the policy key `gates.requires_disposition` with two halves, `review_severities` and
`unrequired_verification_results`. Under today's outcome rules any claim that did not pass already fails the gate, so
the verification half, as written, can never mark anything; E5b builds it as written, and E5b's reviewer agreed. The
question was whether to drop the verification half, or to define which verification results should need a Lead
disposition without failing the gate. The brief recommended defining it narrowly, as unrequired claims that end
`inconclusive` or `not_run`, and otherwise dropping it.

D4 revises the plan: the verification half is kept only for unrequired claims whose verification result is
`inconclusive` or `not_run`, and it never makes a gate fail; such a result needs the Lead's disposition, nothing more.

### D5. The "broker's notifier" the Lead was to learn replies from (F9)

LWA-17, in the F9-A1 adoption, says the Lead learns of worker replies through the attention and resume projections
and, once M4-E's E7 lands, "the broker's notifier". M4-E's plan never had a notifier aimed at the Lead: E7's notifier
is the operator's, run by the operator endpoint (SAE-13). The question was whether F9 owns a Lead-facing wake, or the
projections are enough. The brief recommended that F9 own it, as a coordination lane in the existing `aew harness wait
--any`: no new notifier, and consistent with "no polling" meaning no model-driven polling (LWA-11). D5 approves: F9's
coordination lane joins `wait --any`, and there is no second notifier.

### D6. Bare or non-bare Claude Code runs (F24.2)

C1's pre-request gate, the context budget, uses Claude Code's PostToolBatch hook, and hooks passed with `--settings`
do not run under `--bare`. A non-bare run brings much more with it: a walk of `CLAUDE.md` and `AGENTS.md` up every
ancestor of the working directory (ignoring HOME); a cross-session channel reachable from the agent's shell; about
60 KB of reminders and 18 tools, against about 4.5 KB and 3 tools bare; and shell commands backgrounded at their
timeout rather than killed. The brief judged that each of those breaks an assumption of AEW's containment or of D-22 (the run's deadline
and its bound on a shell command).
C1's variant G gives the same gate under `--bare`, as a pre-egress check in AEW's provider relay (F28), and the probe
showed a loopback provider endpoint works. D6 approves bare runs with variant G, as the brief recommended.

### D7. A harness whose shell can write (F24.2, F40)

Claude Code's native write tools (Edit, Write, NotebookEdit) can be removed from the model's tools, but its shell
still writes. The question was whether the morning's D1 (MCD-01, MCD-02: read-only source, writable scratch, mediated
authoritative mutation, the shell kept) qualifies such a harness under M6a §7 (v0.9 §7, GAE-12 to GAE-14), provided
the source is mounted read-only. D7 confirms: it is the same rule for every harness, so M6a §7 is met that way.

### D8. A project `.claude/settings*.json` in the worktree (F24.2)

Even under `--bare`, Claude Code applies the `env` of a project's `.claude/settings*.json`, the user settings' `env`
and the shell's startup file, so a repository can change the worker's environment. The question was whether the
adapter fails closed when the tree has a project `.claude/settings*.json`, or runs the worker in a tree without one.
The brief recommended failing closed by default, with a named policy exception for a repository that needs its
settings, so the exception is visible and recorded. D8 approves: the adapter fails closed unless the project is
explicitly qualified.

## 3. Filing (lead developer)

- **Ledger:** MIC-01 to MIC-15.
- **D1** is filed on F25 and F19. G1 is approved; F25's slice L7 records its content (ledger CMB, amending EVC-14's
  cost-block source for M4-H only), so no decisions-due item is needed for it. F25's existing item, the Lead part
  (v0.2 §5.7), is a different question and stays open.
- **D2 and D3** are filed on F19 (its G1 and G2), and D2 also on F15.5 (the operator endpoint and its challenge). The
  relay's three properties are binding, and the request and attention disposition table is sealed before calibration.
- **D4** is filed on F15.2. It narrows the M4-E plan v3 §2.4's `unrequired_verification_results`, which no ledger row
  carries; E5b (pull request 182) is implementing it.
- **D5** is filed on F9 and F15.5. LWA-17's "the broker's notifier" is marked `superseded-by:` MIC-09; its attention
  and resume projections stand. The lane lands in a later F9 slice.
- **D6 to D8** are filed on F24.2, and D7 also on F40 and as a note on MCD-02, which it confirms for a harness whose
  shell can write.
- **No decisions-due item** is answered by these decisions: none was filed for F19's G1 and G2, D4 or D5, and F25's
  item is the Lead part.
