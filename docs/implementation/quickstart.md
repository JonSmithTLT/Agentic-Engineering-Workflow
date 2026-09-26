# AEW M1 quickstart (operator and Lead)

M1 is harness-neutral: a Lead agent (or a person) drives everything through the `aew` CLI. Bounded roles act only with their own invocation credential, from inside their Ticket workspace. The OpenCode adapter arrives in M3.

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
aew plan propose T-0001 --file plan.md --expect-rev N
aew plan accept  T-0001 --revision 1   --expect-rev N               # -> READY
aew work staff   T-0001 --execute python_engineer --review code_reviewer --expect-rev N   # optional
aew work assign  T-0001 --expect-rev N    # workspace + implementer credential + launch contract/pack
aew work transition T-0001 --to RUNNING --expect-rev N
```

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

## Losing the session

- Run `aew resume` in a fresh session. It is read-only and rebuilds everything from `.aew/`.
- If the old Lead is gone, **the operator** runs `aew lead takeover --reason "..." --expect-rev N` at an interactive terminal and types the challenge code. Agents cannot do this for themselves.
- In-flight Tickets come back as INTERRUPTED. Inspect them, then `aew work reconcile`.

## Useful views

`aew status`, `aew resume`, `aew work show T-0001`, `aew gate show T-0001`, `aew work roles T-0001`, `aew role list`, `aew doctor`.
