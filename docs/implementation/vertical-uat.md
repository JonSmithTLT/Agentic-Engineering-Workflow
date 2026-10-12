# The vertical UAT (v2): the release gate's measurement

**Status:** in shadow (`VERTICAL_MODE = "shadow"`). It is a test, not a feature, and **it is expected to fail on
today's `main`**: its first job is to measure by how much. Flipping it to `enforce` is the operator's decision, made
when the job is green. This page holds its thresholds; the test module pins the same values and
`tests/unit/test_vertical_ledger.py` checks that the two agree, so **changing a threshold means changing this page,
which needs the operator.** It is an implementation document, not a design.

**Spec v2** carries the amendments the operator approved on 2026-10-11 (Q8: every listed amendment; Q1(e): Windows
outside the enforced gate; Q3: publish by console approval). §7 lists each one and where it is implemented.

**Windows: UNQUALIFIED (excluded from the enforced gate).** The operator's decision (Q1(e)), temporary. The Windows job
keeps running and uploading its ledger, and every verdict and summary it prints leads with that line and the
conditions still open: B5q (the Low-integrity Lead qualification), B5 or B5b (the MIC backend for the workers and the
Lead), and the isolation the designer required in 1(g). Enforcing covers Linux only (`ENFORCED_PLATFORMS`). Lifting
the exclusion is the operator's decision.

Code: `tests/acceptance/test_vertical_path.py` (marker `acceptance("VUAT")`, lane `vertical`) and
`tests/helpers/vertical/` (the ledger and the scripted actors). CI: the `vertical` workflow (`vertical.yml`), per OS
([testing-and-ci-strategy.md](testing-and-ci-strategy.md), §2 and §3).

## 1. What it proves

A **fresh** project and a normal operator session. The operator authenticates at most once, says "fix this one-line
bug", and gets the published result. **The operator handles none of AEW's machinery**, and the Lead spends no
attention on rediscovering AEW.

## 2. The actors (all scripted, all offline in v1)

**The operator** types only what a human would type at a fresh terminal: commands, and chat lines to the Lead. Every
input and output is recorded. The script knows what the product's documentation tells a user, and nothing of AEW's
internals.

- **The ideal path** is a named table in the test module (`IDEAL_PATH`): for each step, the command or chat line a
  user would ideally type. Names that do not exist yet are marked `PROPOSED`. The plan for the vertical-path shifts
  amends that table; nobody else does.
- **A fallback fires only after the ideal step was attempted and observed to fail**, never pre-emptively, and every
  fallback is a ledger entry with its evidence (the ideal input, what it answered, what was typed instead). So the
  ledger stops counting ceremony as soon as the product no longer needs it. Today's fallbacks are the documented
  workarounds (`docs/guides/quickstart.md`): acquire, then copy the credential into `AEW_LEAD_TOKEN`; an
  `--expect-rev` read from `status`; a takeover; an adopt after editing YAML.
- **The setup boundary.** Setup is `aew init` and the project's first configuration (its check command and its
  harness), before the first Lead session opens. A policy file edited by hand in setup is recorded, not counted under
  `raw_yaml`; one edited after setup counts. Everything else in setup (an acquire, a credential, a separate adopt) is
  counted like any other step.
- **Terminal channels.** A decision AEW confirms at the operator's own terminal (a policy adoption, a takeover, a
  steering raise) runs with the terminal channel substituted in-process, the channel AT-1 uses on Windows, on every
  platform. The steering raise goes through the real operator endpoint and its real one-time code.

**The Lead** runs inside a fake OpenCode (`tests/helpers/fake_opencode.py`), started through the real
`aew opencode` entrypoint, and talks to the real Lead broker over MCP (`aew lead mcp`, started from the session's
OpenCode configuration as OpenCode starts it). **It has no AEW knowledge.** Its whole policy:

1. Read the projection (`status`; `resume` once at the start of a session, as its tool description says). Reading the
   projection is the policy's own step, never counted as a guess.
2. If `decisions_required` holds a decision the projection gives to the operator (`owner: operator`), ask the
   operator and wait for the reply. **`decisions_required` counts operator-owned decisions only** (v2): one whose
   stated owner is exactly `lead` or `mechanical`, the Lead takes itself and never asks, and the ledger lists it
   apart. Any other stated owner is asked of the operator, compared like any question, and recorded as a finding
   (`unknown_owner`).
   **Until the projection states owners** (projection v2), no decision has one: the Lead asks the operator, as
   today, and the summary shows "owner not stated" for each.
3. Otherwise call the single action the projection marks as next, with **exactly the arguments the projection
   supplied**. Today's projection marks no action as next, so a single AVAILABLE action is taken as the next one; if
   several are AVAILABLE, `ambiguous_next_action` is recorded and the first in order is taken.
4. When the subject is terminal, report the result to the operator: the diff, an evidence summary and the commit.

**Judgment inputs (v2).** Where an action, or a decision owned by the Lead or the mechanism, names `judgment_inputs`,
the Lead supplies them, as its own judgment, and asks no one (never on an operator's decision, whose choice is the
operator's): a value the projection offers (or the first of its `options`) fills an argument the
projection's arguments leave out, and the names are recorded as the Lead's (`lead.judgment`). Today's projection names
none; projection v2 does, with its `next`.

Where that policy cannot make progress (no available action, a refusal, a blocked state), it falls back the way a
real Lead did, and **counts it**: `explain` or help, the `cli` tool, `aew` from its shell, or a tool the projection did
not offer. The fallbacks are scripted per known gap so the run finishes, and every one is a ledger entry; the
scripted Lead's own accounting is the ground truth for its calls. The known gaps on today's `main`:

| Gap | Fallback (each call counted) |
|---|---|
| An empty project offers no action for the operator's request | `ticket_draft`, a tool the projection did not offer, with the Lead's own proposition and plan |
| No decision asks for the proposed plan's approval | the Lead asks the operator anyway, then accepts the plan from its shell |
| A decision has no typed tool | its `cli_fallback`, from the shell; for `RECONCILE` (an INTERRUPTED Ticket), with the phase it was interrupted from and a reason |
| Nothing AVAILABLE and no decision | one `explain`; then the command a projection hint names, from the shell (subject, revision and `--launch` filled in as refusals ask) |
| A prepared candidate whose post-integration verification reported, with no decision offered | the Lead asks the operator to publish, then calls `integration_publish` (not offered) |
| The gate still lacks the local check after the operator's own workaround (U14) | `aew harness launch` of the implementer's invocation, from the shell, so its check runs again |
| After a takeover and a reconcile, no implementer is active and nothing is offered (the hint's transition is refused) | a new attempt: `aew invoke create --role implementer --launch` (`work redispatch` for a non-mutating Ticket); the refused hint is recorded as `stale_hint` |
| A decision still required after its answer was acted on (its call refused) | never re-asked: one `explain`, then its `cli_fallback` if it is concrete (for `RESOLVE_STAGE`, `aew stage continue` with the Lead's own rationale; when that is refused and the refusal names `abandon`, `aew stage abandon` with the Lead's rationale), then stuck |
| Anything else | the Lead tells the operator it is stuck and waits; whatever the operator says next, it goes on (the ledger says where it stopped) |

**The workers** come from the fake harness: implementer, reviewer, verifier and integration verifier, each run's
script chosen by its role and scope (the operator and the Lead never name a run). They make **a real one-line fix**
to a real Python sample, with a real test. **The project's unit check is a real `python -m pytest`**, which writes
`__pycache__`; no fake hides it, and the sample has **no `.gitignore`** for the caches (a fresh project has none). If
the gate is then observed to refuse (the Lead stuck on `GATE_UNSATISFIED` with the caches in the Ticket's workspace),
the operator's counted fallback is today's U14 workaround: the caches go into `.git/info/exclude`, and the operator
tells the Lead to carry on.

The offline world (the fake harness, the fake OpenCode binary and their scripts) belongs to the test, like an
installed tool: its variables are not the operator's.

## 3. The scenarios

| Id | Scenario | Must hold |
|---|---|---|
| **V1** | **The fresh path.** A new project (a sample the test creates) goes from setup to a published one-line fix, and the operator gets the result: diff, evidence summary, commit. | The ledger zeros in §4, with **two** operator decisions: approving the plan, and approving the publish. Publish stays a judgement unless a grant covers it. |
| **V2** | **Close and reopen with work active.** As V1, but the operator ends the Lead session while the implementer runs, then opens AEW again **from a fresh terminal**, nothing carried over. Parametrized: a clean `/exit` (the primary case) and a killed session. | No takeover, no credential, no INTERRUPTED Ticket and no reconcile. The implementer's run is untouched (still running after the reopen, its evidence accepted, no relaunch). The operator is told where things stand in words. The same zeros. |
| **V3** | **Preflight catches it first.** One case per cause: a `provider_env` variable unset; a configured model the harness does not list; a check that changes the snapshot; stale state the engine could recover (a Lead session that died holding the seat); a model id carrying the provider prefix. | Before any Ticket exists, readiness (the preflight, not doctor) fails, **naming the cause and the fix**. Doctor may pass (the ledger records whether it did). Nothing is launched. |
| **V4** | **Change a setting.** Switch the implementer's model, then V1's path. | One operator action that validates and saves; saving is the adoption. No raw YAML, no separate adopt, no credential, no restart. The implementer runs on the new model. |

- **The provider-prefix case** (UAT U3's shape): the operator pastes the harness's own printed `provider/model` id
  into the profile's `model`, and AEW passes the provider and the id apart, so the reference it uses is doubled
  (`<provider>/<provider>/<model>`). The ideal outcome is that AEW accepts the id as typed (no error at all);
  otherwise readiness must name the doubled reference and suggest the listed id. The names used are synthetic.
- **What counts as naming a cause (V3).** Only a FAIL or WARN entry of the readiness report (the line whose status is
  FAIL or WARN, with its continuation lines) that names the specific cause, or its fix. A PASS or INFO line that echoes
  the configured value is not a diagnosis (`failing_entries`, `diagnoses`), for preflight and for the doctor fact the
  ledger records. A refusal in the CLI's JSON shape (`{"ok": false, "error": {code, message, details}}`) is one failing
  entry, its message and details; a JSON answer with `ok: true` never is.
- **Opening AEW (v2).** The ideal `open` step is `aew opencode`, which opens the operator console (when no endpoint is
  live for the project) and the console asks for the operator's PIN. **The auto-opened console is not a counted
  step**: the test records whether it opened (`open.console`). The PIN is counted under "authenticate at most once"
  (§4, `pin_reentries`). Until the endpoint becomes the operator session, no console opens, the ideal attempt fails,
  and today's fallback (the credential in `AEW_LEAD_TOKEN`) is counted as before. `configure` opens the console the
  same way if it runs first. The steering `raise` stays a decision confirmed at the endpoint's console on every
  platform.
- **V2's reopen.** The ideal step is `aew opencode` with nothing carried over. When it fails, the operator opens the
  Lead the way `docs/guides/opencode.md` documents (`aew opencode --acquire`), and when that is refused, takes the
  seat over at their own terminal and hands the new credential to the session (quickstart, "Losing the session"):
  every step counted, and an INTERRUPTED Ticket or a reconcile recorded as evidence. A reopen from the same shell,
  where the first open's exported credential is still set, is an extra measurement (its own test), never V2's
  verdict. A forced variant kills the session while a stage is half done (the fake harness holds the implementer's
  launch until the test has killed the session, so no timing decides it): reopening moves the stage's subject, and the
  chain abandon, reconcile, new implementer attempt runs, and finishes, on every run on both platforms.
- **Steering on.** V1 and V2 also run with steering on, in the mode that lets the loop push the stages (Run), so "the
  Lead does no stage-pushing" can be measured. Whether that mode completes a Ticket on today's `main` with the fake
  harness is recorded, not assumed: the ledger lists the stages the loop ran and where it stopped. **Raising the mode
  is an operator decision**, recorded under decisions, never a `lifecycle_step`; it is not one of V1's two. With
  steering on, the Lead leaves an action the projection marks `auto_runnable` to the loop: it waits for an event (the
  revision moves, or the loop records a stop) and pushes the action itself, counted, only when the loop declined.

## 4. The burden ledger (the measurement, and the assertions)

Each scenario writes `vertical-ledger.json`: one entry per counted event, each with the evidence for it (the exact
input or call; credentials redacted). It also writes and prints a one-screen summary (`vertical-summary.txt`). The
ledgers go to `AEW_VERTICAL_OUT` (CI uploads them), else the test's own temporary directory. A scenario always runs to
the end and writes its ledger before it asserts.

**Operator counters (all must be 0):**

| Counter | What counts |
|---|---|
| `credentials` | any AEW credential the operator had to see, copy, paste or set (one entry per event) |
| `env_vars` | any environment variable the operator had to set. In offline mode the provider key is also 0 (the fake needs none); the live variant reports it separately. |
| `raw_yaml` | any file under `.aew/policy/` edited by hand after setup |
| `revisions` | any operator input containing a control-state revision (`expect_rev` or a number read from `status`) |
| `generations` | any operator input containing a Lead generation |
| `invocation_ids` | any operator input containing an invocation id |
| `run_ids` | any operator input containing a run id. A Ticket id is allowed: it is a product concept. |
| `takeovers` | any takeover |
| `seat_operations` | acquire, release or reacquire, by hand |
| `lifecycle_steps` | any operator command or chat line that pushes a lifecycle stage. Approving the plan and the publish are decisions, not steps. |
| `manifest_adopts` | any separate adopt step |
| `pin_reentries` | "Authenticate at most once" (v2): the operator's PIN, entered in the operator console, is allowed once per endpoint lifetime (per project, per login session; "session open" is that lifetime). Any further entry while the same endpoint lives is counted, and so is a per-action console challenge on Linux. Never under `credentials`: the PIN is the operator's own secret. |
| `windows_console_challenges` | (v2) each per-action challenge at the operator console on Windows (a one-time code typed back) for an operator-principal operation that is not a decision, such as configure or open, standing in for "authenticate once" until Windows qualifies. A decision confirmed at the console (the steering raise, every re-authenticated item) is a decision on every platform, never a challenge. |

**Any operator fallback fails the verdict.** Every fallback the operator took (each a ledger entry with its evidence)
is listed in the summary and fails the scenario, whether or not one of the counters above classifies it, so a
workaround no counter sees (editing git's own exclude file, for example) can never let the zeros pass.

**Operator decisions** are listed, not counted against: every question AEW or the Lead put to the operator, with the
answer. V1 must list exactly `plan`, `publish`. Any other question fails that comparison and is reviewed by hand: is it
a real product, policy or safety judgement? The summary shows, for each decision, the tool its answer drives and
whose decision the projection says it is ("owner not stated" until the projection carries owners); the test does not
settle that ownership. **v2:** only operator-owned decisions are the operator's. A decision the projection gives to the
Lead or the mechanism is never put to the operator, and the summary lists it apart ("not the operator's"). Every
question that does reach the operator is compared, whatever owner it names, so a question cannot leave the
comparison by its label.

**Lead counters (all must be 0):**

| Counter | What counts |
|---|---|
| `help_calls` | `--help`, or `explain` used to find a command |
| `guessed_commands` | any call to a tool or command the projection did not offer |
| `cli_tool_calls` | the typed surface's `cli` passthrough |
| `shell_aew_calls` | `aew` run from the Lead's shell (the scripted Lead's own accounting is the ground truth) |
| `ambiguous_next_action` | the projection offered several AVAILABLE actions and marked none as next |
| `revision_args` | any Lead call whose arguments include `expect_rev` or any other revision, **including one the projection supplied** |
| `stale_retries` | a STALE_REVISION followed by a retry |
| `refusals` | any refusal, by code and message |
| `mechanical_calls` | calls that only push a stage or wait, with steering on (a steering-off run records them as its measurement, and only a steering-on run is held to 0) |

**Hard limits that the zeros must not buy.** Each is its own assertion, and the ledger keeps its failures apart:
`did_not_refuse` (a safety regression), `refused_without_naming` (an explanation gap), `rebuilt_not_published` (a
conflicting change carried on with, rebuilt and re-verifying, instead of refused) and `not_exercised` (the run
never reached the limit's step: no harness run, no publish, no check). `did_not_refuse` means the protected action
actually went ahead. Every one of them fails the test; only `held` passes.

| Hard limit | Sub-scenario | Holds when |
|---|---|---|
| `semantic_conflict` | V1, with main moved under the prepared publish by a change to the very line the Ticket fixes | the step refuses, with a message that names the change (its commit, subject or path); "last writer wins" fails, and so does a rebuild that carries on |
| `evidence_mismatch` | V1, with a check that also rewrites a tracked file (`ledger/build-stamp.txt`), which no scrubbing of caches can make legitimate | the gate refuses (or AEW flags the check), naming that path; an auto-waived mismatch fails |
| `publish_needs_decision` | every scenario | main moves only after the operator's publish decision (or a grant). **From B1** (the operator's Q3 answer), the publish record must also be console-approved and attributed to the operator; until B1 builds that channel the limit stays "main moved only after the operator's yes" (`PUBLISH_CONSOLE_ATTRIBUTION`, false until B1) |
| `containment` | every scenario | every run's label and the Lead's are each at or above the platform's minimum below (v2: the Lead's label is included, and the minimums only ratchet up) |

A positive counterpart runs beside the semantic conflict: a **compatible** change (another file) lands on main under
the prepared publish, and AEW should rebuild, re-verify and publish both, with no further question to the operator
after the publish approval.

**Containment minimums (they only ratchet up):** labels run from weakest to strongest: no label (`none`),
`workdir_separation_only`, `os_readonly_roots` (`LABEL_ORDER`). A minimum may only be raised, with this page and the
operator; `tests/unit/test_vertical_ledger.py` pins every earlier value and fails if one is lowered. Today's Lead has
no label on any platform (it is uncontained): B4 raises the Linux Lead's minimum, B5 the Windows one.

| Platform | Actor | Minimum | Since |
|---|---|---|---|
| Linux | workers | `os_readonly_roots` | v1 |
| Linux | lead | `none` | v2 |
| Windows | workers | `workdir_separation_only` | v1 |
| Windows | lead | `none` | v2 |

## 5. Where it lives and how it gates

- **Its own lane.** `tests/helpers/lanes.py` maps the module to the `vertical` lane ahead of its `acceptance` marker,
  and collects it only with `--lane vertical` (or when named on the command line). No required lane's job collects
  it: a red shadow test must never block a merge, and a collected test that did not run would fail `assurance`.
  `tests/unit/test_ci_tools.py` proves both.
- **Its own workflow, in shadow.** The `vertical` job (`vertical.yml`, Linux and Windows; outside `ci.yml`, so its red
  never colours the merge gate's run) runs on every pull request and on `main`, uploads
  the ledgers and summaries as artifacts (`vertical-ledger-<OS>`), and writes the summaries to the run's summary page.
  It is not in `assurance`'s needs. It is honestly red while the ledger is not zero: no xfail, no skip, no lowered
  assertion.
- **Platforms.** It runs on Windows and Linux; any platform-only part is pinned in `tests/platform-skips.yaml` (none
  today). **The enforced gate is Linux only** (v2, the operator's Q1(e)): Windows is UNQUALIFIED and excluded from it,
  its job keeps running and reporting, and its state leads every verdict and summary it prints (the status above).
  `tests/unit/test_ci_tools.py` proves the Windows job stays in the matrix.
- **No `enforce` while the Lead is uncontained.** `VERTICAL_MODE` cannot be `enforce` while the Lead is uncontained on
  an enforced platform: each enforced platform's Lead minimum must be above `none`, and the test must read the Lead's
  label from the product rather than assume none (`enforce_blockers`, which `tests/unit/test_vertical_ledger.py`
  checks whenever the mode is `enforce`). Today both conditions block it.
- **Harness faults are not product results.** The chat between the scripted actors survives a failed read (retried
  within its bound, the message never skipped) and records it (`chat_read_error`, `lead.listener_error`); the
  listener's own records are best-effort, so recording an error never ends it. A Lead session that stays alive and
  silent past the bound is recorded as `lead_silent` with whose fault it is, only as far as the evidence goes: the
  harness's only with harness evidence (a chat read error, or the Lead waiting to hear while an operator message it
  has not read exists); otherwise "not established", with what the Lead was doing (a call that never returned, no TUI
  started), so a product hang reads as one. The evidence is the silent session's own: each open gets its own id,
  which its events and its state carry, the previous session's state is removed, and the operator's chat errors
  count from the open. An exception that ends the scripted Lead is recorded as `lead_error`: the
  aew-lead MCP server ending is the product's, anything else is not established. Neither is ever reported as "no
  result reached the operator".
- **Stale revisions are attributed.** For each `STALE_REVISION` the Lead meets, the ledger records the commit that
  staled it (from the transition log), attributed through the stage intent it belongs to: the steering loop's when
  that intent was auto-run, else the Lead's. Only a commit in no stage falls back to its actor, and then a Lead
  credential cannot tell the Lead from the loop, which the record says. So a steering loop's race shows as the loop's,
  not as the Lead's behaviour. It is evidence, not a counter.

## 6. Later (not v1)

- **The live variant:** the same scenarios against real OpenCode 2.0.18 and a real provider, run by the operator. It
  adds the provider key counter and the paid preflight tier (real authenticated calls), and (v2) **a live check of
  auto-open**: `aew opencode` with no endpoint live opens one real operator console window, which asks for the PIN.
  The offline test never opens a window; it records whether a console endpoint came up.
- **A real-model Lead variant:** the same ledger with an actual model as the Lead, to measure what the scripted Lead
  cannot, such as attention spent on judgement, and the Lead's own `aew` shell calls seen at the broker.

## 7. Spec v2: the approved amendments

Approved by the operator on 2026-10-11 (Q8: every listed amendment). Each threshold change here is that approval's.

| Amendment | Where it is implemented |
|---|---|
| The scripted Lead supplies the projection's `judgment_inputs`, where present | §2; `vertical/lead.py` (`judged`) |
| `decisions_required` counts operator-owned decisions only; until the projection states owners, "owner not stated" and today's behaviour | §2, §4; `vertical/lead.py` (`own_decision`), `vertical/ledger.py` (`owner_of`, `not_the_operators`) |
| The evidence-mismatch sub-scenario no longer relies on `__pycache__` | **already met** in v1 (the check rewrites the tracked `ledger/build-stamp.txt`) |
| The `open` row opens the operator console and asks for the PIN; the auto-opened console is not counted; until then the ideal attempt fails and today's fallback is counted | §3; the test module (`IDEAL_PATH`, `console_opened`) |
| A live-UAT check of auto-open | §6, the live variant |
| The PIN under "authenticate at most once": at most 1 per endpoint lifetime, any further entry counted | §4 `pin_reentries`; `Ledger.pin_entered` |
| A `windows_console_challenges` counter, threshold 0 | §4; `Ledger.console_challenge` |
| Windows outside the enforced gate, its unqualified state explicit (the operator, Q1(e)) | the status above, §5; `ENFORCED_PLATFORMS`, `windows_lines` |
| The containment limit includes the Lead's label and only ratchets up | §4; `CONTAINMENT_MINIMUM`, `LABEL_ORDER`, `scripted_operator.containment` |
| From B1, publish is checked as console-approved and attributed to the operator. This one derives from the operator's Q3 answer (2026-10-11), not from the Q8 list; thresholds are the operator's | §4 `publish_needs_decision`; `PUBLISH_CONSOLE_ATTRIBUTION` (false until B1) |

The PIN, the console challenge and the console attribution have no event to observe until the endpoint becomes the
operator session: their counters read 0 and the attribution check stays off until then. That slice wires its console
to `pin_entered`, `console_challenge` and the attribution check, and changes this page if a rule needs to.

## 8. The discovery layer, D2: the output and text rules (DX1)

The discovery-layer specification v3.4 extends this page. Its first slice, **DX1**, is D2: deterministic rules over
what AEW says, scheduled by the operator as the anti-drift guard G2. Like the rest of this page, it is a test, not a
feature: **it observes and changes no product code.** The violations it finds today are its baseline, an allow-list
that may only shrink. It does not fix them.

Code: `tests/helpers/discovery/` (`rules.py`, the capture plugin `capture.py`, `static.py`, the allow-list
`allowed.py` and `allowed.yaml`, `modes.py`), the `discovery` lane (`tests/discovery/`), and
`tools/ci/discovery_ratchet.py`. Tests: `tests/unit/test_discovery_rules.py` and
`tests/unit/test_discovery_registry.py`.

### 8.1 What it reads

- **Runtime outputs.** A pytest plugin captures every output the existing suite produces:
  - the CLI's answer and its refusal, in process (`aew.cli.main._main`'s stdout and stderr) and from every `aew`
    process a test starts with `subprocess.run`;
  - the typed surface's result (`aew.surface.run.run_tool`).

  A process a test drives through `Popen` (a Lead session, the MCP server) is not seen.
- **The output-site key.** It identifies the code path, never the message, because messages carry temporary paths
  and live ids, and the keys are committed:
  - `cli:aew <command words>|<code>` for the CLI. The words are read from the argument vector with the live parser.
    The code is the refusal's code, or `result` for an answer.
  - `tool:<name>|<code>` for the typed surface.

  The specification's "the renderer's caller (module and function)" names a single function for every CLI command
  (the entry point renders them all) and cannot be read from another process, so the command words stand in for it.
- **Static texts.** These are checked with no test running:
  - `LEAD_SYSTEM` and the Lead's commands;
  - the rendered `aew guide`, from the policy `aew init` writes;
  - `docs/guides/*.md`, which include the quickstart;
  - every pack template (each role's launch contract, rendered from synthetic inputs);
  - the typed tools' arguments (O-SECRET).

  A static key names its source and the suggested input, for example `static:docs/guides/quickstart.md|aew ...`.
- **A suggested input** is any of these:
  - a backticked `aew …` span;
  - a line of a fenced code block that starts with `aew`, with continued lines joined;
  - a structured `next`, `next_action(s)`, `remedy`, `cli`, `cli_fallback` or `hint(s)` field.

  Commands chained with `&&` count as one each.

### 8.2 The rules

| Rule | A violation |
|---|---|
| O-IDS | A suggested input asks for an id, decided by position with the live parser: <ul><li>any value of an id-typed argument (a revision, generation, invocation, run, stage intent or authority candidate);</li><li>a concrete id in the engine's formats;</li><li>a placeholder (`N`, `<…>`, `{…}`) in any other slot.</li></ul> These are exempt: a Ticket's slot, a slot whose values the text lists (an argument with choices), and the elision `...` for free text. |
| O-CMD | A suggested input fails to parse in parse-only mode against the live parser. Placeholders are taken as values, and each alternative of `a`-or-`b` (written with a bar) must parse. A command named in text without its required arguments is a mention, but a structured argument list (`cli`, `cli_fallback`) must parse whole. A typed-tool name not in `contract.TOOLS` is also a violation. Text that echoes the input inside a refusal is excluded. |
| O-CODE | A refusal whose cause is known is checked against the code registry (§8.4). In DX1 no cause is known: one is known only when an explorer injected it (DX2), or when the refusal states it in the refusal schema (DX3). So O-CODE judges nothing in the existing suite yet, as the specification's H5 requires. |
| O-WORDS | A refusal without the refusal schema (`cause`, `remedy`, `owner`). Until the product emits it, this is the "unstructured refusal" finding, one per refusal site. |
| O-SECRET | Any of these: <ul><li>an output that asks for a PIN anywhere other than the operator console;</li><li>one that asks a model (the Lead, or a worker through its pack) for a code;</li><li>one that asks its reader to set, copy or pass an AEW credential, the credential variables of `harness.contract.CREDENTIAL_ENV` and their options;</li><li>a typed tool with a PIN, code or credential argument.</li></ul> |
| O-ENV | The Lead's system text, with the guide it is given, does not state the check environment. The expected statement is generated from `agentenv`'s allowlist: that checks run in a scrubbed environment, every variable kept, and `provider_env` as the way to give a check a variable. |

### 8.3 The modes, the allow-list and the ratchet

**The per-rule modes.** `tests/helpers/discovery/modes.py` pins the same values, and
`tests/unit/test_discovery_registry.py` checks that the two agree. A mode changes only by the operator's decision.
In `shadow` a finding is reported and never fails a run. Every rule starts in `shadow`, as the vertical UAT did.

| Rule | Mode |
|---|---|
| O-IDS | `shadow` |
| O-CMD | `shadow` |
| O-CODE | `shadow` |
| O-WORDS | `shadow` |
| O-SECRET | `shadow` |
| O-ENV | `shadow` |

**The allow-list** is `tests/helpers/discovery/allowed.yaml`: every `(rule, site)` key observed when D2 was
introduced, from the static scan and a capture run of the fast lane. It may only shrink.
- **On a pull request,** `assurance` runs `discovery_ratchet.py` over the findings that the tier's lane jobs wrote
  beside their lane reports.
  - A key not on the list is **new**. It is reported, and fails the run if its rule is in `enforce`.
  - A key added to the list relative to the base fails whatever its mode. The exception is an accepted residual: the
    operator's decision, recorded under `residuals` with its reason.
- **On main's full run and nightly,** the same tool also reports every listed key no longer observed as **stale**. A
  stale key fails the run if its rule is in `enforce`, until a pull request removes it. CI never commits the removal.
- **Static texts** are checked on every pull request by the `discovery` lane, in its own workflow (`discovery.yml`).
  The scan is complete, so its new and stale keys are decided on every run.

**The `discovery` lane** is its own lane. `tests/helpers/lanes.py` collects `tests/discovery/` only with
`--lane discovery`, the same split as the vertical lane, and no tier requires it. `tests/unit/test_ci_tools.py`
proves both.

### 8.4 The code registry

Every refusal code that `aew.errors` defines is listed below, with its meaning, the causes allowed to use it, and the
owner of the remedy. `tests/unit/test_discovery_registry.py` enumerates `aew.errors` and fails on any code missing
here, so the registry cannot drift. O-CODE checks an observed refusal's cause against its code's row. The cause ids
are this registry's own vocabulary; the refusal schema will carry them.

| Code | Meaning | Allowed causes | Remedy owner |
|---|---|---|---|
| `AEW_ERROR` | An unclassified failure, the base of every error. No refusal should carry it | `unclassified` | engine |
| `USAGE` | Only malformed input, naming the field and the fault (invalid JSON versus the wrong type, U27) | `input_malformed`, `input_unset` | Lead |
| `NOT_FOUND` | A named object does not exist | `object_missing` | Lead |
| `PROJECT_NOT_FOUND` | No AEW project at the path | `project_missing` | operator |
| `VALIDATION_FAILED` | Input or a record fails its schema or a validation rule | `input_invalid`, `record_invalid` | Lead |
| `REPLY_NOT_IN_THREAD` | `in_reply_to` names no earlier message of the thread | `reply_target_invalid` | Lead |
| `REF_UNKNOWN` | A message ref names no AEW id, or is malformed | `ref_unknown` | Lead |
| `STALE_AUTHORITY` | A superseded Lead, or a revoked credential, attempted an authoritative write | `authority_superseded` | operator |
| `STALE_POLICY` | The legality policy in force is not the one a staged action was bound to | `policy_changed` | Lead |
| `STALE_REVISION` | Only a CAS mismatch. After A3, `CHANGED_SINCE_READ` carries the named semantic change | `cas_mismatch` | Lead |
| `PERMISSION_DENIED` | Only an authority that actually denied the caller. Never "seat held", and never "input not set or malformed" | `authority_denied` | operator |
| `CAPABILITY_UNAVAILABLE` | A capability switched off for the project, or refused where it was called | `capability_off` | operator |
| `OPERATOR_AUTHORIZATION_REQUIRED` | The operation needs the operator's out-of-band authorization | `operator_authorization_missing` | operator |
| `REF_OUT_OF_SCOPE` | A worker's message ref names something outside its own unit, thread, Ticket and runs | `ref_out_of_scope` | Lead |
| `OBSERVATION_MUTATED` | A read-only invocation changed its observation workspace | `observation_mutated` | Lead |
| `WORKSPACE_MUTATED` | An evaluated workspace no longer holds what it was dispatched to evaluate | `workspace_mutated` | Lead |
| `ILLEGAL_TRANSITION` | Only a transition-table refusal, naming the state | `transition_refused` | Lead |
| `GATE_UNSATISFIED` | A gate the transition requires is not met | `gate_unmet` | Lead |
| `DISPOSITION_REQUIRED` | A finding or claim that policy marks for disposition has none | `disposition_missing` | Lead |
| `CARD_CHOICE_REQUIRED` | A stage cannot choose the card a required gate needs | `card_ambiguous`, `card_missing` | Lead |
| `DEPENDENCY_UNSATISFIED` | A unit's dependency is not met | `dependency_unmet` | Lead |
| `CONCURRENCY_LIMIT` | A concurrency bound is reached | `concurrency_bound` | Lead |
| `STALE_CANDIDATE` | The authoritative ref moved, so the integration candidate must be rebuilt | `ref_moved` | engine |
| `QUEUE_ORDER` | An earlier integration queue entry can integrate now | `queue_order` | engine |
| `LEASE_HELD` | Another queue entry holds the integration lease | `lease_held` | engine |
| `LEASE_NOT_HELD` | The operation runs only under the Ticket's own integration lease | `lease_not_held` | engine |
| `LEASE_RECONCILE_REQUIRED` | The integration lease lost its custodian | `lease_orphaned` | Lead |
| `INPUT_STALE` | A consumed source-bound record no longer matches its source | `input_stale` | Lead |
| `DISPATCH_REFUSED` | The dispatch predicate refused, naming every blocking condition | `dispatch_predicate` | Lead |
| `STEERING_NOT_CONFIGURED` | A steering command on a project whose policy names no steering mode | `steering_unconfigured` | operator |
| `MIGRATION_REQUIRED` | The project's control state is v1 and must be migrated first | `migration_pending` | Lead |
| `MESSAGING_DISABLED` | A coordination message while messaging is off | `messaging_off` | operator |
| `TURN_END_NEEDS_MESSAGING` | `harness send --when turn-end` while messaging is off | `messaging_off` | operator |
| `HARNESS_SEND_NEEDS_STORE` | `harness send` while messaging is on, before this AEW can record it in the store | `message_store_unavailable` | engine |
| `MESSAGING_SNAPSHOT_MISMATCH` | A send to a run whose launch snapshot of the messaging switch disagrees with the project's | `messaging_switch_changed` | Lead |
| `COORDINATION_LIMIT` | A coordination message beyond one of its bounds | `coordination_bound` | Lead |
| `LEAD_INBOX_FULL` | The thread already holds the most worker messages not yet shown to the Lead | `inbox_full` | Lead |
| `IDEMPOTENCY_CONFLICT` | An idempotency id already names a message with other content | `idempotency_conflict` | Lead |
| `NOT_A_WORKER` | A coordination message to an invocation that is not a role-bearing worker | `recipient_not_worker` | Lead |
| `RECIPIENT_INDEPENDENT` | A coordination message to an independent confirmer | `recipient_independent` | Lead |
| `RUN_LIVE` | The invocation's latest run may still be running, so a relaunch needs `--replace` | `run_live` | Lead |
| `INTEGRITY_ERROR` | Durable state is damaged, or was modified outside the engine | `state_damaged` | operator |
| `HISTORY_MOVED` | A lock-free reader met a later commit: a race, not damage | `history_race` | engine |
| `DISPATCH_UNDECIDED` | An engine defect: an invocation or run created without a dispatch decision | `engine_defect` | engine |
| `THREAD_UNSEALED` | An engine defect: an invocation ended without its thread sealed | `engine_defect` | engine |
| `MAP_ARTIFACT_CORRUPT` | A project-map artifact no longer hashes to its name, or fails its schema | `map_corrupt` | operator |
| `MAP_REGISTRY_INVALID` | The project-map registry is malformed | `map_registry_invalid` | operator |
| `MAP_ARTIFACT_NONDETERMINISTIC` | Regenerating the selected map gave different bytes | `map_nondeterministic` | operator |
| `MAP_CURRENTNESS_UNPROVEN` | A project map cannot be generated or labelled current from complete inputs | `map_inputs_incomplete` | operator |
| `WORKSPACE_NOT_AUTHORITY` | A workspace copy of AEW state was used as if it were authoritative | `workspace_copy` | Lead |
| `GIT_ERROR` | A git command failed | `git_failed` | operator |
| `LOCK_TIMEOUT` | The control lock could not be taken in time | `lock_contended` | engine |
| `UNAVAILABLE` | This environment cannot provide a capability | `environment_lacks_capability` | operator |
| `HARNESS_ERROR` | A harness run could not be started, supervised or reached | `harness_unreachable` | operator |
| `HARNESS_INCOMPATIBLE` | The harness is unknown, or lacks a capability, model or variant the run needs | `harness_incompatible` | operator |
| `HARNESS_LAUNCH_FAILED` | The launch was committed, but its supervisor did not take custody | `supervisor_no_custody` | Lead |
| `CONTAINMENT_UNAVAILABLE` | Policy requires OS containment, and the run's sandbox could not be established | `containment_unavailable` | operator |

Codes defined outside `aew.errors` are not in this registry yet. They are the typed surface's input refusals
(`aew.surface.errors`), the validation runner's two codes, the dashboard's request codes, and the `cli` escape's
`NOT_COMPLETED`. The specification names `aew.errors` as the registry's source.
