<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-42
source: 30-stages/STG-18-unattended-mission/adopted/msn-r2.1/MSN-POSITION.md
source-sha256: 30fcfef618d677395ed6d4301d90b584d1d62ef1eb6d21c99895d91120f5d65d
edits-sha256: none
-->

# The bounded unattended mission (PROPOSED, revision 2.1)

**Namespace:** `MSN-`
**Status:** proposed.
- It states RX-01's selected mission (`RX-DEC-03`) at contract altitude, and answers A-40's backlog `WISR-B2`.
- It amends A-39 by two protective additions, which only lower and never raise: a mission's stop lapses any `RUN` in force, which adds a lapse condition to `I6-06.g` and a second, lowering-only path to `I6-06.f` (`MSN-04.a`).
- I-7's mechanism for the one consent's outcome is a further amendment, of A-24's set rule or of `I6-06.a`, which I-7 names (`MSN-04`).
- No adopted byte changes.
- **For the operator at adoption:** one question, whether V-01's mission row needs the relay's meter (`MSN-R03`).
**Authority:**
- the first selections of 2026-10-24 (`00-governance/decisions/2026-10-24-operator-first-selections-research-maps-knowledge.md`): one bounded unattended mission in V-01, and what it is;
- the decision on `R-DEC-04` and `R-DEC-03` (`00-governance/decisions/2026-10-25-operator-R-DEC-04-two-steps-auto-run-under-run-and-R-DEC-03-built-supervision.md`): what `RUN` auto-runs, and the built supervision set;
- the selection before I-7 (`00-governance/decisions/2026-10-25-operator-selection-before-I-7.md`, choice 4): its position comes next, before I-7, so its fields join I-7's amendment of the work-proposal types;
- the operator's instruction of 2026-10-25 to start it beside CNI's link vocabulary's review.
**Threat model:** the security depth reset (`00-governance/decisions/2026-10-24-operator-security-depth-reset.md`): a contained agent cannot fake an approval, forge an owner fact, read a credential or escape. Malicious code running as the operator is out of scope (`00-governance/decisions/2026-10-19-operator-G3-threat-model.md`). Here, a mission's acceptance, its stop and its cap are the approvals and owner facts at stake. Under the posture, an unattended run the operator cannot bound would be the real cost.
**Research consulted:**
- **For `RX-DEC-03` and `AEW-FR-42`:** the software research workflow study (`software-research-workflow-2026-10-15`, `private:software-research-workflow-2026-10-15/`, partly adopted). It found no unattended specimen, and advised waiting for one long attended run with a measured stop rule. This position makes attended runs its first gate check (`MSN-Q01`, `MSN-R07`). `RX-DEC-03` also hits the Q7 task-family study (`q7-m4h-task-families-2026-10-06`), which bears on AEW's value gate and says nothing on missions.
- **For `HEB-08` and `CNI-07.a`:** the same study, on recovery, and on research work that forces no Epic, Story or Ticket.
- **For `R-DEC-03`:**
  - the external-workflow study (`external-workflow-2026-10-05`): crawl, walk and run is one confirmation predicate, unmeasured because every run was headless, and it recommends an operator-present arm so the modes can be measured (`MSN-R07`);
  - the agent-effectiveness study and its synthesis (2026-10-09): the Lead's cost sits in queries and waits.
- **For `A-15`:** also the external agent workflow lessons (2026-09-28), on fan-out and cost bounds. This position adds no fan-out rule.
- **For `RX01-22` to `RX01-29`, `WIS-05.h`, `CNI-07.e`, `CNI-08`, `R-DEC-01`, `R01-08`, `R01-09`, `R01-26`, `R01-34`, `R01-42`, `R01-43`, `ADC-08.f`, `AOI-07.f`, `CNI-03.g`, `CNI-05.e`, `IF10-04`, `IF10-13`, `IF10-14`, `G3-03`, `I6-05`, `I6-06`, `A-39`:** none.
**Files:** this file; `CHANGES-r2.md`, the answers to round 1.

## What the adopted text already decides

- **What a mission is:** an accepted objective, a window and stop condition, delegated discretion, its source, grant and attachment identity, a cumulative resource and effect envelope, an expected report and reserved decisions. The unattended designation grants nothing (`RX01-22`, `AEW-FR-42.a`). It may be research or engineering (`AEW-FR-42.a`), and needs no Epic, Story or Ticket (`CNI-07.a`).
- **Its episodes:** a mission may contain identifiable episodes with reports and resource attribution, distinct from grants, with no Epic or Ticket per episode (`WIS-05.h`).
- **Before the operator leaves:** a proportionate preflight of foreseeable questions, with nothing speculative made formal (`RX01-23`, `AEW-FR-42.b`).
- **While the operator is away:**
  - questions are held with their subject, revision, authority and response channel;
  - silence, a timer or a delivered prompt approves nothing;
  - independent work continues;
  - where G3 is unavailable the decision stays held (`RX01-24`, `AEW-FR-42.c`, `AOI-06.c`, `AOI-06.d`).
  - Bounded exploration may run while a decision is pending, and stays provisional (`RX01-25`, `AEW-FR-42.d`).
- **Continuation and recovery:**
  - nothing renews authority (`RX01-26`);
  - a recoverable launch failure gets bounded, supervised retry within current authority and resource limits (`HEB-08.c`);
  - no consequential effect is replayed while its completion is uncertain (`HEB-08.d`);
  - a new Lead rehydrates recorded state without re-asking valid decisions (`HEB-08.f`);
  - nothing resumes because the operator looks (`HEB-08.g`);
  - restarting needs deliberate authorization (`HEB-08.h`);
  - supervision under detach and drain keeps custody distinct (`R01-34`).
- **Holds:** a consequential dispatch is rechecked against its conditions when it takes effect (`CNI-03.g`, `AOI-07.f`), and a hold clears only on qualified evidence and an authorized continuation (`CNI-05.e`). A protective reduction is not blocked by irrelevant basis changes (`AOI-07.f`).
- **Resources:**
  - usage is attributed to the objective (`RX01-27`, `AEW-FR-42.h`), in typed states that keep a cooperative observation apart from qualified settlement (`IF10-14`);
  - money, wall time, concurrency and rate are kept apart (`R01-04`);
  - a hard limit needs a qualified meter and admission binding outside the metered lineage, and an enforceable worst-case charge per paid call; an unsupported class reads `NOT_ESTABLISHED` (`R01-08`, `R01-09`, `R01-42`, `R01-43`, `IF10-13`);
  - a hard limit holds ongoing execution as well as new allocations (`ADC-08.f`).
- **The report:** a recipient-safe disposition separating findings, blocked or unexecuted work, remaining effects, costs and reserved outcomes, never reporting a plan as success (`RX01-29`, `AEW-FR-42.f`). Interrupted or exhausted work keeps its progress and unknowns, without a false termination (`CNI-07.e`). The operator has a supported way to see and answer what the mission needs (`CNI-08.b`, `RX01-35`).
- **A-39:**
  - **the steering mode:** with the operator's consent, R-01 sets it for one Lead generation. It decides only whether an eligible action waits, and lapses to `CRAWL` when the generation ends (`I6-06`, `I6-06.g`). An action the mode does not auto-run waits for the Lead to take it itself (`I6-06.e`). The mode changes only through its own type, and no admission check reads it (`I6-06.f`).
  - **the cap:** a widening is `ISSUE_STANDING_POLICY` (`I6-03`). After a narrowing, every later paid admission compares against the new state, ongoing execution under a hard bound is held at its enforceable boundaries, and a dispatched request that cannot be halted completes and stays accounted (`I6-02.d`).
  - **routes:** a paid dispatch is paid under a standing policy that names its route's provider and account (`I6-05`).
  - **sets:** admitted member by member, each under its own owner (`I6-11`).
- **The decision on `R-DEC-04` (2026-10-25):** under `RUN`, starting a ready Ticket and requesting review auto-run; `WALK` reaches nothing in V-01. In `CRAWL` the Lead takes each step itself. Each activation has an envelope: a deadline, an action count and a repetition key. Spend is bounded by the mission's cap at the provider relay.
- **The decision on `R-DEC-03` (2026-10-25):** heartbeats, the notifier and live usage are the first supervision set, with no idle tokens.
- **A-40's inquiries:** work of their own kind, completed by their answer (`WISR-01`), whose dispositions never read as engineering completion (`WISR-02.d`). Owner facts are AEW's observation (`WISR-09`).

**What is missing:**
- no adopted text says what kind of record a mission is, what it covers, or how it is accepted;
- nothing says what stops it, what a stop holds, or what the report is built from;
- nothing says how the spend cap is honest on a host whose meter is not qualified.

## The parts

| Part | What it is | Written by | Read by |
|---|---|---|---|
| A mission | WIS work of kind `mission`: its objective, the accepted work it covers, its window, stop conditions and drain's end, its report point and its reserved decisions, the attachment identity it runs under, and their revisions | AEW's host code, on the operator's acceptance through G3 | the operator, the Lead, Coordination, R-01 |
| Its preflight | the list, built from records, of what is unanswered, unqualified, reserved or out of reach before the operator leaves | AEW's host code | the operator, at the consent |
| An episode | one run, or one Lead activation, during the mission | AEW's host code, from HEB's run records | the report, the operator |
| Its cap | an I-6 standing policy bounding the paid usage admitted under the mission, expiring at the drain's end | the resource policy issuer, on the operator's consent (`I6-03`) | R-01's admission at effect time |
| Its stop's hold | a hold on the project's new run admissions, from WIS's record of the stop | AEW's host code | each run admission's recheck at effect time |
| Its report | the disposition at the stop, built from records, with the agents' narrative attached as attributed text | AEW's host code | the operator, read-only |
| The provider relay | the route each contained run's model calls take out of its sandbox (STG-05 CS-3b for workers, CS-4 for the Lead) | AEW's host code, outside every sandbox | R-01, as a meter where it qualifies |

## Rules

**MSN-00. Precondition: a mission's stops hold without the operator, and its cap is a hard limit only where R-01 qualifies the paid class.**
- **The window, the drain's end and the stop's hold** are enforced by AEW's host code, from the host's clock and WIS's records, outside every agent's reach. An agent cannot extend, reset, skip or clear them.
- **The steering loop's envelope** (a deadline, an action count and a repetition key per activation, in the decision on `R-DEC-04`) bounds each activation where it is built. A-39 keeps it as a Candidate, and this position states no rule for it.
- **The cap is a hard limit only where R-01 qualifies the paid class as hard-limit-supported on that host and provider:** a meter and an admission binding outside the metered lineage, an enforceable worst-case charge per paid call, and every paid route a mission's run can reach covered (`R01-08`, `R01-09`, `R01-42`, `R01-43`, `IF10-13`). Otherwise the cap's enforcement reads `NOT_ESTABLISHED`, and nothing claims it bounds spend.
- **None of this is built at `main`** (2026-10-25; "Not covered"). No mission counts for V-01's row until the window's enforcement and the stop's hold are built, and, under `MSN-R03`'s reading (a), the meter and the class's qualification. Until then the attended runs of `MSN-Q01` are the only missions.

**MSN-01. A mission is WIS work of its own kind, `mission`, accepted by the operator through G3. It grants nothing, and its stop only holds.**
- **What its accepted revision names:**
  - its objective, as the operator accepted it;
  - the accepted work it covers, each at its accepted revision. Coverage defaults to every accepted, not-done Ticket of the project, and the operator may narrow it (`MSN-R04`);
  - its window, its stop conditions and its drain's end (`MSN-02`);
  - its report point, and the decisions it reserves.
- **Where the rest of `RX01-22`'s fields live,** in records that already exist:
  - **its delegated discretion** is the Lead's current grant, unchanged, less the decisions it reserves;
  - **its source, grant and attachment identity** is the project, the Lead generation and the grant in force at the acceptance, which the mission's record names by reference. The stop's hold names them (`MSN-06`);
  - **its cumulative envelope** is its cap for resources (`MSN-05`), and for effects the covered work's own admissions, none of which the mission widens.
- **It is completed by its report,** at its stop, never by a verification PASS or by its covered work's completion (as `WISR-01` states for an inquiry). It needs no Epic, Story or Ticket of its own, and its report reads no covered inquiry's disposition as engineering completion (`CNI-07.a`, `WISR-02.d`).
- **Every effect inside it** is admitted by its own owner's rules, and nothing is admitted that would be refused with no mission open (`RX01-22`).

**MSN-01.a** What a mission covers is its accepted revision's content. It is not parentage (`WIS-03.a`), and not a link: CNI's link vocabulary (STG-17, in review) closes the kinds a link record may carry, and a mission adds none. A covered work item keeps its own parent, acceptance, grants and lifecycle.

**MSN-01.b** A project has at most one open mission. A second acceptance while one is open is refused, naming the open mission, and changes nothing. Concurrent missions are not selected (the first selections).

**MSN-01.c** Every admission in the project from a mission's start to its stop is under that mission, covered or not. Each is attributed to it (`MSN-08`), counted by its cap (`MSN-05`) and listed in its report (`MSN-10`). Runs admitted before the stop stay under it while they drain. The covered work is the subset that "done" and the stop conditions read.

**MSN-02. A mission's window and its drain end within one bound, and a stored login is shown, never refused on.**
- **The selection bound:** the window and its drain both end within 24 hours of the mission's start (`MSN-R06`).
- **Stored logins:** for every route a mission's run can reach that is served from a stored provider login, which the relay reads and never refreshes (STG-05, CS-4's addendum 1), and that lapses before the drain's end, the preflight shows when it lapses and what follows for that route:
  - for the Lead's route, its judgments wait, and runs on keys continue;
  - for a worker's route, its runs fail at their first model call, and are not retried past `HEB-08.c`'s bound.

  It names the renewing step where the host knows one. Nothing is refused on a login, as addendum 2 warns at the Lead's launch and blocks nothing.

**MSN-03. Before the consent, the preflight shows what the records already name, and nothing speculative.** AEW's host code lists, for the work the mission covers and reaches (`RX01-23`, `AEW-FR-42.b`):
- the decisions pending or reserved, and the questions open;
- the holds in force;
- the reach: every accepted, not-done Ticket of the project, and that all their paid use counts against this mission (`MSN-01.c`);
- each bound's enforcement state: the cap as the consent renders it (`MSN-05`), and the notifier's;
- the window's end, and the drain's end as the latest time anything under the mission runs;
- each stored login that lapses before the drain's end, the Lead's or a worker's, with what follows (`MSN-02`);
- what the operator cannot do while away: "while you are away from this desktop you cannot stop this mission or answer it", since G3 is on the desktop (A-37); and that a Lead end leaves the rest of the window with no Lead and no auto-run (`MSN-06.a`).

The operator answers each item before leaving, or leaves it reserved; one left unanswered is reserved, and held. No item needs an answer before the mission starts. **Candidate:** the preflight is a read of the store at the consent, rendered with the set.

**MSN-04. One consent starts a mission, and costs no more than raising `RUN`.**
- **The set:** the mission's acceptance, its cap, its steering mode unless `RUN` is already in force for the generation, and, while an earlier stop's hold is in force in the project, the continuation that clears it (`MSN-06`). Starting costs one G3 consent and one PIN, however many members the set has (`I6-11`, `I6-12`; the PIN-budget rule of 2026-10-24).
- **The set's outcome:** the mission opens only when its acceptance and its cap are both admitted. Otherwise nothing of the set is in force for it, and the mode is as it was. A continuation in the set is the operator's own deliberate act, and stands whether or not the mission opens. A mode raised in a mission's consent is never in force without that mission open. The mechanism is I-7's, and is itself an amendment, of A-24's member-by-member set rule or of `I6-06.a`'s admission conditions, which I-7 names.
- **No costlier than the raise:** the window and the coverage come pre-filled, and the preflight needs no answer. **Candidate:** a `RUN` raise's own consent offers the mission form.
- **The bare raise stays as A-39 has it.** This position does not bound a `RUN` raised without a mission: bounding it would change `I6-06.g`, which is not this stage's.

**MSN-04.a** Any `RUN` in force for the project's current Lead generation when a mission stops lapses to `CRAWL`, whether it was raised in the mission's consent or before it. R-01 records the lapse on WIS's record of the stop, and the mode's target is unchanged. The lapse only lowers, never raises: it adds a lapse condition to `I6-06.g`, and a second, lowering-only path to `I6-06.f`'s "it changes only through this type" (`MSN-R05`). It rests on `I6-06.g`'s lapse as adopted. The built override lapses to the standing mode instead (STG-12's as-built trace), so this waits for I-6's build.

**MSN-05. The cap bounds the paid routes it can count, says so where it cannot, and ends with the mission.**
- **Its enforcement leaf:** where R-01 qualifies the class (`MSN-00`), the cap's `ISSUE_STANDING_POLICY` is issued `MANDATORY_HARD`. Otherwise it is issued `COOPERATIVE`, with `cooperative_limit_ack` true, and the preflight's `NOT_ESTABLISHED` and the consent's rendering say the same thing (`G3-03`, `IF10-04`).
- **At a reached hard cap:** every later paid call under the mission is held, whatever other policy also covers it, and ongoing execution is held at its enforceable boundaries. A dispatched call that cannot be halted completes, and is accounted under its operation (`I6-02.d`, `ADC-08.f`, `I6-X01`). The mission stays open until a stop (as `WISR-02.f` holds an inquiry at a limit).
- **A cooperative cap** stops nothing, and is never shown as an enforced limit (`R01-43`).
- **Its expiry** is the drain's end, so the paid eligibility it gives ends with the mission (`I6-05`).
- **Routes by class,** the Lead's as a worker's: a route served from a stored subscription login is a quota class, reported apart. A route on a paid key is money, eligible only under a standing policy that names it, and counted by the cap like any paid route (`R01-04`, `I6-05`).
- **A widening** is `ISSUE_STANDING_POLICY` through G3 (`I6-03`), never through the mission.

**MSN-06. A mission stops at its window's end, at a stop condition over records, or at the operator's stop. A stop holds new runs and drains the rest.**
- **The stops:**
  - the window's end, on the host's clock;
  - a stop condition the accepted revision names, which AEW's host code evaluates from records (for example, every covered work item done, or a named hold raised). Some of those records are agents' own, such as a Ticket's transitions, so a condition may end a mission early and never extends one. The window and the operator's stop are the bounds;
  - the operator's stop, through G3. It only reduces, so it is a reducing type, admitted on the operator's consent alone and not blocked by irrelevant basis changes (`AOI-07.f`).
- **At a stop, the hold:** WIS records the stop, and AEW's host code holds every new run admission and every new paid admission in the project that is not the operator's own G3 action, whether the auto-runner or the Lead requests it. That includes the Lead's own model calls on a paid route. A quota route is not a paid admission, and is not held.
  - It is a basis member each such admission rechecks at effect time (`CNI-03.g`, `AOI-07.f`). It reads the stop, never the mode (`I6-06.f`), and names the mission's attachment identity (`MSN-01`).
  - It clears only on the operator's deliberate continuation: one G3 action, which I-7 names (`CNI-05.e`, `HEB-08.h`, `R01-34`). A stop never resolves, so the continuation alone clears it. Its refusal names the stop and that continuation.
  - Read-only work, and the Lead's own work that dispatches and pays for nothing, continue (as `RX01-38` continues independent safe inquiry).
- **The drain:** runs already admitted drain until the drain's end, then are stopped. A run that did not finish, or a remote effect whose state is unknown, is recorded as unknown, never as stopped or done (`HEB-08.b`, `HEB-08.d`, `I6-02.d`).
- **A stop renews nothing and restarts nothing** (`RX01-26`, `HEB-08.h`). The hold waits for the build (`MSN-00`).

**MSN-06.a** The end of the Lead's generation is not a mission stop.
- **What follows:** any `RUN` lapses to `CRAWL` (`I6-06.g`), so nothing auto-runs, and no Lead takes a step. Admitted runs continue under their own admission, and the notifier tells the operator that the runs are detached. The rest of the window has no Lead and no auto-run, and the preflight says so (`MSN-03`).
- **Recovery within the window:** a recoverable launch failure of an admitted run gets bounded, supervised retry within current authority and the mission's cap, and each attempt is recorded (`HEB-08.c`). After a stop, a retry is a new run admission, and the hold holds it.
- **A new Lead** starts only by the operator's deliberate start (`HEB-08.h`). It rehydrates the open mission's record from WIS, and never re-asks what the mission's acceptance records (`HEB-08.f`).
- **The mission stays open until a stop,** and its report records the interruption (A-03's `AS-RX10`; `HEB-08.g`). Like `MSN-04.a`, the lapse waits for I-6's build.

**MSN-07. While the operator is away, a question is held, never answered by silence, and costs no idle tokens.**
- **A reserved decision or a question** is held with its subject and revision, its authority, and its response channel, which is G3 (`RX01-24`). The affected work waits, and independent work continues (`CNI-05`).
- **The answer goes through G3** (A-37). Where G3 is unavailable, the decision stays held. A rendering on the site, the CLI or a message is not an answer (`AOI-06.d`).
- **The notifier** tells the operator, in R-DEC-03's built set. Waiting runs in host code, and no model polls (`R01-26`).

**MSN-08. Every admission under the mission is attributed to it.** Each one names the mission and, where it served covered work, that work (`MSN-01.c`). Usage is in `IF10-14`'s typed states. Money, quota, wall time and concurrency are reported apart, each route by its class (`RX01-27`, `AEW-FR-42.h`, `R01-04`, `MSN-05`).

**MSN-09. Each run and each Lead activation during the mission is an episode.** It is referenced from the mission's record, with its time, its subject and its usage. It needs no Ticket of its own, and carries no grant (`WIS-05.h`).

**MSN-10. The report is built from the records, at the stop.** AEW's host code assembles it (`RX01-29`, `AEW-FR-42.f`, `CNI-07.e`):
- what was done, what was blocked, and what is unknown;
- what ran, and what was proposed or planned but never ran;
- the questions still open and the decisions still held;
- the effects that remain, and the runs whose outcome is unknown;
- usage, in `IF10-14`'s states: a figure from a run's own harness server is `USAGE_OBSERVED_COOPERATIVE`, with its source named as reachable by the run; money and quota apart;
- the stop's cause, and any interruption (`MSN-06.a`).

No covered inquiry's disposition reads as engineering completion (`WISR-02.d`). The agents' own narrative is attached as attributed text, and never replaces a record. The report cites work, claims and results by identity, or by hash and path. Those citations are references, not links Coordination acts on.

**MSN-11. On the operator's return, nothing resumes because they look.** The report and the mission's state are a read-only view from records, which launches no model (`HEB-08.e`, `HEB-08.g`). Continuing any work after the stop is the operator's deliberate continuation (`MSN-06`, `HEB-08.h`).

**MSN-12. A mission's owner facts are AEW's observation.**
- **Who accepted it, its accepted fields, its stop and its cause** are taken from the authenticated command or the owners' records, never from a value the caller supplies (as `WISR-09` states for A-40's records).
- **Its usage** is taken from the meter where R-01 qualifies one. Otherwise it is a cooperative figure, shown as cooperative, and it never lowers the exposure R-01 counts (`R01-08`).

## Interfaces

- **Commands.** **Candidate:** in O-01, with I-7:
  - **the acceptance:** `DECIDE_WORK_PROPOSAL`, with `mission` added to its work kinds and the mission's fields (`MSN-01`), in the same amendment of `CREATE_PROPOSED_WORK` and `DECIDE_WORK_PROPOSAL` that A-40 gives I-7. Its record names the attachment identity by reference;
  - **the one consent** (`MSN-04`): a set of that acceptance, the cap's `ISSUE_STANDING_POLICY` with its `enforcement` leaf and an expiry at the drain's end (`MSN-05`), and, unless `RUN` is in force, `SET_STEERING_MODE` to `RUN`, whose target is unchanged; and, while an earlier stop's hold is in force, the continuation. I-7's pass confirms that one set may carry these owners' members, and gives the set `MSN-04`'s outcome through an amendment it names, of A-24's set rule or of `I6-06.a`;
  - **the lapse** (`MSN-04.a`): R-01's record on WIS's record of the stop, with no new target field;
  - **the operator's stop** (`MSN-06`): a reducing type, as the registry's `STOP_CHILD_NOW`, `SUSPEND_GRANT`, `CLOSE_ATTACHMENT` and `NARROW_OR_REVOKE_STANDING_POLICY` are. A-40's inquiry stop (`WISR-02.b`) was modelled on cancelling work, which the registry has as `PRESERVING_OR_INCREASING`; I-7 registers both stops alike;
  - **the continuation** (`MSN-06`): one G3 action that clears a stop's hold, which widens what may run.
- **Reads.** **Candidate:** in D-01's next revision, with the shared read wire, matched with the wire track: a mission reads as work of kind `mission`, with its preflight, its episodes, its hold and its report.
- **Refusals:** the refusals of `MSN-01.b`, `MSN-02` and `MSN-04`, and the hold's reason (`MSN-06`), which names the stop and the continuation, take their names in O-01's refusal registry with I-7.

## The gate

| Check | What it shows | Pass |
|---|---|---|
| **MSN-Q01** | The first runs are attended (`MSN-06`, `MSN-00`) | before any unattended mission counts for V-01's row, attended runs with the operator present together observe each stop firing (the window's end, a stop condition over records, and the operator's stop), each with a run in flight that drains to the drain's end, and a run admission requested after a stop seen held, then cleared by the continuation. The record is the operator's data, and the operator decides whether it suffices |
| **MSN-Q02** | The stops hold without the operator (`MSN-00`) | an agent that tries to change the window, the drain's end or the stop's hold is refused, and each still fires on time; a `ticket_start` the Lead requests itself after the window's end is held, naming the stop and the continuation that clears it; the cap reads `NOT_ESTABLISHED` wherever R-01 has not qualified the class |
| **MSN-Q03** | A mission is work of its own kind and grants nothing (`MSN-01`) | a mission is accepted only through G3, completes only by its report at its stop, creates no Epic, Story or Ticket, and its record names the attachment identity; no effect inside it is admitted that would be refused with no mission open; no covered inquiry's disposition reads as completion |
| **MSN-Q04** | Coverage is content (`MSN-01.a`) | the covered work keeps its parent, acceptance, grants and lifecycle; no link is recorded for coverage |
| **MSN-Q05** | One mission at a time (`MSN-01.b`) | a second acceptance while one is open is refused, naming the open one, and changes nothing |
| **MSN-Q06** | The window's bound and the login (`MSN-02`) | a window whose drain ends more than 24 hours after its start is refused; where a stored login, the Lead's or a worker's, lapses before the drain's end, the preflight shows when, what follows for that route and the renewing step, and nothing is refused on it |
| **MSN-Q07** | The preflight shows what the records name (`MSN-03`) | each pending decision, open question, hold, the reach, each bound's enforcement state as the consent renders it, the window's and the drain's ends, and what the operator cannot do while away appear before the consent; an item left unanswered is held as reserved; no item needs an answer to start; no item appears that no record names |
| **MSN-Q08** | One consent (`MSN-04`) | starting a mission takes one G3 consent and one PIN; with `RUN` already in force, the mission opens with no mode member; a refused acceptance or cap opens no mission and leaves the mode as it was; no mode raised in a mission's consent is in force without that mission open; with an earlier stop's hold in force, the set carries the continuation, still one PIN, and the new mission's runs start; if that acceptance is refused, the continuation still stands |
| **MSN-Q09** | The mode lapses at the stop (`MSN-04.a`) | after a mission's stop, any `RUN` in force for the generation, raised in the consent or before it, has lapsed to `CRAWL`, and no step auto-runs until the operator raises the mode again; the lapse never raises a mode |
| **MSN-Q10** | The cap is honest (`MSN-05`) | before V-01's mission row counts, the relay meters every paid route a mission's run can reach and R-01 qualifies the class on the row's host, so the cap is issued `MANDATORY_HARD` (`MSN-R03`, pending the operator's call); there, a running worker's next paid call after the cap is held, a call that cannot be halted completes and is accounted, and the mission stays open. On a host without it, the cap is issued `COOPERATIVE` with its acknowledgement, reads `NOT_ESTABLISHED` in the preflight, the consent and the report, and stops nothing. The cap expires at the drain's end; a paid-key route is counted as money, and a stored-login route is reported as quota |
| **MSN-Q11** | Stops hold and drain (`MSN-06`) | at each stop, every new run admission in the project, the auto-runner's or the Lead's, is held until the operator's continuation, and read-only work continues; a model call the Lead makes on a paid route after the stop is held, and one on a quota route is not; admitted runs drain to the drain's end, then stop; an unfinished run or unknown remote effect reads as unknown; a stop condition kept from firing still ends at the window; the operator's stop is admitted despite an irrelevant basis change; nothing restarts |
| **MSN-Q12** | The Lead's end is not a stop (`MSN-06.a`) | when the Lead's generation ends mid-mission, nothing auto-runs, admitted runs continue, and the operator is notified; a recoverable launch failure within the window is retried within limits and recorded; a new Lead starts only by the operator, and rehydrates the mission's record; the mission stays open and records the interruption |
| **MSN-Q13** | Questions are held (`MSN-07`) | a question unanswered for the whole window is still held at the stop, with its authority and response channel; independent work progressed; no model ran while waiting; a rendering on the site answers nothing |
| **MSN-Q14** | Attribution (`MSN-08`) | every admission under the mission, covered or not, names it, with usage in `IF10-14`'s states; money and quota are reported apart, each route by its class |
| **MSN-Q15** | Episodes (`MSN-09`) | each run and Lead activation is listed from the mission with its time, subject and usage; none created a Ticket or carries a grant |
| **MSN-Q16** | The report is built from records (`MSN-10`) | each section matches the records at the stop; a run that never happened is never reported as run; a run-server figure reads `USAGE_OBSERVED_COOPERATIVE` with its source; no inquiry's disposition reads as completion; the agents' narrative is attached and attributed, and replaces nothing |
| **MSN-Q17** | Nothing resumes on return (`MSN-11`) | opening the report launches no model and starts no run |
| **MSN-Q18** | Owner facts (`MSN-12`) | a caller-supplied acceptor, stop cause or usage never reaches the mission's record; a cooperative figure never lowers the exposure R-01 counts |
| **MSN-Q19** | Everything in the project is under the mission (`MSN-01.c`) | an uncovered Ticket that `RUN` starts during the window is attributed to the mission, counted by its cap and listed in its report |

## Scenarios

**MSN-X01.** Given a mission accepted on Friday evening with a twelve-hour window and a one-hour drain, on a host where R-01 has not qualified the paid class, the preflight and the consent show the cap as cooperative and `NOT_ESTABLISHED`. The window and its drain are the bounds that hold, and the report shows usage as `USAGE_OBSERVED_COOPERATIVE` (`MSN-00`, `MSN-05`, `MSN-06`).

**MSN-X02.** Given a question that needs a reserved decision on Saturday, the affected Ticket waits, independent Tickets continue under `RUN`, and the question is still held at the stop. The report lists it as open (`MSN-07`, `MSN-10`; A-03's `AS-RX09`).

**MSN-X03.** Given the Lead's process crashing at 19:00 in a window that ends at 06:00, the mode lapses, nothing auto-runs, the admitted runs finish, and the operator is notified. The rest of the window has no Lead, as the preflight said, and the report records the interruption (`MSN-06.a`; A-03's `AS-RX10`).

**MSN-X04.** Given the window ending while a remote test is still running, the test drains until the drain's end, then is stopped. Its outcome is recorded as unknown, and the report lists the remaining effect with its responsible next action (`MSN-06`; A-03's `AS-RX19`).

**MSN-X05.** Given a worker reporting "all done" while one covered Ticket is still under review, the stop condition "every covered work item done" does not fire, because AEW's host code evaluates it from the records. If the Lead never records that Ticket's resolution, the mission ends at its window (`MSN-06`).

**MSN-X06.** Given an operator who opens the dashboard on Monday, the report reads from records, and no Lead or worker starts (`MSN-11`).

**MSN-X07.** Given the Lead's login lapsing at 04:00 in a window that ends at 06:00, the preflight shows that after 04:00 the Lead's judgments wait and runs on keys continue, with the renewing step. The operator renews the login, shortens the window, or starts the mission as shown (`MSN-02`).

**MSN-X08.** Given the window ending at 06:00 on Saturday, and the Lead, woken at 06:10, requesting `ticket_start` on a covered Ticket, the start is held, naming the mission's stop and the continuation that clears it. Nothing new runs until the operator's continuation on Monday (`MSN-06`).

**MSN-X09.** Given `RUN` raised at 14:00 for attended work and a mission started at 18:00, the consent carries no mode member, and the mission opens with `RUN` as it is. At the stop, `RUN` lapses to `CRAWL` (`MSN-04`, `MSN-04.a`).

**MSN-X10.** Given a mission covering three Tickets, and two Tickets accepted last week becoming ready on Saturday, `RUN` starts them. Their paid use is attributed to the mission, counted by its cap and listed in its report (`MSN-01.c`).

**MSN-X11.** Given a Lead switched to a model on a paid API key before the operator leaves, the Lead's calls are money: eligible only under a standing policy that names the route, counted by the cap and reported as money (`MSN-05`). After the stop, its calls are held until the continuation (`MSN-06`).

**MSN-X12.** Given a worker profile on the operator's stored login, which lapses at 02:00 in a window that ends at 06:00, the preflight shows that from 02:00 that route's runs fail at their first model call, and are not retried past their bound (`MSN-02`).

**MSN-X13.** Given a mission that stopped at 06:00 on Saturday, and the operator starting a second mission at 10:00, the consent carries the continuation with the acceptance. One PIN starts the second mission, and its runs start (`MSN-04`).

## Rulings

**MSN-R01. A mission is work of its own kind.** The operator's choice 4 puts its fields into the work-proposal types, as A-40 put an inquiry's. A-40 refused a seventh identity (`WISR-R01`), and `WIS-05.h` already names missions. So a mission is WIS work, completed by its report, as an inquiry is completed by its answer.

**MSN-R02. What a mission covers is content, not a link.** CNI's link vocabulary (STG-17, in review) closes the kinds a link record may carry, and coverage needs none: Coordination reads it from the mission's accepted revision, as it reads a Ticket's accepted scope.

**MSN-R03. The cap is honest about its meter, and V-01's mission row needs the meter.**
- **The recorded premises:** the first selections made the cap an I-6 hard limit, metered at CS-3b's provider relay, as model usage's first metered class (`R-DEC-01`'s first answer). The decision on `R-DEC-04` bounds `RUN`'s spend by that cap.
- **The facts:** `R01-43` forbids a hard-limit claim without a qualified meter. As built at `main` (2026-10-25), the relay (`src/aew/harness/containment/relay.py`) meters nothing, and live usage comes from each run's own harness server, which the run can reach.
- **Revision 1 changed both premises without asking:** it left the meter to the build and let V-01's row pass on `NOT_ESTABLISHED`.
- **The designer's reading (a):** revision 2 restores them. V-01's mission row counts only where the relay meters every paid route a mission's run can reach and R-01 qualifies the class (`MSN-Q10`). `NOT_ESTABLISHED` stays the honest degraded state on any other host. Its cost: the relay's meter and the class's qualification become V-01 build items.
- **The alternative (b):** V-01's mission ships with a cooperative cap, and the window and its drain as its bounds, and the decision on `R-DEC-04` has its spend line revised. It saves the two build items, and leaves `R-DEC-01`'s first answer, which the first selections tied to the cap, unanswered in V-01.
- **The operator's call at adoption:** (a) keeps what was selected, and (b) changes V-01's scope, so each is the operator's to confirm.

**MSN-R04. `RUN` reaches the project, and so does the mission.** Under `R-DEC-04`, `RUN` auto-runs starting and review requests for every ready Ticket of the Lead generation. Narrowing that would change `I6-06.c`'s eligibility. Instead, every admission in the project during the mission is under it (`MSN-01.c`), and coverage defaults to every accepted, not-done Ticket, so the reach and the coverage coincide unless the operator narrows the coverage. Narrowing eligibility stays backlog (`MSN-B1`).

**MSN-R05. The mode lapses at any mission's stop.** This adds a lapse condition to `I6-06.g`, and a lowering-only path to `I6-06.f`. It only lowers: a `RUN` in force when the operator leaves was given for that absence, whether it was raised in the consent or before it. It names no mission in the mode's target, so the mode's wire is unchanged. The one consent's outcome needs I-7's further amendment, which `MSN-04` names. Raising the mode again is the operator's, as before.

**MSN-R06. The window's ceiling is a day, with its drain.** "A window of hours", with multi-day missions not selected, reads as at most 24 hours. That is a selection bound, the designer's reading, and a tripwire the operator may lower in the consent. Raising it is a new selection. A drain outside the ceiling would make the window a bound of any length, so the ceiling covers both. A stored login's lapse is a host fact, and refusing on it would be a design choice and a wall. CS-4's addendum 2 chose to warn at the Lead's launch, and a lapse mid-mission degrades rather than fails: the Lead's judgments wait, or a worker route's runs fail at once and are not retried past their bound. So the preflight warns for each such route, and names the renewing step.

**MSN-R07. The first runs are attended.** The research study found no unattended specimen, and advised one long attended run with a measured stop rule first. The external-workflow study found the steering modes unmeasured, because every run was headless. A mission ends at its first stop, so `MSN-Q01` asks for attended runs that together observe each stop. Their record is the operator's data for deciding when a mission may run unattended.

**MSN-R08. The Lead's end is not a stop.** Ending a mission when the Lead dies would cut admitted work that can finish safely under its own admission. The adopted recovery rules already govern (`HEB-08.g`, `HEB-08.h`), and A-03's `AS-RX10` is the case. The rest of the window then has no judgment, which the preflight says. Bounded retry keeps a recoverable launch failure from stranding the mission (`HEB-08.c`), and a new Lead picks up the mission's record without re-asking (`HEB-08.f`).

**MSN-R09. The posture: a mission costs one consent, no more than raising `RUN`, and nothing for the work inside it.** The preflight needs no answer, the window and coverage come pre-filled, and a `RUN` raise's consent may offer the mission form. The bare raise is not walled. The covered work runs as it would attended, and every admission in the project is under the mission (`MSN-01.c`), so an agent has nothing to gain by working outside it.

**MSN-R10. The stop holds new runs, rather than trusting the lapse.** A mission that grants nothing must still bound what follows its stop. After the lapse to `CRAWL`, the Lead takes `ticket_start` itself (`I6-06.e`, and the decision on `R-DEC-04`), so a lapse alone bounds only the auto-runner. The hold is derived from adopted holds, not a new mechanism. It is a basis member each run admission rechecks (`CNI-03.g`, `AOI-07.f`), cleared only on the operator's deliberate continuation (`CNI-05.e`, `HEB-08.h`). It reads the stop, never the mode (`I6-06.f`). It covers paid admissions too, so on a paid-key Lead the window bounds the Lead's own calls as well. A later mission's consent carries the continuation, so it costs nothing extra there. On return it costs the operator one G3 action, which is the deliberate continuation `HEB-08.h` already asks for.

## Backlog

**MSN-B1.** Auto-run eligibility narrowed to the mission's covered work (`MSN-R04`), if the attended runs show a need.

**MSN-B2.** Multi-day and concurrent missions, not selected.

**MSN-B3.** Stall detection during a mission (the register's U1), outside `R-DEC-03`'s first set.

**MSN-B4.** Stopping or answering a mission while away, through a channel other than the G3 desktop (A-37's), if the attended runs show a need. Until then the preflight says so plainly (`MSN-03`).

## Not covered

- **The wire:** O-01's commands with I-7, and D-01's reads with the shared read wire, matched with the wire track.
- **The meter:** the provider relay's metering and the class's qualification are the build's, under IF-10's and R-01's rules. Under `MSN-R03`'s reading, V-01's mission row needs them (`MSN-Q10`).
- **I-6's build of the lapse:** the built override lapses to the standing mode, not to `CRAWL` (STG-12's as-built trace, 2026-10-25). `MSN-04.a` and `MSN-06.a` wait for it.
- **The bare `RUN` raise:** this position does not bound it (`MSN-04`).
- **Detached-run handling and drain mechanics** beyond the two outcomes the first selections scoped into V-01 (detached-run attention, and the drain deadline as a stop condition): the register's hold group for them.
- **Supervision** beyond `R-DEC-03`'s built set.
- **The as-built state:** no mission is built. `git grep -w mission` finds nothing in `src/aew` at `main` (2026-10-25).
- **A-16's and A-39's bytes:** unchanged. This position adds to them.

## Changes

- Revision 1 (2026-10-25): the first text.
- Revision 2 (2026-10-25): answers round 1 (MSN1, 20 findings) and the designer's two items (`CHANGES-r2.md`).
- Revision 2.1 (2026-10-25): applies the quick check's three minors and four nits, with no further check (MSN2, `CHANGES-r2.1.md`).
  - **The hold** covers paid admissions, the Lead's paid model calls included, and its refusal names the continuation (`MSN-06`).
  - **A later mission's consent** carries the continuation (`MSN-04`).
  - **Every stored login,** a worker's as the Lead's, is shown (`MSN-02`).
  - **`MSN-00` is conditional** on `MSN-R03`'s call.
  - **The set's mechanism** is named as I-7's further amendment.
