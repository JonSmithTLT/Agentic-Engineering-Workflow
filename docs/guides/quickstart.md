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
aew init --check-command "{python} -m pytest -q" --model openai/gpt-6-sol   # also discovers authority *candidates*; confers no authority
aew doctor
aew opencode --acquire
```

`aew init` takes the first configuration in that one call and writes it before it pins, so a fresh setup needs no hand
edit, no adopt and no credential. On contained Linux a worker uses the saved API-key login through the built-in
provider relay when the policy names that provider's variable and its other names are set or are other built-in
providers' key variables. One login decides per provider for the Lead and workers. If the Lead uses a refreshing
login for a provider, keep it and export that provider's API key for workers. For an explicit override or a legacy
launch, use the
shell-only forms below with the provider variable in place of `AEW_LEAD_TOKEN`. Use `aew opencode --provider-env NAME`
when feeding the Lead's own model from that export. A certificate-only provider skips key setup.

- **`--check-command`** sets the `unit` check. It's split as POSIX on every platform, with no shell, and `{python}` is
  the running Python. The result prints the argv. A command that would pin something broken is refused: empty or
  unparseable; a bare shell operator (`&&`, `||`, `|`, `;`, `<`, `>`) or a leading `VAR=`, which take a shell you name
  yourself (`sh -c '"{python}" -m pytest && make'`, with `{python}` in double quotes because that shell reads its path);
  a backslash outside single quotes, which this split would spend (write `/` or `{python}`). Nothing else is refused:
  with no shell, nothing expands `~`, `$VAR` or a glob, and a lone `&` is an argument, so read the printed argv.
  **`--check-timeout SECONDS`** goes with it.
- **A check command is not a place for a credential.** AEW doesn't scan it, and it sits in plain text in
  `.aew/policy/checks.yaml`, which goes wherever that file is committed.
- **`--model`** sets the workers' model, written as the harness lists it, in one profile named `default`; **`--provider`**
  goes with a bare id. They don't set the Lead's own model. For a provider that needs a key, `provider_env` gets the
  variable's name. `aew init` only records the name. Use a paid model. An unknown provider takes the route below, as
  does a proxy variable such as `HTTPS_PROXY`.
- **No check or model runs at init.** The check isn't run and the model isn't looked up: `aew doctor` has
  `provider-env` and `model-refs`. Init does read your repository once, to make the first project map from the branch's
  head when it has a commit. Its report's `map` line says what happened, and a map that can't be made never fails init.
- **On an initialized project** `aew init` is refused, flags or not. One interrupted before it finished may run again,
  with other values.

Everything after the pin goes through the Lead credential and an adopt. That's also the route for what the flags don't
cover. On a project already initialized, skip this block's first line, which `aew init` would refuse:

```bash
aew init                        # discovers authority *candidates*; confers no authority
$EDITOR .aew/policy/checks.yaml # configure the real test command; gates stay blocked until you do
aew lead acquire --expect-rev 0 --session-label lead-1   # shows the Lead credential ONCE, on your terminal
aew manifest adopt --reason "configured the test command" --expect-rev 1   # asks for the Lead credential, hidden
```

**The two routes don't mix.** `aew lead acquire` holds the seat, and a held seat refuses `aew opencode --acquire`, so a
Lead session on that route starts with `aew opencode` and your credential. `--acquire` itself never shows a credential (a
session that exits with work in flight keeps the seat, and taking that over shows one), so the authority candidates wait:
they block nothing, and you classify them after the session exits and releases the seat, through `aew lead acquire`. That
holds the seat again, so when you've classified them, `aew lead release` gives it up (with `--expect-rev` and the revision
from `aew status`, like any change) and `--acquire` works again.

The policy files under `.aew/policy/` are pinned like `project.yaml`: after any edit, every Lead change is refused until
you review it and run `aew manifest adopt` (a recorded decision). Adopt asks you to type back a one-time code at your
own terminal, so the Lead, which has no terminal, can never approve a policy change it made.

### Giving AEW the Lead credential

A command that needs the Lead credential asks for it at a hidden prompt on your terminal, and uses it for that command
only. Nothing you type there is shown or lands in your shell's history. Never put the credential on a command line:
`--token` takes no value, because a command line is saved in your shell's history.

To run several commands, or a Lead session (`aew opencode`, `aew lead session`), without the prompt, set
`AEW_LEAD_TOKEN` with one of these forms. Each echoes nothing and leaves nothing in history:

```bash
read -rsp 'Lead token: ' AEW_LEAD_TOKEN; echo; export AEW_LEAD_TOKEN    # bash
```

```powershell
$env:AEW_LEAD_TOKEN = Read-Host "Lead token" -MaskInput                 # PowerShell 7
$s = Read-Host "Lead token" -AsSecureString; $env:AEW_LEAD_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)); Remove-Variable s    # Windows PowerShell 5.1
```

Set it for this shell session only: a persistent variable reaches every process you start, and a startup file is a
plain file in your home directory, like history. A Lead session removes it from its harness's environment and holds
the credential in its broker's memory; `--acquire` takes a vacant seat instead. The credential is never written to disk.
Once a Lead session (`aew opencode`, `aew lead session`) is running, AEW never asks for the Lead credential inside the
Lead's own window: a prompt there is not AEW's.

A command that issues a credential writes it only to your terminal, never to standard output, and the JSON result says
`"(written to your terminal)"` instead. With no terminal (a pipe, a harness tool call) it is refused before anything is
issued. A script that keeps the credential safe can ask for it on standard output with `aew --print-credential ...`;
a Lead session refuses that flag.

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
aew work assign  T-0001 --expect-rev N    # workspace + launch contract/pack; the implementer credential on your terminal
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

A project created before ADR-0011 has control state v1, where finished work stays in the active state. Its Lead migrates it once, with no harness run live; until then the Lead's other changes are refused with `MIGRATION_REQUIRED`:

```bash
aew migrate --expect-rev N    # finished work moves to the history in one transaction; running it again does nothing
```

Finished work leaves the active state when it finishes (ADR-0011). Views show counts and the most recent finished units; the history commands reach the rest by stable id, without knowing where anything is stored:

```bash
aew history list --kind unit --limit 20                     # newest first; --since/--until take UTC times
aew history show T-0042                                     # the record, its annotations and its trust label
aew history show INV-0101                                   # an invocation, credential or evidence of finished work
aew history links T-0042 --depth 2                          # recorded provenance, in both directions
aew history load T-0042 --into T-0107 --reason "..." --expect-rev N   # reference context for T-0107's next packs
aew history load INV-0101-discovery-1 --into T-0107 --reason "..." --expect-rev N   # or an exact evidence record
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
aew harness wait R-INV-0001-1 --timeout 110       # its evidence, each item's result, and the next action (exit 20: no evidence)
aew harness launch INV-0001 --expect-rev N        # relaunch (a fresh session; the credential rotates)
```

A run's end moves nothing: the Lead still ingests and transitions, as above. Every run works with **workdir separation only**, not filesystem containment, so use scratch repositories and clones until containment exists.

## Losing the session

- Run `aew resume` in a fresh session. It is read-only and rebuilds everything from `.aew/`.
- If the old Lead is gone, **the operator** runs `aew lead takeover --reason "..." --expect-rev N` at an interactive terminal and types the challenge code. Agents cannot do this for themselves.
- **With OpenCode:** losing the TUI or its state loses nothing. Run `aew opencode` again and `/aew-resume`. Harness runs keep going, and a lost run is relaunched with `aew harness launch`. A lost harness is not an interruption: the Ticket and its invocation are unchanged.
- After a takeover, in-flight Tickets come back as INTERRUPTED. Inspect them, then `aew work reconcile`. A non-mutating Ticket then continues only with `aew work redispatch` (a new attempt); nothing its interrupted executor submitted is accepted.

## Useful views

`aew guide` (how work flows in this project: risk classes, their gates, the Ticket lifecycle, the tool or command for each step), `aew status`, `aew resume`, `aew work tree`, `aew work show T-0001`, `aew gate show T-0001`, `aew work roles T-0001`, `aew role list`, `aew doctor`, `aew harness status`, `aew harness config opencode <INV>|--lead`.
