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
    review, finding 6).
  - `internal`: started by AEW or the Lead's harness itself; not user-facing. Its `launcher` says what starts it.
- **`users`**: `operator`, `lead`, `worker` or `internal`.
- **`journeys`**: evidence only. It lists the vertical UAT's scenarios that exercise the entry today (`V1` to `V4`,
  [vertical-uat.md](vertical-uat.md) §3), possibly none.
- **`mutates`**: declared, with `mutates_basis` saying how it was determined. The values:
  - `"no"` or `"yes"` (quoted, because YAML reads a bare yes as true);
  - `{with: [--flag, ...]}` when it mutates only with those flags;
  - `unknown`, which is reported, never taken as false.

  The declaration is cross-checked against the code's own markers (check `mutates`).
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

    It is settled before any probe runs, so housekeeping the setup left pending is never blamed on a surface.
  - **The arguments.** The entry's `probe` is one argument list or several. `{ticket}`, `{invocation}`, `{token}` and
    `{invocation_token}` are filled in.
  - **What it asserts.** After each run, every file under the sample's directory is unchanged. That covers:
    - the project and its `.aew/` (the control state and its revision, transitions, evidence, the outbox);
    - the workspaces root beside the project;
    - ignored files;
    - `.git/`'s refs, HEAD, config, hooks and worktrees.

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
| `fields` | enforce | an entry lacks exactly one home, users, a `journeys` list, a valid `mutates` with its basis, or `refusals`; or uses a value outside the vocabulary |
| `users` | enforce | the users contradict the live classification: an operator-only command (`lead_broker.OPERATOR_ONLY`) with any user but `operator`; a Lead-reachable command without `lead`; `worker` on anything but the worker bridge's commands (`bridge.OPERATIONS`), or missing from one |
| `home` | enforce | a `diagnostic` entry whose `mutates` is not `"no"`, or with journeys; an `internal` entry without its `launcher`; a new diagnostic entry without its `diagnostic_justification` |
| `mutates` | enforce | the declaration contradicts the code: a tool's differs from `contract.Tool.mutates`; a command with an expected-revision argument is neither `"yes"` nor `with` that flag; a command taking a credential (Lead or invocation) is neither `"yes"` nor `with` (unless `mutates_exempt` gives the reason); an operator-only command is neither `"yes"` nor `with` (unless `mutates_exempt` gives the reason); a command that runs a primitive is `"no"` |
| `door` | enforce | a Lead-reachable command names no door; a door outside the vocabulary; a typed door not proved (above); a `via` or `partly_via` tool not built on the normal profile, or not running the entry's `primitive`; a primitive that is not the command's |
| `disposition` | enforce | a Lead-reachable command names no `lead_disposition`, or one outside the vocabulary; `typed` without a typed door, or a typed door without `typed` |
| `new_surface` | enforce | an entry outside the baseline breaks the standing rule: Lead-reachable and undecided; mutating with no credential and no mechanism keeping the Lead out (`lead_kept_out_by` with a decided disposition, `OPERATOR_ONLY`, or `internal` with its `launcher`); `typed` without a proved typed door, or still in `LEAD_REACHABLE`; `engine-owned` or `forbidden-to-lead` without its `primitive` (or `none` with a reason), still in `LEAD_REACHABLE`, or run by a typed tool |
| `ideal_path` | enforce | an existing ideal-path command is not registered; a PROPOSED one is not under `proposed`; a proposed command exists now |
| `codes` | enforce | a refusal code is not a code in `aew.errors` |
| `refusal_floor` | enforce | an entry omits a refusal its own arguments imply |
| `owner` | report | a Lead lifecycle operation (a Lead-reachable command, a mutating tool) has no owner: until A1 puts `owner` in the projection |
| `structured_refusals` | report | the refusal inventory is partial, or refusals are not structured: until A2 |
| `mutates_unknown` | report | an entry's `mutates` is `unknown` |
| `undecided` | report | a Lead-reachable command's disposition is `undecided`: until A2's plan decides each |
| `disposition_applied` | report | an `engine-owned` or `forbidden-to-lead` command is still in `LEAD_REACHABLE`: until A4 |
| `lead_shell_lifecycle` | report | a Lead-reachable command is reached by the shell only (the end-state metric, 0): until A4 |
| `unevidenced` | report | a `product`, `operator-admin` or `recovery` entry that no vertical journey exercises yet |
| `probe` | enforce | a surface declared `mutates: "no"` has no `probe`; a probe runs another command; a run changed the sample (named); a probe was refused, or the surface is exempt, outside `PROBE_LIMITED`; a limited surface now runs fully; a new command's probes leave an option unpassed |
| `probe_coverage` | report | the `PROBE_LIMITED` surfaces, with why each is refused on the sample or not run |
| `probe_flags` | report | an option of a `mutates: "no"` command that no probe passes |
| `shell_reachable_mutation` | report | a grandfathered command that mutates, takes no credential, and is kept from the Lead's shell by no stated mechanism |

Each enforced check also has a test that feeds it the drift it exists to catch and asserts that it names the item.

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
