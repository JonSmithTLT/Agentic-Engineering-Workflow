# The vertical UAT (v1): the release gate's measurement

**Status:** in shadow (`VERTICAL_MODE = "shadow"`). It is a test, not a feature, and **it is expected to fail on
today's `main`**: its first job is to measure by how much. Flipping it to `enforce` is the operator's decision, made
when the job is green. This page holds its thresholds; the test module pins the same values and
`tests/unit/test_vertical_ledger.py` checks that the two agree, so **changing a threshold means changing this page,
which needs the operator.** It is an implementation document, not a design.

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
2. If `decisions_required` is non-empty, ask the operator and wait for the reply.
3. Otherwise call the single action the projection marks as next, with **exactly the arguments the projection
   supplied**. Today's projection marks no action as next, so a single AVAILABLE action is taken as the next one; if
   several are AVAILABLE, `ambiguous_next_action` is recorded and the first in order is taken.
4. When the subject is terminal, report the result to the operator: the diff, an evidence summary and the commit.

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
- **V2's reopen.** The ideal step is `aew opencode` with nothing carried over. When it fails, the operator opens the
  Lead the way `docs/guides/opencode.md` documents (`aew opencode --acquire`), and when that is refused, takes the
  seat over at their own terminal and hands the new credential to the session (quickstart, "Losing the session"):
  every step counted, and an INTERRUPTED Ticket or a reconcile recorded as evidence. A reopen from the same shell,
  where the first open's exported credential is still set, is an extra measurement (its own test), never V2's
  verdict.
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

**Any operator fallback fails the verdict.** Every fallback the operator took (each a ledger entry with its evidence)
is listed in the summary and fails the scenario, whether or not one of the counters above classifies it, so a
workaround no counter sees (editing git's own exclude file, for example) can never let the zeros pass.

**Operator decisions** are listed, not counted against: every question AEW or the Lead put to the operator, with the
answer. V1 must list exactly `plan`, `publish`. Any other question fails that comparison and is reviewed by hand: is it
a real product, policy or safety judgement? The summary shows, for each decision, the tool its answer drives and
whose decision the projection says it is (today it says nowhere); the test does not settle that ownership.

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
| `publish_needs_decision` | every scenario | main moves only after the operator's publish decision (or a grant) |
| `containment` | every scenario | every run record carries the platform's containment label, unchanged from today's minimum |

A positive counterpart runs beside the semantic conflict: a **compatible** change (another file) lands on main under
the prepared publish, and AEW should rebuild, re-verify and publish both, with no further question to the operator
after the publish approval.

**Today's minimum containment label:** `workdir_separation_only` on Windows, `os_readonly_roots` on Linux. The test
never weakens it.

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
  today).

## 6. Later (not v1)

- **The live variant:** the same scenarios against real OpenCode 2.0.18 and a real provider, run by the operator. It
  adds the provider key counter and the paid preflight tier (real authenticated calls).
- **A real-model Lead variant:** the same ledger with an actual model as the Lead, to measure what the scripted Lead
  cannot, such as attention spent on judgement, and the Lead's own `aew` shell calls seen at the broker.
