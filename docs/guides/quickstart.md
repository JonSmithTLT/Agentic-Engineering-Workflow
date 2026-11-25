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

AEW's Git commands ignore settings injected through `GIT_CONFIG_COUNT` and its `GIT_CONFIG_KEY_n` / `GIT_CONFIG_VALUE_n`
pairs, `GIT_CONFIG_PARAMETERS`, and `GIT_CONFIG`. Put settings such as `safe.directory` in your global or system Git
configuration file.

## Operator: initialize a project

```bash
cd <repo>                       # the main worktree, on the authoritative branch
aew init --check-command "{python} -m pytest -q" --model openai/gpt-6-sol   # also discovers authority *candidates*; confers no authority
```

If you use an exported key (not a saved OpenCode login), set it in the terminal you'll start AEW from. Use the form for your shell.

Bash

```bash
read -rsp 'OPENAI_API_KEY: ' OPENAI_API_KEY; echo; export OPENAI_API_KEY
```

PowerShell 7

```powershell
$env:OPENAI_API_KEY = Read-Host "OPENAI_API_KEY" -MaskInput
```

Windows PowerShell 5.1

```powershell
$s = Read-Host "OPENAI_API_KEY" -AsSecureString; $env:OPENAI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)); Remove-Variable s
```

```bash
aew doctor
aew opencode --provider-env OPENAI_API_KEY
```

This command uses the exported key for the Lead's own model. To use the Lead's existing login, start with
`aew opencode --acquire`.

`aew init` takes the first configuration in that one call and writes it before it pins. With both flags, a fresh
setup needs no hand edit, no adopt and no credential at init. Its `next` says what's left for what you gave it.
After setting the key, you can go straight to OpenCode. If a required key is unavailable, `aew doctor` reports
the missing provider variable under `provider-env` and shows how to supply it.

On contained Linux a worker uses the saved API-key login through the built-in provider relay when the policy names
that provider's variable and its other names are set or are other built-in providers' key variables. One login
decides per provider for the Lead and workers. API-key workers use an export when the deciding login is refreshing.
Once the pinned OpenCode version is qualified, an adopted `plan_login` profile can use the operator's plan on
contained Linux. For an explicit override or a legacy launch,
use the shell forms above with that provider's variable in place of `OPENAI_API_KEY`.
A certificate-only provider skips key setup.

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
  variable's name. The policy records only that name. Use a paid model. An unknown provider takes the route below, as
  does a proxy variable such as `HTTPS_PROXY`.
- **Init checks the provider login.** After creating the project, init makes a no-cost models request through each
  available worker and default Lead relay. Its `provider_relay` rows identify which login the route used and the
  provider's HTTP status. A rejection or unavailable route leaves the project initialized. Run `aew doctor` to check
  again. Init runs no model completion or project check. It also builds the first project map from the branch head
  when it has a commit. The `map` result says what happened.
- **Project maps are on for a new project.** Each worker's pack carries a bounded slice of that map, as navigation and
  never authority, and a dispatch whose map is out of date for its work makes a new one first. To turn them off, set
  `maps.pack_slices` to `"off"` (with the quotes) in `.aew/policy/execution.yaml`, then adopt it as in
  [Edit pinned settings](#edit-pinned-settings-or-classify-authority-candidates): that needs the Lead credential, with
  the Lead session ended first. A project initialized before maps were on keeps them off: `aew opencode` asks once at
  its start, where Enter alone keeps them off, and `aew doctor` shows the answer. To be asked again instead, delete
  that switch's row from `.aew/local/switch-offers.json`: the next `aew opencode` start asks, with no seat needed.
- **On an initialized project** `aew init` is refused, flags or not. One interrupted before it initialized the project
  may run again, with other values. The first project map, tool screen and provider relay checks follow the initial
  pin. If interrupted after the pin, use `aew doctor` to repeat the relay checks. The tool screen comes again when
  the Lead starts, and the first dispatch that needs a map makes one.

### Edit pinned settings or classify authority candidates

After the Lead session exits and releases the seat, acquire it at your terminal and keep the credential it shows.
For a pinned edit, review the changes
under `.aew/` and give a reason. Adopt asks for the credential and a one-time code. Authority candidates can wait
while the Lead works. Replace the example candidate ID with one from `aew authority list`. Run the middle command
or commands you need, then release the seat.

```bash
aew lead acquire --session-label lead-1
aew manifest adopt --reason "updated the pinned settings"
aew authority accept C-001 --class decisions
aew lead release
```

The terminal holds the seat until `aew lead release`. Once the seat is vacant, start the Lead again with
plain `aew opencode` if your shell has no exported Lead credential, or use `--acquire` to take the seat
explicitly. If the old session kept the seat, see [Losing the session](#losing-the-session).

### Declare project CI coverage

Ask the Lead to read the project's CI configuration and draft a `coverage.ci_tools` list for
`.aew/policy/checks.yaml`. List each tool once. Its `covered_by` list names configured check IDs or the built-in
`guardrails` check. Use `covered_by: []` when no check covers it.

```yaml
coverage:
  ci_tools:
    - name: ruff
      covered_by: [lint]
    - name: pyright
      covered_by: []
```

A project whose CI selects the tests a change affects can declare the selector and the unit it selects, such as tests
or lanes. The selector receives the changed paths in `{changed_paths_file}` and writes one UTF-8 item per line to
`{selection_out}`. Both files are outside its disposable copy of the integration candidate. Validation accepts up to
1 MiB of selector output. A larger file leaves the selection unknown (`selector_no_output`). The selector timeout
bounds how long validation waits for the copy and its result. On expiry, validation asks the process supervisor to
stop the selector and proceeds within the checks' separate deadline. The CLI may stay open while the copy owner
finishes pending setup or cleanup.
List the selector code and configuration under `inputs` so validation reports the selection as unknown when a change
touches them. When `inputs` is omitted, the selector's project-file arguments are its declared inputs. An empty
selection in validation is known only when `may_select_none` is true and the command writes an empty output file.
Doctor's explicit empty-change probe can report a written empty file as a successful diagnostic.

```yaml
coverage:
  affected_tests:
    unit: lanes
    selector:
      command: ["{python}", "tools/ci/tier.py", "--event", "pull_request", "--base-ref", "main",
                "--labels", "", "--paths-file", "{changed_paths_file}", "--lanes-out", "{selection_out}"]
      cwd: "."
      timeout_s: 120
      network: isolated
      inputs: ["tools/ci/**", "tests/helpers/lanes.py"]
```

The example reuses AEW's CI tier selector. A check that consumes the result includes `{selection_file}` in its
command. AEW records whether that check finished after receiving the list. The project's check is responsible for
running the selection, and for interpreting a single `*` line as a request to run its full scope when selection is
unknown. AEW's own project checks do not yet have a lane runner that consumes this file. Its validation lists
selected lanes as unrun. Single worker and verifier check calls receive the full-scope marker.

The operator reviews the draft, pastes it into the policy and runs the manifest adoption command from the preceding
section in one sitting. The project is frozen between the edit and adoption because reads of the changed policy
are refused. A contained Lead can draft the text. An uncontained Lead can also edit the file for the operator to adopt.

Validation reports the CI tools from the adopted declaration. A tool marked as run means a covering check finished.
Doctor reports undeclared lists, tools with no configured check, and a declared selector with no consuming check
under `checks-configured`. `aew doctor --run-checks` probes the selector against an empty change on a disposable
copy of the authoritative commit. The probe is diagnostic.

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
the credential in its broker's memory. Plain `aew opencode` without an exported credential takes or resumes the
seat. `--prompt-token` opens the hidden prompt for an existing credential. The credential is never written to disk.
Once a Lead session (`aew opencode`, `aew lead session`) is running, AEW never asks for the Lead credential inside the
Lead's own window: a prompt there is not AEW's.

A command that issues a credential writes it only to your terminal, never to standard output, and the JSON result says
`"(written to your terminal)"` instead. With no terminal (a pipe, a harness tool call) it is refused before anything is
issued. A script that keeps the credential safe can ask for it on standard output with `aew --print-credential ...`;
a Lead session refuses that flag.

## Lead: one Ticket, end to end

With `aew opencode`, the Lead performs the Ticket steps below through its own tools.

A mutation checks current Lead authority and the facts it relies on. The operator terminal reads the needed prior value or approval subject for the examples below. When automating from a Lead session, pass the binding shown in the current status or projection. The revision returned in results orders committed events.

```bash
aew work create ticket --title "..." --class 1 --scope "src/**" \
    --goal "observable outcome" --contract "conformance rule"
aew plan propose T-0001 --file plan.md --assurance none   # or --review/--verify <card|default>
aew plan accept  T-0001 --revision 1                 # -> READY
```

Every plan declares its assurance. `--review` and `--verify` name the cards the plan relies on (`default` is the
archetype's default card); accepting the plan makes them required gates, and only a new plan revision changes them.
`--assurance none` declares that the plan adds nothing to the unit's policy path. A review promised only in the plan's
text binds nothing, which is why the declaration is required.

```bash
aew work staff   T-0001 --execute python_engineer --review code_reviewer   # optional
aew work assign  T-0001    # workspace + launch contract/pack; the implementer credential on your terminal
aew work transition T-0001 --to RUNNING
```

**Free text is data.** Any command takes `--fields FILE|-`: a YAML or JSON mapping of its option values, which become the command's options without passing through a shell. Use it whenever a shell would otherwise see titles, goals, contract clauses, scopes, reasons or notes, because a shell rewrites `$`, backticks, globs and quotes:

```bash
aew work create ticket --class 1 --fields - <<'EOF'
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
aew work transition T-0001 --to REVIEW_PENDING
aew invoke create T-0001            # next planned/default reviewer card + pack + credential
aew review ingest T-0001 --evidence <id>
aew work transition T-0001 --to VERIFY_PENDING
aew invoke create T-0001            # verifier
aew verify ingest T-0001 --evidence <id>   # failure? -> aew verify classify (Lead only)
aew work transition T-0001 --to COMMIT_READY
aew integrate prepare T-0001
aew invoke create T-0001 --scope integration   # post-integration verifier
aew verify ingest T-0001 --evidence <id>
aew integrate publish T-0001         # atomic ref CAS -> DONE + completion record
```

## M2: Epics, Stories and non-mutating Tickets

Small work stays small: a standalone Ticket needs no Story or Epic. When work has structure, create the parents and plan them like Tickets:

```bash
aew work create epic  --title "Toolchain readiness" --class 1
aew work create story --title "Durable state" --class 2 --parent E-0001 \
    --mandatory-gate review_security          # non-waivable for every descendant
aew plan propose S-0001 --file story-plan.md --review default && aew plan accept S-0001 --revision 1
aew work create ticket --title "Survey the store" --class 1 --parent S-0001 --non-mutating \
    --card investigator --goal "..."         # or researcher / planner
aew work create ticket --title "Harden the store" --class 2 --parent S-0001 \
    --depends-on T-0001:evidence --scope "src/**" --goal "..."
aew work tree                                               # Epic -> Story -> Ticket, derived states
```

A parent's state is derived (PLANNING, IN_PROGRESS, ACCEPTANCE_PENDING), and `work transition` never changes it. Changing an ancestor's accepted plan (including its first one) stops its descendants until you run `aew plan reconfirm <id> --reason ...` or replan them.

**A non-mutating Ticket** is dispatched, not assigned. It gets its own read-only observation of the authoritative source and no workspace:

```bash
aew work dispatch T-0001         # pins executor card + expected output kind (attempt 1)
aew work transition T-0001 --to RUNNING
AEW_INVOCATION_TOKEN=<credential> aew -C <observation> submit --kind discovery_record --file record.md
aew evidence ingest T-0001 --evidence <id>
aew work accept T-0001           # -> DONE, evidence-only completion record
aew work redispatch T-0001 --reason "..."   # instead: supersede the attempt, start the next
```

- If a consumed discovery or plan proposal no longer matches the source, the next dispatch of its consumer is refused with `INPUT_STALE`. Refresh the input (a new investigation, plus `aew work depend`), or record that you rechecked it for this commit: `aew work acknowledge-input T-0002 --input <E> --from T-0001 --reason "..."`.
- A Planner's accepted proposal becomes a *proposed* plan revision with `aew plan adopt <T> --evidence <E> --from <planning Ticket>` and the plan's assurance declaration. You still accept it.

**Closing a parent.** When every child is DONE or CANCELLED, the parent is ACCEPTANCE_PENDING. Review and verify the parent (the packs carry every child's own integrated change), then close it:

```bash
aew invoke create S-0001 --role reviewer    # then: aew review ingest S-0001 ...
aew invoke create S-0001 --role verifier    # then: aew verify ingest S-0001 ...
aew work close S-0001 --reason "..."
```

An Epic closes only once the history is audited through the current root: run `aew history audit --record` first.

**Structure changes.** Each is a recorded Lead decision:
- `aew work cancel <S|E>` cascades to the parent's open descendants;
- `aew work move <id> --parent <P|none>`;
- `aew work promote <T> --to story --title ...` keeps the Ticket's identity and evidence;
- `aew work depend <id> --add X[:evidence|mutating] --remove Y`.

## Finished work and its history

A project created before ADR-0011 has control state v1, where finished work stays in the active state. Its Lead migrates it once, with no harness run live; until then the Lead's other changes are refused with `MIGRATION_REQUIRED`:

```bash
aew migrate    # finished work moves to the history in one transaction; running it again does nothing
```

Finished work leaves the active state when it finishes (ADR-0011). Views show counts and the most recent finished units; the history commands reach the rest by stable id, without knowing where anything is stored:

```bash
aew history list --kind unit --limit 20                     # newest first; --since/--until take UTC times
aew history show T-0042                                     # the record, its annotations and its trust label
aew history show INV-0101                                   # an invocation, credential or evidence of finished work
aew history links T-0042 --depth 2                          # recorded provenance, in both directions
aew history load T-0042 --into T-0107 --reason "..."   # reference context for T-0107's next packs
aew history load INV-0101-discovery-1 --into T-0107 --reason "..."   # or an exact evidence record
aew history audit                                           # advisory verification; add --record to record it
```

A loaded record is reference, never current evidence: packs label it, and claims that depend on versions or current state are revalidated through normal evidence. `aew status` reports the audit backlog against the gates policy's optional `history_audit` thresholds.

## M3: running with OpenCode

Configure `.aew/policy/execution.yaml` (which harness, provider, model and effort run each role) and set your provider key, as `opencode.md` describes. Then:

```bash
aew doctor                      # policy:execution PASS; containment WARN (workdir separation only)
aew opencode                    # the Lead in OpenCode's TUI; the Lead credential stays in the session's broker
```

In the TUI, `/aew-ticket <objective>` drafts a Ticket and plan, and `/aew-next <id>` takes one step at a time. Dispatches carry `--launch`, so each role runs in its own private OpenCode server and acts through a run-scoped bridge:

```bash
aew work assign T-0001 --launch    # run R-INV-0001-1 starts; no credential is printed
aew harness wait R-INV-0001-1 --timeout 110       # its evidence, each item's result, and the next action (exit 20: no evidence)
aew harness launch INV-0001        # relaunch (a fresh session; the credential rotates)
```

A run's end moves nothing: the Lead still ingests and transitions, as above. Every run works with **workdir separation only**, not filesystem containment, so use scratch repositories and clones until containment exists.

## Unattended Run

Under Run, the steering loop starts Tickets and requests reviews itself, for one Lead generation, and the operator
endpoint tells you what stops it. A project starts in crawl. Run needs four things, and `aew doctor`'s
`steering:run-ready` line says which are missing, each with its fix:

- **a Lead in the seat.** The raise binds its generation, and the steering loop runs in its session, so doctor run
  before terminal 2 below says the seat is vacant.

- **a notifier that can deliver.** `aew init` sets the desktop one (`[aew, notify, desktop]`). Check it from the
  terminal the endpoint will run in: `aew notify desktop --check`. With no desktop session there (an ssh login on a
  Linux host), use the headless one, which appends each event to a file you watch (`tail -f`):
  `notify.command: [aew, notify, file, /home/you/aew-events.jsonl]`. Check it with
  `aew notify file /home/you/aew-events.jsonl --check`. Doctor judges the notifier in its own terminal's environment,
  so run the check from the endpoint's terminal.
- **a `deadline_s` on every profile routing can pick.** First configuration (`aew init` with `--model`) writes one
  (provisional, bounding only runs started under Run). Without it, the raise is refused and names the profiles.
- **the operator endpoint, up the whole time.** Each Run activation pings it, and so does doctor.

Changing `notify.command` or a profile is an edit of `.aew/policy/execution.yaml`, a pinned file: end the Lead session
first, then follow "Edit pinned settings or classify authority candidates" above, start the Lead again and raise again.

Then, in three terminals:

```bash
aew operator serve --dev        # 1: the endpoint; keep it running. It shows the one-time codes
aew opencode --acquire          # 2: the Lead session (generation 1)
aew lead mode raise run         # 3: type the code terminal 1 shows; the raise lasts for this Lead generation
```

`aew status` then shows `Steering: effective run` and `Run: ready`, or what Run is missing while it cannot act.

## Losing the session

- If OpenCode took the seat itself, start plain `aew opencode` from your terminal on the same host and as the same
  user. The previous session must be gone and no handoff can be pending. If active work is carried or processes may
  still be running, AEW names them and asks for one confirmation code. A successful resume leaves carried runs active.
- If resume is refused and you need to replace the holder, run `aew lead takeover --reason "..."` at
  your own terminal and type its confirmation code.
- In the new session, run `/aew-resume` or `aew resume` to rebuild context from `.aew/`. A lost run can be relaunched
  with `aew harness launch`. Losing the harness leaves the Ticket and its invocation unchanged.
- After a takeover, in-flight Tickets come back as INTERRUPTED. Inspect them, then `aew work reconcile`. A non-mutating Ticket then continues only with `aew work redispatch` (a new attempt); nothing its interrupted executor submitted is accepted.

## Useful views

`aew guide` (how work flows in this project: risk classes, their gates, the Ticket lifecycle, the tool or command for each step), `aew status`, `aew resume`, `aew work tree`, `aew work show T-0001`, `aew gate show T-0001`, `aew work roles T-0001`, `aew role list`, `aew doctor`, `aew harness status`, `aew harness config opencode <INV>|--lead`.
