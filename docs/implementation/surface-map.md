# The surface map (anti-drift guard G1)

**Status:** in force (approved by the operator, 2026-10-12; register F47). It is a test and a registry, not a feature:
it changes no product behaviour. Its pinned modes live in `tests/unit/test_surface_map.py` (`CHECKS`), and that test
checks that the table below says the same, so **changing a mode means changing this page.**

## The standing rule for new surfaces (operator, 2026-10-12)

**Every command or tool added from now on ships with its full entry in [`surface-map.yaml`](surface-map.yaml), and its
implementation honours that entry's `lead_disposition` in the same pull request.** Whether the Lead can reach it is
decided by the mechanism, never by the `users` label. The Lead broker gates only the commands that take the Lead
credential, so a command without one runs in the Lead's shell whatever its `users` say (PR 215 second review,
finding 2).

- **A Lead-reachable command:** its disposition is decided, never `undecided`.
- **Any other new command that mutates:** it must do one of the following.
  - Take the Lead credential, so the broker classifies it.
  - Join `OPERATOR_ONLY`.
  - Act only with an invocation credential.
  - Be homed `internal` with its `launcher`.
  - Declare a decided `lead_disposition` with `lead_kept_out_by`: the mechanism, in the code, that keeps the Lead out.

  Until A4 takes `aew` off the Lead's PATH, that mechanism is what honours the disposition. `shell_reachable_mutation`
  reports the grandfathered commands that have no such mechanism today.

**A keep-out claim is proved, never stated** (PR 215 third and fourth reviews). A keep-out claim is a
`lead_kept_out_by`, an `engine-owned` or `forbidden-to-lead` disposition, or an `internal` home.

- **The run.** The entry's `keep_out_probe` runs against the sample in a real Lead session's environment. That
  environment is built from the product's own definition, `lead_broker.ENV_NAMES` (what `run_session` gives the
  harness; it pops `AEW_LEAD_TOKEN`), with synthetic values.
- **The result.** The command must be refused with a code that means "not here" (`PERMISSION_DENIED`, or
  `OPERATOR_AUTHORIZATION_REQUIRED` declared as `keep_out_refusal`), and it must change nothing. The refusal must say
  that the session caused it: its details carry `reason: lead_session` and `variables` naming exactly the session's
  variables that were set. That is how `custody_ops.refuse_lead_session` refuses (PR 215 fifth review, finding 1); a
  message alone proves nothing.
- **The comparison.** The same probe also runs without that environment, with an empty stdin. It must not carry the
  session marker, nor end in the same refusal (code and message), so the refusal is the session's, not the probe's
  arguments'.
- **Today.** `integrate custody` passes: refused by `custody_ops.refuse_lead_session` in a session, and past it, to
  the credential read, outside one.
- **Not a keep-out.** A typed-surface transport (`lead mcp`, `lead tool`) is the Lead's door by design, not a
  keep-out. In the product, `lead_broker.NOT_RELAYED` only stops relaying, so membership proves nothing by itself.
  The test pins the transports to exactly these two (`TRANSPORTS`, digest-pinned, shrink-only), and `users` fails
  whenever `NOT_RELAYED` holds anything else (fifth review, finding 2).
- **Unproved claims.** A claim the test cannot prove would need the pinned, shrink-only `KEEP_OUT_LIMITED` list,
  which is empty.
- **Launchers.** An `internal` home's `launcher` is `{code: "module:attribute"}`. It must produce an argv: a list of
  strings, or a callable that returns one, or a callable that would start one. The words after `aew` must resolve to
  the command. A table that merely mentions it does not count.

  A callable is never run for real (fifth review, finding 3). It is called with synthetic arguments in a temporary
  working directory, while `subprocess.Popen` at its bottom layer (`Popen._execute_child`, so an aliased `Popen` is
  covered), `os.system`, `os.startfile` and `os.spawn*`/`os.exec*`/`os.posix_spawn*` record the argv they are given and
  raise instead of starting a process. Other ways to start one (a C extension, `ctypes`) are not covered. So `custody_ops.spawn_worker`, the real spawner, resolves
  without spawning anything.

The dispositions:

- **`typed`:** the Lead reaches it through a typed tool, an existing one extended or a new one, whose primitive is
  proved (below). It is never reached through the shell, so the command stays out of `lead_broker.LEAD_REACHABLE`.
- **`engine-owned`:** the engine does it. It is not in `LEAD_REACHABLE`, and no typed tool runs it.
- **`forbidden-to-lead`:** operator, admin or diagnostic authority. It is reachable through neither Lead door.

For `engine-owned` and `forbidden-to-lead`, the entry names its `primitive`, so "no typed tool runs it" is checked
against every tool's `expands_to`. A command that has no primitive gives `primitive: none` with its
`primitive_reason`.

The check `new_surface` enforces this for every entry outside the grandfathered baseline. The baseline is the
registry as it stood when the rule was adopted. Its existing `undecided` dispositions stay report-only until A2 and A4.
The baseline may only shrink: its list is pinned by a digest, and an entry leaves it through `GRADUATED`.

## The entry

Every `aew` command (each leaf of the live parser, including the ones that exist only when switched on) and every
typed Lead tool (`aew.surface.contract.TOOLS`) has one entry:

- **`home`**: exactly one intentional home.
  - `product`: a supported normal workflow of the operator, the Lead or a worker.
  - `operator-admin`: the operator's authority, configuration or maintenance.
  - `recovery`: putting interrupted, lost or damaged work right.
  - `diagnostic`: observes or repairs implementation state for an expert or the operator, is needed by no supported
    normal workflow, and changes no authority, policy, work state, evidence admissibility, publication, lifecycle or
    external system (the designer's positive definition, 2026-10-12). So a diagnostic entry is always
    `mutates: "no"`; a command that mutates only with a flag is homed by its mutating form, or split. Its
    `journeys` are empty: a journey that uses it is evidence that a supported workflow needs it (PR 215 second
    review, finding 6). A guide mentioning a command as a way to inspect state does not make it a workflow step;
    journeys do.
  - `internal`: started by AEW or the Lead's harness itself; not user-facing. Its `launcher` says what starts it.
- **`users`**: `operator`, `lead`, `worker` or `internal`.
- **`journeys`**: evidence only. It lists the vertical UAT's scenarios that exercise the entry today (`V1` to `V4`,
  [vertical-uat.md](vertical-uat.md) §3), possibly none.
- **`mutates`**: declared, with `mutates_basis` saying how it was determined. The values:
  - `"no"` or `"yes"` (quoted, because YAML reads a bare yes as true);
  - `{with: [--flag, ...]}` when it mutates only with those flags.

  The declaration is cross-checked against the code's own markers (check `mutates`). A `"yes"` the sample would not
  show by itself, because the surface is a no-op when its output is current, carries a `mutates_proof`: the file to
  remove and the probe that writes it again (`context pack`).
- **`door`**, for every command a Lead session may relay (`LEAD_REACHABLE`): how the Lead reaches it today.
  - `typed`: its lifecycle use has a typed home. `via` names the tools, and `primitive` names the step they run.
  - `shell-only (pending A2/A4)`: only by `aew` from the shell or the recovery `cli` tool. `partly_via` names tools
    that cover some of its uses.

  A read with a typed equivalent (`aew status` and the `status` tool, for example) may also carry `door: typed` and
  `via`.
- **`lead_disposition`**, for every Lead-reachable command: the end state. It is `typed`, `engine-owned`,
  `forbidden-to-lead`, or `undecided` until A2's plan decides it with its reason.
  - Today, a command whose current tool already covers it is `typed`, and every other is `undecided`.
  - Dispositions are not this guard's to decide. The point is not one typed button per command: A2's plan decides
    which needs the Lead really has (`typed`), which the engine should own, and which the Lead must never reach.
- **`owner`**, for a Lead lifecycle operation: the owner A1's projection will mark on it (`operator`, `lead` or
  `mechanical`). It is `pending (A1)` until then.
- **`refusals`**: the `aew.errors` codes it is known to raise.
  - The floor comes from its arguments:
    - any command: `USAGE`;
    - a Lead credential: `PERMISSION_DENIED` and `STALE_AUTHORITY`;
    - any expected revision (`--expect-rev`, `--expect-map-rev`): `STALE_REVISION`;
    - a mutating tool: the same.
  - On top of the floor: `PROJECT_NOT_FOUND` where it opens a project, and the codes its own handler raises.
  - `refusal_status` says the inventory is partial and the refusals are not yet structured (a cause, a remedy and an
    owner each). A2 delivers both.

**A typed door is proved, never just claimed** (PR 215 review, finding 1). For a Lead-reachable command, a typed door
needs all of these:

- `via`, naming built tools on the normal profile;
- a `primitive` that those tools run, with a declared side effect in `aew.engine.primitives.SPECS`;
- a primitive that names this command. Its words are the command's words (`work.create` is `aew work create`;
  `invoke.create.mutating` starts with `invoke create`), or one of the aliases: `stage.resolve` for
  `stage continue` and `stage abandon`, and `steering` for `lead mode lower`.

**A home never exempts anything** (the designer's question, 2026-10-12: can a lifecycle-changing command avoid
the checks by being labelled diagnostic? No, by construction):

- **Doors and dispositions key off the code, not the label.** The door, disposition and new-surface checks key off
  `LEAD_REACHABLE` and the typed surface, never off `home`. A Lead-reachable command needs a disposition whatever its
  home, and a new one needs a decided disposition.
- **`mutates` is cross-checked against the code's markers.** A credential (`--token` or `--invocation-token`), any
  expected revision, or membership of `OPERATOR_ONLY` means `"yes"` or `with`, unless the entry gives
  `mutates_exempt` with its reason (reviewed like any change). A tool's `mutates` equals `contract.Tool.mutates`.
- **A behavioural probe runs every surface declared `mutates: "no"`.**
  - **The sample.** `aew` runs in process; the sample's own git setup runs as subprocesses with no window. The sample
    project is:
    - a git repository;
    - `aew init`, with messaging and recall search switched on and adopted, so their commands exist;
    - a Lead;
    - one Ticket with an accepted plan, assigned without a launch, so its invocation `INV-0001`, its workspace and its
      pack exist.

    It is settled before any probe runs, so housekeeping the setup left pending is never blamed on a surface. The
    settling may remove only the spent redo records under `.aew/state/txn/`; anything else fails.
  - **The arguments.** The entry's `probe` is one argument list or several. `{ticket}`, `{invocation}`, `{token}` and
    `{invocation_token}` are filled in.
  - **What it asserts.** After each run, every file under the sample's directory is unchanged. That covers:
    - the project and its `.aew/` (the control state and its revision, transitions, evidence, the outbox);
    - the workspaces root beside the project;
    - ignored files;
    - `.git/`'s refs, HEAD, config, hooks and worktrees;
    - what git's index holds: what is staged, and what is marked assume-unchanged (`git status --porcelain=v2`,
      `git ls-files -s -v`).

    The exceptions are the derived history and recall indexes and git's object store and index stat caches.
  - **Each probe must run the command's real path (exit 0).** A probe refused on the sample, or a `probe_exempt`, is
    accepted only for the surfaces in the test's `PROBE_LIMITED` list, each with its reason in the registry
    (`probe_refused`). The list is digest-pinned and only shrinks. A limited surface whose probe starts to run fully
    must leave it. `probe_coverage` reports the list.
  - **Options.** A mutation behind an option no probe passes is out of the probe's sight. `probe_flags` reports those
    options, and a new command is probed with every option it takes (PR 215 second review, finding 3).
  - **A probe that ran but had nothing to do** proves nothing about the surface's real work. Such a surface is
    declared by what it does, not by what the sample shows. `history compact`, which acts only past a 4,096-revision
    window, is declared `"yes"` (finding 5).
- **A new diagnostic entry justifies its home.** It gives `diagnostic_justification`: one line matching the positive
  definition, saying what implementation state it observes or repairs, for whom, and why no supported normal workflow
  needs it.

The registry also lists, under `proposed`, the commands the vertical UAT's ideal path (`IDEAL_PATH`) names that do not
exist yet. When one is built, it moves to `commands`.

**A `resolve` home is proved by its pair** (the A1 slice plan, reviewed CLEAR, §2.1 item 4). `resolve` runs one
primitive per call, chosen by its `choice`, so its `expands_to` alone would accept it as the home of any of them. A
command `resolve` homes names the (choice, subject kind) pairs that home it (`via_choices: {choice: [kind, ...]}`),
and each must be in `aew.surface.contract.RESOLVE_CHOICE_PRIMITIVE` and run the command's primitive. So one choice can
home two commands by subject kind (A2's `cancel`: a unit's `work.cancel`, an invocation's `invoke.cancel`). That
mapping owns the choices, their order and `resolve`'s `expands_to`.

## The planned dispositions (A1-0)

The A1 slice plan (reviewed CLEAR, §2) decides where each still-`undecided` command goes. Until its homes exist, the
registry records the plan, not the decision:

- **`planned`**, on every `undecided` command and only there: `{disposition, homes, primitive, lands, reason}`.
  - `disposition`: `typed`, `engine-owned` or `forbidden-to-lead`.
  - `homes`: for a typed plan, the typed tools (built, or under `proposed_tools`) and `resolve` choices, written
    `R(<choice>)` (built in `RESOLVE_CHOICE_PRIMITIVE`, or under `proposed_choices`), that will reach it. An empty list
    means no home is designed yet (`work dispatch` and `work redispatch`, an A2 design item). Other plans have none.
  - `primitive`: the step the homes run, named like a typed door's (or `none`).
  - `lands`: the slice that builds the homes and decides the row, from the vocabulary's `lands`.
- **`proposed_tools`** (with the `expands_to` each will have) and **`proposed_choices`** (with their
  `(subject kind: primitive)` pairs): the homes not built yet.
- **Shrink-only.** The planned rows and both proposal lists are pinned in the test by their digests. The registry
  holds exactly the pinned entries less those that graduated, so one leaves only through its graduated list, and none
  is added.
- **Every use is accounted for** (`planned_coverage`; the A1-0 review's F1 and F2). A typed plan's homes must cover
  every use of its command before the row can be decided. Four scans derive the uses from the code, for every
  planned row:
  - **transition edges:** every `transitions.RULES` edge whose operation the command runs. The operation's command
    comes from the engine's own `transitions._COMMANDS`, else `work <via>` when that command is live. That table is
    one-valued: it gives one command per operation, while in the code three operations have more callers (`work
    cancel`'s cascade and `work promote` also take `transition` edges, `work dispatch` also takes `assign`, and
    `integrate.validate` maps to no command). None hides a gap today: `R(cancel)` and `work_amend` cover their
    fixed edges, `work dispatch`'s row is wholly uncovered, and the validation row is engine-owned.
  - **dispatch entrypoints:** every `dispatch.ENTRYPOINTS` entry whose `cli` is the command;
  - **state-selected entrypoint uses** (the re-review's N2): a dispatch guard whose if/elif chain selects among a
    unit's states (two links or more, read from the guard's source) gives its entrypoint one use per state. Today
    that is `invoke.slot`: a prepared COMMIT_READY with scope integration, ASSIGNED and RUNNING (implementer),
    REVIEW_PENDING (reviewer) and VERIFY_PENDING (verifier).

    **What counts as a unit's state** (the re-review's N4):
    - **The unit:** a name assigned from an expression that indexes `"work"`, or that calls a `unit(...)` accessor
      (`self.units.unit(state, w)`).
    - **Its state:** `unit["state"]`, `unit.get("state")`, or a name assigned from either.
    - **The states compared:** string literals, collections of them, or a constant. A bare constant name resolves
      through the guard's module and the engine's constants (`st in EXECUTE_STATES`); a module-qualified one
      (`H.TERMINAL`) resolves through the guard's module.
    - **What the scan cannot read** as "selects these states" becomes a `?` state carrying its source, never dropped
      and never misread (the re-reviews' N5 and N7). That covers:
      - an unresolved constant;
      - reversed operands (`'B' == st`);
      - a method test (`st.startswith(...)`);
      - a negation (`st not in {...}`, or `not (...)` as a link's own test);
      - a call given the state or the unit (`is_terminal(st)`, `H.done(unit)`);
      - any other link test that reads the state, or passes the unit to a call, yet yields no states.

      So the scan fails closed. A `not (...)` in a branch's body keeps its states, because
      `if not (st == X ...): raise` is how a link requires X. The agreement test refuses any `?` state on the
      engine.

    **A second, form-agnostic detector must agree.** It counts a guard's `if`/`elif` lines that compare anything
    reading like a state, or call a method on it. The agreement holds at two levels:
    - **Per guard:** over every registered guard, its set must equal the scan's, less stated exclusions.
      `queue.order` is excluded because it selects among a queue entry's states, not a unit's.
    - **Per link:** for each guard the scan finds, its line count must equal the scan's link count.

    Both detectors read the guards that `DispatchGuard("name", self._method)` registers, by any name the module
    binds it to: an import alias such as `DispatchGuard as DG`, or an assignment. The test also asserts that this is
    every `DispatchGuard` call in `src/aew`, in any form, including aliases and `module.DispatchGuard` (the
    re-reviews' N6 and N8). So a chain, or a link,
    or a registration that one side cannot read fails the test rather than quietly dropping uses.
  - **options:** every option and positional of the live parser's command, less the generic ones (the Lead
    credential, the expected revisions, the print-only options).

  **What covers a use:**
  - **A built stage's transition step** covers the edges its `work.transition` step takes, into its fixed target
    (`availability.STAGES`). The sources are the state its producing step leaves, or, when no earlier step produces
    one, the sources of edges into the target that the step's own arguments can take. An edge that requires a reason
    is taken only by a step that passes one (the re-review's N1).
  - **A built stage's dispatch step** covers a state-selected use only if the stage *starts* in that state: no
    earlier step of it produces the state, and its arguments select the branch. A home that reaches the state
    through its own transition cannot replace a lost invocation of a unit already there.
  - **A proposal** covers the edges its `transitions` name (`*` for any state); a proposal running `work.transition`
    must name them. A proposal covers no state-selected use.
  - **Any other edge** is covered by a home whose primitive names the edge's command, and an entrypoint by a home
    that runs it.
  - **Options** are covered by the plan's `options` map. It classifies every option the parser gives (none missing,
    none stray) as `homes` (all of the row's homes), one named home, `uncovered` or `retired`. A covered option is
    covered over its whole domain: a flag's both values, and every value of a repeatable option.

  The uses no typed home covers, built or proposed, are the plan's `uncovered: {lands, uses}`. That list is the
  scans' output, checked equal to them, never typed in. A plan that is not typed has neither key: its command leaves
  the Lead's doors.
- **Home built ⇒ row decided** (`home_built`). The trigger is every home of a planned row built and running its
  primitive, and every use of the command covered by a built home. When it holds, the same change sets the row
  `typed` (door typed, `via`, `primitive`) and drops `planned`; a built proposal leaves its section. A built home
  that does not run the primitive yet is an A2 debt, which `planned_sweep` reports.
- **Out of the door ⇒ row decided** (`out_of_door`). A command that has left `LEAD_REACHABLE` is not `undecided`;
  `keep_out` then proves an `engine-owned` or `forbidden-to-lead` one.
- **What the checks cannot see.**
  - `home_built` reads the homes a plan names. A tool that starts to run a planned row's primitive without being
    named in its `homes` is not seen by it; `new_surface` and `door` still hold it to the standing rule once the row
    is decided.
  - The option scan derives the option set, not its meaning. Whether a home's argument really does what an option
    does is the classification's judgment, which review checks.
  - A stage that runs from more states than its producing step leaves is not credited with them.
  - A built stage's earlier steps are not checked against a state-selected use's state. The scan credits a dispatch
    step that has no state-producing step before it with every branch its arguments select.
  - A state check inside a helper a guard calls (`require_launchable`, for example) is a single precondition, not a
    branch.
  - A guard selecting by something other than an if/elif chain on the unit's state is not seen.
  - Both state detectors miss a chain on a state read through an arbitrary helper into a variable not named like a
    state. The test pins this as a probe. Either detector alone seeing a chain fails the agreement test.
  - A built `resolve` choice that runs `work.transition` covers no edge until its edges have an owner in the code.
  - Routes of two or more steps are not scanned.
  - A use that is neither an edge, an entrypoint, a state-selected entrypoint use nor an option is not seen.

## The end-state metric

The end state is not "48 typed equivalents". It is **every Lead lifecycle need covered by typed or engine-owned
behaviour, and Lead shell lifecycle operations = 0** (designer, 2026-10-12).

Today there are 48 Lead-reachable commands:

- 12 have a proved typed door, disposition `typed`.
- 36 are shell-only, disposition `undecided`. They are the Lead's shell lifecycle operations, which `lead_shell_lifecycle`
  reports.

That check becomes `enforce` at A4.

## The checks

The test (fast lane; `aew` in process, git subprocesses with no window) builds the live parser with every switched
command registered. The probe runs one surface per test, so xdist spreads it and a failure names its own test. It reads the live tool catalog, the primitive declarations and the vertical UAT's `IDEAL_PATH`, and runs
each check.

- An `enforce` check fails, naming every item it finds.
- A `report` check computes its findings the same way and prints them as a warning (`SurfaceMapReport: ...`) without
  failing.
  - It prints under any warning filter (`-W error`, an ignore filter, the default) and under xdist.
  - When `AEW_SURFACE_MAP_REPORT` names a directory, it also writes `surface-map-<check>.json` there.
  - It is enforced when the slice it waits for lands. A tripwire test fails, saying so, once its findings reach zero
    on `main`.

| Check | Mode | Fails (or reports) when |
|---|---|---|
| `registered` | enforce | a live command or tool has no entry |
| `live` | enforce | an entry names a command or tool that no longer exists, or is registered twice |
| `fields` | enforce | an entry lacks exactly one home, users, a `journeys` list, a valid `mutates` with its basis, or `refusals`; or uses a value outside the vocabulary; an undecided command has no `planned`, or a decided one keeps it; a plan's disposition, homes, primitive, landing slice or reason is missing or invalid (below); a proposal homes no planned row |
| `users` | enforce | the users contradict the live classification: an operator-only command (`lead_broker.OPERATOR_ONLY`) with any user but `operator`; a Lead-reachable command without `lead`; `worker` on anything but the worker bridge's commands (`bridge.OPERATIONS`), or missing from one |
| `home` | enforce | a `diagnostic` entry whose `mutates` is not `"no"`, or with journeys; an `internal` entry whose `launcher` does not resolve to code that starts the command; a new diagnostic entry without its `diagnostic_justification` |
| `mutates` | enforce | the declaration contradicts the code: a tool's differs from `contract.Tool.mutates`; a command with an expected-revision argument is neither `"yes"` nor `with` that flag; a command taking a credential (Lead or invocation) is neither `"yes"` nor `with` (unless `mutates_exempt` gives the reason); an operator-only command is neither `"yes"` nor `with` (unless `mutates_exempt` gives the reason); a command that runs a primitive is `"no"` |
| `door` | enforce | a Lead-reachable command names no door; a door outside the vocabulary; a typed door not proved (above); a `via` or `partly_via` tool not built on the normal profile, or not running the entry's `primitive`; a primitive that is not the command's; a command `resolve` homes without `via_choices`, or naming a (choice, subject kind) pair that is not in `RESOLVE_CHOICE_PRIMITIVE` or does not run its primitive; `via_choices` on any other command |
| `disposition` | enforce | a Lead-reachable command names no `lead_disposition`, or one outside the vocabulary; `typed` without a typed door, or a typed door without `typed` |
| `new_surface` | enforce | an entry outside the baseline breaks the standing rule: Lead-reachable and undecided; mutating with no credential and no mechanism keeping the Lead out (`lead_kept_out_by` with a decided disposition, `OPERATOR_ONLY`, or `internal` with its `launcher`); `typed` without a proved typed door, or still in `LEAD_REACHABLE`; `engine-owned` or `forbidden-to-lead` without its `primitive` (or `none` with a reason), still in `LEAD_REACHABLE`, or run by a typed tool |
| `ideal_path` | enforce | an existing ideal-path command is not registered; a PROPOSED one is not under `proposed`; a proposed command exists now |
| `codes` | enforce | a refusal code is not a code in `aew.errors` |
| `refusal_floor` | enforce | an entry omits a refusal its own arguments imply |
| `owner` | report | a Lead lifecycle operation (a Lead-reachable command, a mutating tool) has no owner: until A1 puts `owner` in the projection |
| `structured_refusals` | report | the refusal inventory is partial, or refusals are not structured: until A2 |
| `undecided` | report | a Lead-reachable command's disposition is `undecided`: until A2's plan decides each |
| `disposition_applied` | report | an `engine-owned` or `forbidden-to-lead` command is still in `LEAD_REACHABLE`: until A4 |
| `lead_shell_lifecycle` | report | a Lead-reachable command is reached by the shell only (the end-state metric, 0): until A4 |
| `unevidenced` | report | a `product`, `operator-admin` or `recovery` entry that no vertical journey exercises yet |
| `probe` | enforce | a surface declared `mutates: "no"` has no `probe`; a probe runs another command; a run changed the sample (named); a probe was refused, or the surface is exempt, outside `PROBE_LIMITED`; a limited surface now runs fully; a new command's probes leave an option unpassed |
| `probe_coverage` | report | the `PROBE_LIMITED` surfaces, with why each is refused on the sample or not run |
| `probe_flags` | report | an option of a `mutates: "no"` command that no probe passes |
| `keep_out` | enforce | a keep-out claim (`lead_kept_out_by`, `engine-owned`, `forbidden-to-lead`, an `internal` home other than a `NOT_RELAYED` transport) has no `keep_out_probe`; declares a refusal that does not mean "not here"; in a real Lead session's environment is not refused with it or changes the sample; or is refused the same way outside one; outside `KEEP_OUT_LIMITED` (empty) |
| `keep_out_coverage` | report | the `KEEP_OUT_LIMITED` claims, with why each is not proved by running it |
| `shell_reachable_mutation` | report | a grandfathered command that mutates, takes no credential, and is kept from the Lead's shell by no stated mechanism |
| `home_built` | enforce | a proposed tool or `resolve` choice is built now and still proposed; every home of a planned row is built and runs its primitive, and built homes cover every use of its command, yet the row is undecided |
| `planned_coverage` | enforce | a typed plan's `uncovered` differs from what the four scans derive (transition edges, entrypoints, state-selected entrypoint uses, options); it does not classify exactly its command's options; names an option's home outside its homes; states `uncovered` uses other than the scans derive (or omits them); a plan that is not typed has `options` or `uncovered`; a proposal runs `work.transition` without naming its `transitions` |
| `out_of_door` | enforce | a command that has left `LEAD_REACHABLE` is still `undecided` |
| `planned_sweep` | report | a planned typed row's home, built or proposed, that does not run its primitive yet: the A2 debts |
| `planned_by_slice` | report | the planned rows, by the slice they land in: until every row is decided |

Each enforced check also has a test that feeds it the drift it exists to catch and asserts that it names the item.
Each check that reads the code also has an **ablation**: the code input loses the property, by monkeypatching the
live constant or function, and the check must name it. The inputs ablated include the worker bridge's operations,
`OPERATOR_ONLY`, `LEAD_REACHABLE`, a tool's `expands_to` and `mutates`, the tool catalog, `IDEAL_PATH`, an error
code, the launcher, a guard keyed on the wrong variable, a refusal that is not the session's, and a command that
stops writing what its `mutates_proof` shows. The pins and the shrink-only lists are ablated too. So no check can
pass by reading a copy of what it guards, or by passing whatever happens.

## Changing the map

- **A new command or tool:** add its full entry, and honour its disposition in the same pull request (the standing
  rule above).
- **A command whose disposition A2's plan decides:** set it. Then make the code honour it (A2, A4), and let it leave
  the baseline through `GRADUATED`.
- **A new refusal code** that an entry lists must exist in `aew.errors`. The full refusal registry is the vertical
  UAT's output-rules guard, a separate guard. It records each code's meaning, its allowed causes and its remedy's
  owner.
- **A mode change** (report to enforce, when A1, A2 or A4 lands) changes the table above and `CHECKS` together. Bump
  the registry's `version` when an entry's meaning changes.
