# The surface map (anti-drift guard G1)

**Status:** in force (approved by the operator, 2026-10-12; register F47). It is a test and a registry, not a feature:
it changes no product behaviour. Its pinned modes live in `tests/unit/test_surface_map.py` (`CHECKS`), and that test
checks that the table below says the same, so **changing a mode means changing this page.**

## The rule

Every `aew` command (each leaf of the live parser, including the ones that exist only when switched on) and every
typed Lead tool (`aew.surface.contract.TOOLS`) has one entry in [`surface-map.yaml`](surface-map.yaml), added in the
same change that adds the command or tool. An entry says:

- **`users`**: `operator`, `lead`, `worker`, `internal` (started by AEW or the Lead's harness, never typed) or
  `diagnostic`;
- **`journeys`**: the vertical UAT's scenarios that need it (`V1` to `V4`, [vertical-uat.md](vertical-uat.md) §3),
  `diagnostic` for a read no journey depends on, or `unmapped` when no journey uses it yet, which means a decision is
  owed: name the journey that needs it, or retire it;
- **`door`**, for every command a Lead session may relay (`lead_broker.LEAD_REACHABLE`): `typed` when the Lead's
  lifecycle use of it has a typed home (`via` names the tools, and `primitive` the step they run), or
  `shell-only (pending A2/A4)` when the Lead reaches it only by `aew` from its shell or the recovery `cli` tool
  (`partly_via` names the tools that cover some of its uses). This makes the one-door gap of the vertical path's
  shift 1 explicit, command by command; A2 gives the Lead's lifecycle operations their typed homes and A4 closes the
  shell door;
- **`owner`**, for a Lead lifecycle operation: the owner A1's projection will mark on it (`operator`, `lead` or
  `mechanical`); `pending (A1)` until then;
- **`refusals`**: the `aew.errors` codes it is known to raise. The floor is derived from its arguments (any command:
  `USAGE`; a Lead credential: `PERMISSION_DENIED` and `STALE_AUTHORITY`; an expected revision: `STALE_REVISION`; a
  mutating tool likewise), plus `PROJECT_NOT_FOUND` where it opens a project and the codes its own handler raises.
  `refusal_status` says the inventory is partial and the refusals are not yet structured (a cause, a remedy and an
  owner each): A2 delivers both.

The registry also lists, under `proposed`, the commands the vertical UAT's ideal path (`IDEAL_PATH`) names that do not
exist yet. When one is built, it moves to `commands`.

## The checks

The test (fast lane, in-process: no subprocess, no window) builds the live parser with every switched command
registered, reads the live tool catalog and the vertical UAT's `IDEAL_PATH`, and runs each check. An `enforce` check
fails, naming every item it finds. A `report` check computes its findings the same way and lists them as a
warning (`SurfaceMapReport: ...`) without failing: it is enforced when the field it waits for is delivered.

| Check | Mode | Fails (or reports) when |
|---|---|---|
| `registered` | enforce | a live command or tool has no entry |
| `live` | enforce | an entry names a command or tool that no longer exists, or is registered twice |
| `fields` | enforce | an entry names no users or no journeys, or one outside the vocabulary, or `unmapped` beside a journey |
| `users` | enforce | the users contradict the live classification: an operator-only command (`lead_broker.OPERATOR_ONLY`) with any user but `operator`; a Lead-reachable command without `lead`; `worker` on anything but the worker bridge's commands (`bridge.OPERATIONS`), or missing from one |
| `door` | enforce | a Lead-reachable command names no door; a door outside the vocabulary; a `typed` door without `via`; a named tool not built on the normal profile, or not running the entry's `primitive` |
| `ideal_path` | enforce | an existing ideal-path command is not registered; a PROPOSED one is not under `proposed`; a proposed command exists now |
| `codes` | enforce | a refusal code is not a code in `aew.errors` |
| `refusal_floor` | enforce | an entry omits a refusal its own arguments imply |
| `owner` | report | a Lead lifecycle operation (a Lead-reachable command, a mutating tool) has no owner: until A1 puts `owner` in the projection |
| `structured_refusals` | report | the refusal inventory is partial, or refusals are not structured: until A2 |
| `one_door` | report | a Lead-reachable command is shell-only: until A2 and A4 |
| `unmapped` | report | an entry waits for a journey decision |

A report check never hides its findings: they print in every run's warnings summary
(`python -m pytest tests/unit/test_surface_map.py`). Each enforced check also has a test that feeds it the drift it
exists to catch and asserts it names the item.

## Changing the map

- **A new command or tool:** add its entry. Name its journey from the vertical UAT; if none needs it, `unmapped`, and
  say so in the pull request, since that is a decision someone owes.
- **A command made Lead-reachable:** give it a door. `typed` only when the Lead's use of it has a typed home.
- **A new refusal code** that an entry lists must exist in `aew.errors`. The full refusal registry (each code's
  meaning, its allowed causes and its remedy's owner) is the vertical UAT's output-rules guard, a separate guard.
- **A mode change** (report to enforce, when A1 or A2 lands) changes the table above and `CHECKS` together. Bump the
  registry's `version` when an entry's meaning changes.
