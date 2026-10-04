# What M3's tests taught us

**For:** the operator and the designer, before the operator's acceptance session in OpenCode's TUI and the independent review.  
**Covers:** every empirical test of M3: live conformance with free models (step 8), the paid dogfood (step 9) and its model comparison, and the dogfood's amendments A3 to A7 (the Class 0 path, the Lead's guide, the Leads' own debriefs); also what the audits found in that data. Nothing here is new data: every number comes from the document cited beside it.  
**Spend:** USD 6.80 of the operator's USD 10 on paid models (OpenAI's GPT-5.6 Luna and GPT-6 Sol). Step 8 used free models.

## 1. The answers in brief

1. **Quality: not shown either way on these tasks.** Plain OpenCode passed 20 of 20 runs; AEW passed 24 of 26 on the hardened code, and 12 of 12 with Sol. Both models solve these small tasks unaided, so the tasks could not show AEW improving a result (§3.2).
2. **AEW made one result worse.** In T4 the Lead turned the operator's wrong hypothesis into a goal that could be met by editing its own inputs, and every gate passed the wrong change. The gates judge what the Lead wrote, not whether it is right (§3.2).
3. **The price is about 7×** the cost and time of plain OpenCode on small tasks. The Lead is about 40% of it, and that is workflow choreography (about 20 workflow commands a session), not waiting (§3.3).
4. **What AEW demonstrably adds:**
   - durability: a Lead whose harness was destroyed rebuilt its context from AEW alone and finished, 3 of 3;
   - independent review: every first review of a seeded defect caught it, 19 of 19;
   - custody: no AEW credential and no provider key in any file, in any run;
   - gates that hold when a model is wrong (§3.1).
5. **A model Lead can run AEW once it is told how AEW works.**
   - Without the guide, it learns by refusal: 20 refused commands and 16 `--help` lookups in 6 runs.
   - With the guide: 1 and 6 in 12 runs.
   - Outcomes were the same in both. The difference is steps, about a quarter more on multi-step tasks without the guide (§3.4).
6. **The model Leads exposed design gaps more than bugs:**
   - A Ticket's scope cannot change once the Ticket exists, which twice cost a whole Ticket.
   - The next actions ignored what evidence said.
   - The contract's own class definitions put every Ticket in Class 1.
   - There is no command to read a piece of evidence.

   The first two are now fixed or designed; the last two are open (§3.5, §3.6).

## 2. What ran

| Evidence | Date | Runs | Models | USD | Question | Source |
|---|---|---|---|---|---|---|
| Live conformance (step 8) | 09-28 | 7 lifecycle and 9 rework trials | free OpenCode models | 0 | Does the adapter keep AEW's guarantees with real models in every role? | `harness-conformance.md` §6 |
| The dogfood (step 9) | 09-28, 29 | 47: 27 AEW, 20 plain OpenCode | Luna, Sol | 5.75 | Does AEW make real work better, not just more elaborate? | `m3-dogfood-report.md` §1 to §5 |
| Model comparison | 09-29 | 6 trials | Luna and Sol, crossed between roles | 0.33 | Where does a stronger model pay off? | report §5 |
| A3: the Class 0 path | 09-30 | 2 (plus 1 at USD 0) | Luna | 0.03 | Does Class 0 work end to end? | report §6.4 |
| A4: the guide, on demand and embedded | 09-30 | 12 | Luna | 0.43 | Does the Lead act differently with the guide? | report §6.5 |
| A5: no guide at all | 09-30 | 6 | Luna | 0.18 | The same, with a true "before" arm | report §6.5 |
| A6: the Leads' debriefs | 09-30 | 18 answers | Luna | 0.08 | What do the Leads themselves say? | `eval/m3/dogfood/debriefs.jsonl` |

Every run and trial is recorded, including failures, in `eval/m3/dogfood/results.jsonl`, `comparison.jsonl`, `debriefs.jsonl` and `eval/m3/live/`. Each paid batch was pre-registered in `eval/m3/dogfood/rubric.md` before it ran.

## 3. What we learned

### 3.1 AEW's guarantees held under real models

- **Custody.** No AEW credential and no provider key in any file the runs left, databases included: all 68 dogfood runs, the model comparison, every step-8 run and all 18 debriefs.
- **Only the Lead's recorded steps move state.**
  - A run ending moved nothing.
  - Gates counted only evidence for the exact snapshot and plan being accepted.
  - A rejected attempt's evidence never satisfied a gate.
  - The rejected implementer's credential was dead (step 8's rework trials assert all of this).
- **The gates held when a model was wrong.** A change outside its Ticket's scope was refused (§3.6). The seeded defect was rejected at review every time. Mistakes by models in roles were caught by engine checks, not by harness permissions, and each refusal was enough for the model to correct itself in one step (`harness-conformance.md` §6).
- **The limit: containment is workdir separation only.** In step 8 a verifier model wrote its report into the operator's real AEW checkout (M3-D6). Until real containment exists (F2), AEW is used on scratch repositories only.

### 3.2 Where AEW's value showed, and where it could not

- **Shown:**
  - resuming after the Lead's harness was destroyed (T6, 3 of 3);
  - independent review: 9 of 9 in step 8, 4 of 4 in T5, 6 of 6 in the model comparison. With Sol, a reviewer also caught a subtler precision defect in the rework that no hidden test measures;
  - investigation Tickets before fix Tickets (T3, 4 of 4);
  - a verifier catching a goal corrupted by shell interpolation (T1, run 1).
- **Not shown: better results.** Plain OpenCode passed 20 of 20. The tasks were a 200-line project with single-concern changes, and both models solve them alone. A quality benefit needs tasks where a single session fails or regresses (Q7 in `future-work.md`).
- **Worse once: T4.** The Luna Lead took the operator's wrong hypothesis as its plan, let the sample data into the Ticket's scope, and wrote a goal about that data. The implementer edited the data to meet the goal, and review and two verifications passed it. With Sol as Lead, AEW investigated or planned the real fix both times. The gates cannot compensate for a goal that can be met by changing its inputs. That is what plan assurance (F14) is designed for: acceptance integrity and protected acceptance conditions (report §6.2; O3).

### 3.3 The price, and where it goes

- **About 7×** the cost and time of plain OpenCode: 6.5× with Luna, 7.5× with Sol.
- **The Lead is about 40% of it.** The audit's recount (L1) found waiting is only 12% of the Lead's steps. The rest is choreography: about 20 workflow commands a session, each a model step that re-reads a growing context. Stage commands (F15) target that.
- **The guide cut Lead steps** on the multi-step tasks by about a quarter (§3.4).
- **Risk class is the biggest lever on a small task.** At Class 0, T1 cost half as much as at Class 1: two role runs instead of four (A3, A5).
- **Where a stronger model pays** (a hypothesis, not a result): the Lead and the reviewer. Sol's Lead avoided T4's trap, and Sol's reviewers caught the rework's precision defect (report §5).

### 3.4 How a model Lead learns AEW

- **Without the guide, by refusal, with the same errors every time.**
  - `aew evidence ingest` on an implementation report: all 6 no-guide runs.
  - An option on the wrong command (`verify ingest --scope integration`).
  - A dispatch before the plan was accepted.
  - An ingest before RUNNING.

  Each refusal named the command that applies (audit X1), so every run recovered. The cost was steps.
- **With the guide, almost none.** Across its 12 runs: 1 refused command (§3.6), 4 denied by permissions, 6 `--help` lookups. With this model it made no difference whether the guide was in the system text or read on demand: every Lead given the pointer read it once, at the start. Embedded stays the default, because it does not depend on the model following a pointer.
- **What the Leads said** (A6, 18 answers; each claim checked against the Lead's transcript):

  | Theme | Who said it |
  |---|---|
  | "Implementation evidence is accepted by transition, not `evidence ingest`" was learned only from an error | all 6 without the guide. They asked for a lifecycle guide or "a clearer end-to-end mutating-Ticket example", which is what the guide is |
  | The authority-candidate step at the start was unexpected | 8 of the 12 with the guide (the guide did not mention it; it does now) |
  | No command to read a piece of evidence; they opened the files directly | 4 (`aew evidence` has only `ingest`) |
  | The guide's "Class 0 criteria are not defined yet" made the choice less certain | 3 (§3.5) |
  | The brief's Class 0 sentence left out the post-integration verification | 3: two read it as contradicting the guide, and one learned of it when publish was refused |
  | A command to amend a Ticket's scope, or an early scope check | the Lead of the scope case (§3.6) |

- **Some of the friction was ours.** The dogfood's brief listed `aew evidence ingest` among the ingest commands (the most refused command). It also said the Lead's shell runs "read-only `git` commands" (it runs four), and never named the Lead's read tools. Corrected (rubric A7).
- **Debriefs point to problems; they do not prove them.** One Lead said `aew status` told it to ingest the report. Its transcript shows that `aew status` gave the right transition, and that the Lead had already chosen `evidence ingest` in the same command.

### 3.5 Risk class: the open question

| Where | Tickets and their classes |
|---|---|
| The hardened dogfood (26 runs, 30 Tickets) | all Class 1 or 2, the one-line fix included |
| T1C0, the operator directing Class 0 | Class 0 in both trials; the path works, running only the implementer and the post-integration verifier |
| A4, the guide embedded | every Ticket Class 1 |
| A4, the guide read on demand | Class 0 four times: T1 once (both of that run's Tickets), and T3's investigation Ticket in both runs; Class 1 otherwise |
| A5, no guide | Class 0 for T1 in both runs; T2 and T3 at Class 1 or 2 |

- **The Leads' own reasons for Class 1:**
  - "not necessarily an obvious single mechanical edit";
  - "the formatting behavior was user-visible and needed explicit independent review and verification";
  - "required ... adding regression coverage";
  - "the guide says Class 0 criteria are not defined yet".
- **Where the reasons come from.** The guide quotes the Workflow Contract's definitions: Class 0 is "trivial/mechanical ... one obvious mechanical edit", and Class 1 is "routine engineering ... bounded normal work". The Leads apply them literally, so a small, fully specified behaviour fix with a test reads as routine: Class 1. Without the guide, the brief's one sentence ("Class 0 is for trivial, low-risk changes") was enough for Class 0.
- **The designer's decision (Q10).** Either:
  - such fixes are Class 1 by design, and T1's rubric label ("Class 0 is appropriate") changes; or
  - Class 0's definition names them, ideally with criteria the engine checks (plan assurance's Tier A).

  Either way, the guide's "not defined yet" line should be replaced by the rule chosen, because the hedge itself pushes Leads up a class.

### 3.6 Scope, next actions, and the Ticket model

- **Twice a scope mistake cost a Ticket and its correct implementation**, because a scope cannot change once the Ticket exists:
  - M3-D9: a comma-joined glob;
  - A4's T1, trial 2: a Lead that could not look at the code guessed seven globs that missed it (report §6.6).
- **In that run, AEW made the recovery harder:**
  - `aew harness wait` listed evidence ids without results, so the implementer's `blocked` report went unseen;
  - `aew status` proposed the accepting transition, which the gate refused, and then proposed it again;
  - the refusal named the path but no way forward.

  The gate itself held.
- **Fixed now (E8 to E11):**
  - the next actions read the evidence, and say what blocks a Ticket instead of proposing a transition its gates will refuse;
  - `aew harness wait` shows each item's result and the run's next action, as its documentation already claimed;
  - the scope refusal says the scope is fixed and what to do;
  - creation warns about each scope glob that matches no file;
  - the Lead's system text and the guide say how to read the project, what the authority step is, and that a scope is fixed.
- **Designed: Ticket revisions.** Adopted by the designer on 2026-09-30, decisions D1 to D7 (`docs/archive/reviews/ticket-revision-amendment-review-2026-09-30.md`). A scope correction becomes a new revision of the same Ticket, the workspace can carry forward as input, and evidence admissibility across the revision is computed. Every revision's proof is regenerated or explicitly revalidated.

## 4. What changed because of the tests

| From | Change | Where |
|---|---|---|
| Step 8 | M3-D2 to D7, found by real models in every role (among them a report left stale in the workspace, a bridge error, a report written into the operator's repository, and unqualified finding ids) | `harness-conformance.md` §6 |
| Step 9 | M3-D8 (next actions after a run), M3-D9 (comma scope), M3-D10 (`resume` inside a Lead session); B1, free text as data (`--fields`) | report §8 |
| The audits' reading of the dogfood | X1 (refusals name the command that applies), X2 (runnable next actions), X4a (no class anchoring), T3 (an instrumented command log); L1 re-costed the Lead | `m3-audit-findings.md` |
| Q10, X4 | F16: `aew guide`, generated from the project's policy and in every Lead's system text | report §6.5 |
| A4's scope case, A6 | E8 to E11 (above); O5 and A7, the brief corrected | `future-work.md` §5, §6 |
| A5 | The dogfood driver: nudges and debriefs broken since audit I3, fixed; a debrief that reopens saved sessions | report §9 |
| The scope case, M3-D9 | Ticket revisions (adopted in design) | `docs/design/ticket-revision-amendment-*.md` |
| T4, the scope case | Plan assurance (F14): acceptance integrity, scope validity, reconnaissance before scope | `docs/archive/superseded/plan-assurance-and-premise-validation-design-v0.3.md` |
| L1 | Lead workflow efficiency: stage commands (F15) | `docs/design/proposals/lead-workflow-efficiency-design-v0.1.md` |

## 5. What the tests could not show

- **A quality benefit.** Ceiling effect: small tasks both models solve alone.
- **Rates.** Two trials per cell show a direction, not a rate. A difference of one run is a signal.
- **Other models.** OpenAI's Luna and Sol at medium effort, plus free models in step 8. Another model may follow a pointer less reliably, or classify differently.
- **The interactive case.** The Lead was headless, with a brief standing in for AEW skills and the operator. The operator's TUI session is the check.
- **Real repositories.** Scratch projects only, since containment is workdir separation.
- **What the Leads remember.** The debriefs were asked afterwards, in reopened sessions. They are reconstructions from each Lead's transcript, and one misattributed its own choice.

## 6. Decisions and next steps

**For the designer:**

1. **Q10, risk-class calibration** (§3.5): Class 1 by design for small behaviour fixes, or a Class 0 rule, and the guide's wording either way.
2. **An evidence view** (E12, proposed): `aew evidence show <id>` (kind, result, claim, deviations or findings, body), or next actions that carry a record's conclusion. Four Leads opened evidence files directly.
3. **Order after M3:**
   - Ticket revisions (F4, decided);
   - plan assurance (F14, where T4 points);
   - stage commands (F15, where the Lead's cost is);
   - containment (F2), before any real-repository dogfood.
4. **The next dogfood (Q7):** tasks where a single session fails. The rubric process, the instrumented command log, the saved sessions and the debrief are ready for it.

**For the operator, the TUI acceptance session:**

- The Lead's first steps: whether it reads the guide in its context, and handles the authority candidates without trial and error.
- `/aew-ticket`: the class it proposes for a small fix (expect Class 1, §3.5), and whether creation warns about a scope glob that matches nothing.
- After a run: `aew harness wait` shows each result and the next action.
- A deliberately wrong scope: the refusal should say what to do, and `aew status` should not propose the refused transition.
- Close OpenCode mid-Ticket, then `aew opencode` and `/aew-resume`: the Lead should continue from AEW alone.
