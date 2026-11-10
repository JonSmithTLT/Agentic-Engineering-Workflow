<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-56
source: 30-stages/STG-31-steering-mode-persistence/adopted/smp-r4/SMP-POSITION.md
source-sha256: 05f0050a07dea956d7365a9677ec84b51348f55991ab443b7a905e8e7d7c3bd5
edits-sha256: none
-->

# A steering raise that persists for the project, until a change that may affect the run (PROPOSED, revision 4)

**Namespace:** `SMP-`
**Status:** proposed, revision 4, 2026-11-08, revising A-56 (revision 3, adopted the same day). It amends A-39's `I6-06`, `I6-06.a`, `I6-06.f`, `I6-06.g`, `I6-R01` and its owner table's line for the mode (`I6-PROFILE.md:91`); A-43's `I7-00.a`, its table line for `SET_STEERING_MODE` (`I7-PROFILE.md:94`), its reason table's "names instead" (`:131-132`) and its list of records in force (`:234`); and A-42's `MSN-04` and `MSN-Q08`, for one case only (`SMP-10`). `I6-X04` now holds only for a one-generation raise (`SMP-X04`). It keeps A-42's stop: where A-42 reads a lapse from `I6-06.g` (`MSN-POSITION.md:61`, `:136`, `:138`, `:161`), that lapse also ends the consent (`SMP-04`). It loosens authority, so it's the operator's to adopt.
**Authority:** the operator's decision `00-governance/decisions/2026-11-08-operator-steering-raise-persists-per-project.md`.
**Threat model:** the operator's decisions of 2026-10-19 and 2026-10-24: steered agents and AEW bugs, not malicious code run as the operator.
**Research consulted:** `tools/research_index.py lookup` on `I6-R01`, `I6-06` and `R01-38`: none. On `R-DEC-04`: `external-workflow-2026-10-05`, which recommends `WALK`, not `CRAWL`, because `CRAWL` adds ceremony to trivial work. This position moves toward that concern without changing the default: see `SMP-R02`.
**Files:** this file.

## What the adopted text already decides

- **The mode decides only whether an eligible action waits or is auto-run,** and no admission check reads it: `I6-06`, `I6-06.f`, `R01-38`.
- **What `RUN` reaches:** ticket start and review request, by the operator's decision on `R-DEC-04` of 2026-10-25. `WALK` reaches nothing.
- **A configuration default is not a mode:** `I6-06.f`, `I6-04.c`. This position keeps that.
- **A mission's stop lapses any `RUN`,** with no auto-run until the operator raises again: `MSN-Q09`, A-42. This position keeps that.
- **The consent:** one use, rendered from its leaves (`G3-03`, `G3-08`). When G3 doesn't count, the typed-back code stands in: G3-C's PR C3.

## The parts

- **The operator:** gives and withdraws the consent. Nothing else can.
- **R-01:** owns the mode record, the consent's standing and the open ask. No agent can write them.
- **The run's boundary** (HEB and its harness adapter): observes the Lead's harness and model route. The Lead's own word is never the source.
- **The Lead:** reads the mode and the reason for it. It can't raise it.

## Rules

**SMP-01. A persistent raise is a `SET_STEERING_MODE` consent that names what it persists against, and the operator sees those values when approving.**
- **The target gains three required, nullable leaves:** `harness_ref` (the harness and its version), `lead_route_ref` (the provider and model) and `legality_ref` (the legality-affecting policy digest).
- **All set:** a persistent raise. **All null:** A-39's raise for one generation, unchanged.
- **Refused, as `POLICY_INVALID`:** some set and some null (`PERSISTENCE_INCOMPLETE`); any set with a mission (`PERSISTENCE_WITH_MISSION`); any set on a change that isn't a raise (`PERSISTENCE_ON_LOWER`).
- **The project and installation** are the set's subject, already in every O-01 set. So a project copied to another installation carries no raise.

**SMP-02. R-01 admits a persistent raise only if the values it names are the ones the boundary currently observes for the current Lead (`PERSISTENCE_STALE`, `PRECONDITION_STALE`), on top of `I6-06.a`.** An unavailable source is a hold (`LEAD_STATE_UNAVAILABLE`).

**SMP-03. A new Lead generation inherits the project's persistent raise only when compared and matched.**
- **The record:** when HEB reports a new current generation, R-01 records its mode at `CRAWL`, as `I6-06.g` says.
- **Inherited:** at the boundary's first observation of the generation's harness and route, if the consent stands, the values match, the new Lead has caught up (`SMP-11`), and the built raise's own checks still pass (the configuration and the notifier for `RUN`), R-01 records the inherited mode. The record cites the consent, is attributed to R-01, not the operator, and has a new version. `MODE_STALE` reads that version.
- **Until that observation,** the generation runs at `CRAWL`, and nothing is asked.
- **A harness declared unobservable** (`SMP-08`) is `SMP_NOT_OBSERVED` from the start. For any other, a late first observation only delays the inheritance: it ends nothing, and `status` says the mode is waiting for it.
- **A check that fails** is `SMP_CHECK_FAILED`, with the check's own reason. The mode is `CRAWL`, the consent stands, and inheritance resumes at the next comparison once the check passes.
- **An inherited record spends no consent.** This is the one path that raises a mode without a consent of its own. It amends `I6-06.f`. The consent's `valid_until` (`G3-06`) bounds its use at consume, not this.

**SMP-04. Each of these ends the consent, and the mode is `CRAWL` with that reason.**
- `SMP_HARNESS_CHANGED`: the harness or its version differs.
- `SMP_ROUTE_CHANGED`: the provider or model differs. Going back to the old pair later is still a new approval.
- `SMP_NOT_OBSERVED`: this harness is declared unobservable, or a value doesn't fit O-01's ref pattern.
- `SMP_POLICY_CHANGED`: the legality-affecting digest differs from the consent's `legality_ref`.
- `SMP_ASSURANCE_CHANGED`: the consent was given by the typed-back code, and G3 now counts. A consent given through G3 isn't affected by G3 later not counting.
- `SMP_MISSION_STOPPED`: a mission's stop (`MSN-Q09`).
- `SMP_WITHDRAWN`: the operator changed the mode through `SET_STEERING_MODE`, or adopted a lower default. The mode is the one they set, not `CRAWL`.

**SMP-05. The comparison happens before every auto-run step.**
- The auto-runner compares the current observation with the consent before each step (`R01-39`). A difference records `CRAWL` with its reason, and the step waits.
- **No current observation means no auto-run for that step.** It ends nothing, and `status` says so.
- A step already admitted completes under its own admission (`I6-06.g`).

**SMP-06. After a drop, raising again is trivial: AEW asks, and the operator answers once.**
- **AEW makes the ask itself.** The operator composes no command and recalls no mode. It names what changed, from and to, and offers the mode the consent had, with the new values filled in.
- **The answer is one act:** the PIN on the confirmer where G3 counts, otherwise the typed-back code. Where the values can't be observed, the offer is a one-generation raise (all leaves null).
- **Work continues at `CRAWL` while the ask is open.** The Lead takes each step itself. Nothing is held or refused.
- **R-01 owns the ask.** A no is recorded, keyed to the reason and its values, and isn't asked again until those change or a raise clears it. `SMP_NOT_OBSERVED` asks once per generation, whatever an earlier no said, because its values may never change. An expired approval isn't a no: it's offered again at `status` and at the next start. The operator can still raise at any time.
- **No agent can answer it:** the same approval path as `SET_STEERING_MODE`.
- **Candidate:** `aew opencode`'s start, for a change seen at the start; the notifier and `status`, for one seen mid-session. Both reach the same endpoint operation.

**SMP-07. The reason is visible.** `status`, `resume` and the Lead's wake show the mode, whether it's inherited or dropped, and the reason. The Lead reports a drop in a line. A drop is not a failure, and the Lead has nothing to recover. A takeover's output says which mode carries over, and how to lower it.

**SMP-08. Each harness adapter declares whether it can observe the Lead's harness and route.** One that can't runs under `SMP_NOT_OBSERVED`, and that gap is a register row for it (the operator, 2026-11-06).

**SMP-09. An observation counts only from a source the Lead's model can't falsify, or is labelled.**
- **Auxiliary calls aren't the Lead's route:** a harness's title, summary and compaction agents are excluded. Every other session of the generation is compared.
- **Candidate, Linux, contained:** the session's own record on the server AEW hosts for push wake (`model-switched`, the session's model), with the provider relay outside the sandbox as the check that the requests match. A mismatch is `SMP_ROUTE_CHANGED`.
- **Candidate, Windows:** the same server read. There's no boundary there, so `status` says the value is the harness's own report. It's the weaker posture Windows already has, and G3 doesn't count there.

**SMP-10. A mission and an inherited mode don't combine.**
- **No generation inherits** while a mission is open or opening. A mission's own raise (`I7-07.c`) is unaffected.
- **Accepting a mission while an inherited `RUN` is in force** is refused as `INHERITED_MODE_IN_FORCE` (`POLICY_INVALID`), naming the fix: lower it, then accept, with the mission's own raise in its set. `MSN-04`'s "unless `RUN` is in force" assumes the operator was present for that `RUN` (`MSN-R05`), so this overrides `MSN-04` and `MSN-Q08` for this case only.
- Missions aren't built, so this costs nothing today.

**SMP-11. An inherited mode waits until the new Lead has caught up.**
- **Every new generation, a takeover's included,** stays at `CRAWL` until its Lead has rebuilt its context with `resume`. The boundary records that call. A note or a claim from the Lead doesn't count.
- **A Lead that hasn't called it** holds no work, and asks the operator nothing. `status` says the mode is waiting for it.
- **A consent the operator gives during the generation** isn't held by this rule. It's their own, current word.

## Interfaces

- **Wire:** O-01's next revision gains the three leaves on `SET_STEERING_MODE`'s target, the reasons above and `I7-PROFILE.md:131-132`'s "names instead" text for them.
- **Bridge:** until convergence re-vendors the wire, G3-C's overlay carries the leaves, and its equality test names them as differences from A-43. `legality_ref` replaces C3's stretch of `reason_ref`.
- **Rendering:** the member needs three more lines, within G3's bound of 30 (`G3-03`, `R2-1`; computed by `render.member_line_limits`'s method).
- **Depends on:** G3-C's C3; steering PR 2's server; a generation-start record, which the built engine doesn't have.
- **Candidate, code:** a slot of its own beside `standing` and the override, because `effective()` labels any non-operator override as lowered (`steering.py:107`), and `standing` can't hold a raise (`:280-281`).

## The gate

| Check | What it requires |
|---|---|
| **SMP-Q01** | A new generation with the same values inherits, no consent is spent, and the record cites the original consent |
| **SMP-Q02** | Each of `SMP-04`'s reasons, by a planted change, yields its stated mode and reason, and ends the consent |
| **SMP-Q03** | A mid-generation route change stops the next auto-run step, with no window in which a step runs under the old mode |
| **SMP-Q04** | Before the first observation the generation is at `CRAWL`, asks nothing and ends nothing, and `status` says so; a late first observation that matches still inherits |
| **SMP-Q05** | No agent-written label, note or message changes a comparison |
| **SMP-Q06** | A test counts the operator's inputs from the drop to the raised mode: one |
| **SMP-Q07** | Nothing is held while the ask is open; a no isn't asked again for the same reason and values; an expired approval is offered again |
| **SMP-Q08** | A one-generation raise (leaves null) behaves as A-39's, with `I6-X04` unchanged |
| **SMP-Q09** | A title, summary or compaction call on a small model causes no drop |
| **SMP-Q10** | With a mission open or opening nothing inherits, and a mission over an inherited `RUN` is refused with its fix |
| **SMP-Q11** | A failed check gives `SMP_CHECK_FAILED`, the consent stands, and inheritance resumes once it passes |
| **SMP-Q12** | No step auto-runs between a new generation's first observation and its Lead's `resume`, and a Lead's text saying it has caught up changes nothing |
| **SMP-Q13** | A takeover with the same values inherits after `resume`, with no second approval, and its output says which mode carries over and how to lower it |

## Scenarios

**SMP-X01.** Given `RUN` approved once on one harness and model, the Lead's next session on the same pair runs at `RUN` from its first observation, with no PIN.

**SMP-X02.** Given the same project, the operator picks a new model in the next session. At the first observation the mode is `CRAWL`, naming old and new. The ask appears, and one PIN later the mode is `RUN`, under a consent naming the new model.

**SMP-X03.** Given `RUN` in force, the operator switches model mid-session. The next auto-run step doesn't run, and the same ask appears.

**SMP-X04.** Given a persistent `RUN` in generation 5, a takeover makes generation 6 on the same values. It's at `CRAWL` until its Lead calls `resume`, then `RUN`, with no second approval. Given a one-generation `RUN` instead, generation 6 starts at `CRAWL`, and only a new consent raises it (`I6-X04`).

**SMP-X05.** Given a Lead that writes "model unchanged" into a note, the comparison ignores it.

**SMP-X06.** Given `RUN` from a typed-back code, G3 is installed and counts. The next generation starts at `CRAWL` with `SMP_ASSURANCE_CHANGED`, and the ask is a PIN.

## Rulings

**SMP-R01.** This replaces `I6-R01`'s reason with a check of it. `I6-R01` lapsed every generation because a new one "may be another model, harness or actor". Here, a model and a harness are compared. The actor is the operator, who approves a takeover themselves (`TAKEOVER_LEAD`), so a takeover changes none of what the consent was given for. The operator's words: "its only when a change is deteceted that may change teh quaslity of run does it say l;ets slow down".

**SMP-R02.** The default stays `CRAWL`. Nothing here raises a mode the operator didn't raise once. The study's concern about ceremony is met by not asking again, not by a higher default.

**SMP-R03.** These go beyond the operator's three named changes, and each tightens: the version in `harness_ref`, `SMP_POLICY_CHANGED`, `SMP_ASSURANCE_CHANGED`, `SMP_MISSION_STOPPED`, `SMP_WITHDRAWN`, and a route's return needing a new approval. Each fits the operator's test, or keeps adopted text. The operator can strike any at adoption.

**SMP-R04.** An unobservable harness asks every generation, rather than trusting a label. It costs one approval per session, which is what the operator has today.

**SMP-R05.** Any reason ends the consent, rather than only skipping one generation. So a declined ask can't leave a raise that the next generation quietly regains.

**SMP-R06.** A takeover doesn't end the consent. The operator's words: "meh if possible a takeover shouldnt". The cost is stated: after a takeover because a Lead went wrong, `RUN` stays unless the operator lowers it, which `SMP-07`'s line tells them at that moment. What the drop was also doing, keeping a new Lead from starting into `RUN` unread, is now `SMP-11`, for every generation.

## Backlog

**SMP-B1.** The effort setting isn't compared. It's a row if evidence shows it changes runs.

**SMP-B2.** Whether a mission could accept over an inherited `RUN` with its operator told, rather than refused as `SMP-10` has it. Settle it when the mission is placed.

**SMP-B4.** The relay's check is provider-specific: Google's model is in the URL path, not the body. Evidence today is OpenCode 2.2.6 only, and the Lead's own route to `switchModel` is unproved. The builder's first step covers these, from steering PR 2's measurements.

**SMP-B3.** Withdrawn in revision 4: a takeover no longer costs a second approval (`SMP-R06`).

## Not covered

- A raise bound to a mission (`I7-07.c`), apart from `SMP-04`'s stop and `SMP-10`.
- **Qualification** (`HEB-01.c`, which binds to the effective configuration). No admission check reads the mode (`R01-38`), so a mode can't stand in for it, and qualification changes hold protected effects by their own rule.
- Any change to what `RUN` reaches (`R-DEC-04`).
- The Lead's own lowering, built but unexamined at `I6`'s flag: it stays for its generation and doesn't end the consent.

## Changes

- **Revision 4 (2026-11-08):** the operator's change, after the designer told them a takeover can be routine: a takeover no longer ends the consent; `SMP-11` holds every new generation at `CRAWL` until its Lead calls `resume`; a takeover's output says what carries over.
- **Revision 3 (2026-11-08):** answers the quick check: the amendment list, `SMP-10` in place of an override sitting in the backlog; no deadline on the first observation; the no's key against an unobservable harness; a lower default; `SMP_CHECK_FAILED`; qualification. The review's "what does 'harnass qualify' mean" is settled: that phrase named the builder, harness-qualify, and answered who takes push wake.
- **Revision 2 (2026-11-08):** answers one review round, findings 1 to 13 plus its challenge, in `REVIEW-r1.md` beside this file: the mission stop; the amendment list; lowering; the no and expiry; which reasons end the consent; missing failure behaviours; categories; the unobservable offer; `legality_ref` in place of a digest the consent didn't bind; assurance change; auxiliary calls; observation sources.
- **Revision 1 (2026-11-08):** first draft, from the operator's decision.
