<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-57
source: 30-stages/STG-32-knowledge-lessons/adopted/kp-r1/KP-POSITION.md
source-sha256: a232582c9ec62c284f9f0f16d5c0bbb92e643a33ba6d8c7d077e99a7075bd68e
edits-sha256: 5f95180ff88fd3b492460ddf7443f91e64ddc246ca60ca031cc18140a7839e60
-->

# Lessons: the knowledge system's first increment (PROPOSED, revision 1)

**Namespace:** `KP-`
**Status:** proposed, revision 1, 2026-11-08. It is K-01's own increment for the `L` profile and for `H` going on by default. It changes adopted text only as `KP-36` lists, for Lessons only. Each change's effect is on the operator's page, and the operator accepted the rows marked "added after review" before this file was frozen. It gives `W12` a type, which A-43 left to this increment.
**Authority:** the operator's approval of 2026-11-08, on `OPERATOR-PAGE.md`: "Approve all four"; the condition that viewing and approving be easy on the dashboard; "Yes, click plus PIN"; and "i can accept those", on the rows added after review. Also the operator's selection of Lessons (`2026-11-01-operator-K01-lessons-and-F35-selected-after-V01.md`) and their stated picture (`2026-11-08-operator-knowledge-picture.md`).
**Threat model:** the operator's decisions of 2026-10-19 and 2026-10-24: steered agents and AEW bugs, not malicious code run as the operator.
**Research consulted:** `tools/research_index.py lookup` on `K01-16`, `K01-46`, `K01-47`, `K01-49` and `O01-16`: none. On `K-DEC-01`: `knowledge-service-identity-spike-2026-10-04`, on a service credential, which this increment doesn't need (`KP-R03`). The index doesn't map the two studies this position rests on, so they are named here: `docs/research/aew-knowledge-capture-admission-and-agent-usefulness-v0.1.md` (role-authored lessons are never the sole gate, :76; advisory text biases work, :36), and the Lead memory research of 2026-11. Where this position departs from the first, `KP-R46` says so and why.
**Files:** this file, and `OPERATOR-PAGE.md`, the operator-approved page, frozen beside it and not a D1 source. This file defines the page's requirements under the same numbers.

## What the adopted text already decides

- **Who decides what enters Knowledge:** agents nominate, host code admits under rules the operator approves, and judgment-bearing changes need the operator (`K-DEC-01`, the operator's decision of 2026-10-24). Whoever approves must have qualified authority and be independent of the nominator and the interested roots (`K01-43`, `K01-46`).
- **What a Lesson must carry and how it is served:** `K01-08`, `K01-03`, `K01-09`, `K01-42`, and `K01-49`'s complete-or-marked rule.
- **No benefit claim without a comparison:** `K01-19`.
- **A correction or removal control over Knowledge must keep historical provenance, distinct author and admin authority, a protected command origin, disclosure and any reliance impact:** `K01-47`.
- **What is never G3:** a website session or click, a CLI flag, a token (`G3-13`). The site can't mint origin evidence, and a click can't claim G3 (`O01-16`).
- **G3's mechanics:** one approval per set, whole-set yes or no (`G3-03`, `G3-05`, `G3-08`), confirmer rendering from typed leaves only, and a held outage (`G3-11`).
- **The dashboard never connects to G3** (`BOY-05`, as `BOY-POSITION.md:134-135` states it), and it stays non-authoritative.

## The parts

- **A nominator:** any LLM role, in a worker's or Lead's own context. It can submit a nomination and a challenge, and read what `KP-30` allows. It writes no control state and sets no class, origin or visibility.
- **The door and the store:** host code in AEW. It resolves and pins sources, applies ceilings, folds records at the next Lead commit, and computes flags. No agent has a route to write its records; `KP-24`'s same-UID residuals apply.
- **The operator:** the only judge of a Lesson's delivery. Nothing else can approve or release one.
- **The dashboard:** reads Lessons and asks the operator endpoint to raise a request. It holds no authority and writes no Knowledge record.
- **The operator endpoint:** outside the sandbox. It builds the command set, asks G3, consumes the approval and records the decision.
- **G3 and its confirmer:** the origin proof, wherever `G3-12` holds.
- **The pack builder:** selects Lessons at dispatch, by a fixed rule, with no model.

## Rules

**KP-01. It is for agents.** The goal is that agents don't rediscover what AEW already learned.

**KP-02. Lessons are the core.** A Lesson, what a past agent learned with its conditions and sources, is the main record from the first slice, and isn't a later step to be earned.

**KP-03. It starts empty and grows from real work.** Nothing ships in the package, and AEW's own project imports its standing items once, as ideas.
- `aew knowledge import` is operator-only and runs once; a second run is refused. Each item passes the secret scan and a names list kept outside the repository. Host rows and failures are left out and named in its output.

**KP-04. The operator isn't a curator.** Agents can find Lessons with no operator step, delivery and release wait for the operator, and all of that is optional: with no operator act nothing stops, everything stays findable, and delivery only shrinks.

**KP-05. A Lesson never decides anything.** It can't grant, approve, pass or change a requirement, and it carries the single authority class advisory.

**KP-06. On by default once built.** A failure in it never stops work (`KP-34`).

**KP-07. An idea is its own declared kind and needs no source.** It's stored held, findable by search, never delivered and never listed for action.

**KP-08. Viewing and approving are easy.** The operator can see what's waiting, read each Lesson, and approve a batch on the dashboard without leaving it, wherever G3 counts (`KP-20`).

**KP-09. Two levels of reach.** A recorded nomination is findable with its status and labels; a Lesson is delivered in packs only on the operator's approval.
- A findable candidate isn't published Knowledge, and nothing an agent writes is served as established.

**KP-10. No automatic admission in this increment.** No timeout, rule or agent approves a Lesson.
- A later rule runs in shadow against the operator's recorded decisions, and is adopted for a class only if it agrees with them (`KP-B2`).

**KP-11. A nomination states its case.** It holds a claim, a free-text subject, the future question it answers, roles, paths in `glob_match`'s language, any host, limits, known counterevidence and alternatives, why it isn't a check instead, and its sources.

**KP-12. Sources are typed.** A source is a check result, review finding, invocation or Ticket event, project decision, or file at a commit.
- A citation of a Lesson resolves to that Lesson's own sources, so repeats count once.
- A decision-only nomination is stored as a pointer, not a Lesson.
- A nomination with no source is stored as an idea (`KP-07`).

**KP-13. The door refuses with a typed reason, and records nothing:** a cited source that doesn't resolve (`SOURCE_UNRESOLVED`), a role outside the archetypes (`ROLE_UNKNOWN`), a path outside the glob language (`PATH_INVALID`), a secret-scan hit (`SECRET_SCAN_HIT`), a ceiling exceeded (`CEILING_EXCEEDED`), or a rendered full unit or pointer over its ceiling (`LINE_TOO_LONG`).
- Over-long lines are refused rather than truncated, because a condition is never trimmed.
- A glob matching no file gets a warning, not a refusal.
- Nominations count per work unit for a worker, and per Lead generation for the Lead (`KP-R14`). A new generation is the operator's act, so a Lead can't reset its own count.
- The door resolves a source with the submitter's own read rights: its work unit's records, what its role's `history search` returns, and any commit in the project's repository. The Lead reads the whole project. A source outside those rights gets `SOURCE_UNRESOLVED`, the same reply as one that doesn't exist, so the door reveals nothing the role can't see (`K01-41`, `K01-12`).

**KP-14. Recording happens at the next Lead commit.** It pins each source by hash and rechecks it; a mismatch holds the candidate; the same nomination twice returns the first receipt; and AEW sets class, origin and visibility.

**KP-15. AEW computes the flags, and a flagged candidate can't join a plain batch.** The flags:
- it names a sensitive path: AEW's shipped list, plus the project's review triggers and protected paths;
- it is broad: no path, or more files matched than `KP-R14`'s count. AEW counts at the Lead commit that folds the version and keeps that count on the version, so an unrelated commit can't flag a batch member;
- it claims paths outside every source's unit scope, finding location or cited file;
- it names reviewer or verifier as a role;
- it would push an approved Lesson out of a pack at its paths (`KP-15.b`);
- it replaces a version while adding a path, removing a condition or counterevidence, or replacing another nominator's Lesson.

**KP-15.a** Flagged candidates go in their own sets of at most 8 named members, each shown with its version and flags. A K3 candidate goes alone, on either path.

**KP-15.b** The push flag: for each role a candidate names and each glob it declares, AEW builds the section twice for a Ticket scoped to that glob, at the project's current commit, by `KP-26.a`, `KP-27` and `KP-28`, ignoring host and `KP-26.b`. The first build holds the approved Lessons. The second adds the candidates being decided, ranked as the newest approvals and then by version id. The flag goes on each candidate ranked above an approved Lesson with a declared path that moves from Full or Pointer to Count.
- The list computes it for each candidate alone. A request computes it for everything ticked, and a refusal (`BATCH_MEMBER_FLAGGED`) names the members to untick.
- It's computed at request and not again at consume, since only the operator's decisions add to the approved set, one at a time.
- A pathless approved Lesson can't set it, since pathless Lessons rank last by design. A move from Full to Pointer doesn't set it, and the list shows that move. So up to about 4 narrow approved Lessons can take the Full slots with no flag. It doesn't judge a Ticket wider than the glob, where the section may already be full.

**KP-15.c** Flags and `KP-15.a`'s limits bind `APPROVE` and `RELEASE`. `HOLD` can take any versions in one batch, since it's reversible. `REJECT` takes candidates only, in a batch. `STRIKE` can't be undone, so it always goes in named sets of at most 8.

**KP-16. The list shows enough to judge.** Claim, sources, conditions, counterevidence, source kinds, whether the run was contained, rank at its paths, the ids it would push out and the ids it would move from Full to Pointer, declared globs, paths and conditions against any version it replaces, possible overlaps (same role, intersecting paths, same subject), and rejected candidates with the same root and intersecting paths.
- It can't detect a contradiction in prose, and it doesn't say it can.

**KP-17. Approval is of exact versions.** It re-resolves each source and refuses a changed one, records its committed store revision, and names any version it replaces and in what scope.

**KP-18. The operator's decisions.** Each is on exact versions, through the same paths.
- **`APPROVE`:** applies only to a version that isn't challenged or held. Those take `RELEASE`, and `APPROVE` is refused (`VERSION_NEEDS_RELEASE`).
- **`REJECT`:** the candidate leaves ordinary search and stays readable by id, and the door tells a re-nominator it was rejected.
- **`HOLD`:** stays findable, not delivered.
- **`RELEASE`:** approves a challenged or held version, including a held candidate (`KP-R18`).
- **`STRIKE`:** the body leaves search, delivery and by-id read, and the status stays. By-id read means `knowledge show`, `history show`, `history load` and the dashboard, each of which shows the id, status and a marker. Search leaves a struck version out when it builds and when it re-reads the authenticated record, so a rebuild or a private index can't bring it back, and this never counts as a stale row. A missed secret stays in the immutable record: the version's file and the nomination's sealed evidence file, which are never deleted, plus a local index row until its next rebuild. A run's own prompt, event log and transcript under `local/harness/runs/` keep what was delivered, and no AEW command reads them.
- **Correcting:** the operator rejects a candidate, or holds or strikes an approved Lesson, and a replacement comes by nomination.

**KP-19. The list is its own lane.** It never stops work, never joins the decisions that stop the steering loop, and never times out into approval.
- A pending `knowledge_decide` holds its own one-request slot, never `_authorizing`, and doesn't set `_awaiting`. So `aew lead mode raise` and capability changes aren't refused while a batch waits in the confirmer, and a pending raise doesn't refuse a batch. `_engine_lock` is held only for reads and the commit, never across the wait. `knowledge_decide` takes no console code: it runs only on the G3 path, and the typed path never reaches the endpoint (`KP-24`).

**KP-20. One path per request, chosen once.** Where `G3-12` holds and `knowledge_decide` has its binding row, a decision takes the G3 path; elsewhere it takes the pasted command (`KP-24`). Once on the G3 path, an outage holds and never moves to the typed code (`G3-11`).
- A G3 service that doesn't know the action holds, and the reply names the root reinstall. The pasted command refuses there too.

**KP-21. The protected action is `W12`, `ADMIT_KNOWLEDGE_CLAIM`, at G3 origin.** A set holds at most `G3`'s 8 members, each with scalar target leaves only.
- **A batch** is one member with a decision, a reference, a digest and a count. For `APPROVE` and `RELEASE`, the digest covers the decision and the exact version ids and source hashes. For `HOLD` and `REJECT`, it covers the decision and the version ids alone. It omits the store revision, so an unrelated Lead commit doesn't void a pending batch.
- **A flagged set** names one version per member, with its flags in the target, so the confirmer shows them.
- **The confirmer shows typed leaves and never agent text.** So reading happens on the dashboard, and AEW records that the operator approved, not that they read.

**KP-22. The endpoint refuses at consume, and records nothing,** if the digest isn't the one it raised (`BATCH_DIGEST_MISMATCH`), any member of a plain batch now carries a flag or a named member's flags differ from its target (`BATCH_MEMBER_FLAGGED`), or a member moved (`BATCH_MOVED`).
- A member moved if, since the request, its status changed, its set of open challenges changed, or a source no longer resolves to its pinned hash. The endpoint keeps what it bound at request and compares at consume, as `g3_adapter.moved` does.
- The flag and move refusals apply to `APPROVE` and `RELEASE`. `REJECT`, `HOLD` and `STRIKE` bind version ids alone, and are refused only if a batch's digest isn't the one raised (`BATCH_DIGEST_MISMATCH`) or a version id doesn't exist, so an agent's churn can't stall a protective act. A member the decision no longer changes is recorded as unchanged, and the rest go ahead (`AOI-07.c`).
- The push flag isn't rechecked at consume (`KP-15.b`).
- A refusal names the members. The page says to tick again. No approved consent is reused.

**KP-22.a** A set is decided whole. The endpoint runs `KP-22`'s checks on every member before consuming any, and any failure consumes none and records nothing. It then consumes each member in set order (`G3-08`), and commits all the decisions in one transaction. A move found at the commit refuses an `APPROVE` or `RELEASE` the same way; `REJECT`, `HOLD` and `STRIKE` still commit (`KP-22`). If a consume answers anything but `CONSUMED`, or the endpoint stops before the commit, nothing is recorded and the candidates stay as they were. Spent members are never reused: ticking again asks for one new approval for the whole set. Each member has its own `intent_ref`, unique and ascending (`CS-01`).

**KP-23. The dashboard's route only requests.** It carries the decision and exact versions to the endpoint, and it writes no Knowledge record and can't return success for a decision.
- **Refused:** no valid session, or a `Host`, `Origin` or `Sec-Fetch-Site` other than the exact same-origin values, where a missing `Origin` is also refused (`REQUEST_NOT_SAME_ORIGIN`).
- **Refused:** a second request while one is pending for the project (`REQUEST_ALREADY_PENDING`), so prompts don't stack.
- **Refused:** G3 not counting (`G3_PATH_UNAVAILABLE`). The page shows the pasted command and says why.
- **Refused:** G3 counting and no endpoint running (`ENDPOINT_NOT_RUNNING`). The page says to start it, and offers no pasted command. The route calls `g3_adapter.choose` first, with no probe, so a host without G3 is never told to start an endpoint it doesn't need.
- **Refused:** a version whose state reference differs when the endpoint receives it (`BATCH_MOVED`). The list gives each version that state reference, over its status, its open challenges and its flags other than the push flag, and the request and the copied line carry it, so the check runs from the tick. `HOLD`, `REJECT` and `STRIKE` skip this (`KP-22`).
- **The page shows** requested, pending and decided states from sourced records only (`O01-16`), and shows the same short reference as the confirmer.
- This is the one write route this position selects. A renewed security review is owed with its PR.

**KP-23.a** The endpoint owns the wait. The route returns once the endpoint reports pending, with the approval ref and the short reference. The dashboard's connection ending doesn't end the wait: the endpoint waits until the approval is decided or expires, and consumes on approval with nobody connected. The endpoint alone answers `REQUEST_ALREADY_PENDING`, from its slot (`KP-19`).
- **The record:** the endpoint writes the `BOY-05.a` record for each approval it starts, and the dashboard only reads it. This PR builds that writer if `BOY`'s slice hasn't landed. The record holds no typed value, so a reloaded page shows the approval ref, which the confirmer also lists.
- **A refusal at consume:** the record's outcome names the `KP-22` code, and the page says to tick again. A decision shows as decided only from the committed Knowledge record.
- **A G3 service restart:** the pending approval is lost. The endpoint reads the 404 and records it, and the page says to tick again.
- **An endpoint restart:** the request ends and nothing consumes it. The page shows `BOY-05.b`'s client-gone row: decline the prompt or let it expire. A PIN entered there approves nothing. A new tick is allowed, and the confirmer lists both until the old one expires.

**KP-24. The pasted command is the first version and the lasting fallback where G3 doesn't count.** It names exact versions and takes the Lead credential and the existing typed-back code at a terminal (the decision of 2026-11-01). It needs no endpoint, and confirms with `operator.authorize` at the terminal it runs in.
- Every command that records a decision calls `g3_adapter.choose` first. Where that says G3, the command refuses (`G3_PATH_REQUIRED`), takes no code, and names the dashboard and the endpoint to start. Before the binding row ships, `choose` says no on every host, so the first version takes the code everywhere. The binding row ships in the PR that adds the page's button, so a G3 host is never pointed at a page with no button.
- The limits in `KP-15.a` and `KP-15.c` hold, and each flag refuses a plain `APPROVE` or `RELEASE` batch.
- `KP-17`'s and `KP-22`'s checks live in one engine function both paths call. The copied line carries the batch digest and the state references, and no expected store revision, so an unrelated commit can't stale it.
- Its record is labelled interim, because the typed route isn't production authority.
- **The broker and the engine refuse an agent's ordinary route.** `approve`, `reject`, `hold`, `release`, `strike` and `import` are operator-only in the Lead broker, and the engine refuses a decision with no `operator-tty` record (`operator.py:204`). `nominate`, `list` and `show` stay Lead-reachable. This doesn't stop a same-UID agent outside containment that runs the code in its own process and answers the challenge through a pty, or that writes `.aew/` directly (`operator_client.py:32-38`). Those residuals stand until F18.6, which is why this route is labelled interim.

**KP-25. A challenge stops delivery only if it cites a typed source.** The source must not be a bare file or the Lesson's own, and its scope or location must intersect the Lesson's paths.
- Anything else raises one spool line to the Lead.
- A source already on record at release can't hold that version again.
- Challenges count against a ceiling per work unit for a worker, and per Lead generation for the Lead (`KP-R14`).
- A pathless Lesson intersects any typed source in the project, because it can reach every Ticket.
- The status reads challenged, not false, and the version joins the list.
- A withdrawn, missing or changed source has the same effect.

**KP-26. Selecting for a pack starts from the Ticket's paths.** They are `scope.paths`, else the accepted plan's `affected_paths`. If both are empty, only pathless Lessons are delivered, and the pack says so.

**KP-26.a** The filter keeps a version only if it is current; approved; not challenged, held or struck; not replaced in a scope covering the Ticket's paths; for the pack's role; with a declared glob overlapping the Ticket's paths (`overlapping_scopes`) or no path at all; and with no conflicting host.

**KP-26.b** For reviewer and verifier packs, the filter also drops anything rooted in or nominated from the Ticket under review, its descendants, the replaced lineage or same-parent Tickets. This is a default on the pack and recall routes, proved by sentinel tests, and not a boundary against reading.

**KP-27. Rank is a total order, and has no model.** First, fewest tracked files matched by the Lesson's whole path list at the pack's commit, where a Lesson matching zero files is left out and pathless Lessons rank last. Second, newest approval revision. Third, version id, ascending by code point.
- Ticket paths filter and never rank. Use counts and age never enter, apart from the second step's tie-break.

**KP-28. The section renders in three parts, each with its own budget in characters.** Full: one fenced unit per Lesson with claim, conditions, counterevidence and alternatives, author, source, approval and how to expand. Pointer: "If <future question>: see K-nnnn", stating no claim, marked incomplete, with its expansion handle. Count: "N more match your paths: search for them".
- **Starting budgets:** about 1,400 and 1,600 characters, about 4 and 16 Lessons, and one line. These are provisional settings: the designer's judgment and not measurements, set from pointer opens once they exist. A person changes a budget in a release (`KP-R14`), and one Lesson's opens never reach selection. The operator approved the provisional 3 KB shape.
- A whole Lesson drops or none of it does, and no condition is ever trimmed (`K01-49`).
- The section's budget is separate from any pack budget. If a pack budget is later set, the section sits in the recall tier, and Lessons never displace authority or source sections.
- A recorded host or tool condition shows as unchecked unless it matches. A path changed since approval shows "may not apply" on the full line and the search hit, and the pin holds that line.

**KP-29. A pack's Lessons are pinned at dispatch.** Selected versions, omitted count and host result are pinned on the invocation and listed in `inv.pack.sources`, and regeneration reads only the pin.
- **A launch never refuses over a Lesson.** A hold or challenge after dispatch acts at the next pack build, plus the spool line.
- **The one exception is `STRIKE`.** Regeneration of any pack, launched or archived, renders a struck version as a marker with its id, never its body. This covers a version a Lead loaded with `history load`, and `history load` refuses a struck version.
- `context show` returns a stored pack only if the invocation's pin lists no struck version. Otherwise it renders the pack afresh, and a writer overwrites the stored file. A strike deletes nothing: stored packs are disposable, and a bundle holds only a pack's path, hash and sources.
- A launch or relaunch of an invocation carrying a struck version stops at the existing pack guard. The refusal names the version and gives the re-dispatch commands, in the form the stale-gate list gives them. The Lead runs them, and AEW never dispatches on its own.
- A live run isn't stopped, and it keeps what it has read. The strike's one line to the Lead names each active invocation carrying the version, with those same commands.
- `context pack` reports `matches_recorded: false` and names the struck versions. No audit compares packs, so a mismatch with no strike on record stays what it is today.

**KP-30. Search finds what isn't delivered.** Held candidates, ideas and approved Lessons are findable with status and labels, and rejected ones aren't. Text is fenced and labelled.
- Reviewer and verifier searches omit unapproved nominations and anything under `KP-26.b`; raw history still answers them. This filter ships with workers' search.
- Raw history never enters a pack.

**KP-31. Agents are told.** The Lead's and workers' text says the system exists and how to nominate, in concrete words, derived from the switch and the role's operations, with no instruction to search every time. A per-role test records its bytes.

**KP-32. Observed, not claimed.** AEW counts, per run, Lessons served in full, pointers shown and opened, expansions, challenges, and bytes × requests. It also runs known-answer searches over past incidents with no model, and measures how much of a hand-written brief AEW now carries.
- These are observations, never benefit (`K01-19`), and they don't feed ranking.

**KP-33. Critical events stop it.** A Lesson that changes a permission or gate, one that crosses project scope, or an unapproved one delivered, means switch off and hold. A hostile text merely stored and findable isn't one.

**KP-34. One switch, and failure stays quiet.** `knowledge.lessons` is a string switch with the values `disabled` and `enabled`. An absent key reads `disabled`. `aew init` writes `enabled` in the execution policy, so a new project has it on. An existing project stays as it is until the operator takes the shared switch offer's row at `aew opencode`'s start. A no is remembered and leaves it off, and `aew doctor` keeps showing it. A flip takes effect at the next launch.
- Off, packs carry no section, and search keeps working.
- While `recall.raw_history_search` is off, the section holds full Lessons only, with no pointers and no count, and the pack says search is off.
- A failed read gives no section plus a labelled line, and never stops a launch.
- Where a run wasn't contained, its Lessons are labelled weak.

**KP-35. Release terms.** No comparator and no thresholds, so no benefit claim. AEW refuses to enable if a test fails its expected result in this position's gate or scenarios. A row that needs a path runs once that path ships. A wrong conclusion from a genuine source isn't a refusal, since the operator accepted it. Rollback is the switch, plus a hold on any version, with history kept.

**KP-36. What changes in adopted text, for Lessons only.** The gates stay for Cases and for any benefit claim, and the lines below are read with these changes.
- **The order** (adoption §7; admission design §24, §25; `KAD-02`, `KAD-11`, `KAD-13`; `KST-18`; `KCA-44` to `KCA-47`; `KRR-41`, `KRR-45`; A-13:36): Lessons proceed on this position. Reaching Cases needs the evaluation unfrozen.
- **Default serving** (`KCA-23`, admission design :438, :440): delivery on the operator's approval. Automatic admission stays off, unchanged.
- **Pack injection** (`AEA-16`, `AEA-36`, `AEA-39`, `AES-19`, F35's note): approved Lessons are delivered in packs. Raw history stays out.
- **The scenarios** (`KRB-14`): ordinary tests now. Held-out labels move with the evaluation.
- **Release** (`K-DEC-03`, A-13:277, `K01-49`'s last clause): `KP-35`, with no comparison.
- **Acceptance** (the agent-use acceptance gate, `KCA-45`): switching on isn't acceptance, and nobody claims improved outcomes.
- **Held material** (admission design :465, `KCA-25`): held candidates and ideas are findable by ordinary explicit search, with status.
- **Visibility** (`K01-12`): nominations are visible across the project once recorded, except through `KP-26.b`.
- **Serving recheck** (`K01-16`'s serving half; `K01-45`, added after review): `KP-29`. A hold or retraction after dispatch acts at the next pack build, and a launched pack keeps its pinned text, which shows its approval date and revision (`KP-R27`).
- **A candidate's basis** (admission design :399, A-13:146, research :134, :142): ideas are a separately declared kind (A-13:67) with no basis, explicit as such (`K01-03`).
- **Pending knowledge** (`KCA-33`, `KCA-73`, admission design :660, ADR-0013:122-125): `KP-19` (`K01-48`).
- **Secrets** (`AEW-FR-36.a`, adoption record :108): the scan enforces it, and a miss is a stated residual.
- **The site** (`O01-16`; `dashboard-main-line-api-design-v0.1.md:83`; the 11-06 hold match, item 3): one request-only route, `KP-23`.
- **`W12`** (I7-PROFILE:64; A-32's proposed origin `OWNER_DECISION`): `KP-21`, at G3 origin.
- **The typed route** (`K01-47`'s protected command origin, for `REJECT`, `HOLD` and `STRIKE`; `K01-46`'s K3 protected judgment path, for `APPROVE` and `RELEASE`; `O01-10` and `G3-12`'s hold, for all five), added after review: where `G3-12` doesn't hold, or before the binding row ships, `KP-24` decides on the typed code and labels the record interim, instead of holding. Once the row has shipped, on a host where G3 counts, `KP-20` applies and this row doesn't.
- **Unknown applicability** (`K01-16`'s missing bases; admission design :398; shared semantics §7.6), added after review: a condition AEW can't evaluate doesn't suppress delivery. A host or tool condition shows unchecked and a free condition renders verbatim (`KP-28`, `KP-R22`).
- **K3's burden** (`K01-46`'s proportionate scoped tests and separate adjudication), added after review: for an advisory Lesson, the tests are `KP-17`'s re-resolution of each source, and the operator's decision is the adjudication. No candidate-specific test runs, and `KP-16` shows the source kinds.
- **Changed sources** (`K01-38`, `K01-37`), added after review: a Lesson whose paths or cited files changed since approval stays delivered, marked "may not apply" (`KP-R31`), unless its paths now match no file, which leaves it out of packs (`KP-27`). Only a withdrawn, missing or changed pinned source holds it (`KP-25`).

## Interfaces

**Candidates, not rules: the build may start from these.**

- **The overlay row**, beside `SET_STEERING_MODE`'s, read by the G3 service and client only: action `ADMIT_KNOWLEDGE_CLAIM`, catalog `W12`, origin `PROTECTED_G3`, class `OPERATOR_RESERVED`, owner label `ADC`, runtime `REFUSE_OR_HOLD_NO_G3`, direction `PRESERVING_OR_INCREASING`. The row keeps the conservative direction for a mixed action (`AOI-07.c`), and the endpoint derives each decision's direction from the `decision` leaf: `APPROVE` and `RELEASE` preserve or increase, and `REJECT`, `HOLD` and `STRIKE` reduce. The wire allows four owner labels and Knowledge isn't one, so `ADC` is a label stretch, as C3's is. It's a bridge until O-01 convergence. Each host needs a root reinstall for it.
- **The target's leaves:** `decision` (`APPROVE`, `RELEASE`, `REJECT`, `HOLD`, `STRIKE`), `subject_ref` (a batch reference or one version), `digest_ref` (`knowledge-batch:sha256:…`, or null for a named member), `member_count`, `flags_ref` (flag names joined with `/`, since a comma isn't in the wire's ref pattern, or null). In each member, `predecessor` is `basis_ref` the project ref, `basis_version` the member's `subject_ref`, and `source_epoch` `knowledge-policy:<policy_version>`. It never holds the store revision.
- **The adapter:** `g3_adapter`'s raise-only parts generalised to a binding table row `knowledge_decide`.
- **The read:** `GET /api/v1/lessons` and `GET /api/v1/lessons/{version}`, new routes and a contract minor version, since response objects are closed. Agent text is inert and labelled (`AOI-04.f`). The contract, C0 renewal and page are the web developer's.
- **The request:** `POST /api/v1/lessons/decision-requests`, on the checks `KP-23` names, and a contract bump. The CSP keeps `form-action 'none'`, and the page uses `fetch`.
- **The commands:** `aew knowledge nominate`, `list`, `show`, `approve`, `reject`, `hold`, `release`, `strike`, `import`, each with its surface-map entry and broker class. The site's copied line comes from a new allow-listed builder, not `readOnlyCommand`.
- **The worker's route:** a new evidence kind over the existing submit, plus a signal the next Lead commit folds. No new bridge operation or tool name for nominating, since the surface budget has about 95 bytes free. The kind is a carrier, not evidence: it isn't an expected output, and no gate counts it. `ingest_ref` refuses it, so it never enters a unit's evidence list, a bundle, raw-history search, `history show` or `history load`. The fold copies its text into the version, and the record names its id and hash under no key recall reads as evidence. The signal, the commit summary and any spool line carry ids and hashes only, and the fold removes the signal. The dashboard's evidence routes leave the kind out. So the version is the only route that serves a nomination's text, and `REJECT`, `HOLD` and `STRIKE` act in one place.
- **The record:** `aew/knowledge/lesson/v1`, ids `K-nnnn.vN`, one spelling everywhere: store, search, page, copied line and wire. Committed like the audit record: `write_record`, entries and a counter in one transaction.

## The gate

| Check | What it shows | Pass |
|---|---|---|
| **KP-Q01** | A pack regenerated from its pin is byte-identical, whatever has been approved or challenged since (`KP-29`) | identical |
| **KP-Q02** | An approval, challenge or hold after dispatch never refuses a launch (`KP-29`) | launch proceeds; a struck version's launch is refused, naming the version and the commands, and running them gives a pack without it |
| **KP-Q03** | A strike reaches stored packs and regeneration (`KP-29`) | with a pack stored before the strike, `context show` returns the marker on a hot and on an archived invocation; `context pack` reports the mismatch and names the version; a version loaded by `history load` also shows the marker |
| **KP-Q04** | A cut drops a whole Lesson (`KP-28`) | no condition trimmed; set equality holds on every full line |
| **KP-Q05** | A line over the line ceiling is refused at the door (`KP-13`) | `LINE_TOO_LONG` |
| **KP-Q06** | Rank is total (`KP-27`) | a many-file list ranks below a narrow one; ties resolve the same every run |
| **KP-Q07** | A Lesson matching no file at the pack's commit is left out (`KP-27`) | absent |
| **KP-Q08** | A Ticket with no paths gets only pathless Lessons (`KP-26`) | and the pack says so |
| **KP-Q09** | A pointer holds no claim (`KP-28`) | it carries the incomplete marker and handle, and opens through the search read |
| **KP-Q10** | The omitted count is right (`KP-28`) | it matches what the filter kept and the budgets dropped |
| **KP-Q11** | Independence (`KP-26.b`, `KP-30`) | reviewer and verifier packs and searches omit the listed Tickets and unapproved nominations; raw history still answers |
| **KP-Q12** | A challenge needs a real source (`KP-25`) | a bare file raises only a line; a source without intersecting scope doesn't hold; a source on record at release can't hold again; a pathless Lesson can be held by a typed source; ceilings bind a worker and the Lead |
| **KP-Q13** | Each flag in `KP-15` refuses a plain `APPROVE` or `RELEASE` batch | every flag, on both paths |
| **KP-Q14** | An agent's ordinary route can't pass an operator decision (`KP-24`) | a Lead session's `aew knowledge approve` is refused at the broker; an engine call with no `operator-tty` record is refused; on the G3 path nothing is recorded without a consumed approval. This doesn't test the same-UID residuals |
| **KP-Q15** | A waiting Lesson never stops the steering loop (`KP-19`) | the loop continues |
| **KP-Q16** | The switch (`KP-34`) | off: no section, and search works; an absent key reads `disabled`; `aew init` writes `enabled`; a declined offer stays `disabled`; search off gives full Lessons only |
| **KP-Q17** | A digest that differs at consume is refused (`KP-22`) | `BATCH_DIGEST_MISMATCH`, no record |
| **KP-Q18** | On `APPROVE` or `RELEASE`, any flag but the push flag is refused at consume, even with a valid PIN (`KP-22`) | `BATCH_MEMBER_FLAGGED`, no record |
| **KP-Q19** | On `APPROVE` or `RELEASE`, a moved version or source is refused, and an unrelated commit isn't (`KP-22`) | `BATCH_MOVED`; a challenge after the tick refuses at request and at consume; a named member's new flag refuses its set; the unrelated commit leaves the batch valid |
| **KP-Q20** | Sets (`KP-15.a`, `KP-15.c`) | 8 named members pass; a ninth is refused; a K3 candidate in an `APPROVE` or `RELEASE` set of more than one is refused, and a `HOLD`, `REJECT` or `STRIKE` that includes one passes; a `STRIKE` of a plain batch is refused; `REJECT` of an approved Lesson is refused |
| **KP-Q21** | A forged click (`KP-23`) | no session or a wrong or missing origin raises nothing; a valid one raises a prompt, and with no PIN records nothing |
| **KP-Q22** | The click grants nothing (`KP-23`) | the route writes no Knowledge record; a G3-path decision is recorded only after a consumed approval |
| **KP-Q23** | Prompts don't stack (`KP-23`) | a second request while one is pending is `REQUEST_ALREADY_PENDING` |
| **KP-Q24** | Where G3 doesn't count (`KP-20`, `KP-24`) | the page offers the copied command and says why; the record is labelled interim |
| **KP-Q25** | A G3 outage holds (`KP-20`) | it never moves to the typed code. On a G3 host with no endpoint, the route answers `ENDPOINT_NOT_RUNNING`, and the pasted command refuses and takes no code. A service that doesn't know the action holds and names the reinstall |
| **KP-Q26** | Agent text on the page is inert, and never reaches the confirmer (`KP-21`) | a planted script doesn't run; rendered lines contain typed leaves only |
| **KP-Q27** | A record planted in a worktree's `.aew` is neither served nor integrated | absent |
| **KP-Q28** | A set fails partway (`KP-22.a`) | a failed third consume, or a crash before the commit, records nothing; a new tick needs a new approval and records the whole set |
| **KP-Q29** | The wait outlives the request (`KP-23.a`) | the route's connection closing leaves the approval live, and a PIN records the decision; after an endpoint restart a PIN records nothing, and the page shows client gone |
| **KP-Q30** | A pending batch stops nothing (`KP-19`) | a raise and a capability change each proceed while a batch is pending; a second batch is `REQUEST_ALREADY_PENDING` |
| **KP-Q31** | A nomination's text has one route (`KP-18`, `KP-30`) | a sentinel nominated through evidence, on a unit then archived, is absent from raw search, `history show`, `history load` and the dashboard's evidence routes; after a strike, `knowledge show` shows a marker and a rebuilt index finds nothing; a run that only nominated doesn't read as ended with evidence |
| **KP-Q32** | A source outside the submitter's read rights (`KP-13`) | `SOURCE_UNRESOLVED`, identical to an unknown id |
| **KP-Q33** | Failure stays quiet (`KP-06`, `KP-34`) | a corrupt store or index: launch proceeds with a labelled line, and search says unavailable |
| **KP-Q34** | `REJECT` (`KP-18`) | it leaves search, reads by id, and the door tells a re-nominator |
| **KP-Q35** | The list (`KP-16`) | it shows every field `KP-16` names |
| **KP-Q36** | The push flag (`KP-15.b`) | three members that each fit alone and together push an approved Lesson to Count are refused at request, naming those ranked above it; a pathless Lesson or a move from Full to Pointer sets no flag |
| **KP-Q37** | Protective acts aren't stalled (`KP-22`) | a `HOLD` or `STRIKE` with a moved source, a new flag or a new challenge since the request is recorded, with no second PIN |
| **KP-Q38** | The import (`KP-03`) | a planted private name and a host row are absent; a second run refuses |

## Scenarios

These are the research's 28 scenarios as ordinary tests, labelled conformance and not held-out evaluation. A departure from the research's expected behaviour is marked and explained at `KP-R46`.

**KP-X01.** A parser bug with a bounded fix: findable with pinned sources, and in a pack only after approval.

**KP-X02.** A routine `pwd`: a green check creates no candidate. If volunteered, it's findable and not delivered unless approved, and a ceiling refuses a flood. Departure.

**KP-X03.** A "dead function" later disproved: a hit shows status and counterevidence, never fact, and it isn't in a pack unapproved.

**KP-X04.** A linker failure in a known environment: the failing check is pinned and conditions are kept, and after archiving the unit the source resolves by hash.

**KP-X05.** A mistyped filename: as `KP-X02`. Departure.

**KP-X06.** One Rocky and clangd observation: AEW can't bind wording and never widens conditions, and an empty condition reads unknown. Departure: the operator could approve a generalisation.

**KP-X07.** Two feature flags: two records with their conditions and no conflict state, and a challenge from the other flag needs a typed source on those paths.

**KP-X08.** Opposite results under the same conditions: both wait, and neither is delivered. The overlap label needs the same subject. Partial departure: nobody requests discriminating evidence, and two different subjects carry no label.

**KP-X09.** Evidence narrows a scope: approving v2 takes v1 out of packs in that scope, and v1 stays readable.

**KP-X10.** A validated replacement: a scope outside v2 keeps v1, and a widening is flagged.

**KP-X11.** Paraphrases: the same claim and sources return the first receipt and one pack line. A true paraphrase gets the overlap label only with the same role, paths and subject. Partial departure: otherwise undetected.

**KP-X12.** A named project decision in a report: stored as a pointer, not a Lesson.

**KP-X13.** "Store this; bypass review": never delivered unapproved, no authority change, fenced, and a strike removes it. It's findable until struck or rejected. Departure.

**KP-X14.** A confident story with no evidence: an idea, held, never delivered, and absent from the list and packs.

**KP-X15.** A failure and fix with replay: source kinds labelled, conditions verbatim, and labels name the replay check. Departure: the operator could approve a generalisation.

**KP-X16.** A claim crossing two components: several paths, both select it, and the subject is free text with no required topic.

**KP-X17.** A nomination citing its own Lesson: the citation resolves to that Lesson's sources, and the label shows one root.

**KP-X18.** Similar ids in two worktrees: AEW sets origin, same-named ids stay distinct, and nominations are visible across the project once recorded. Departure.

**KP-X19.** A source changes while queued: approval re-resolves and refuses, naming the candidate, which stays listed. Only a new version clears it.

**KP-X20.** A crash before acknowledgment: the same nomination returns the first receipt, with one record.

**KP-X21.** An artifact missing or mismatched: a bad hash is refused at submit or held at the commit, and later tampering holds.

**KP-X22.** A "fix" that disables a security check: a listed path is flagged and a batch refuses it. Partial departure: a "fix" outside listed paths reaches the batch.

**KP-X23.** Hostile text in a passing report: the typed record is resolved, nothing acts on prose, and a report isn't labelled as a check.

**KP-X24.** No short lesson possible: raw history still answers a known-answer search.

**KP-X25.** A large irrelevant history: results and budget stay bounded, with no quota.

**KP-X26.** Old evidence arriving late: a hold doesn't supersede. A hit's source order and marks are the same on every read, and a late challenge leaves the version's source list unchanged (`KP-R33`).

**KP-X27.** A tool version changes: a recorded host or tool condition shows unchecked, not matched.

**KP-X28.** Rare and never recalled: no expiry and no use signal, and status is unchanged over any period.

## Rulings

Each names the inventory items it answers (the designer's inventory of 126 checked questions). The designer's, under the operator's page.

**KP-R01.** `k01-increment-vehicle`, `a13-companions-missing`: this position is the increment. A-13's candidate schema, examples and fixture catalog weren't recovered, so tests are written fresh from its section 9 and `K01-25`.

**KP-R02.** `operator-decision-command-custody`, `w12-w14-wire`, `judgment-surface-and-attention`: overtaken by the operator's yes. `W12` is G3-origin, not an owner decision with no PIN. `W14` stays untyped until K1 templates need it. Waiting Lessons show a badge and no desktop notification, in keeping with `KP-04`.

**KP-R03.** `k-dec-06-unowned-wire`, `lesson-tool-transport-owner`: this increment owns the wire, in-process typed schemas over CLI and bridge, with D-01 unchanged and recall section 29's list as conformance. The dashboard's routes are its local contract, and converge with D-01's batch. No service principal, capture worker or receipt kind is needed.

**KP-R04.** `nomination-door`: nominate any time, with an optional closeout field beside G4's. `NO_CANDIDATE` is success. A worker submits through evidence and commits nothing; the Lead uses a relayed command. The pack names the door.

**KP-R05.** `lesson-support-roots-and-required-fields`: the page overtakes a refusal for no root: it becomes an idea (`KP-12`). A wasted round cites invocation or Ticket event ids. An operator decision record is a valid root. It doesn't count as independent support for the operator's own approval (`K01-43`), and a Lesson with other roots shows "your own decision is a root" on the list. Role-attested roots are labelled and never upgrade.

**KP-R06.** `root-survival-on-archive`: the fold pins roots in the commit, and the audit fails loudly if a pinned root is missing.

**KP-R07.** `class-predicate`: structural. With no templates, everything agent-written is K2. K3 has one marker in this increment: `KP-15`'s first flag, a sensitive path. AEW's shipped list covers authority, security, containment and credential code. Applicability wider than the project has no field in `KP-R22`, because no Lesson reaches another project (`K-DEC-04`), and sharing groups add the field and the marker together. A broad candidate is flagged and stays K2, so it can share a set of 8 (`KP-R48`). The operator can approve any candidate alone, and no reclassification is recorded. Host code can't detect a mixed claim, so the operator holds one, and splitting is the nominator's act.

**KP-R08.** `admission-policy-home`: in code with a `policy_version` constant, approved through this position, and a change needs a release. Knobs move to settings only when a need appears.

**KP-R09.** `challenger-required`: none while the operator judges. AEW resolves each root, and the list shows the rest.

**KP-R10.** `instruction-text-validator`: structural only: a closed schema, no authority fields, prose fenced and labelled at serving. No natural-language gate, since it would catch little and give false comfort.

**KP-R11.** `structural-failure-outcome`: refuse at the door what a retry can fix (`KP-13`), and hold at the fold what changed after (`KP-14`). Only the operator rejects.

**KP-R12.** `rejected-and-poisoned-retention`: the existing redaction and scan at the door. All else is kept, and a miss is a stated residual on the page.

**KP-R13.** `duplicate-rule-without-model`: the fingerprint is SHA-256 of the canonical JSON of claim, applicability and roots. Root count is distinct canonical ids.

**KP-R14.** `numeric-limits`: one policy constant per limit, naming its source and type. Each value below is a tripwire, the designer's judgment of 2026-11-08 and not a measurement. A change is a new `policy_version` (`KP-R08`). `KP-32` also counts refusals per ceiling, and the values are revisited after first use.
- **A rendered full unit:** at most half the Full budget, 700 characters at the start, so two full Lessons always fit. In a rough sample of 49 real lessons, 48 were under this, without counterevidence fields.
- **A rendered pointer:** at most one eighth of the Pointer budget, 200 characters at the start, so eight pointers always fit.
- **Broad:** more than 100 tracked files. A module directory stays out (43 to 71 files, sampled) and a whole tree is flagged (300 or more).
- **A nomination:** at most 4,000 characters and 8 sources. At most 5 per work unit, and 10 per Lead generation.
- **Challenges:** at most 3 per work unit, fewer than the Lessons delivered in full, so one run can't empty that part of a pack. At most 5 per Lead generation.
- **Disclosure:** the secret scan (`SECRET_SCAN_HIT`).
- **Pending:** at most 20 attention items, from ADR-0013. An overflow shows a count and never a default.
- The one-time import (`KP-03`) isn't a nomination and counts against none of these.

**KP-R15.** `checkable-sort-mechanism`: the required field, plus a reject reason "should be a check" that files a row. It stays judgment, with no extra queue.

**KP-R16.** `conflict-detection-at-admission`: the mechanical overlap label only (`KP-16`).

**KP-R17.** `held-candidate-discoverability`: workers get held candidates on explicit request, labelled and never in packs (`KP-36`).

**KP-R18.** `vocabulary-and-initial-state`, `state-machine-and-fold`: one transition table in code with one owner: relation, from-states, actor class, dimension set. The first event is `held_active`, which projects as candidate. In `KP-18`, `KP-22`, `KP-26.a` and the list's status, held means a later hold, by the operator's `HOLD` or by host policy (`KP-14`, `KP-R19`). In `KP-07`, `KP-30`, `KP-36`, `KP-R17` and `KP-X14`, held is the reach: stored and findable, not delivered. A held candidate stays listed, marked, and can't take `APPROVE`; `RELEASE` approves it, under the flag rules. Rejected is terminal per version.

**KP-R19.** `retraction-who-and-direction`: tightened from the inventory's candidate. Host policy may hold on a critical event or a moved source. The Lead challenges like any agent, under `KP-25`, because the gaming review found cheap silencing. Only the operator admits, releases, rejects or strikes.

**KP-R20.** `record-schema-and-ids`: the five kinds join the enum at once. Schemas: `lesson`, `idea`, `reference` and `knowledge-disposition`. `idea` is a sixth, separately declared kind with no sources (`KP-07`), so the inventory's "hypothesis as a held lesson" is overtaken. `KP-12`'s pointer is a `reference`. Both take ids and versions, so `STRIKE` reaches them.

**KP-R21.** `versioning-rules`: any change to claim, applicability, exclusions or roots is a new version with its own status. A different proposition is a new id with refines or supersedes, whose scope is required.

**KP-R22.** `applicability-schema`: closed fields role, paths, host and free conditions. AEW never widens them. The inventory's "unknown blocks default serving" is overtaken: conditions render verbatim and a host or tool condition shows unchecked (`KP-28`).

**KP-R23.** `lesson-selection-rule`, `lesson-compact-shape`: `KP-26` to `KP-28`, one record for both routes, with a set-equality check before render. That check runs at the pin. Versions are immutable and the launch's pack guard holds the bytes to the pin, so this is `K01-49`'s final check. A worked example with five Lessons is a fixture.

**KP-R24.** `serving-policy-table`, `f35-first-slice-scope`, `f35-no-default-changes-line`: only an admitted-Lessons section, on all dispatchable worker cards, with the per-role table as archetype data. F35's other parts stay rows, and explicit orientation stays opt-in.

**KP-R25.** `lead-lesson-delivery`: the Lead has no pack. It finds Lead-role Lessons by search, and its resume shows counts of pending and of Lead-role Lessons.

**KP-R26.** `verifier-plan`: the pack is unchanged, and lookup may read the plan. Read KDR as "the same-Ticket rule hides no plan", and correct F35's line.

**KP-R27.** `serving-currentness-witness`, `serving-recheck-vs-launch-pack`: within one store, the witness is the same transaction's hash, chain position and expected revision. No time-to-live. Served text carries approval date and revision.

**KP-R28.** `receipts-and-placement`: no new kind. `inv.pack.sources` with exact version and revision is the record, launch acknowledgment is the boundary, and absent is `NOT_ESTABLISHED`. No attention claim.

**KP-R29.** `withdrawal-impact-and-recipients`: on a hold or withdrawal, delivery stops and one line reaches the Lead naming the version and the packs that carried it. No acceptance path treats a Lesson as a premise until that row lands (`KP-B5`).

**KP-R30.** `challenge-and-protective-hold-rule`: `KP-25`, narrowed from the inventory's candidate by the gaming review.

**KP-R31.** `revalidation-triggers`: a changed path shows "may not apply" at read time, with no automatic reassessment. Count how many get flagged before adding holds.

**KP-R32.** `h-activation-and-qualified`, `search-default-on`, `lead-read-route`, `lead-relay-fails-contained`: `H` goes on through ordinary tests, with no per-host record, because it adds no protected effect. The Lead's read is a relayed command (`RELAYED_READS`, the lock-free committed path). A search says which it is, as far as disclosure allows: no match over the named coverage, source unavailable, or not established (`K01-18`). A filtered reviewer gets no match, never withheld. Qualified, for `L` and `H` (`K01-24`, A-13:44), means this position's gate and scenarios pass (`KP-35`). `K01-24`'s actual-host forgery tests bind positive K1, which isn't selected. This is a reading, not a change. On by default works as in `KP-34` for `recall.raw_history_search`: `aew init` writes `explicit`, an absent key reads `off`, and an existing project gets the shared switch offer's row.

**KP-R33.** `KP-X26`'s source order: a hit lists a version's sources in the order the fold pinned them, which is stable. It shows each with its own mark: the commit it was evaluated at, or else the control revision that recorded it. Nothing sorts them by age, because a commit and a control revision can't be compared (`AOI-04.d`), and no clock enters. A later source isn't in that list: it comes as a challenge or a new version, and it never supersedes by arriving late. This closes the page's open scenario.

**KP-R34.** `agents-told`: `KP-31`, with one guide line for the Lead and one preamble line per offered operation.

**KP-R35.** `worker-bridge-op-shape`, `not-model-visible-and-f15-3-text`, `operation-names`, `search-index-admitted-records`: one `history search` over all kinds with a kind on each hit; `history.read` in `ROLE_OPERATIONS`, with its surface-map entry. Versions index as `K-nnnn.vN`, dispositions aren't indexed, and the substrate version bumps. The worker row's PR changes the guard, refusal text and F15.3's words.

**KP-R36.** `codex-parity`: a capability declaration plus a test, and any Codex gap is a register row. A shell-routed read should need nothing harness-specific, which the build confirms by reading.

**KP-R37.** `role-matrix-never-written`: implementer, planner, researcher and frontier advisor: `EXPLICIT_LOOKUP`, `CONTEXT_ROUTING`. Reviewer and verifier: the same with the filter. Investigator and Lead: plus `INVESTIGATION_HISTORY`. Operator tooling: `DEBUG_EVALUATION`. `AUTOMATIC_DISCOVERY`: none. The first `H` slice is `EXPLICIT_LOOKUP` only, with the mode from the bridge's role.

**KP-R38.** `investigation-mode-for-assessors`: not inside an assessor invocation. Prose comes through the Lead or an investigator, as a record.

**KP-R39.** `filter-scope-and-reasoning`, `filter-mechanics`, `filter-guard-or-boundary`, `filter-over-lessons`: `KP-26.b`, one list both routes derive from, adding AIR-53's fields, with `implementation_report` hidden as a whole kind. It's applied in the query, with new columns under the substrate version, and tested by sentinels through the bridge route. Lead-loaded records stay, labelled deliberate.

**KP-R40.** `knowledge-on-by-default-meaning`, `l-switch-definition`, `reversible-default-risk`: `KP-34`. The switch is legality-affecting, with a switch-offer row. Keep the record of which Lesson reached which invocation, since that can't be added later.

**KP-R41.** `existing-project-migration`: an optional key, where absent means empty, and no migration step. Test that an old project opens untouched and an old engine refuses a widened manifest.

**KP-R42.** `host-scoped-lesson-meaning`: a host condition narrows applicability only, and sharing waits for groups. Executable host facts sort toward checks and the host settings layer first.

**KP-R43.** `e176-promotion-path`: no promotion path. A Lead's lesson nominates through the same door with a real root, or stays an idea. E176 needs nothing from Knowledge.

**KP-R44.** `seed-and-first-use`, `gates-own-measurement-or-waived`, `use-observation-has-no-owner`: `KP-03` and `KP-32`. Counts are local per project, hold no query text, and are telemetry, not APP. F21's and F35's stop-go lines become these observations, labelled non-causal.

**KP-R45.** `adversarial-corpus-gate`, `stop-conditions-have-no-detector`, `conformance-test-map`: `KP-X01` to `KP-X28` and the gate are ordinary fixtures, with `KP-33` as the stop list. Each PR's description maps its clauses to these tests, and a part served only partly says what isn't served.

**KP-R46.** The departures from the research, accepted on the operator's page. `KP-X02`, `KP-X05` and `KP-X13`: a volunteered note or a "bypass review" instruction stays findable, where the research expects none or a rejection, because search is cheap and a strike exists. `KP-X06` and `KP-X15`: the operator can approve a generalisation the research would hold. `KP-X08`, `KP-X11` and `KP-X22`: limits that need a model or an expert, stated as residuals. `KP-X18`: visibility, changed in `KP-36`.

**KP-R47.** `pending-lessons-stop-run`: `KP-19`, with a dated ADR note.

**KP-R48.** Flagged sets of up to 8 are this position's relaxation of the page's draft 5 wording, told to the operator before their yes. Twenty flagged items at one PIN each would be the chore `KP-08` forbids. The cost is that a member shares its set's yes, which is why each is shown by name and a sensitive path goes alone.

**KP-R49.** How the typed route and G3 stand. The operator, on accepting `KP-36`'s typed-route row, said G3 "is basically done mechanically", so that even a G3 requirement is "wiring", not waiting. It matches main at `e951c207`: the service, confirmer, client, `g3_adapter` and the owner's consume are merged (`#386`, `#389`). What's left is this increment's wiring: the overlay row, the adapter past its one binding, the endpoint's own wait and record, and each host's reinstall, plus `KP-B4`'s auto-start. So the typed route is a short bridge on a contained Linux host, and lasting only where G3 can't count. The designer recommends placing click plus PIN straight after Lessons delivered, to keep that bridge short. Placing is the operator's.

## Backlog

**KP-B1.** The first slice's filing, for the Lead, under "selected; not placed": `F21` split into `L` and a Case-and-capture row; `E185` and the register's knowledge system row rewritten to the relayed read; the on-by-default row; the switch offer's row.

**KP-B2.** The rule in shadow against the operator's recorded decisions (`KP-10`).

**KP-B3.** The rest of F35, sharing groups, the host settings layer, Cases and capture.

**KP-B4.** Endpoint and dashboard auto-start, on which click plus PIN depends.

**KP-B5.** `K01-10`(a), `K01-22` and `K01-16`'s acceptance half, `K01-34`, `K01-35`(a): accepted-premise impact.

**KP-B6.** Text fixes found on the way: `projection.py:510-512` tells the Lead `.aew/` is read-only while its harness directory is a writable bind; a test that a planted `AGENTS.md` isn't obeyed.

## Not covered

- **Sizes and placement:** the page's §8, and placing is the operator's.
- **Answered elsewhere or later, needing no ruling here:** `k-dec-01-gap-03-issuer-role` and `k2-judge-is-the-operator` (`KP-R02`, the operator's page); `l-needs-no-service-principal` (`KP-R03`); `service-credential-for-c`, `capture-runner-and-triggers`, `source-class-derivation`, `k01-24-on-the-actual-host`, `forge-route-linux`, `k0-durable-or-pointer`, `commit-closure-absent`, `comparative-gates-have-no-number`, `c-first-source-class-and-replay` (Cases, unselected); `l-activation-conditions` (this position's acceptance list, with `KP-35`); `agent-use-acceptance-gate`, `operator-picture-vs-adopted-design`, `l-ahead-of-the-adopted-gate`, `k-dec-03-rollout-terms`, `lessons-default-served-in-packs`, `k2-judgment-burden-or-class-rule`, `operator-read-correct-and-strike`, `workers-read-frozen-under-sys06` (`KP-36`, `KP-35`, `KP-18` and the page's decisions); `source-class-meaning`, `distiller-model-required`, `no-operator-response`, `pack-serving-is-l-not-e`, `expiry`, `worker-route-mechanism`, `arm-b-corpus-and-hit-shape`, `s32-settled-items`, `trust-model`, `which-text-governs`, `gates-g1-g4-w1-w5-bearing`, `first-use-v01-measure-nothing`, `feedback-and-lead-use-as-evidence`, `benefit-stage-no-producer`, `adr13-qualification`, `ranking-and-left-to-evidence`, `worktrees-and-integration` (settled as the inventory records, and this position changes none of them); `e-activation`, `app-activation` (held and off by the operator); `k-dec-04-sharing-groups`, `host-settings-layer-never-designed` (`KP-B3`); `f42-3-vs-g4-context-feedback`, `l-placement`, `f21-row-split`, `text-waiting-on-frozen-f19`, `k01-rows-owed-without-specs`, `where-records-go-and-how-committed`, `adr-and-design-placement-text-stale`, `a13-status-banner-stale`, `slice-sizes`, `owed-rows-status-ledger` (register and pointer notes, `KP-B1`, for the Lead's filing).
- **Measurement left to first use:** `no-model-retrieval-check`, `pack-budget-and-knob-defaults`, `tool-result-budgets`, `s32-latency`, `adr13-probe-numbers-stale`. `KP-32` carries the first; `KP-28` and `KP-R14` the budgets; the rest are logged in the storage and search PRs, with no number set now.
- **Benefit:** nothing here shows Lessons help.

## Changes

- Revision 1: the first text, from `OPERATOR-PAGE.md` and the working rules beside it, answering its independent review (19 findings), that review's verification (6 more), a critic's pass (8) and a quick check, saved as `REVIEW-r1.md`.
