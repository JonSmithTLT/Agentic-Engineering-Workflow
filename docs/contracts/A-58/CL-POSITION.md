<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-58
source: 30-stages/STG-33-conversational-lead/adopted/cl-r1/CL-POSITION.md
source-sha256: 034a2d9d68030228f11da27ff442515c3cf4f13de012202d203a7389984780d7
edits-sha256: fee37ec9c1635deb4a534e4d08cafb3cad48c460ecbcb870d7ed0a72a6ebdf95
-->

# The conversational Lead: how a Lead waits (PROPOSED, revision 1)

**Namespace:** `CL-`
**Status:** proposed. It gives the operator's rule an adopted home. No line of D1 changes. Adopting it does move adopted and approved text beyond D1, and "What adoption moves" lists all of it. The operator adopted it on 2026-11-09 with that table in front of them.
**Authority:** the rule, in the words the Lead put to the operator (the Lead's record of decisions, under 2026-11-09): "a Lead rests idle and AEW wakes it. Every new signal is a wake reason, in one list. `harness_wait` returns those same reasons, and is only for waits of seconds or where wakes can't reach. It gets no features of its own." The operator's words, verbatim, from the Lead's transcript: "ah i see what youre saying youre saying that absically we have teh ability with steering and wake to wake a lead for a set of reasons. which is basically teh same thing we were palnning to do with harness wait so its teh same core ideas jjust a different delivery mechanism?", then "yup i agree with that send the ahrnass wait context tot eh designer." On 2026-11-06, relayed by the Lead, of the steering brief's revision 3: "this may be the one largest ux improvement weve had in months. mostly because it actually returns the strongest benefit of an llms. the conversational aspect. the ability to dive into problems or receive corrections thats a massive downside we were just accepting". The adoption, 2026-11-09, answering "Adopt the conversational Lead position?": "Adopt it".
**The designer's:** everything beyond those four sentences. `CL-01`, `CL-02` and `CL-04` state the rule, and a rule's text says where it goes further. The steering brief's design is the source of `CL-03`, `CL-05` and `CL-06`. The operator's adoption made these theirs.
**Threat model:** the operator's decisions of 2026-10-19 (no malicious code as the operator) and 2026-10-24 (agent-reachable findings only).
**Research consulted:** `tools/research_index.py lookup` on `R01-26`, `MSN-07`, `BOY-09`, `HEB-06.a` and `AIR-61`: none. The agent-effectiveness synthesis reports that a Lead "spends 61% of its wall time blocked in" the wait, on 68 dogfood records from a 12-file fixture, and A-44 cites it. That's a share of wall time, not of tokens, and being deaf to the operator wasn't measured. Nothing measures a Lead at rest: this rests on the operator's use.
**Files:** this file. The design it holds is the steering brief at the designer's commit `8a48dc6`, revision 4, its §1 to §5, §8 and its ruling of 2026-11-08, which stays a design under this position and binds only through it. That commit pin is how it's held, since the rules here carry what a builder must obey. The register PR's text is the designer's, given to the Lead.

## What the adopted text already decides

- Waiting runs in host code, and no model polls or spends idle tokens (`MSN-07`, `R-DEC-03`).
- The Lead keeps working while a run is active, and their lifecycles stay separate (`HEB-06.a`, `HEB-06.c`, `HEB-07.a`).
- Progress can be rebuilt without a running conversation (`CNI-03.f`).
- A notice grants nothing (`ADC-01.d`, `R01-34`). A lost notice can't strand work for good, and a stale one can't clear a newer one (`R01-26`, written for workers' waits and not selected by `R-DEC-03`; this position takes it as its pattern for the Lead's).
- The operator kept `harness_wait` "with a requirement in A-06" (`2026-10-25-operator-S12-4-flags-batch-1.md`, its fifth flag), and no such requirement exists. Adoption records `CL-04` as an A-06 requirement under flag 5, in the shape A-44's adoption gave `BOY-08`, and A-06's next revision writes it. The flag stays open until then, with `explain` and `cli` still owed.
- A-44's "your turn" sources stand (`BOY-09`). `SMP-07` already names the Lead's wake.

### What adoption moves

Q9 and Q10 were never asked, so no answer of the operator's is reversed. The wait stays and still returns each reason, so most of these lines are extended by a second delivery. One is replaced: the idle loop, in a design the operator adopted, by the operator's own rule.

| The text | Its standing | What moves | Where |
|---|---|---|---|
| Q9, and `BOY-R08`'s rejection of it | A-44, adopted | The rejection is overtaken for AEW's own launch, and Q9 closes | `CL-R02` |
| S7's row, S8's row, its Risks line, and Q10 | A-44, adopted | S7 narrows to two questions; S8 splits; Q10 stays open with the row that keeps it | `CL-R04` |
| The consult's committer, its same-turn use, its "failed", its wake's delivery | Consult v2, adopted | Corrected: its committer could not commit | `CL-R03` |
| §7's wake line and §8's reactions; §6 of its implementation note | Run health design, approved 2026-10-05 | "Harness wait wakes" becomes a reason on the list | `CL-R01` |
| §11.1's lane, §18's candidate, the W6 row | Cross-feature design v0.5, frozen | "Its lane in `wait --any`" becomes a list row | `CL-R01` |
| D5's lane and the attention spine's lane | Decision records of 2026-10-10 and 2026-10-11 | "A lane in `wait --any`" becomes the list | `CL-R01` |
| The Lead's idle loop, §15 | The Lead-worker messaging amendment, adopted by the operator and the designer, 2026-10-09 | "Wait-any" gives way to resting | `CL-R01` |
| The reset's line on the wait, at its :89 | An operator decision record, under the designer's readings | A pointer line | `CL-R01` |

**The selection:** adoption selects the wake and its reasons into `R-DEC-03`'s built set, notify-only and in host code, with a pointer line on that record, as `BOY-09` has. It doesn't select stall detection (`CL-R05`).

## The parts

| Part | What it is | Who writes it | Who reads it |
|---|---|---|---|
| The list | The closed list of wake reasons, each with what it means, what to do and what to tell the operator (Candidate: `WAKE_GUIDE`) | AEW's code, one owner | Both deliveries, the Lead's text |
| A wake | One delivery: AEW posts into the Lead's session, which starts a turn if it's idle | The Lead broker | The Lead |
| The wait | The other delivery: `harness_wait` returns while the Lead's turn stays open | The engine | The Lead |
| The digest | What a live run has been doing, the facts both deliveries read | The run's meter, host side | Both deliveries |
| The next step | Which delivery applies now, told after a dispatch and a return | The engine, one owner | The Lead |

## Rules

**CL-01. A Lead rests idle, and AEW wakes it.** After starting work, the Lead says in one line what it started and what it's waiting on, then ends its turn.
- Between wakes an idle Lead spends nothing, and the operator can talk to it at any time, as in any conversation.
- Each wake is a turn at full context, including `quiet` for each live run. `lead.quiet_wake_s` defaults to 1200 s, within 600 to 3600, from the Lead's report of 2026-11-06. It's a tripwire and operational, and the acceptance runs measure it.
- Between wakes it may do other work.
- This holds on every route where a wake can reach it (`CL-04`).

**CL-01.a** No reason exists for the operator's own message. An idle Lead hears the operator natively, and a Lead mid-turn hears them when its turn ends.

**CL-02. Every new signal is a wake reason, in one closed list with one owner.** The designer reads this to take in the signals wakes carry today and the steering loop's stops (`CL-R07`), as well as new ones. A design that has a new signal for the Lead adds a row to the list.
- It adds no second lane, no second notifier and no separate polling (`MIC-10`, `AIR-61`). The list is `AIR-61`'s one primitive: a reason reads its facts from the digest, or, with no run, from the action projection or the outbox fact that line names.
- Each row states what the reason means, what the Lead does about it, and what it tells the operator.
- The reason names the signal. The Lead's text is derived from the list, never restated.

**CL-02.a** A reason the list holds is never dropped silently. A reason with no rule for whether it still holds fails a test, rather than being dropped at runtime by either delivery.

**CL-03. The two deliveries carry the same reasons and the same engine-set facts.** A wake and a wait's return differ in how they arrive and in what `CL-03.a` declares.
- One test sends every reason on the list through both deliveries.
- For an ended run, the facts both carry include its evidence, its results and its reason, so acting on one costs the same as acting on the other.
- Worker text in either is framed data, never a fact the engine set (`CL-05`).
- What a wake quotes passes the same scrub as a wait's result, before it leaves the host.

**CL-03.a** The declared differences. `quiet`, the backstop, is the wake's alone, because a wait's timeout carries every run's digest and does its job there; that's the designer's narrowing of "those same reasons". `timed_out` is the wait's alone, and isn't a reason. A later difference is added here with its reason, or it's a defect.

**CL-03.b** What one delivery pushes unasked, the other doesn't push again. A wait the Lead explicitly makes on a run a wake already reported still returns its end: the Lead asked, and it would otherwise block for nothing.

**CL-04. `harness_wait` is for waits of seconds, and for where wakes can't reach.** It gets no features of its own: anything proposed for the wait goes on the list instead. It blocks in the broker without holding it, and no model polls.
- **Waits of seconds:** a wait the Lead chooses because it expects the run to end within seconds.
- **Where wakes can't reach:** Windows until a real wake has been measured there, Codex until its route exists, the policy's `off`, a policy edit not yet adopted, and a live broker with nothing posting, such as a Lead started with the bare `aew lead session` command, which `aew opencode` is not.
- It stays while any such route exists. This position doesn't retire it.

**CL-04.a** The next step says which applies, from one owner, and it's right at the time it's told. "Don't end your turn while a run works" reaches only a Lead on a route with no wake.

**CL-04.b** A Lead on a route with no wake tells the operator so in its one line, because the conversational Lead is what they'd expect. The exception is an operator who set `off`, who already knows.

**CL-04.c** The designer's rule. On a route where wakes post, a wait returns within `lead.wake_route_wait_s`, in the typed tool and in the relayed `aew harness wait` alike, default 60 s, operational, chosen from "waits of seconds" and not measured, a tripwire. Its next step says to end the turn. Telling a Lead not to wait long wouldn't survive compaction, and a long wait is the deafness this rule ends. Each wait capped this way is counted, so the number can be checked.

**CL-04.d** The switch is `lead.push_wake`, default `on`, operational. The default reaches existing projects at upgrade with no migration, since `aew init` writes no `lead:` key, and a typed `off` stays off. This is the requirement that key has traced to no adopted text for.

**CL-04.e** A broker that isn't running is a different case. A contained Lead's typed tools stop with it, so no next step can reach that Lead. `status`, from the operator's shell, says so, and a restarted `aew opencode` posts the wake it held once the operator's first prompt opens a session (`CL-X03`).

**CL-05. A wake grants nothing, and isn't the operator speaking.** It's headed as AEW's, it carries no authority (`ADC-01.d`), and what it quotes is data.
- The header marks and never proves, and no text in the session carries authority (the ruling of 2026-11-08).
- Nothing in a wake is the operator's word, so nothing in one is recorded as what they said. This is the designer's rule, `E176` consumes it, and `E176`'s tests are its gate for its `said` and `typed` lines.

**CL-06. A wake describes the present, and a burst costs one turn.** It's checked when it's gathered and again immediately before it's posted, and a wake whose condition has cleared is dropped or folded into a newer one.
- At most one wake is undelivered. Triggers merge into it while it's pending, what arrives after its post waits in the digests, and a run-less fact takes the next wake and keeps its key.
- A wake is durable before it's posted, and is told once. "Delivered" means its turn took it in, not that it was acted on, and `status` says so.
- It isn't posted into a running turn. A turn that starts between the check and the post takes it queued, at that turn's end.
- A worker can't make the Lead spend without a bound. Each worker-driven trigger, an out-of-scope path included, passes the anti-spin rule (the brief's §1): at most one wake per run per reason per 30 s. `run_ended` is bounded at once per run, and `quiet` by its own clock. Each run's wakes are counted against the budget `CL-Q15` sets, which is checked at acceptance.

**CL-06.a** The designer's rule. A wake goes to the session the operator last viewed. A wake posted between `/new` and the first prompt goes to the old session. It costs a turn, the status line says where it went, and the new session rebuilds with `resume` (the designer's check of 2026-11-08, §8). An older session the operator opens to read takes wakes the same way, and that's accepted too: it's the same launch and the same Lead, and the status line says where. It's a row if it bites.

**CL-06.b** A wake's turn runs on the model the session would use, and this is unmeasured. `E212` measures whether a wake posted early inherits the wrong model, and AEW names the Lead's model after it (the operator: "yes name the lead's model after e212"). The designer accepts this as a risk for the default-on switch, because a wrong model there is a cost, visible at the turn, and grants nothing.

**CL-07. A new design names the act that commits, and the state its work sits in until that act comes.** This is the designer's rule. A wake tells, and an explicit act commits.
- Until the act comes, the work stays visible in `resume` and `status` as a next action, and nothing is lost.
- Placements already adopted stand, such as the usage record's at the Lead's next transaction (`CUL-11`) and `BOY-09.b`'s.
- The consult's case is in `CL-R03`.

**CL-08. The operator can see what the Lead is waiting on, on every route.** `status` shows the live runs from control state, and whether a broker is running. Where wakes post, it adds the last wake posted and delivered, and where it went. Where they don't, it says no wakes post on this route and that the Lead waits with `harness_wait`. `CL-R04` takes this to the site.

**CL-09. Every harness either supports the wake, or has a declared gap with a register row.** The operator's rule on harness features applies: "supported on both", or a gap noted as work for AEW's build of Codex (`harness_capabilities`). A gap falls back to `CL-04`, and is never silent. `CL-03`'s scrub and `CL-06.a`'s target are stated for each harness.

## The gate

| Check | What it shows | Pass |
|---|---|---|
| **CL-Q01** | One list, both deliveries (`CL-02`, `CL-03`) | a test parametrised over the list: every reason has a fixture, is posted as a wake and is returned by a wait, apart from `CL-03.a`'s exception and a reason its row marks as not yet produced |
| **CL-Q02** | Nothing dropped (`CL-02.a`) | with the same exemption, a listed reason with no rule for whether it still holds fails the test, the rules read spanning every place a reason's currency is decided, or moved to one owner; ablation: drop one rule |
| **CL-Q03** | The Lead's text is derived (`CL-02`) | with the same exemption, every reason appears in the Lead's text from the list; no wake guidance is hand-written beside it |
| **CL-Q04** | Same facts (`CL-03`) | a run ended under a wake and under a wait gives the same engine-set fields, `ended_by` included or stated in `CL-03.a` |
| **CL-Q05** | Told once (`CL-03.b`) | a run waited on and returned in a turn doesn't wake at that turn's end; a wake gathered during a wait isn't posted after the wait has returned it; an explicit wait on a run a wake reported still returns its end |
| **CL-Q06** | The next step is right (`CL-04.a`) | each route in `CL-04` gets the right next step and its stated reason, and "don't end your turn" reaches only the no-wake routes; includes `aew lead session` after a crashed `aew opencode` on the same generation |
| **CL-Q07** | The operator hears the gap (`CL-04.b`) | the no-wake next step tells the Lead to say so, except where the operator set `off` |
| **CL-Q08** | It rests (`CL-01`) | on the brief's §8 acceptance run: a Lead dispatches, ends its turn, answers the operator while idle, and is woken by the run's end. A fake model and synthetic values, the provider route closed by `E213`'s helper. A real model is the operator's, per event |
| **CL-Q09** | No authority (`CL-05`) | a wake claiming approval, a post with no header and a post quoting the header change no gate's answer |
| **CL-Q10** | Windows (`CL-04`) | the launch changed there with PR 2, so its acceptance tests are green on Windows for the fake harness. One wake run there, on a fake model with no credential and its own approval, or Windows stays on the wait as a declared gap (`E210`) |
| **CL-Q11** | The scrub (`CL-03`) | a synthetic credential in AEW's own form, planted in a digest, reads as redacted in both deliveries; ablation: remove the wake's scrub. Provider shapes are their own row, for results and wakes alike |
| **CL-Q12** | The present (`CL-06`) | one ablation each for the re-check, the single undelivered wake, durable before the post, never into a running turn, and the anti-spin on an out-of-scope path, through the adapter interface |
| **CL-Q13** | What the operator sees (`CL-08`) | `status` on a wake route, on a no-wake route and with a dead broker says what `CL-08` and `CL-X03` say |
| **CL-Q14** | Both harnesses (`CL-09`) | the capability-declaration test names the wake for each adapter, or a gap with its row |
| **CL-Q15** | Wakes are measured (`CL-06`) | a wake log keeps each wake's `why`, run and tokens, and survives the record's overwrite. The first VM runs set the per-run budget, the operator approves it, and then an acceptance run over it fails |
| **CL-Q16** | The cap (`CL-04.c`) | on a wake route a longer wait, by the typed tool and by the relayed command, returns at the cap with the end-your-turn step, and is counted; a no-wake route is unaffected |

A brief that names no act fails its design review, since `CL-07` has no test of its own.

## Scenarios

**CL-X01.** Given a Lead that has dispatched and ended its turn, when the operator asks it something, it answers at once, and the run's end wakes it later.

**CL-X02.** Given a Lead on Windows, the next step tells it to wait, its line tells the operator no wake is coming, and the wait returns the same reasons.

**CL-X03.** Given a broker that stops while the Lead rests, `status` says so and shows the wake it held, and a restarted `aew opencode` delivers it once the operator's first prompt opens a session.

**CL-X04.** Given a new signal proposed for the wait, the design adds a list row, and both deliveries carry it.

**CL-X05.** Given a loop stop that needs the Lead's judgment and a resting Lead, the Lead is woken. If it still makes no call for T, `BOY-09`'s item raises it to the operator. A Lead that reads and stops clears the item (`CL-B1`).

## Rulings

**CL-R01.** The lines that name the wait as the route for a signal keep their requirement, and the mechanism becomes a wake reason. These documents govern: the ledger only tracks them. So this is one named amendment, put to the operator at adoption, in the shape `cost-usage-ledger-design` §11 took: a decision record in `docs/design` with its own ledger ids (`CLA-01`, the Lead rests; `CLA-02`, one list and two deliveries), a README "as amended by" on the documents it touches, a pointer line in each, and a status on each line below. The Lead carries them in the register PR, whose text is written out and owns each status's wording.

| The requirement | The lines | What it becomes |
|---|---|---|
| The Lead's idle loop | `LWM-16` | Resting replaces "wait-any", and the wait stays for waits of seconds and where wakes can't reach (`CLA-01`). The rest of the loop stands |
| The Lead's wake for worker replies | `MIC-09`; `LWA-17`, whose status names that lane; register `F9`'s note | `worker_message`, already in the list, by both deliveries (`CLA-02`). F9 still owns it |
| A run that stops making progress | `RHP-07`, `RHN-07`, the run health design's §7 line and its table's STALLED row, the implementation note's §6, register `U1`'s Work | `stalled`, a reason by both deliveries, when it's built (`CL-R05`, `CLA-02`). The edge trigger, the confidence rule and "never terminates" stand |
| A worker's blocked permission | `RHP-08`'s and the table's "blocked permission" | No row today. On the OpenCode worker path every rule is allow or deny, and a request is rejected and the turn ends, so it reaches the Lead as `run_ended` (read, not run). A harness that can hold a worker on a permission takes a row |
| Cross-feature and integration wakes | `CFI-51`, `CFI-105`; §11.1 and §18 of the cross-feature design and its W6 row | Each is a list row if and when it's built (`CLA-02`). `CFI-51`'s "whether or not the F9 messaging switch is enabled" stands |
| The same, in an unadopted amendment | `IDA-19`, in `wc8-e19b-interface-dependency-amendment-v0.1.md`, "Proposed" and not governing | A list row if and when it's built, and a pointer line for when it's adopted |
| Run-less facts the Lead must act on | `AIR-19`; register `F43` | A reason with no run (`CLA-02`). Its "never separate F9 and D5 mechanisms" stands, as the one list |
| The reset's line on the wait | `2026-11-06-operator-reset-finish-and-switch-on.md:89`, under the designer's readings | A pointer line on that record, naming this position |

**Why `MIC-10` stands, which the operator should see.** Its "no second notifier" could be read to bar the broker's wake thread. Its reason is that E7's notifier stays the operator's and no model polls, and both hold: the wake thread is the Lead's one route, the list is its one owner, and it never touches E7's notifier. The amendment says so in words.

**Left alone, by one rule:** a line is listed only if it names the wait as the Lead's route for a signal. So of the 23 ledger ids naming the wait, the other 14 stay as compatible: `OBX-14`, `OBX-18`, `OBX-38`, `OBX-42`, `TLS-07`, `TLS-25`, `TLS-26`, `TLS-28`, `LWE-02`, `IQR-03`, `CUL-11`, `CUL-23`, `EVR-01`, `AES-09`. `CFI-49`, `CFI-50`, `CFI-84`, `CFI-85`, `CFI-93`, `RHN-10` name wakes and stand: a merged wake keeps its `(dependent, subject)` keys. `CMG-19` stands too, since `CL-03` carries the same facts by a wake. `AIR-61` stands as `CL-02` reads it. Closed rows, ADRs and reports stay as history. Open rows that name a wake without the wait (`E158`, `E174`, `E201`, `E203`, `E206`, `F41.7`) are candidate reasons, and join the list when each is built.

**CL-R02.** `BOY-R08`'s rejection of "AEW owning the Lead's OpenCode server now (Q9)" is overtaken for AEW's own launch, and Q9 closes at this adoption. It was rejected as a route to a fallback signal, when push wake didn't exist. The designer's ruling of 2026-11-08 and the designer's check, §9, placed the server under AEW's launch, the ADR-0009 amendment on #393's branch is the act, and `SMP-09` reads it. The operator's "yes fetch it when pr 2's turn comes" answered the Windows question, not this one. This takes effect when #393 merges. The rest of `BOY-R08` stands: the fallback's signals stay in host code and capped at attention, because their job is raising an item to the operator, which owning the server doesn't change. A-44's frozen bytes don't change: a pointer line records this.

**CL-R03.** The consult needs no reason of its own, and its committer is corrected. The error is the designer's: consult v2 names `status` and `harness_wait` as committers, and they could not commit, because both are declared never to (`surface/contract.py:28-29`).
- **The wake:** a consult is a run, so on PR 3's code `run_ended` already reaches an idle Lead with no consult code. Adding a reason would be a second name for the same fact, against `CL-02`.
- **The committer (`CL-07`):** the Lead's explicit read, `consult_show`. It always returns the body, framed. It does the ingest, which frees the slot, and it completes the consult in the same call only where the guard allows, meaning a passing, fresh record with no gate pending. Otherwise the consult stays ingested and not done, the reply gives the reason, and the Lead uses the acts that exist. A refused ingest still returns the body with the refusal.
- **Before the read:** the consult sits ended and not ingested, its record sealed. Nothing is lost, `resume` names it, and it holds its slot where a cap is set. It keeps its observation until read or cancelled, cancelling is the way to drop one unread, and a cap refusal names the unread consults holding the slots. The broker isn't made to commit: its wake thread holds no credential, on purpose.
- **A run with no record:** the existing relaunch-or-cancel next action, and `consult_show` says there is no record. Consult v2's "completes as failed" goes, since no such state exists.
- **The door:** `consult_show` is a mutating Lead tool, and not `relayed`, because its commit is a lifecycle operation. The tool budget's decision (`TLS-21`) comes before E158 is placed.
- **What the wake carries:** `CL-03`'s facts, and not `last_message`, in either delivery, so a consult's answer arrives one way and the read can't be skipped by accident. `run_ended`'s guidance gains the consult's action from the engine-set record kind, not by widening the row.
- **What else it inherits:** the list, except `test_failed`: a failing test is likely what the consult was asked about, and its answer says so.
- **A requested review:** the read completes only with no gate pending. E158's brief and E159's record settle how a review requested after the read binds to the record, since consult v2 refuses `consumes`.
- **How the Lead uses it:** it says what it asked and ends its turn, and answers in the wake's turn. On a route with no wake, it waits, in slices. This replaces consult v2's implied same-turn use. Counting by hand, that's three requests either way for a consult under ten minutes, with more on the wait's path for a longer one. Unmeasured.
- **Owed in E158's brief:** consult v2's lines 56, 57, 60, 63, 134 and 135; the committer moving to PR 1, and E158's split of two PRs; the hold match's row spec; `CL-B2`'s fields, which this depends on; and how the loop treats the read's commit (`BOY-08.a` classes such commits).

**CL-R04.** A-44's slice S8, "the Lead's harness waits shown as items", splits in two.
- **What the Lead is waiting on, shown on the site.** On wake routes a long wait is no longer the normal state, and the record it needs exists on PR 3's branch. On no-wake routes it reads the live runs from control state, `BOY-09.a`'s beat for a wait in flight, and says no wakes post. So this part needs neither S7, Q9 nor Q10. E110 carries this wording, and its placement stays the operator's.
- **The contract step it owes:** a block with no items in S2's `/waiting`, beside the notifier's state with its own read time, so C0 still renews once; if S2 ships first, a second renewal. The contract file and C0 are the web developer's (`BOY-R10`), and the projection is the dashboard backend's. The A-12 requirement it needs, and how `D01-EXT-04`'s fields and an outage read treat a `.aew/local` record, are settled before E110 is placed.
- **The pending dialog keeps a row of its own.** A TUI permission ask or form, named as an item. Its floor is `BOY-09.a`'s idle source, "your turn", and that needs no run active (`CL-B1`). AEW now owns the server, which may make this cheap: `session.active` during a dialog is on PR 2's measure list, and whether forms persist isn't known. E109 narrows to those two, its data is recorded against this row, and Q10 stays open with it. It returns to the operator with that data.
- **Chat-only questions** stay with `BOY-09`, whose coverage line says AEW can't tell one from a finished turn.

**CL-R05.** `stalled` stays in the rule and isn't scheduled. U1 is unplaced and its system stays designed only (the operator: "tbh i see mroe valuen in run that and teh scehduler than stall detction right now"). The pull-forward trigger stands: a real run repeating the 20-minute hang, or the scheduler holding a slot on a stuck worker. When U1 is placed, `stalled` is a reason on the list, under the statuses in `CL-R01`. The designer's notes hold what its brief must settle.

**What the code reading changes now (read, not run):**
- At `adapter.py:1009-1033` a turn's end ends the run, and the supervisor kills the process tree, unless the Lead interrupted it (`held`). So a worker that starts a background process and ends its turn doesn't leave it running, and wakes the Lead as `run_ended`.
- `worker_idle` then fires, on the normal path, only in `held`. It stays as the alarm for the edges where the adapter hasn't closed a turn: poll errors with the server alive, a prompt answering 404, a newest message that isn't an idle after the delivered prompt, and a prompt still in the inbox.
- A worker that stops with a question ends its run, and `send` then refuses. So what the Lead told the operator is corrected: "a worker idle beside a stuck process is caught" and "`worker_idle` wakes the Lead when a worker's turn ends without its run ending" hold, on the normal path, only in `held`. The ranking's reason stands either way.
- **Texts that change, when measured:** the `worker_idle` row, the wait rule, the tool's description, the meter's docstring, and `run_ended`'s row, which points at `last_message` for a question until M2's `worker_message` arrives.
- **The measurement, owed by M2 or E206, whichever comes first:** a fake model in a loopback-only namespace, no real provider. Does the session go idle with a background shell running, does the run's end kill it, does a shell's timeout kill its children, can `held` keep one alive, and can a newest message not read `idle`? If the reading is wrong, the designer rules again.

**CL-R06.** The word "wake" also names the outbox's in-process wake file (`OBX-12`, `OBX-13`). That's a different thing, and `CL-` means only the Lead's wake. The spool's `loop_stopped` event is also a different thing, which is why `CL-R07`'s reason has another name.

**CL-R07.** A loop stop that needs the Lead's judgment is a reason, and the scheduler's chain owns it.
- **Why:** `DECISION_REQUIRED`, `BLOCKED` and `UNKNOWN` are recorded but not notified, because the Lead's next call would see them. Under `CL-01` there may be no next call. Attention stops also wait on the Lead and notify only the operator, so they take the row too.
- **The row:** `loop_waiting`, with no run, marked not yet produced until the chain's first PR builds it, before RUN is on by default. That brief names the wake's run-less slot, the row's rule for whether it still holds, and its told-once key.
- **Beside `BOY-09`, which stands:** the wake normally lands first, and the item goes to the operator if the Lead still makes no call for T. Each runs on its own clock, either order is harmless, and they have different audiences, so neither replaces the other.
- **A run the loop handles:** `run_ended` for a run the loop will ingest or has ingested isn't current (`CL-06`), so it doesn't wake. `test_failed` and `out_of_scope` still do, since the loop doesn't steer. The scheduler's brief pins how.

## Backlog

**CL-B1.** Four states where a resting Lead raises nothing unprompted, for whichever slice next touches attention:
- A dead broker: `BOY-09.a`'s idle source needs a live broker as well as no run active, and observations end with the broker.
- A live run: R1 ends, the woken Lead asks a chat-only question and ends its turn while R2 works, and the idle source stays silent until R2's wake. Resting makes this the normal shape.
- `lead.push_wake` turned to `off` during rest: the Lead was told to end its turn, and no wake comes.
- A read clears `BOY-09`'s item: a Lead woken for a loop stop that reads and stops isn't raised, and nothing re-arms it. Whether only a commit should clear the item goes to the slice that builds `BOY-09`, as a pointer, since `BOY-09.b` is adopted.

**CL-B2.** Where PR 3's branch differs from this position, for a small follow-on right after PR 3. The designer's call is that these don't hold PR 3's merge: each costs a turn or a line of text, and the gates pass by the end of that follow-on, before steering's next slice.
- The wake's missing engine-set fields and `ended_by` (`CL-Q04`): about one extra request per run's end.
- The double report (`CL-Q05`): about one extra turn on the wait path.
- The hand-written wake text (`CL-Q03`), a reason with no rule (`CL-Q02`), and next-step text for each route (`CL-Q06`, `CL-Q07`, `CL-X02`).
- `status` on no-wake routes and its wording for "delivered" (`CL-Q13`), the anti-spin for out-of-scope paths (`CL-Q12`), the wake log (`CL-Q15`), the wait's cap (`CL-Q16`), whose timed-out step must not say "what you started".
- The wake re-tells a reverted path that the wait doesn't return: the wait takes the same rule, or `CL-03.a` declares it.
- A wake re-posted when the operator changes session: the delivery check looks only at the session viewed now.
- A session with no poster clears the serving mark at start (`CL-Q06`).
- **One does hold PR 3:** `CL-Q11`'s scrub, since a switch-on sends what a wake quotes to the Lead's provider.

**CL-B3.** The steering brief's preamble and §1 to §4 have small drifts from the code. A later revision of the brief takes them. The position governs where they differ.

**CL-B4.** A wake whose turn fails counts as delivered and told. If the Lead's provider errors on that turn with the operator away, the run is watched no more, and `quiet` doesn't fire if it was the last live run. The direction: such a wake is told again once, then raises attention. `BOY-09`'s no-call source catches it when built. A row, in the follow-on if it fits.

## Not covered

- F8's intake, which has no live runs, and whose ruling stands.
- Retiring `harness_wait`.
- Whether resting is cheaper in practice: nothing measures a Lead's idle cost against a wait's. The expected saving is from the design, not a run. `CL-Q15` starts the measuring.
- U7's automatic recovery, and U1's first slice (`CL-R05`).

## Changes

- Revision 1: the first text, on the operator's rule of 2026-11-09, answering its independent review. Adopted 2026-11-09.
