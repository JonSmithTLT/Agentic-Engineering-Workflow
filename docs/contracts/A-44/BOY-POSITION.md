<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-44
source: 30-stages/STG-20-blocked-on-you/adopted/boy-r2.1/BOY-POSITION.md
source-sha256: dac0af44189be147b3e2243ab730d8c19f35dec79034fd418b024fc05bed2118
edits-sha256: 1281a691bdba757900d48dc6885a95b3ab216944557cf61cbed3099af0b299a2
-->

# Blocked-on-you: whenever AEW waits on the operator, it says so (PROPOSED, revision 2.1)

**Namespace:** `BOY-`
**Status:** proposed.
- It amends nothing adopted until the operator adopts it, and no adopted byte changes.
- **What adoption would add, each the operator's to confirm.** FLAGS is the operator's flags decision of 2026-10-25 (`00-governance/decisions/2026-10-25-operator-S12-4-flags-batch-1.md`):
  - an A-06 requirement for the Lead's ask door (`BOY-08`), under FLAGS' flag 5 (FLAGS:23; Q3);
  - A-12 requirements for D-01's three gaps, under FLAGS' flag 2 (FLAGS:20; Q2).
- **For the operator at adoption:** ten questions, under "Rulings". Two of them are asked only with S7's data.
**Authority:** the operator's decision of 2026-10-28 (`00-governance/decisions/2026-10-28-operator-blocked-on-you-designed-now.md`): blocked-on-you, for approvals and agents' questions alike, is designed now as its own piece beside the wire track, with the approvals view as its first section.
**Threat model:** the operator decision of 2026-10-19 (`00-governance/decisions/2026-10-19-operator-G3-threat-model.md`): malicious code running as the operator is out of scope. The security depth reset of 2026-10-24 narrows it (`00-governance/decisions/2026-10-24-operator-security-depth-reset.md`): only agent-reachable findings count. Here, what is at stake is that no item decides, answers or approves, and that no agent's text sets an item's tier.
**Research consulted:** every hit of `tools/research_index.py lookup`, a superset of the design brief's header.
- **For `AOI-06.b`, the other `AOI-`, `CNI-`, `R01-` and `D01-WR-` IDs, `AEW-FR-28`, `AEW-FR-29` and `MSN-07`:** none.
- **For `R-DEC-03` and the register's U1:** three studies each.
  - The external-workflow study (`external-workflow-2026-10-05`): its synthesis §4 item 1 puts health thresholds in execution policy, and T follows it (`BOY-09.c`).
  - The agent-effectiveness study (`agent-effectiveness-2026-10-09`): its synthesis §1 finding 3 and §11 item 2 make reading a harness's session database the operator's decision on reading and retention, and the fallback follows it (`BOY-R08`, Q10).
  - Its public synthesis (`agent-effectiveness-and-model-leverage-synthesis-2026-10-09`): its §11 item 2 repeats that decision. Its report that the Lead spent 61 percent of wall time blocked in harness wait (§1, §5) bears out the idle source's exclusion of a harness_wait in flight (`BOY-09.a`).
- **For the register's F20.7:** the same two agent-effectiveness studies, with the same finding (Q10). Neither bears on the long poll itself (`BOY-B4`).
**Files:** this file. Its inputs are under `inputs/`:
- the design brief (brief), which this revision follows;
- the fact map (FM), the approvals-view draft, and the draft's independent check (CHK).

G3P is A-37's `30-stages/STG-03-G3-trusted-origin/adopted/g3-r7.1/G3-PROFILE.md`. AEW code is cited at `main` 21ea8674.

## What the adopted text already decides

- **Agents may ask, asking grants nothing, and agent attention is bounded across the root lineage** (`AOI-06.b`, `CNI-04.a`, `D01-WR-09`, `D01-WR-19`; the case `IF-26`).
- **A pending decision has a supported way to find and answer it,** and a rendering is not an answer (`AOI-06.a`, `AOI-06.d`, `OI-FR-08`, `CNI-08.b`, `RX01-24`, `MSN-07`).
- **Nothing that notifies approves** (`AOI-01.c`, `AOI-08.b`). A-32's U06 `ACK_NOTICE` is `MANUAL_LOCAL`. Agent text is inert on every surface, notifications included (`AOI-04.f`). Delivery technology is the implementation's (`AOI-08.e`).
- **Unknown is never "nothing pending"** (A-10 §4.1; `AOI-05.b`), recency shows (`AEW-FR-29.d`), and silence proves nothing (`CNI-08.e`).
- **Escalation:** time-critical blockers are prompt, routine matters are consolidated, and decisions are briefed with options and the cost of delay (`AEW-FR-28.b`, `AEW-FR-28.c`, `AEW-FR-28.d`, `CNI-08.c`, `R01-35`).
- **Idleness:** a heuristic is only `POSSIBLE_STALL` (`R01-15`), nothing destructive rests on it (`R01-20`), and waiting runs in host code with no idle tokens (`R01-26`, `MSN-07`). The decision on `R-DEC-03` (2026-10-25) built heartbeats, the notifier and live usage; stall detection enters only by its own selection.
- **D-01 0.3.4's attention read** (A-25) is GET-only and no-store, with owner-derived lanes and priorities, a CNI source owner and inert narrative. It has no raised-at field, no where-to-answer relation, and no category for a pending G3 approval (FM:59-63, :83).
- **G3** (A-37):
  - a client reads its own approval by ref (`G3-07`);
  - a pending approval expires within at most 10 minutes (`G3-02`, G3P:79);
  - a pending approval does not survive a restart (`G3-11`, G3P:159);
  - consent is valid for at most 15 minutes (`G3-06`);
  - no client or agent string is shown as prose (`G3-03`);
  - G3 is not established until CS-4 contains the Lead (`G3-12`).

  A-37 leaves notification out, and says the website shows waiting through `ORIGIN_PENDING` and `HELD` (G3P:213-214, read in `BOY-R01`).
- **The mission** (A-42): held questions are answered through G3 and the notifier tells the operator (`MSN-07`); the preflight lists the notifier's state (`MSN-03`); detached runs are notified (`MSN-06.a`).
- **Outage reads:** material holds and required operator decisions stay discoverable "through applicable canonical owners" and through authorized read-only outage paths (`CNI-08.d`, A-09:137).

**What is missing:**
- the build: nearly every rule above is a GAP at pack a866be06, and closes through hold groups 2, 9, 10, 12 and 15, the mission build and the G3 build (FM:20, :38);
- a way for an agent to raise an item: no O-01 0.9 action does it, and no A-06 clause gives the Lead one (FM:23, :70-71);
- a record of a waiting approval the site can read: at `main` the CLI holds the approval before it submits, so no `ORIGIN_PENDING` exists during the wait (CHK:28-30);
- detection of a Lead left idle after asking (FM:28, :308);
- a site alert while its tab is hidden, and a default desktop notifier (FM:422, :621);
- one tier mapping, and a rule for when an item closes (FM:30).

## The parts

| Part | What it is | Written by | Read by |
|---|---|---|---|
| The approval record | one record per approval that a G3 client AEW ships starts, per host, in the operator's state directory (`BOY-05.a`); at `main` that client is `aew g3 request` alone | the client that started it only, which also prunes it | the attention module, read-only |
| The question record | the Lead's open question per root lineage, and its superseded ones; CNI-owned, committed in AEW's store (`BOY-08.a`) | the Lead broker only, from the ask door | the attention module, the Lead's status, O-02's reader |
| The steering requests | the Lead's open requests for a raise or a confirmation (SQ-n), in committed control state (FM:182-185; `BOY-08.e`) | the engine, from the Lead's `steering` tool, and its close on the door's withdraw (`BOY-08.f`) | the attention module, O-02's reader |
| The loop record and the broker's beat | loop.json and the beat, host records under `.aew/local`; the beat gains two fields (`BOY-09.a`) | the steering loop, and the Lead broker | the attention module |
| An observation | an item AEW raises itself from a loop stop or the broker's call times (`BOY-09`) | AEW's host code | the attention module |
| The attention module | one table that derives each item's tier, lane, order and occurrence key (`BOY-02`) | AEW's host code | every consumer below |
| The overview items | the waiting items in contract 0.1.3's attention list, sorted first (S1) | the dashboard backend, GET-only | the site, `aew status` |
| The /waiting read | `GET /api/v1/waiting` in contract 0.1.4 (S2) | the dashboard backend, GET-only | the site's hidden-tab signal |
| The hidden-tab signal | the title count, the second icon and the opt-in browser notification (S2w) | the web developer's page | the operator |
| The desktop notifier | `aew notify desktop`, the default `notify.command` (S3) | AEW's host code, run by the operator endpoint | the operator's desktop |
| The confirmer | unchanged: it notifies G3 approvals and takes the decision | A-37's root-owned install (`G3-14`) | the operator |

## Rules

**BOY-00. Precondition: nothing in this position decides, answers or approves.** An approval is decided only in AEW approvals, with the PIN (`AOI-01.c`, `AOI-08.b`, `G3-13`).
- No item, count, icon or notification is an answer, an acknowledgement or a consent.
- Every item points at a home that already exists (`BOY-06`). This position designs no new place to answer (STG-20's `STAGE.md`).

**BOY-01. Whenever an AEW record says the operator is awaited, exactly one item says what waits, who asked, since when and where to answer.** It shows on the site and in `aew status` with the site stopped (`AOI-06.a`, `AOI-06.d`, `OI-FR-08`, `CNI-08.b`).
- **On the desktop,** where a notifier is available, it is announced as `BOY-11` and `BOY-12.b` partition it: a G3 approval by the confirmer's own notification, any other blocked-on-you item by AEW's notification of its own, and an attention item by its combined notification. FYI items are not announced.
- **The sources:** a G3 approval's client record (`BOY-05`), the Lead's open question (`BOY-08`), the Lead's open steering requests (`BOY-08.e`), AEW's observations (`BOY-09`), and the existing alert events.
- **"Since when"** is the source's own time: an approval's `started_at`, a question's `raised_at`, a request's `at`. It is never the time of the read.
- **"Who asked"** is the owner-derived actor. An approval's starter role is labelled as the client's own claim.

**BOY-02. One attention module derives each item's tier, lane, order and occurrence key, and every consumer reads it from there** (`AOI-10.e`).
- **The consumers:** /overview, /waiting, `aew status`, the desktop notifier and the browser notification.
- **No consumer classifies again.** The page renders the backend's tier (the web developer's reply, FM:485).
- **An item's occurrence key changes with each new need:** a question's record id, an SQ-n, an approval's ref, an observation's key (`BOY-09.b`), and for an existing alert event its id with its kind and `first_seen_at`, never contract 0.1.3's id alone. So a dismissal bound to it (`BOY-10`) never hides a new need.

**BOY-02.a** `aew status` prints the same items, from the same module, with the dashboard stopped (`OI-FR-08`).

**BOY-03. Tier, lane, priority and order come from the source record's class through one table, never from agent text or the category it chose** (`AOI-06.b`, `D01-WR-09`, `D01-WR-19`).

**BOY-03.a** The table has three tiers, and each source class sits in one. Each approval state of `BOY-05.b` sits in one too.
- **Blocked-on-you:**
  - a G3 approval in `BOY-05.b`'s one blocked-on-you state;
  - a WIS decision need, once built;
  - a mission's held question or reserved decision, once built (`MSN-07`, answered through G3).
- **Attention ("your turn"):**
  - every agent-lane item: the Lead's questions, its open steering requests, AEW's observations, and later a pending permission ask or form in the Lead's TUI, as a service observation;
  - owner-normal needs;
  - the existing alert events;
  - a G3 approval whose state is unknown (`BOY-05.b`). It shows as "?".
- **FYI:**
  - the end of a Lead generation;
  - each approval state that `BOY-05.b` marks FYI;
  - an item whose asker has ended;
  - a reserved row for done events, which only the operator would add.
- **Not items:** "G3 is not on this host" and the nothing-waiting sentence are a source's outcome and coverage (`BOY-04`), never a count.

**BOY-03.b** Each tier behaves one way, and an agent item is never in an approval's tier.
- **Blocked-on-you** is counted in the title, marked by the icon, sorted first, and gets its own desktop notification: AEW's, except a G3 approval's, which the confirmer serves (`BOY-11`).
- **Attention** is counted, and gets one combined desktop notification per combining key: the item's root lineage where it has one, otherwise its source class. The existing alert events carry no root lineage, and an owner-normal need may carry none. A G3 approval in this tier gets no AEW notification (`BOY-11`).
- **FYI** shows on the site only.
- **Order:** waiting items come first, so the six-row Overview cannot hide them, and owner items come before agent items.
- **No tier makes a sound,** and no agent item is worded or styled as an approval.

**BOY-04. Unknown, unavailable, unsupported and signed-out states show as themselves, with their read time and coverage, never as nothing pending** (A-10 §4.1, `AOI-05.b`, `AEW-FR-29.d`).
- Each source reports its own outcome and read time.
- A source that fails never yields a count of 0, and an empty list states what it covers.

**BOY-04.a** Every item that waits on the operator names its source record: a committed store record, or a host record outside the store (`CNI-08.d`, `AOI-06.a`). /waiting and `aew status` carry that name on the item.
- **The open steering requests and the question record** are committed: the requests in control state (FM:184, :196), the question in control state or a record it pins (`BOY-08.a`). An outage read can see both.
- **A G3 approval's record** is a host record (`BOY-05.e`).
- **An observation** rests on host records under `.aew/local` (loop.json and the broker's beat), and ends with the broker (`BOY-09.b`). It is not committed. How an outage read treats such a source is STG-21's position-in-progress (`30-stages/STG-21-O02-independent-outage-reader/`).
- **The notifier's state** (`BOY-12`) rests on host records under `.aew/local` too: the notify spool and the notifier's summary. It is not an item, but its `failed` state raises AT-notifier, whose source is that summary (`BOY-12`). How an outage read treats it is STG-21's.
- **This position owns** the records, and the normal behaviour of `/v1/read/attention` and `/v1/read/waiting`. How they answer while AEW's live services are down is STG-21's.

**BOY-05. A pending G3 approval is shown from the record of the AEW client that started it, and the dashboard never connects to G3** (`G3-07`).
- The dashboard only checks that `request.sock`'s path exists, to tell "G3 is not on this host". It never connects.
- The client already polls its own approval every second, and it records what it sees (`BOY-05.a`).

**BOY-05.a** The record is per host, written by every G3 client AEW ships for each approval it starts, and only by that client. It holds only the ref, expiry, G3's action names, the starter's role, the project label, the start time, a liveness handle, `from_request`, the last state the client read and the time that read completed, the time G3 last answered, and the outcome (`G3-03`).
- **It never holds** a rendering line, a typed value or a consent record.
- **The action names** are those of the TEMPLATE lines of G3's reply, never the client's own words.
- **The project label** is the project the client found by walking up from its directory or from `-C`, or "outside a project". The lookup is new client behaviour: it only labels the item, and grants no scope.
- **While G3 does not answer, or answers 503,** the client keeps reading until the approval's expiry, and records each read. It prints once that G3 is not answering, that it keeps trying until HH:MM, and that Ctrl+C stops it. This is new client behaviour too: at `main` the client exits on either (AEW `src/aew/g3client.py:197-215`).
- **It is written** at start, after each of the client's reads of G3, and at exit. Only the client writes and prunes; the dashboard only reads. **Candidate:** each write is atomic (write, then rename), so the dashboard never reads a torn record.
- **The `from_request` field** is reserved, and nothing fills it yet (`BOY-B7`).
- **Candidate:** the directory `$XDG_STATE_HOME/aew/g3/requests/`, and a liveness handle of the pid plus the process start time.

**BOY-05.b** Each record shows one truthful state, derived from the record and the clock, and only a pending approval before its expiry, whose live client still reads it, is blocked-on-you (A-10 §4.1).
- **Pending, client alive, last read within the stale-read bound:** blocked-on-you.
- **Client gone:** FYI, not counted: "Nothing will submit this. Decline it in AEW approvals, or let it expire at HH:MM." Before expiry, it decides before the unknown row: nothing will submit the approval whatever G3's state, and the confirmer still lists it.
- **Approved and submitted, approved but not submitted, declined, expired:** recent, FYI.
- **G3 answered 404:** "No longer known to G3. Request it again if still wanted." FYI, never blocked-on-you.
- **No answer, a 503, or a live client's last read older than the stale-read bound:** unknown, "?", with the time G3 last answered (`BOY-05.a`). A working client completes a read at least once per request timeout and poll, so a read older than the bound, which adds one more poll as margin (`BOY-14`), means it is suspended or stuck.
- **Expiry passed, no outcome, the client alive or gone:** "Unknown whether decided. Nothing waits on it." FYI. Past its expiry, this row decides before every other row for a pending record: G3 approves nothing after expiry (`G3-02`, G3P:195), and a running client records the expiry itself within its few seconds of grace (AEW `src/aew/g3client.py:197-202`).
- **Windows, or no `request.sock`:** unsupported, "G3 is not on this host".
- **A record the dashboard cannot read:** unknown.
- **Nothing waiting:** "No approval that AEW started on this host is waiting. AEW approvals lists every approval, from any client."

**BOY-05.c** A record stays in the view until its expiry plus `G3-06`'s validity ceiling has passed, a final one as a recent outcome, FYI. Then it leaves the view, and its client prunes it (`G3-02`, `G3-06`).
- That is at most 25 minutes after start: at most 10 under `G3-02` and at most 15 under `G3-06`, both adopted tripwires (G3P:79, :118, :183). It bounds both the display and the recent window.
- There is no 24-hour display window.

**BOY-05.d** An item shows what the confirmer lists, and nothing the confirmer does not show.
- **It shows:** the raw registry action names; the ref's tail and `expires_at`, as the confirmer lists them; the time left and the state; the starter's role, labelled as the client's own claim; "the action stays held until you decide"; and the pointer to AEW approvals (`BOY-06`).
- **It has no table of display words.** The registry holds none, and the operator matches the item to the confirmer's row by its ref (CHK:77-83).
- **Before G3 is established,** each item adds "G3 is not established here: approving admits nothing yet" (`G3-12`). The owner fact behind this line is a stop-and-ask ("Not covered").

**BOY-05.e** An approval record is per host and outside AEW's store, so an outage read never shows a G3 approval as an item (`CNI-08.d`, `BOY-R13`).
- **The approval records are the source outside the store** that an outage read's rendering names under O-02's rule 06.b. Why the rendering, not D-01's wire, names it is O-02's ruling R09.
- **This position's part** is the record's place outside the store, and naming its directory as a host-record source (`BOY-04.a`). How the read stamps its result is STG-21's.

**BOY-06. An item names where to answer in fixed words from a closed set of existing homes, and never links to, launches, raises or pre-selects any of them** (`AOI-06.d`).
- **The set:**
  - `aew_approvals`: "Decide in AEW approvals: the desktop notification, or AEW approvals in the applications menu";
  - `lead_terminal`: "Answer in the Lead's terminal";
  - `g3_request`: "If you agree, start it with aew g3 request at your terminal";
  - `operator_endpoint`: "Decide at the operator endpoint: <COMMAND> at your terminal", where <COMMAND> is the endpoint's command for the request, named from the surface map (stop-and-ask 5).
- **No URL scheme:** it would be a new confirmer input that any web page can invoke.
- **No pre-selection or raise:** the confirmer's own code keeps the PIN field disabled on a raise until the operator picks an approval (window.py:104-140, 203-211), for addendum 4's focus reason.

**BOY-07. Agent text appears only as inert, attributed detail of an agent item on the site** (`AOI-04.f`, `AOI-06.c`).
- **Never** in a title, a severity, a tier or the tab's title, and never in a notification AEW composes: the v2 payload (`BOY-12.c`) and the text `aew notify desktop` posts.
- **The named exception:** the v1 payload, as it stands. Its `reason` carries a steering request's rationale, and its `ref` a confirmation request's `action_ref` (FM:653; AEW `src/aew/harness/notify.py:521-523`). Its `subject`, `reason` and `ref` are cleaned of control characters and capped at 512 characters (AEW `src/aew/harness/notify.py:96-98`; `src/aew/harness/event_spool.py:46`). It stays byte-identical for existing commands (`BOY-12.c`), and is inert under `AOI-04.f`.
- **Never** on a G3 approval item, and never the Lead's rationale or `action_ref` string on a steering request's item.
- **Rendered inert,** as `AOI-04.f` requires.

**BOY-08. The Lead asks through one broker door that derives who asked and writes a CNI record that grants nothing, needs no steering mode or expected revision, and keeps one open question per root lineage** (`AOI-06.b`, `CNI-04.a`, `AEW-FR-28.b`).
- **The door** is a Lead-reachable `aew` command, relayed through lead.cli, so the tool list's bytes are unchanged. **Candidate:** `aew ask`, with the actions ask and withdraw. Its withdraw also takes the Lead's own open steering requests (`BOY-08.f`).
- **The Lead's system text** gains one line, derived from the command's surface-map entry. It says to withdraw a question or a steering request once it is answered.
- **The Lead's status** shows its open question on every call.
- **Who raises now:** the Lead, and AEW's own services (`BOY-09`). Workers ask the Lead once MS4 lands (`BOY-B2`). A mission asks through its episodes, and its held questions are owner records (`BOY-B3`).

**BOY-08.a** The record is a committed store record, in control state or in a store record that control state pins, so an outage read can see it (`CNI-08.d`).
- **Its exact place** is a Candidate for the builder, within that bound. It is never in `.aew/local`, a run directory or a service's memory.
- **Only the broker writes it.** The contained Lead cannot (a stop-and-ask, "Not covered").
- **A commit race is the broker's to retry,** never the Lead's: the Lead supplies no expected revision.
- **The ask's commit stales the other actor's expected revision,** as every control-state commit does (FM:196). It is one of the Lead's own commits, so its reply names the revision it made, and the Lead's next call starts from that revision, as after any of its own commits. A steering-loop call it races goes stale and re-projects, as with any commit (steering_loop.py:40-42, :366-374). The Lead never retries because it asked.
- **A commit that only records an ask moves nothing of steering's envelope** (A1 §3), since asking is communication, not authority (`AOI-06.b`). The class is the door's ask and withdrawals (`BOY-08.f`), and steering's own `request_raise` and `request_confirmation`. Such a commit, alone, starts no loop activation, renews no deadline or action count, and clears no repetition count. It changes no action, blocker or decision the projection offers, so it is no change that justifies repetition (A1 §3.1). An ask also holds nothing: the loop stops only where the projection stops it.
- **Candidate:** at `main`, once the loop has stopped, a commit it did not make starts a new activation, and within one such a commit clears the repetition counts (steering_loop.py:353-358, :407-408). The loop reads the commits since its last tick's revision from the transition log, as it reads its own steps' commits (steering_loop.py:524). When every one is in the class, it marks the change seen, starts nothing and keeps its counts. The door's event kinds are added to the loop's event table as `control_state`: the table is total, so an unlisted kind would stop the loop (steering_loop.py:203-214).

**BOY-08.b** The broker derives `raised_by` (kind, generation, session_label), `root_lineage_ref` (the project's Lead seat across generations), `raised_at` and where to answer, and refuses a caller-supplied actor, lineage, priority, lane or tier.
- **The refusal** is `ATTRIBUTION_IS_THE_BROKERS` (a Candidate name). It names the field, and records nothing.
- **`raised_by`, not `asked_by`:** `asked_by` already belongs to W15 (FM:210).

**BOY-08.c** The agent's fields are inert text, and an ask whose subject does not resolve is refused `SUBJECT_UNKNOWN`.
- **The category:** clarification, direction_brief or blocker. A question is a clarification.
- **The text:** at most 2,000 characters, a snapshot of steering's rationale bound (FM:185), so the Lead meets one limit. A longer text is refused, naming the limit.
- **The subject** is optional. `SUBJECT_UNKNOWN` says how to find refs, and records nothing.
- **Optional:** the recommendation, the options and the cost of delay of `AEW-FR-28.d`.

**BOY-08.d** One question is open per root lineage: a newer ask supersedes it, and the superseded one stays recorded and retrievable (`AOI-06.b`; `IF-37`, which A-10 §12.4 proposes).
- **The reply** tells the Lead to fold anything still open into the new question (`AEW-FR-28.b`).
- **The bound is structural,** and needs no number. The steering requests keep their own snapshot cap of 8 (FM:184).
- **A question ends** only when the Lead withdraws it, a newer one supersedes it, or its asker's generation ends. One whose asker's generation ended shows as FYI: "the Lead that asked has ended"; a withdrawn one clears (`BOY-10`), and a superseded one stays retrievable. Expiry and silence never close it.

**BOY-08.e** A confirmation is asked through steering, never through the ask, and open steering requests are derived into the agent lane, never copied.
- **The refusal:** a confirmation sent through the ask is refused `ASK_IS_A_CONFIRMATION` (a Candidate name), with "use steering request_confirmation, naming the action".
- **The projection:** the current Lead generation only, in fixed text per kind (FM:185).
  - **A confirmation request:** "The Lead asks you to confirm <ACTION>" appears only when `action_ref` exactly matches a registry action or `g3:action:<ACTION>`; otherwise "The Lead asks for a confirmation". Where: `g3_request` only when the matched action's origin is `PROTECTED_G3` (FM:207), since G3 refuses any other set (`G3-02`); otherwise `lead_terminal` (`BOY-06`).
  - **A raise request:** "The Lead asks you to raise the steering mode to <MODE>", where <MODE> is the request's `mode` from its closed enum (walk or run); with no `mode`, "The Lead asks for a raise". Where: `operator_endpoint` (`BOY-06`).
- **Never shown:** the rationale, and the `action_ref` string.
- **One item for a request and its approval** waits until a client writes `from_request` (`BOY-B7`).

**BOY-08.f** The door's withdraw also withdraws one of the Lead's own open steering requests by its SQ-n, and steering closes it in its own record as withdrawn by the Lead. It grants, confirms and raises nothing.
- **Which requests:** an open raise or confirmation request of the current Lead generation. Any other id is refused `REQUEST_NOT_OPEN` (a Candidate name), which names the open ones and records nothing.
- **The close** is steering's own: the request leaves control state's open requests, and its record line names "withdrawn by the Lead", as for every closed request (AEW `src/aew/engine/steering.py:431-440`). Its item clears (`BOY-10`). The notifier stops offering it, since it offers only open requests (AEW `src/aew/harness/notify.py:511-524`).
- **Like the ask,** it needs no steering mode and no expected revision from the Lead, its commit is one of the Lead's own, and it moves nothing of steering's envelope (`BOY-08.a`).
- **The tool list's bytes are unchanged:** `steering` keeps its three actions (AEW `src/aew/surface/contract.py:116-119`), and the withdraw rides the relayed door (`BOY-R06`).
- **The Lead is told:** its status already lists each open SQ-n (AEW `src/aew/engine/steering.py:247-249`) and gains the withdraw command beside it, and steering's reply to a request names it too.

**BOY-09. AEW raises one attention item itself when the loop has stopped for a silent Lead, or when the Lead has made no call for T with nothing running, folded into any open item for that Lead** (`R01-15`, `R01-20`, `R01-26`, `MSN-07`).
- **It is built only if** the operator's answer to Q5 selects it into `R-DEC-03`'s built set, notify-only and in host code.
- **It only notifies.** It never stops, restarts or steers anything (`R01-20`), and it spends no model tokens.

**BOY-09.a** Each source has fixed text and AEW's attribution.
- **A quiet loop stop** (`DECISION_REQUIRED`, `BLOCKED` or `UNKNOWN`, in loop.json) with no Lead call since, for T: "AEW's loop stopped at HH:MM: <code words> on <subject>. The Lead has made no call since. Check the Lead's terminal." <subject> is the stop's subject as loop.json records it, a ref or "the project" (steering_loop.py:98, :598), never a title or the stop's message.
- **The Lead idle:** the broker is alive, no run is active, no harness_wait is in flight, and there has been no lead.tool or lead.cli call for T: "The Lead has made no call to AEW for N minutes. It may be waiting for you in its terminal."
- **The attribution:** "AEW observed this; no agent raised it", with provenance service_observation, in the agent lane.
- **The coverage line:** "AEW cannot tell a question asked only in the Lead's chat from a finished turn; both show as 'your turn'."
- **The broker's beat** gains `last_call_at` and `harness_wait_in_flight`, and lead.cli calls are logged too.
- **Open steering requests and open questions** are items already (`BOY-08`), and are not raised again.

**BOY-09.b** An observation is confirmed over two polls, raised once per occurrence, and cleared by the Lead's next call.
- **Its key:** the stop's condition, the generation and the last call.
- **It folds** into any open item for the same Lead, and the idle source joins the one combined attention notification, never one notification per episode.
- **It clears** on the Lead's next call, the condition changing, or the broker ending. Under CS-4, operator input at the terminal relay also clears it and holds one off (Candidate).
- **It never reaches blocked-on-you.**

**BOY-09.c** T is an execution-policy key, defaulting to 300 seconds, the run-health design v0.1's recommended tool floor (FM:332); it is a tripwire, to be replaced by the measured 95th percentile of the Lead's gaps between calls.

**BOY-10. An item clears only when its source changes, its raiser withdraws or supersedes it, its observation ends or its asker's generation ends, and never because it was seen, dismissed locally or notified** (`AOI-08.b`, `CNI-08.e`).
- **A dismissal** is browser-local (U06 `MANUAL_LOCAL`) and writes nothing shared. It takes the item out of that browser's title count, icon and browser notification (`BOY-13`), and the item stays listed there, marked dismissed, until the operator restores it. It binds the item's occurrence key and tier (`BOY-02`): when either changes, or the browser's storage is cleared, the item counts again. It never removes a source's mark (`BOY-13.a`). `aew status`, the desktop notifier and other browsers are unchanged. **Candidate:** the browser's local storage, keyed by occurrence key.
- **"Seen"** is never an acknowledgement.
- **A steering confirmation request** clears when the Lead withdraws it (`BOY-08.f`), a newer request for the same action replaces it, or its generation ends. An approval of the same action does not clear it, since no record links the two until `BOY-B7`.
- **A steering raise request** clears when the raise is made, a newer raise request replaces it, the Lead withdraws it (`BOY-08.f`), or its generation ends (FM:184, :327).

**BOY-11. The confirmer alone notifies G3 approvals, and AEW notifies every other item it announces in fixed text, never in the confirmer's words** (`AOI-04.f`).
- **AEW never posts** for a G3 approval, and never uses "An AEW approval is waiting".
- **The opt-in browser notification** follows the same partition (`BOY-13.b`).

**BOY-12. AEW ships a default desktop notifier, and a missing notifier or an unreachable desktop is one `unavailable` state shown once with its fix** (`CNI-08.c`, `AEW-FR-28.c`, `MSN-07`).
- **The program:** `aew notify desktop`. Under a yes to Q6, `aew init`'s template writes it into `notify.command`, in the slice that builds `BOY-12.d`. Under a no, the template writes no `notify` key, as at `main`.
- **Existing projects** are offered it through the settings path, with a fix line in doctor and status. Under a no to Q6, the offer says that Run's gate checks only that the program is executable, not that it can deliver.
- **Decision 1's mechanism is unchanged:** the argv, the delivery log, its bounds and the operator's override. What passes its gate is not: the gate checks only that `command[0]` is executable, and `aew` is, so the default passes it wherever it is `unavailable` (FM:659). So the template's default waits on Q6 (`BOY-12.d`).
- **`unavailable` is a new outcome:** no command, a command that is not executable, or, for the default program, no session bus (for example, an endpoint started over ssh). It is recorded when it changes, and shown once in status, doctor and the site, with its fix.
- **`failed` keeps its meaning,** and the "notification failed" item (AT-notifier) is raised only for it.
- **The notifier's state** is one of available, `unavailable`, `failed` (its last delivery failed) and "the operator endpoint is not running", since the notifier runs only inside `aew operator serve` (FM:199). /waiting serves it with its read time and its fix. How the dashboard learns that the endpoint is not running is a Candidate for the builder.
- **Windows:** the program reports `unavailable` in V-01. A toast is backlog (`BOY-B5`).

**BOY-12.a** Only the notifier's child process gets `DBUS_SESSION_BUS_ADDRESS` and `XDG_RUNTIME_DIR`, and it never gets `DISPLAY`, `WAYLAND_DISPLAY` or `XAUTHORITY`.
- **Candidate:** it posts with gdbus, falling back to notify-send.
- **The pinned keep-list test** is a snapshot, and moves with this reason (FM:657).

**BOY-12.b** It posts fixed text per event and tier, and withdraws a notification when its item clears.
- **Each blocked-on-you item that is not a G3 approval** gets its own notification. A G3 approval gets none from AEW, in any tier (`BOY-11`).
- **Attention items** share one notification per combining key of `BOY-03.b`, replaced in place.
- **Withdrawal and replace-in-place** are slice S4.

**BOY-12.c** A new payload, `aew/notify-event/v2`, carries the item id, the tier, a fixed title and the new events attention_waiting, attention_resolved and question_raised, and no agent text.
- **The v1 payload stays byte-identical,** and existing commands get no new events.
- **Candidate:** the policy names which version a command takes.

**BOY-12.d** Under a yes to Q6, Run's gate refuses the default while it reports `unavailable`, at the raise and at each Run activation. So the default never passes Run's gate while it reports `unavailable` (decision 1, FM:672; A1 §4, FM:673).
- **The refusal's fix** names both ways back: start `aew operator serve` inside the desktop session, or adopt a `notify.command` of your own through the settings path.
- **A command the operator wrote** keeps today's check, that `command[0]` is executable (FM:659).
- **`failed` refuses nothing,** since decision 1 gives a delivery failure no workflow effect (FM:672). The endpoint not running keeps today's stop at the loop's ping (AEW `src/aew/harness/steering_loop.py:455-461`).
- **`unavailable` refuses only Run.** Crawl, walk, an ask and every read are unchanged, so a host with no session bus loses only unattended Run, as a fresh project does at `main`.
- **The order:** the refusal and the template's default land in one slice (S3). Under a no, the template writes no default (`BOY-12`).
- **Candidate:** a raise is previewed and committed inside the operator endpoint, which runs the notifier and knows its state (AEW `src/aew/harness/operator_endpoint.py:335, :352`), and the endpoint's ping carries the state to the loop's check.

**BOY-13. While its tab is hidden, the site shows the backend's waiting count and a blocked-on-you icon, and a browser notification is opt-in and only stands in for a desktop notifier that is not delivering** (`AOI-08.e`).

**BOY-13.a** Only /waiting keeps polling while the tab is hidden, and neither a failed read nor a failed source shows a bare count.
- **The poll:** every 30 seconds, a tripwire, with ETag 304s. Browsers may throttle it to about once a minute (READING, FM:505-509).
- **The title:** "(N) Waiting on you · AEW Workbench", where N counts the blocked-on-you and attention items this browser has not dismissed (`BOY-10`). A second static icon shows while any blocked-on-you item this browser has not dismissed waits. With nothing to count and no source marked, the title shows no count.
- **An unknown approval** is an attention item (`BOY-03.a`), so N counts it, and its item shows "?".
- **A failed or stale read** of /waiting replaces the count with "(?)". A 401 or the 24-hour session expiry shows "(!) signed out".
- **A source that is unknown or unavailable** on the last read marks the count: "(N?)", or "(?)" when N is 0 (`BOY-04`, A-10 §4.1). A dismissal never removes the mark. An unsupported source, such as "G3 is not on this host", marks nothing: it is coverage, not a failure (`BOY-03.a`). The icon shows only for an item the read returned, so the mark alone carries a failed approvals source.
- **The visible tab's** 2-second polling is unchanged.

**BOY-13.b** The browser notification is off by default, turned on by the operator's click, and never fires for a G3 approval.
- **It uses** fixed text, and fires once per item.
- **It stands in** for AEW's desktop notifier only while /waiting's notifier state is `unavailable`, `failed` or "the operator endpoint is not running" (`BOY-12`).

**BOY-14. Every consequential limit names its source and type,** as the position template's section 5 requires (`00-governance/templates/POSITION-TEMPLATE.md`, on the operator's templates decision of 2026-10-23, `00-governance/decisions/2026-10-23-operator-templates.md`).
- **The 2,000-character text:** a snapshot of steering's rationale bound (`BOY-08.c`).
- **The 25 minutes:** the sum of two adopted tripwires, which bounds both a record's display and the recent window of its outcome (`BOY-05.c`).
- **The stale-read bound:** the G3 client's request timeout plus two polls, 32 seconds at `main`: a snapshot of the client's own constants (AEW `src/aew/g3client.py:50`, `:53`), with one poll of margin for the write after a slow read, held to them by a test. It moves when they move (`BOY-05.b`).
- **One open question per root lineage:** structural, so there is no number to type (`BOY-08.d`).
- **T, 300 seconds, and the 30-second hidden poll:** tripwires (`BOY-09.c`, `BOY-13.a`).
- **The two-poll confirmation:** a tripwire, after the worker adapter's turn-over rule (FM:318).
- **The steering requests' cap of 8:** a snapshot (FM:184).
- **The tool surface's 11,694 bytes:** a snapshot of AEW's pin, which moves only with the designer's G3 answer (`BOY-R06`).
- **The trial** records the false items, the gaps between Lead calls and the hidden-tab lag, which replace the tripwires.

## Interfaces

- **The approval record** (`BOY-05.a`). **Candidate:** one JSON file per approval in `$XDG_STATE_HOME/aew/g3/requests/`.
- **Contract 0.1.3, unchanged (S1):**
  - a waiting approval is kind `decision_required`, severity high; an approval whose state cannot be read is kind `anomaly`, severity medium;
  - items carry newly registered reason codes, and `first_seen_at` is `started_at`;
  - `aew status` prints the same items, from the same module;
  - the stale 403 reason, which names the closed F15.1, is corrected to name the dashboard half of the typed-surface projection, tracked under E18 (its requirement is named at FM:398, :440-441).
- **Contract 0.1.4 (S2):** `GET /api/v1/waiting`, an additive route that renews C0 once (FM:452). Its closed schema carries:
  - **per item:** id, tier, lane, what, who, since, where (`BOY-06`'s closed set), expires_at, subject, state and source (the class and record `BOY-04.a` names, keyed to that source's entry for its outcome and read time), an approval item's time G3 last answered (`BOY-05.a`), plus inert narrative on agent items only;
  - **per source:** its outcome and its read time;
  - **the notifier's state** (`BOY-12`), with its read time and its fix.
- **D-01:** the reads that overlap D-01 converge on `/v1/read/attention` as hold group 12 builds it. D-01's three gaps go to A-12 under FLAGS' flag 2: a category for a pending G3 approval, a raised-at time and a where-to-answer relation (FM:63, :83). They are batched with STG-21 into one D-01 revision (FM:685). That is the operator's (Q2).
- **The ask door** (`BOY-08`). **Candidate:** `aew ask`, `aew ask --withdraw` for the open question, and `aew ask --withdraw SQ-n` for one of the Lead's open steering requests (`BOY-08.f`), relayed through lead.cli. Its reply names the open question, any superseded one, the Lead's open SQ-n with the withdraw, and the instruction to fold.
- **Refusals:**
  - `SUBJECT_UNKNOWN` (`BOY-08.c`);
  - `ASK_IS_A_CONFIRMATION` (`BOY-08.e`, a Candidate name);
  - `ATTRIBUTION_IS_THE_BROKERS` (`BOY-08.b`, a Candidate name);
  - `REQUEST_NOT_OPEN` (`BOY-08.f`, a Candidate name).
- **The broker's beat** (`BOY-09.a`): `last_call_at` and `harness_wait_in_flight`.
- **Execution policy:** T (`BOY-09.c`), the default `notify.command` (`BOY-12`), and the payload version a command takes (`BOY-12.c`). The key names are a Candidate, the builder's.
- **The notifier:** the payload `aew/notify-event/v2` (`BOY-12.c`), and the outcomes delivered, failed, dropped and the new `unavailable` (`BOY-12`).

## The gate

| Check | What it shows | Pass |
|---|---|---|
| **BOY-Q01** | The dashboard reads approvals without G3 (`BOY-05`) | `src/aew/dashboard` imports no G3 client and connects to no G3 socket, shown by a static test and a runtime spy; it only checks that `request.sock`'s path exists |
| **BOY-Q02** | The record holds only its fields (`BOY-05.a`) | a planted typed value, rendering line and consent record appear in no record, projection, ETag representation, status output or log; only the client writes or prunes the directory |
| **BOY-Q03** | One truthful state per record (`BOY-05.b`) | synthetic records and an injected clock yield every state with its own text, and a record that matches two rows takes the one that decides first; only a pending approval before its expiry, whose live client still reads it, is blocked-on-you, and an unknown state shows "?"; the client rewrites the record after each read, and keeps reading through no answer and a 503 until expiry, printing once that G3 is not answering, until when it keeps trying, and that Ctrl+C stops it; a suspended client's pending record reads "?" with the time G3 last answered once the stale-read bound passes, and "Unknown whether decided. Nothing waits on it.", FYI, once its expiry passes; the stale-read bound equals the client's `TIMEOUT_S` plus two `POLL_S`, read from `aew.g3client`, so changing either constant moves it |
| **BOY-Q04** | Coverage and its absence (`BOY-04`) | approvals started from a second checkout and from outside any project both show, each with its label; Windows shows "G3 is not on this host"; an empty list shows the coverage sentence, and an unreadable record shows unknown; a planted failed read of the question record, of the steering requests and of the broker's beat each shows that source's own outcome and read time; none of these shows 0; a static test finds that every caller in `src/aew` of G3's approval request writes the record |
| **BOY-Q05** | Records leave the view (`BOY-05.c`) | with an injected clock, a final record shows as a recent outcome, FYI, until its expiry plus `G3-06`'s validity ceiling; every record leaves the view then, and the client's next write prunes it |
| **BOY-Q06** | Each tier's behaviour (`BOY-03.b`) | with seven or more existing items, a waiting approval sits first within the overview's six, and agent items come after owner items; FYI items appear in no count and no notification; no notification asks for a sound; no agent item carries an approval item's wording or style |
| **BOY-Q07** | Agent text stays inert (`BOY-07`) | markup, ANSI, a spoofed "type your PIN" prompt and a URL in agent text never reach a title, severity, tab title, v2 payload or the text `aew notify desktop` posts, and render inert in an agent item's detail; `aew notify desktop`, given a v1 payload whose `reason` and `ref` carry them, posts its fixed text for the event and none of the payload's strings |
| **BOY-Q08** | Steering requests' words (`BOY-08.e`) | only the current generation's requests show; confirmation words appear only on an exact registry match; a match whose origin is `PROTECTED_G3` points at `g3_request`, and a match on any other origin, or no match, points at `lead_terminal`; a raise request shows its fixed text, with its mode from the closed enum or the no-mode text, pointing at `operator_endpoint`; neither the rationale nor the `action_ref` string shows; a confirmation sent through the ask is refused `ASK_IS_A_CONFIRMATION`, naming the fix |
| **BOY-Q09** | The ask door (`BOY-08`) | an ask works with no `steering.mode` and with no expected revision from the Lead; it is relayed through lead.cli; the Lead's tools/list bytes are unchanged; the Lead's status shows the open question |
| **BOY-Q10** | The bound (`BOY-08.d`) | replaying `IF-37`, adapted to two Lead generations since workers ask only after `BOY-B2` (40 "urgent" asks across the two), yields one open item and 39 retrievable earlier ones, superseded or ended with their generation, with the owner item first; a withdrawn question clears; expiry and silence close nothing |
| **BOY-Q11** | AEW's own item (`BOY-09`) | a quiet stop with no Lead call for T yields one item after two polls; nothing is raised while a run is active or a harness_wait is in flight; the item never reaches blocked-on-you; nothing is stopped or restarted |
| **BOY-Q12** | The partition (`BOY-11`) | AEW's notifier never gets a G3 approval and never uses the confirmer's notification title |
| **BOY-Q13** | The default and the notifier's state (`BOY-12`) | under a yes to Q6, `aew init` writes the default, and under a no it writes no `notify` key, as at `main`; the settings path offers the default to an existing project, and under a no the offer says the gate checks only that the program is executable; no command, a command that is not executable, or the default with no session bus gives `unavailable`, shown once; AT-notifier appears only on `failed`; with the endpoint stopped, /waiting serves "the operator endpoint is not running", with its read time and its fix |
| **BOY-Q14** | The hidden tab, on the VM (`BOY-13`) | a hidden tab's title and icon change within the measured lag; an expired session shows "(!)" and a stopped backend shows "(?)"; with the desktop notifier available, there are zero browser notifications |
| **BOY-Q15** | Desktop notifications, on the VM through xrdp (`BOY-12.b`) | a planted blocked-on-you item from a source other than G3 gets one notification of its own (a test fixture: no such source is built before `BOY-B3`), and a G3 approval gets none from AEW; one combined notification per combining key; each is withdrawn when its item clears; no window opens by itself; over ssh, the notifier reads `unavailable` |
| **BOY-Q16** | Status with the site stopped (`BOY-02.a`) | with the dashboard stopped, `aew status` lists the same items as the site, from the same module |
| **BOY-Q17** | Nothing decides (`BOY-00`) | no item, count, icon or notification changes any approval, consent or decision record; the site, `aew status` and every notification carry no decide control and no PIN field |
| **BOY-Q18** | One item per waiting record (`BOY-01`) | for each source, a planted waiting record yields exactly one item, with what, who, the source's own time and where, on the site and in `aew status`; where a notifier is available, the desktop announces it as `BOY-11` and `BOY-12.b` partition it |
| **BOY-Q19** | One module (`BOY-02`) | for one planted set of sources, every consumer shows the same items with the same tiers, order and keys; the page parses the tier and computes none |
| **BOY-Q20** | Tier from source class (`BOY-03`) | an agent item whose text or category says "urgent", "approval" or "blocker" keeps its table tier and lane |
| **BOY-Q21** | The table (`BOY-03.a`) | each built source class, and each approval state of `BOY-05.b`, yields its table tier; an approval whose client has gone, one G3 answered 404, one past its expiry with no outcome, its client alive or gone, and an item whose asker has ended, are FYI; an unknown approval is attention; "G3 is not on this host" and the nothing-waiting sentence are counted nowhere |
| **BOY-Q22** | Every item names its source record (`BOY-04.a`) | every item the module derives, and every item /waiting and `aew status` serve, names its source record, a committed store record or a host record, keyed to that source's outcome and read time; an unknown approval item on /waiting carries the time G3 last answered; the question record and the steering requests are committed, an approval record and an observation's inputs are host records |
| **BOY-Q23** | What an approval item shows (`BOY-05.d`) | an item shows the raw action names, the ref's tail and `expires_at` as the confirmer lists them, the time left, the state, the labelled starter's role and the pointer; before G3 is established, it carries the not-established line |
| **BOY-Q24** | Approvals stay outside the store (`BOY-05.e`) | the client writes approval records only in the host directory of `BOY-05.a`, and nothing of them into AEW's store; the attention module names that directory as a host-record source, which an outage reader can name as not read |
| **BOY-Q25** | Where to answer (`BOY-06`) | every item's where is in the closed set, in its fixed words; the site and the notifications hold no link, URL scheme, launch, raise or pre-selection of an answer home |
| **BOY-Q26** | The question is committed, and an ask moves no envelope (`BOY-08.a`) | a question the broker records is read by a committed-records reader with every live service stopped; the contained Lead cannot write it; a commit race is retried by the broker, and the Lead's call passes no expected revision; the ask's reply names the revision it made, and the Lead's next call made from it is not refused for a stale revision; in Run, with the loop stopped at `max_auto_actions`, an ask, a withdrawal, a withdraw of an SQ-n and a steering `request_confirmation` each start no activation and run nothing; in Walk, with the loop stopped at `max_auto_actions`, a steering `request_raise` to `run` starts no activation; with the loop mid-activation and one action run once, an ask leaves the deadline, the action count and that action's repetition count, so the loop stops at `repetition_n` as with no ask, while a Lead checkpoint in the same place still clears the count |
| **BOY-Q27** | The broker's attribution (`BOY-08.b`) | an ask whose body claims another actor, lineage, priority, lane or tier is refused `ATTRIBUTION_IS_THE_BROKERS` and records nothing; an accepted ask carries the broker's attribution |
| **BOY-Q28** | The agent's fields (`BOY-08.c`) | a nonexistent subject is refused `SUBJECT_UNKNOWN`, naming how to find refs; a 2,001-character text is refused, naming the limit; a question records as a clarification |
| **BOY-Q29** | The observation's text (`BOY-09.a`) | each source shows its fixed text, AEW's attribution with provenance service_observation, and the coverage line; a quiet stop's <subject> is the stop's ref or "the project", and a Ticket title or stop message planted with markup appears nowhere in it; lead.cli calls are logged; the beat carries the two new fields |
| **BOY-Q30** | The observation's bounds (`BOY-09.b`) | the next lead.tool or lead.cli call clears the item, and a repeat raises nothing; a second observation for the same Lead folds into the open item; the idle source joins the combined notification |
| **BOY-Q31** | T (`BOY-09.c`) | T is read from execution policy and defaults to 300 seconds; a changed policy value moves the raise with it |
| **BOY-Q32** | What clears an item (`BOY-10`) | viewing, dismissing or notifying an item leaves it open in its source, in `aew status` and in another browser; a dismissal writes nothing outside the browser, takes the item out of that browser's N, icon and browser notification, and keeps it listed as dismissed until restored; with every item dismissed and no source marked, the title shows no count and no icon, and a dismissal never removes a source's mark; a dismissed item counts again when its occurrence key or tier changes, or when the browser's storage is cleared; a dismissed alert whose kind changes or whose condition recurs counts again, and so does a dismissed question once a newer one supersedes it; a withdrawn steering request, raise or confirmation, clears its item and leaves N; an item clears only on its source's change, a withdrawal, a supersession or replacement, its observation's end or its generation's end |
| **BOY-Q33** | The notifier's environment (`BOY-12.a`) | the child's environment adds only the two session-bus variables, and never `DISPLAY`, `WAYLAND_DISPLAY` or `XAUTHORITY` |
| **BOY-Q34** | The payload (`BOY-12.c`) | v1's bytes are unchanged, and existing commands get no new events; a v2 payload carries no agent text |
| **BOY-Q35** | The title (`BOY-13.a`) | in a browser test, a hidden tab polls only /waiting; an unknown approval counts in N and its item shows "?"; a failed read shows "(?)" and a 401 shows "(!) signed out", never 0; with /waiting answering 200, one planted unavailable source and no items show "(?)", the same source beside one attention item shows "(1?)", and a host with no `request.sock` shows a bare count; the visible tab still polls every 2 seconds |
| **BOY-Q36** | The browser notification (`BOY-13.b`) | it is off until the operator's click; it fires once per item, with fixed text, never for a G3 approval, and only while the notifier's state is `unavailable`, `failed` or "the operator endpoint is not running"; with the state available, it fires for nothing |
| **BOY-Q37** | Limits name their source (`BOY-14`) | each limit in `BOY-14`'s list carries its source and type where the code or policy sets it; the trial records the false items, the gaps between Lead calls and the hidden-tab lag, which replace the tripwires |
| **BOY-Q38** | Run's gate on the default, under a yes to Q6 (`BOY-12.d`) | with the default written, `steering.mode` set and the endpoint started with no session bus, a raise to `run` is refused, and a Run already in force stops at its next activation with `NOTIFIER_UNAVAILABLE`; the refusal names both ways back; an executable command the operator wrote passes as at `main` with no session bus; a `failed` delivery refuses nothing; crawl, walk, an ask and every read are unchanged |
| **BOY-Q39** | The Lead withdraws its steering requests (`BOY-08.f`) | through lead.cli, with no expected revision and with `steering.mode` removed from the policy, the Lead withdraws an open raise request and an open confirmation request of its generation; each leaves control state's open requests, its steering record line names "withdrawn by the Lead", and its item clears and leaves N; an ended generation's request or an unknown id is refused `REQUEST_NOT_OPEN`, naming the open ones, and records nothing; no mode, approval or consent record changes; the Lead's tools/list bytes and `steering`'s three actions are unchanged; the Lead's status and steering's reply to a request name the withdraw; the Lead's system text carries the one line, derived from the door's surface-map entry, saying to withdraw a question or a steering request once it is answered |

## Scenarios

**BOY-X01.** Given an approval started with `aew g3 request` while the site's tab sits behind another, the confirmer posts its notification and AEW's notifier posts nothing. The hidden tab's next /waiting read turns its title to "(1) Waiting on you · AEW Workbench", with the second icon. The operator decides in AEW approvals, and the item becomes a recent outcome, FYI (`BOY-05`, `BOY-11`, `BOY-13`).

**BOY-X02.** Given the Lead asking a clarification while the operator is away, the broker commits one question with its own attribution. The item shows at the attention tier, pointing at the Lead's terminal, and the desktop gets one combined notification for the Lead's lineage. Nothing expires it. The operator returns and answers in the terminal, and the Lead withdraws the question (`BOY-08`, `BOY-03.a`, `BOY-10`, `BOY-12.b`).

**BOY-X03.** Given the Lead ending its turn with "what do you want to do?" in chat only, with no run active and no harness_wait in flight, AEW raises one "your turn" item after T and two polls, as its own observation, with the coverage line. It never becomes blocked-on-you. The operator answers in the terminal, the Lead calls AEW, and the item clears (`BOY-09`, `BOY-09.a`, `BOY-09.b`).

**BOY-X04.** Given a yes to Q6 and a fresh project made with `aew init` on a host with no session bus, with `aew operator serve` started over ssh, `aew init` writes the default notifier into `notify.command`. The notifier reads `unavailable` once in status, doctor and the site, with its fix, and no "notification failed" item appears per event. With no `steering.mode` configured, the Lead can still ask, and the site shows every item. Once the operator configures `steering.mode`, a raise to `run` is refused with the notifier's fix, as a fresh project's raise is at `main`, and crawl and walk are unchanged (`BOY-12`, `BOY-12.d`, `BOY-08`, `BOY-04`).

**BOY-X05.** Given G3 not answering while an approval waits, the client keeps reading and records no answer, and the item reads unknown, "?", with the time G3 last answered. It is now an attention item, so the title still counts it, "(1) Waiting on you · AEW Workbench", never 0, and the second icon no longer shows (`BOY-03.a`, `BOY-13.a`). After G3 restarts, the client sees a 404, and the item reads "No longer known to G3. Request it again if still wanted.", never blocked-on-you (`BOY-05.b`, `BOY-04`).

**BOY-X06.** Given the dashboard, the broker and the endpoint all down, an outage read shows the Lead's open question and its open steering requests from their committed records. The waiting approval is not an item, and an outage read answers for its record under O-02's rule 06.b (`BOY-05.e`). The confirmer still lists the approval, with no AEW service running (`BOY-R13`). No observation is open, since an observation ends with the broker (`BOY-09.b`). How that read stamps currency and coverage, and how it treats a source under `.aew/local`, are STG-21's (`BOY-04.a`, `BOY-05.e`, `BOY-08.a`).

**BOY-X07.** Given a Lead sending 40 "urgent security" asks across two generations of one root lineage (`IF-37`, adapted to two Lead generations, since workers ask only after `BOY-B2`), one question is open. The 39 earlier ones stay retrievable: the first generation's last question ended with its generation, and the rest were superseded. The item stays at the attention tier, a waiting approval stays first, and "urgent" reaches no title or notification (`BOY-08.d`, `BOY-03`, `BOY-07`).

**BOY-X08.** Given an uncontained Lead before CS-4 writing a record into the approvals directory, the site shows a false approval item, with "G3 is not established here: approving admits nothing yet". The confirmer lists only G3's own approvals, and nothing is decided. Under CS-4 the directory is out of the Lead's reach (`BOY-05.a`, `BOY-05.d`, `BOY-R04`).

**BOY-X09.** Given an existing project whose adopted policy has no `notify.command`, the notifier reads `unavailable` once in status, doctor and the site, with the fix that offers the default through the settings path. No "notification failed" item appears per event. Until the operator adopts a command, a raise to `run` is refused, as at `main`, whatever the answer to Q6 (`BOY-12`, `BOY-12.d`).

**BOY-X10.** Given the Lead asking with `steering request_confirmation` for a `PROTECTED_G3` registry action, the item reads "The Lead asks you to confirm <ACTION>" at the attention tier, and the hidden tab reads "(1) Waiting on you · AEW Workbench". The operator starts the approval with `aew g3 request`, and while it waits the title reads "(2)": the approval and the request are two items until `BOY-B7`. The operator approves with the PIN, and the approval becomes a recent outcome, FYI. Once its action is admitted, the Lead withdraws the request by its SQ-n (`aew ask --withdraw SQ-n`), steering's record closes it as withdrawn by the Lead, and, with no source marked, the title shows no count. Had the Lead forgotten, the operator dismisses the item in the browser: that browser's title shows no count, the item stays listed there as dismissed, and `aew status` still lists it (`BOY-08.f`, `BOY-10`, `BOY-13.a`).

**BOY-X11.** Given an approval waiting while the operator suspends its client with Ctrl+Z, the record keeps its pending state and its last read time. Once the stale-read bound passes, the item reads unknown, "?", with the time G3 last answered, and the title still counts it. Once its expiry passes, the item reads "Unknown whether decided. Nothing waits on it.", FYI, and leaves the count, whatever the client's liveness (`BOY-05.b`, `BOY-03.a`, `BOY-13.a`).

## Rulings

**BOY-R01. A-37's line 214 covers the time after submission, and this view covers the wait before it.**
- The line sits under "Out of this text" (G3P:209-214).
- At `main`, the CLI waits for the decision before it submits, so no `ORIGIN_PENDING` exists during the wait (CHK:28-30).
- Addendum 4's fallback sentence (its lines 62-63) is corrected: on the CLI path, the held states start only after approval.
- Line 214's wording is an erratum candidate for G3's next revision, which is the operator's.

**BOY-R02. The dashboard reads the client's own record, not G3.**
- **The basis:** `G3-07` is a client reading its own approval (G3P:121). So the view needs no "website backend" reading and no new reach, and the check's facts 3 and 5 and skeptic points 6 and 7a fall away (CHK:65-76, :118-136).
- **The standing:** `CB-10` was cut, so the dashboard's read-only standing rests on its GET-only design.
- The dashboard has no G3 client, so it adds no journal lines, and G3's logging rule stays unchanged.
- **Rejected:** a G3 reader in the dashboard, which rests on two readings the check said must go to the operator, and would hold consent records; confirm.sock's pending list (G3P:46-47); a list route on request.sock, which changes A-37's interfaces; a decide route on the site.

**BOY-R03. The approval record is per host.**
- G3 and the confirmer are per host, and the CLI takes no project (CHK:52-55, :137). A per-host record closes the coverage gap.
- Contained contexts see the host root read-only (AEW `src/aew/harness/containment/layout.py:3-5`).
- So, under A-10 §4.1 ("What the adopted text already decides"), the empty and unsupported states say what they cover (`BOY-05.b`).
- **Rejected:** a per-project record, and a 24-hour display window.

**BOY-R04. A record forged before CS-4 is a false display item, not a finding.**
- Before CS-4, the uncontained Lead can write the record (FM:336), and so can runs started uncontained under `allow_weaker`.
- That yields a false item only, never a decision, and G3 is not established then (`G3-12`).
- Under the security depth reset, it is not a finding. Build-first's sentence on forged records is corrected to this.

**BOY-R05. The question record is CNI's, committed in AEW's store, and outside O-01.**
- D-01 fixes attention's source owner as CNI (FM:61). A-10's subjects 21 and 24 bear on it: the requesting actor owns the attention it raises, and CNI governs its routing (A-10:54, :57). `CNI-04.a` (FM:218) and `AOI-06.b` (A-10:130) bound it.
- The record is committed, for the outage reads (`BOY-R13`; STG-21's position-in-progress, `30-stages/STG-21-O02-independent-outage-reader/`). The brief's Candidate place beside the coordination threads is withdrawn.
- **Rejected:**
  - an O-01 action (FM:230): a successor wire, a registry type with no protection direction, and no Lead sender of O-01 intents;
  - a `question` kind on steering's requests: the steering.mode gate, the shared cap of 8 (FM:184) and the wrong owner. Steering also closes an ended generation's requests (FM:184), while an ended question stays retrievable as FYI (`BOY-08.d`);
  - coordination messages alone: they fail "even if the agent forgot";
  - operator-first's unbounded store;
  - `aew attention close` labelled U06, since it would write a shared record;
  - a question record outside control state's revision, so the loop never sees its commit: it would be in neither control state, nor a record it pins, nor the transition log, so an outage read would not disclose it (O-02's rule 04), and it would fail `BOY-08.a`.

**BOY-R06. The door is a relayed command, not a 16th tool.**
- The tool surface is pinned at its present size. The test asserts the exact list of 15 tools and a size of at most NORMAL_BYTES_PIN, 11,694 bytes, which today's surface meets exactly. The pin moves only with the designer's G3 answer (AEW `tests/unit/test_surface_mcp.py:49, :84-87, :100, :448`). Its looser bounds, under 12,000 bytes and at most 16 tools (:90), never bind. So any 16th tool breaks the pin, and would also spend the 206 bytes that the 11,900-byte stop line keeps for E6b (:96-99).
- lead.cli relays only commands classified Lead-reachable, runs them with the credential the broker holds, and fails closed (AEW `src/aew/harness/lead_broker.py:1-35`).
- A typed tool is backlog (`BOY-B1`).

**BOY-R07. The bound is structural.** One open question per root lineage needs no number, and enforces the consolidation of `AEW-FR-28.b`.
- **Rejected:** listed bounds of 3 or 8 with a cap of 64, which are borrowed numbers.

**BOY-R08. The fallback when the Lead goes quiet is AEW's own signals, in host code, capped at attention.**
- Of the panel's three designs, only this one gives the operator's chat-only case an item at `main`. At `main`, AEW cannot see the Lead's TUI (FM:308).
- **The adopted bounds** are the idleness ones ("What the adopted text already decides"; `R01-15`, `R01-20`, `R01-26`, `MSN-07`). So the fallback only notifies, from host code, and never above attention.
- Its selection into `R-DEC-03`'s built set is the operator's (Q5).
- **Rejected:** operator-first's first layer alone, which misses the chat-only case; a heuristic at blocked-on-you; AEW owning the Lead's OpenCode server now (Q9); a reporting plugin; classifying the Lead's text; reading opencode.db, which the agent-effectiveness study gives to the operator (Q10).

**BOY-R09. The operator-notification tiers fold in, as one table in the attention module.**
- **The reasons:** `D01-WR-09` and `AOI-06.b` ("What the adopted text already decides"). The check's skeptic point 2 asked the same (CHK:35-43).
- Attention items still alert the hidden tab and the desktop, so the operator's constraint holds.
- **Conflicts resolved:**
  - an approval whose client left is FYI: nothing waits on it, the confirmer still shows it, and counting it would be a false alarm;
  - contract-first's agent items at blocked-on-you are rejected;
  - operator-first's permission ask in the owner lane is rejected, because the Lead triggers such asks at will (FM:315).
- New done events would be the operator's, and none are proposed (`BOY-B8`).

**BOY-R10. The site comes in two steps.**
- S1 rides contract 0.1.3 with no contract byte change (CHK:62-64). S2 adds one additive route (FM:452), and renews C0 once.
- The web developer owns the contract file, the C0 renewal and S2w's code. The backend owns the tiers, there are no two default senders, and the visibility handling is reused (FM:485).
- **Rejected:** a title count taken from the overview's attention count, which mixes every kind of item; kind used as a tier; serving /attention from the dashboard's own derivation, against the typed-surface projection that E18 tracks (FM:398, :440-441); waiting for E18 or F20.7; a browser notification on by default; the Push API, which needs an internet push service that a host with no internet access rules out.

**BOY-R11. The desktop notifier is a default command, partitioned from the confirmer.**
- The cleaned environment drops the session-bus variables (FM:657-658). Today a missing notifier fails on every event, which is noise (FM:660). v1's event enum is closed (AEW `src/aew/schemas/notify-event.schema.json:8-14`).
- The notifier is relied on by `MSN-03`, `MSN-06.a`, `MSN-07` and `R-DEC-03` (FM:676-677).
- **Rejected:** an absent `notify.command` meaning the built-in default, which changes Run's gate (Q6); the template's default without `BOY-12.d`, which passes Run's gate where it cannot deliver; merging with the confirmer, which is A-37's; a resident now (`BOY-B6`); widening the environment with `DISPLAY`; extending v1.

**BOY-R12. T and the 30-second hidden poll are tripwires the designer chose.** Each is replaced by the trial's measurement (`BOY-09.c`, `BOY-13.a`, `BOY-Q37`).

**BOY-R13. Outage reads bind the records, not this position's reads, and the approval records meet `CNI-08.d` through G3 itself.**
- **The requirement:** `CNI-08.d` keeps a required decision discoverable "through applicable canonical owners" and through authorized read-only outage paths (A-09:137). O-02's reader, the outage path in STG-21's position-in-progress (`30-stages/STG-21-O02-independent-outage-reader/`), discloses committed records under O-02's rule 04.
- So the question record is committed (`BOY-08.a`), and an outage read sees it beside the steering requests.
- **The approval records stay per host** for coverage (`BOY-R03`). They meet `CNI-08.d` because G3, the approval's canonical owner, and its confirmer list and notify every pending approval with no AEW service running (G3P:46-47, :194).
- **The outage read's part** is O-02's rule 06.b, for the source `BOY-05.e` names. STG-21 cites this ruling (O-02's ruling R06).
- An observation is AEW's own inference, not an operator need that `CNI-08.d` binds, so it is not committed (`BOY-04.a`).
- STG-21's rules are cited, never restated.

**BOY-R14. The build order is the slices table below.**
- Each slice fits one builder and one round, follows the plan WIP limit and the register's hold rule (AEW `docs/implementation/future-work.yaml:8`), and keeps G3-C out.
- Each slice also proves the experience: a normal Lead session and the 2-second visible polling are unchanged.
- **Rejected:** operator-first's bundled first slice, and one large PR.
- The order is the designer's; the milestones are the operator's.

**BOY-R15. The approvals-view draft's independent check (CHK) is answered item by item.**
- **Skeptic 1, facts 1:** by the reading of line 214 (`BOY-R01`).
- **Skeptic 2, facts 2:** the Lead's confirmation request moves to the agent lane (`BOY-08.e`).
- **Skeptic 3, facts 7:** by the states, the prune rule and the client's record of its last state (`BOY-05.b`, `BOY-05.c`).
- **Skeptic 4, facts 6:** by the per-host record and the empty and unsupported wording (`BOY-R03`).
- **Skeptic 5, facts 4:**
  - a slice starts after CS-4 merges and after the operator's placement;
  - the A-12 requirement under FLAGS' flag 2 is Q2;
  - S1 rides contract 0.1.3;
  - the reason for waiting is corrected to `G3-12`, the window before CS-4 in which the Lead can write records, and the planning WIP limit.
- **Skeptic 6:** moot (`BOY-R02`).
- **Skeptic 7, facts 3 and 5:** moot. Action names come from G3's reply (`BOY-05.a`), and the dashboard's standing is its GET-only design (`BOY-R02`).
- **Skeptic 8:** by the content rule (`BOY-05.d`).
- **The nits:**
  - the PIN-field guard on a raise is the confirmer's code (window.py:104-140, 203-211), with addendum 4's focus reason (`BOY-06`);
  - the clause for UI controls is `AOI-01.c` (`BOY-00`);
  - the expiry is "at most 10 minutes" (`BOY-05.c`);
  - the URL-scheme reason is "a new confirmer input any web page can invoke" (`BOY-06`);
  - runs started uncontained under `allow_weaker` join the exposure before CS-4 (`BOY-R04`).

**BOY-R16. A steering request clears through the Lead that raised it, and the operator's quiet is local.**
- E7c's operator-side clear is not built, and the register gives its confirmation to G3 (FM:674). So the Lead withdraws its own request through the door (`BOY-08.f`), and the operator takes a stale item out of their browser's count (`BOY-10`).
- **Rejected:**
  - a fourth `steering` action, which changes the pinned tool list's bytes (AEW `src/aew/surface/contract.py:116-119`; `BOY-R06`);
  - clearing a confirmation request when an approval of the same action ends: no record links the two until `BOY-B7`, so the clear would be an inference;
  - an operator close command, which writes a shared record (`BOY-R05`) for a request the Lead can withdraw;
  - keeping dismissed items in that browser's count, which leaves only an agent able to quiet it.

### The slices, in build order

Every slice starts after CS-4 merges and after the operator's placement (`BOY-R14`).

| Slice | What it builds | What it serves | Waits on | Milestone |
|---|---|---|---|---|
| S1 | The approvals view: the record, the attention module and tier table, /overview, the status lines, the 403 reason fix | `OI-FR-08`, `CNI-08.b`, `AOI-06.a`, `AOI-06.d`, A-10 §4.1, `AEW-FR-28.c`, `AEW-FR-28.d`, `AEW-FR-29.d`; F41.14 item 12's dashboard half (hold group 9); F20 (hold group 12); F43's producer (hold group 10) | Q1 | Contained |
| S2 | The /waiting read in 0.1.4, and the steering requests in the agent lane | FLAGS' flag 2; `AOI-06.a`; F20 | S1, Q2, the C0 renewal | Contained |
| S2w | The hidden-tab signal, the browser-local dismissal (`BOY-10`) and the opt-in browser notification (the web developer's) | the operator's hidden-tab constraint; A-10 §4.1; F20.6 in part | S2 | Contained |
| S3 | The default notifier: `unavailable`, Run's gate on it (`BOY-12.d`) and the template's default, as Q6's answer decides; the v2 payload; the partition | F15.5's notifier clause (hold group 19); `CNI-08.c`; `MSN-03`, `MSN-06.a`, `MSN-07`; A1 §4; decision 1 | S1, Q6 | V-01 |
| S4 | Withdrawal and replace-in-place | `AOI-08.b` in practice | S3 | V-01 |
| S5 | The Lead's ask, its withdraw of the Lead's own steering requests (`BOY-08.f`), and the steering loop's reading of the commits that only record an ask (`BOY-08.a`) | `AOI-06.b`, `IF-26`, `IF-37`, `AEW-FR-28.b`, `AEW-FR-28.d`; A1 §3; F15.9's always-present part | S2, S3, Q3; the capability register's PR 2, if both change the Lead's surface classification | V-01 |
| S6 | The fallback when the Lead goes quiet | `R01-26`, `CNI-08.e`; U1 stays held | S2, S4, Q5 | V-01 |
| S7 | A probe of OpenCode 2.0.18, with no product code: can AEW learn the TUI's port and password, does the TUI attach to a server with a password, is a session active while a permission ask is pending, do forms persist | the chat-only and pending-ask cases | CS-4 | Evaluation |
| S8 | The Lead's harness waits shown as items | the same | S7, and Q9 or Q10 | the operator's |

The later slices are backlog: S9 (`BOY-B2`), S10 (`BOY-B3`), S11 (`BOY-B4`) and S12 (`BOY-B5`).

### For the operator at adoption

Asked in the adoption proposal, after the review round:
- **Q1.** Place S1, S2 and S2w at Contained, drawing out the members they serve? Recommend yes.
- **Q2.** Write D-01's three gaps as A-12 requirements under FLAGS' flag 2, with the dashboard's route serving until hold group 12 converges, and one D-01 revision shared with STG-21? Recommend yes.
- **Q3.** Record the Lead's ask door, with its withdraw of the Lead's own steering requests (`BOY-08.f`), as an A-06 requirement under FLAGS' flag 5? Recommend yes.
- **Q4.** Place S3 to S6 in V-01, with U1 still held? Recommend yes: `MSN-07` and `R-DEC-03` rely on the notifier.
- **Q5.** Does the "yup" of 2026-10-28 select the fallback when the Lead goes quiet (`BOY-09`) into `R-DEC-03`'s built set, notify-only and in host code? Recommend yes.
- **Q6.** Should Run's notifier precondition (decision 1) refuse the shipped default while it reports `unavailable`, at the raise and at each Run activation, with the fix (`BOY-12.d`)? A command the operator wrote keeps today's check. Recommend yes: today's check passes the default wherever it cannot deliver, so `aew init` writes the default only under a yes. Under a no, `aew init` writes none, as at `main`, and the settings path offers it with that caveat.
- **Q7.** Put the Windows toast and the notifier's system packages in E99 at Internal alpha? Recommend yes.
- **Q8.** May a slice start before CS-4 merges when a slot is free and no critical-path slice is ready? Before CS-4, the uncontained Lead can write false display items, never decisions. Recommend yes, under the WIP rule.
- **Q9 (asked only with S7's data).** Reverse ADR-0009's `--standalone` for the Lead? Recommend yes only if the TUI attaches with AEW's per-launch password and sessions keep the curated environment.
- **Q10 (asked only with S7's data).** Read the contained Lead's opencode.db read-only? Recommend deciding on the probe's data, as the agent-effectiveness study asks.

## Backlog

**BOY-B1.** A typed ask tool on the Lead's surface, once the lead-surface cap research sets its byte budget (`BOY-R06`).

**BOY-B2.** Workers' questions, asked of the Lead, as slice S9, once MS4 lands (`HEB-05.b`). Its gate replays `IF-37` as written: 40 "urgent" texts across worker descendants of one root grant, while an owner time-critical need exists.

**BOY-B3.** The held questions of `MSN-07` as blocked-on-you items, as slice S10, built with the mission build.

**BOY-B4.** The long poll of F20.7 for the hidden tab, as slice S11, only on measured need.

**BOY-B5.** The Windows toast and E99's packages for the notifier, as slice S12, on the operator's answer to Q7.

**BOY-B6.** A resident desktop notifier on the confirmer's pattern, built only if the trial shows the endpoint is often not running.

**BOY-B7.** One item for a steering request and the approval started from it, once a client writes `from_request`.

**BOY-B8.** Done events in the FYI tier: the operator's, and none are proposed.

## Not covered

- **Outage reads:** how `/v1/read/attention` and `/v1/read/waiting` answer while AEW's live services are down is STG-21's position-in-progress. This position states only what its records must be (`BOY-04.a`, `BOY-05.e`, `BOY-08.a`). That covers the steering requests, which are committed, and the observations and the notifier's state, which rest on `.aew/local`.
- **D-01 and A-12:** the three gaps and the convergence are the operator's (Q2), batched with STG-21.
- **O-01:** no action is added (`BOY-R05`).
- **Answering an agent's question:** the position points at existing homes, and designs no new one (STG-20's `STAGE.md`).
- **A-37 and the confirmer:** unchanged, and G3-C stays out. Line 214's erratum is the operator's, at G3's next revision (`BOY-R01`).
- **Placement and the hold groups:** the operator's (Q1, Q4, Q7, Q8). Nothing in a held group is built until then (AEW `docs/implementation/future-work.yaml:8`).
- **Workers, missions, the Windows toast, the long poll and a resident notifier:** backlog.

### Stop-and-ask facts the builder measures

Each is measured before its slice's code relies on it. Where a fact does not hold, the builder stops and asks the designer.
1. The operator's state-directory convention, and that no writable bind in CS-4's Lead layout covers the approval record's directory (`BOY-05.a`).
2. That the dashboard can test the liveness handle without writing (`BOY-05.b`).
3. Which owner fact says "G3 is established" for `G3-12` (`BOY-05.d`). If none exists, stop and ask.
4. Where in AEW's store the question record lives, and that the contained Lead cannot write it under CS-4 (`BOY-08.a`).
5. The command name for the answer pointer on a raise request, taken from the surface map (`BOY-06`).
6. `rpm -q glib2 libnotify` on the Rocky 8 test VM and on the work host; the form of xrdp's `DBUS_SESSION_BUS_ADDRESS`; and whether xrdp shows notifications, since the G3-D trial may have run on the VM console (`BOY-12.a`, `BOY-12.b`). Also whether the poster can replace and close a notification by its id on both hosts. If it cannot, stop and ask before S4.
7. Hidden-tab throttling in the operator's browser and version, and the browser's enterprise policy (`BOY-13.a`).
8. The gaps between Lead calls, needed to replace T (`BOY-09.c`).
9. Whether CS-4's reaper can export operator-input times (`BOY-09.b`). If that needs a CS-4 design change, stop and ask.

### Risks

- **The site is not a sure channel.** Browsers throttle and discard hidden tabs, and the desktop notifier works only while the endpoint runs inside the desktop session (`BOY-12`, `BOY-B6`).
- **The fallback is inferred.** Long thinking gives false "your turn" items, and a Lead that keeps calling status is missed. Alert fatigue could teach the operator to ignore the count, and the trial measures it (`BOY-Q37`).
- **Some waits show only as "your turn":** chat-only questions, and TUI permission asks and forms, until S7 and S8, which may need Q9.
- **Questions and requests can go stale.** A question or steering request the Lead forgets to withdraw stays until it is superseded, replaced or its generation ends. The operator can take it out of their browser's count (`BOY-10`), and the trial counts such items among the false items (`BOY-14`).
- **Some approvals stay unknown.** One whose client died reads "client gone" until its expiry, then "Unknown whether decided". A record forged before CS-4 shows a false item (`BOY-R04`).
- **The per-host scope is new behaviour** for the web developer's page.
- **D-01 convergence is debt,** shared with STG-21, and the C0 renewal's timing depends on the web developer.
- **The operator learns two desktop sources,** and agent items at the attention tier may feel under-signalled.
- **A granted browser notification permission** on 127.0.0.1:4280 is inherited by dev servers on that port.
- **If CS-4 slips,** every slice slips.

## Changes

- Revision 1 (2026-10-28): written from the design panel's brief (inputs/design-brief-2026-10-28.md), which answers the approvals-view draft's independent check. Before the review round, the designer fixed the drafting checks' last findings, and took STG-21's result-level reading of an outage read (O-02's rule 06.b and ruling R06).
- Revision 2 (2026-10-28): answers round 1's 16 findings (`CHANGES-r2.md`; `FINDINGS.json`, source BOY1).
- Revision 2.1 (2026-10-28): applies the quick check's minor and four nits, with no further check under the reset (`CHANGES-r2.1.md`; source BOY2).
