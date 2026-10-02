# AEW quickstart (operator and Lead, M1 to M3)

AEW is harness-neutral: a Lead agent (or a person) drives everything through the `aew` CLI. Bounded roles act only through their own invocation's authority, from inside their Ticket workspace.

The sections below use the CLI directly, with scripted roles and printed credentials. **With M3, the usual way is OpenCode**: the Lead in OpenCode's TUI and every role a harness run, with no credential in any model's hands. See [Running with OpenCode](#m3-running-with-opencode) and `opencode.md`.

## Install

```bash
python3.11 -m venv .venv && . .venv/bin/activate      # Windows: py -3.13 -m venv .venv
pip install -e ".[dev]"
aew doctor
```

Runtime dependencies are PyYAML and jsonschema. Both are already in the SPT py311 offline wheelhouse.

## Operator: initialize a project

```bash
cd <repo>                       # the main worktree, on the authoritative branch
aew init                        # discovers authority *candidates*; confers no authority
$EDITOR .aew/policy/checks.yaml # configure the real test command; gates stay blocked until you do
aew lead acquire --expect-rev 0 --session-label lead-1   # prints the Lead credential ONCE
```

Hand the credential to the Lead session (for example in its environment as `AEW_LEAD_TOKEN`). It is never written to disk.

## Lead: one Ticket, end to end

Every mutation takes `--expect-rev <revision>`. The revision is shown by `aew status`, and each command returns the new one.

```bash
aew authority accept C-001 --class decisions --expect-rev N         # classify candidates
aew work create ticket --title "..." --class 1 --scope "src/**" \
    --goal "observable outcome" --contract "conformance rule" --expect-rev N
aew plan propose T-0001 --file plan.md --assurance none --expect-rev N   # or --review/--verify <card|default>
aew plan accept  T-0001 --revision 1   --expect-rev N               # -> READY
```

Every plan declares its assurance. `--review` and `--verify` name the cards the plan relies on (`default` is the
archetype's default card); accepting the plan makes them required gates, and only a new plan revision changes them.
`--assurance none` declares that the plan adds nothing to the unit's policy path. A review promised only in the plan's
text binds nothing, which is why the declaration is required.

```bash
aew work staff   T-0001 --execute python_engineer --review code_reviewer --expect-rev N   # optional
aew work assign  T-0001 --expect-rev N    # workspace + implementer credential + launch contract/pack
aew work transition T-0001 --to RUNNING --expect-rev N
```

**Free text is data.** Any command takes `--fields FILE|-`: a YAML or JSON mapping of its option values, which become the command's options without passing through a shell. Use it whenever a shell would otherwise see titles, goals, contract clauses, scopes, reasons or notes, because a shell rewrites `$`, backticks, globs and quotes:

```bash
aew work create ticket --class 1 --expect-rev N --fields - <<'EOF'
title: 'Fix #12: show refunds as -$15.00'
goal:
  - 'format_amount(Decimal("-15")) == "-$15.00"'
contract: ['changes stay within ledger/ and tests/']
scope: ['ledger/**', 'tests/**']
EOF
```

The mapping is parsed as YAML, so put each value in single quotes (write `''` for a quote inside one), or write a longer value as a block (`goal: |-` followed by indented lines). Unquoted, YAML would cut `Fix #12` where a space precedes the `#`, and join a value's lines with spaces; AEW refuses such input rather than store changed text, and it also refuses a key given twice, anchors, aliases and tags. JSON works too; its double quotes process escapes, so write a backslash as `\\`.

The quoted `'EOF'` keeps the shell out. In PowerShell, pipe a single-quoted here-string (`@'` … `'@ | aew ...`) instead.

Launch the implementer with its pack (`aew context show INV-0001`) and its credential.

The implementer works in the workspace path printed by `aew work assign`:

```bash
AEW_INVOCATION_TOKEN=<credential> aew -C <workspace> check run unit
AEW_INVOCATION_TOKEN=<credential> aew -C <workspace> submit --kind implementation_report --file report.md
```

Then the Lead moves the Ticket through review, verification and integration:

```bash
aew work transition T-0001 --to REVIEW_PENDING --expect-rev N
aew invoke create T-0001 --expect-rev N            # next planned/default reviewer card + pack + credential
aew review ingest T-0001 --evidence <id> --expect-rev N
aew work transition T-0001 --to VERIFY_PENDING --expect-rev N
aew invoke create T-0001 --expect-rev N            # verifier
aew verify ingest T-0001 --evidence <id> --expect-rev N   # failure? -> aew verify classify (Lead only)
aew work transition T-0001 --to COMMIT_READY --expect-rev N
aew integrate prepare T-0001 --expect-rev N
aew invoke create T-0001 --scope integration --expect-rev N   # post-integration verifier
aew verify ingest T-0001 --evidence <id> --expect-rev N
aew integrate publish T-0001 --expect-rev N         # atomic ref CAS -> DONE + completion record
```

## M2: Epics, Stories and non-mutating Tickets

Small work stays small: a standalone Ticket needs no Story or Epic. When work has structure, create the parents and plan them like Tickets:

```bash
aew work create epic  --title "Toolchain readiness" --class 1 --expect-rev N
aew work create story --title "Durable state" --class 2 --parent E-0001 \
    --mandatory-gate review_security --expect-rev N          # non-waivable for every descendant
aew plan propose S-0001 --file story-plan.md --review default --expect-rev N && aew plan accept S-0001 --revision 1 --expect-rev N
aew work create ticket --title "Survey the store" --class 1 --parent S-0001 --non-mutating \
    --card investigator --goal "..." --expect-rev N         # or researcher / planner
aew work create ticket --title "Harden the store" --class 2 --parent S-0001 \
    --depends-on T-0001:evidence --scope "src/**" --goal "..." --expect-rev N
aew work tree                                               # Epic -> Story -> Ticket, derived states
```

A parent's state is derived (PLANNING, IN_PROGRESS, ACCEPTANCE_PENDING), and `work transition` never changes it. Changing an ancestor's accepted plan (including its first one) stops its descendants until you run `aew plan reconfirm <id> --reason ...` or replan them.

**A non-mutating Ticket** is dispatched, not assigned. It gets its own read-only observation of the authoritative source and no workspace:

```bash
aew work dispatch T-0001 --expect-rev N         # pins executor card + expected output kind (attempt 1)
aew work transition T-0001 --to RUNNING --expect-rev N
AEW_INVOCATION_TOKEN=<credential> aew -C <observation> submit --kind discovery_record --file record.md
aew evidence ingest T-0001 --evidence <id> --expect-rev N
aew work accept T-0001 --expect-rev N           # -> DONE, evidence-only completion record
aew work redispatch T-0001 --reason "..." --expect-rev N   # instead: supersede the attempt, start the next
```

- If a consumed discovery or plan proposal no longer matches the source, the next dispatch of its consumer is refused with `INPUT_STALE`. Refresh the input (a new investigation, plus `aew work depend`), or record that you rechecked it for this commit: `aew work acknowledge-input T-0002 --input <E> --from T-0001 --reason "..."`.
- A Planner's accepted proposal becomes a *proposed* plan revision with `aew plan adopt <T> --evidence <E> --from <planning Ticket>` and the plan's assurance declaration. You still accept it.

**Closing a parent.** When every child is DONE or CANCELLED, the parent is ACCEPTANCE_PENDING. Review and verify the parent (the packs carry every child's own integrated change), then close it:

```bash
aew invoke create S-0001 --role reviewer --expect-rev N    # then: aew review ingest S-0001 ...
aew invoke create S-0001 --role verifier --expect-rev N    # then: aew verify ingest S-0001 ...
aew work close S-0001 --reason "..." --expect-rev N
```

An Epic closes only once the history is audited through the current root: run `aew history audit --expect-rev N` first.

**Structure changes.** Each is a recorded Lead decision:
- `aew work cancel <S|E>` cascades to the parent's open descendants;
- `aew work move <id> --parent <P|none>`;
- `aew work promote <T> --to story --title ...` keeps the Ticket's identity and evidence;
- `aew work depend <id> --add X[:evidence|mutating] --remove Y`.

## Finished work and its history

Finished work leaves the active state when it finishes (ADR-0011). Views show counts and the most recent finished units; the history commands reach the rest by stable id, without knowing where anything is stored:

```bash
aew history list --kind unit --limit 20                     # newest first; --since/--until take UTC times
aew history show T-0042                                     # the record, its annotations and its trust label
aew history show INV-0101                                   # an invocation, credential or evidence of finished work
aew history links T-0042 --depth 2                          # recorded provenance, in both directions
aew history load T-0042 --into T-0107 --reason "..." --expect-rev N   # reference context for T-0107's next packs
aew history audit                                           # advisory verification; add --expect-rev N to record it
```

A loaded record is reference, never current evidence: packs label it, and claims that depend on versions or current state are revalidated through normal evidence. `aew status` reports the audit backlog against the gates policy's optional `history_audit` thresholds.

## M3: running with OpenCode

Configure `.aew/policy/execution.yaml` (which harness, provider, model and effort run each role) and set your provider key, as `opencode.md` describes. Then:

```bash
aew doctor                      # policy:execution PASS; containment WARN (workdir separation only)
aew opencode --acquire          # the Lead in OpenCode's TUI; the Lead credential stays in the session's broker
```

In the TUI, `/aew-ticket <objective>` drafts a Ticket and plan, and `/aew-next <id>` takes one step at a time. Dispatches carry `--launch`, so each role runs in its own private OpenCode server and acts through a run-scoped bridge:

```bash
aew work assign T-0001 --launch --expect-rev N    # run R-INV-0001-1 starts; no credential is printed
aew harness wait R-INV-0001-1 --timeout 110       # its evidence, each item's result, and the next action
aew harness launch INV-0001 --expect-rev N        # relaunch (a fresh session; the credential rotates)
```

A run's end moves nothing: the Lead still ingests and transitions, as above. Every run works with **workdir separation only**, not filesystem containment, so use scratch repositories and clones until containment exists.

## Losing the session

- Run `aew resume` in a fresh session. It is read-only and rebuilds everything from `.aew/`.
- If the old Lead is gone, **the operator** runs `aew lead takeover --reason "..." --expect-rev N` at an interactive terminal and types the challenge code. Agents cannot do this for themselves.
- **With OpenCode:** losing the TUI or its state loses nothing. Run `aew opencode` again and `/aew-resume`. Harness runs keep going, and a lost run is relaunched with `aew harness launch`. A lost harness is not an interruption: the Ticket and its invocation are unchanged.
- After a takeover, in-flight Tickets come back as INTERRUPTED. Inspect them, then `aew work reconcile`. A non-mutating Ticket then continues only with `aew work redispatch` (a new attempt); nothing its interrupted executor submitted is accepted.

## Useful views

`aew guide` (how work flows in this project: risk classes, their gates, the Ticket lifecycle, the command for each step), `aew status`, `aew resume`, `aew work tree`, `aew work show T-0001`, `aew gate show T-0001`, `aew work roles T-0001`, `aew role list`, `aew doctor`, `aew harness status`, `aew harness config opencode <INV>|--lead`.
