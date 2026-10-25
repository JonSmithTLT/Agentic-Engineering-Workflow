# Running AEW with OpenCode

How to install, configure and use OpenCode as AEW's harness. The design is ADR-0009 (the harness boundary and the adapter) and ADR-0010 (execution profiles); `m3-opencode-v2-rebaseline.md` records the OpenCode V2 facts they rest on.

## What you get

- **The Lead in OpenCode's TUI.** `aew opencode` starts OpenCode with AEW's Lead agent and commands. The Lead's credential stays in a broker process: the model acts through `aew`, and never holds or sees a credential.
- **Every role as a harness run.** A dispatch with `--launch` starts the role in its own private OpenCode server, with its pinned model, its launch contract, and only the permissions its role allows. The role acts through a run-scoped bridge and never holds a credential either.
- **Disposable harness state.** Everything OpenCode stores is local and deletable. Losing it loses a conversation, never the project: `aew resume` rebuilds the Lead's context from `.aew/`.

## Requirements

- **OpenCode V2, version 2.0.18.** It is the only version tested. V1 is not supported, and a server that is not V2 is refused.
- **Windows** is where real runs are tested. On Windows, AEW uses OpenCode Desktop's versioned CLI at `%APPDATA%\ai.opencode.desktop\cli\2.0.18\opencode-cli.exe`. Elsewhere it uses `opencode-cli` (or `opencode`) on `PATH`. To use another copy, set `AEW_OPENCODE_BIN` to its path.
- **Linux** is covered in CI by a fake V2 server that serves the real 2.0.18 API description. No real Linux run has been made.
- A provider account for the models you configure.

AEW never contacts OpenCode Desktop's own background service, and never writes to your OpenCode configuration or state.

**What a launch checks, whatever the version.** Each run's server must load AEW's agent as projected: the system text, the pinned model and effort, the step limit, and AEW's permission rules in order as the last block that can grant anything. A server may append its own rules after AEW's only if they deny (2.0.22 appends `browser: deny`); an `allow` or `ask` there refuses the launch. A server that serves stored credentials (`GET /api/credential`, from 2.0.22) must hold none, because the agent can reach its own server. A newer version still runs as untested until it is added to `TESTED_VERSIONS` after a live-lane run.

## 1. Configure execution (once per project)

`aew init` writes `.aew/policy/execution.yaml` as an unconfigured template. Until it is configured, `aew harness launch` and `--launch` refuse. A minimal configuration:

```yaml
schema: aew/execution/v1
configured: true
harness: opencode
profiles:
  standard: {provider: openai, model: gpt-6-sol, effort: medium}
  light:    {provider: openai, model: gpt-5.6-luna, effort: medium}
routing:
  default: standard
  archetypes: {}          # e.g. {implementer: light}
  classes: {"0": light}   # by risk class
  cards: {}               # by role card id
provider_env: [OPENAI_API_KEY]
```

- **Model ids** are OpenCode's, exactly as its model list prints them: `model: openai/gpt-6-sol` needs no separate `provider`. With `provider: openai`, the bare `gpt-6-sol` and the printed `openai/gpt-6-sol` pin the same model. A prefix that names another provider than `provider` is refused, naming the field and what to write (a routing provider's model whose own id contains `/` is written in full, as OpenCode prints it; so is a model whose own id begins with its provider's name, such as `router/router/auto`, because the provider's own prefix is removed). `aew doctor`'s `model-refs` line shows each profile's model as OpenCode is given it. **`effort`** is the model's variant; a launch refuses if the pinned model or variant is missing, and never falls back to another.
- **`provider_env`** lists the *names* of the environment variables OpenCode's server needs. Never put a key in this file. The value is read from the environment of whoever launches the run, and goes only to that run's OpenCode server, never to the agent's shell. A launch from an environment where a listed variable is not set is refused before anything starts, naming the variable; `aew doctor`'s `provider-env` line says the same beforehand. Behind a proxy, list the variable OpenCode reads for your provider's scheme here too: `HTTPS_PROXY` for an `https://` provider, `HTTP_PROXY` for an `http://` one (OpenCode 2.0.18 does not read `ALL_PROXY`, and `HTTP_PROXY` never applies to `https://`). AEW then adds `127.0.0.1`, `localhost`, `::1` and `[::1]` to `NO_PROXY`, keeping any entries you pass (a `NO_PROXY` of `*` is left as it is), so OpenCode's loopback traffic never goes through the proxy. AEW's own calls to the run's server ignore proxy settings in any case. `aew opencode --provider-env` does the same for the Lead's OpenCode.
- **Routing** is most specific first: card, then risk class, then archetype, then default. The profile is pinned on each invocation at dispatch, so editing the policy never changes work already dispatched. The Lead can override one dispatch with `--profile NAME` or `--model PROVIDER/MODEL [--effort E]`.

The policy files are pinned: after editing one, run `aew manifest adopt --reason ... --token <credential> --expect-rev N`
at your own terminal to accept the change (until then every Lead change is refused).

Then check the project:

```bash
aew doctor
```

`policy:execution`, `model-refs` and `provider-env` should be PASS (`provider-env` checks the terminal you run doctor in; a Lead session already running keeps the environment it was started with). Doctor exits 1 when any line is FAIL, in text and `--json` alike; WARN lines leave it 0. `containment` is always WARN, and that is expected: see [Containment](#containment). On Windows, the first line is `platform`: WARN, "Windows: UNQUALIFIED (excluded from the enforced gate)", with the reason.

## 2. Set the provider key

Set the key in your own environment, under the name `provider_env` lists (on Windows, as a user environment variable; open a new terminal afterwards). Runs launched from that terminal pass it to their OpenCode servers only.

The Lead's own model is different. By default it uses the credentials OpenCode has stored for you (`opencode auth login`), and its environment holds no provider key.
- **On Linux** the Lead runs contained (see [Containment](#containment)): AEW reads your stored logins on the host, never inside the sandbox, and gives each provider whose key OpenCode reads from a variable (openai, anthropic, google) a relay of its own; inside, that variable holds only a stand-in the relay swaps for the key. `aew opencode --provider-env NAME` feeds that provider's relay from your environment instead, and the Lead's shell still never sees the key. The session's first lines say which logins are relayed and why any is not.
- **Elsewhere** (Windows) `aew opencode --provider-env NAME` passes a key to the Lead's OpenCode; the Lead's shell can then read that key, and the command says so.

## 3. Start the Lead

From the project's main worktree:

```bash
aew opencode --acquire
```

- `--acquire` takes the vacant Lead seat inside the session, so the Lead credential exists only in the broker's memory. It is never printed. At exit the seat is released if nothing is in flight; otherwise it stays held, and the output tells you that continuing needs a terminal takeover. `--keep-seat` keeps it held.
- Without `--acquire`, the broker takes the credential from `AEW_LEAD_TOKEN` in your shell, and removes it from OpenCode's environment.
- Extra OpenCode TUI arguments go after `--`. `--server` is refused, because the Lead's shell would then get the server's environment.

In the TUI, the agent is `aew-lead`, with these commands:

| Command | What it does |
|---|---|
| `/aew-resume` | rebuild the Lead's context from AEW (`aew resume`) |
| `/aew-status` | work, Lead authority and harness runs, with proposed next actions |
| `/aew-ticket <objective>` | draft a Ticket and a plan for an objective, show them to you, and create them only after you agree |
| `/aew-next <id>` | take the next step on a unit: dispatch with `--launch`, wait, ingest, advance |
| `/aew-handoff` | record a checkpoint for a handoff. The handoff itself (`aew lead handoff offer`) is yours, at your own terminal. |

**The Lead's guide.** The Lead's system text includes the project's guide to how AEW works (`aew guide`, rendered from this project's own gates policy when `aew opencode` starts): what each risk class requires and still guarantees, the Ticket lifecycle, and the command for each step. The default-policy version is [`lead-guide.md`](lead-guide.md).

The Lead's permissions: reading and searching, `aew`, and `git status|diff|log|show` are allowed; editing files and subagents are denied; any other shell command or tool asks you.

## 4. Runs

The Lead dispatches with `--launch` on `work assign`, `work dispatch`, `work redispatch` and `invoke create`. Each starts run 1 of the new invocation. Then:

```bash
aew harness wait R-INV-0001-1 --timeout 110     # until the run stops; its evidence, each item's result, and the next action
aew harness status [INV]                        # runs, their local status, and whether they still hold authority
aew harness send R-INV-0001-1 --file nudge.md   # a message to a running agent, at its next step boundary
aew harness interrupt R-INV-0001-1              # stop the current turn and keep the session
aew harness stop R-INV-0001-1 --reason "..."    # stop the harness; the invocation is unchanged
aew harness launch INV-0001 --expect-rev N      # a new run of the same invocation (rotates its credential)
```

- **A run's end moves nothing.** Whatever a run reports, the Ticket advances only when the Lead ingests evidence and makes the transition, as before.
- **A run that ended without its expected output is not progress.** `aew harness wait` then exits 20 (every other ending, and a wait that timed out, exit 0) and its result starts with a one-line `headline`; the result is printed either way. A run whose provider rejected the key says so: `reason_code: provider_auth_failed`, with what to do in its next action.
- **Relaunching** starts a fresh session with the same pack plus a continuation built from AEW's durable state: earlier runs, this invocation's evidence and the workspace's changes. It rotates the invocation's credential, so the old run, if it is still somewhere, has no authority. If the old run may still be alive, the launch refuses (`RUN_LIVE`) unless you add `--replace`.
- **Each run is private.** Its own OpenCode server, state directories and database, under `.aew/local/harness/runs/<run>/`. A reviewer never sees an implementer's conversation; what passes between roles is AEW state.

To see exactly what a harness receives, without starting anything:

```bash
aew harness config opencode INV-0001   # the run's projection: agent, system text, permissions, environment names
aew harness config opencode --lead     # the Lead's (the same as `aew opencode --print-config`)
```

## What each run gets

- The **workspace** (or read-only observation) recorded for its invocation, as OpenCode's session directory. No command takes a path.
- A **system text** with the AEW rules, and a first message with the preamble and the pinned context pack.
- **Permissions**, all allow or deny (an `ask` would block forever): reading, searching and the shell are allowed; editing only for implementers; web access only for cards that request `documentation_lookup`; subagents, questions and directories outside the run are denied. `.env` files are unreadable.
- **No skills.** M3 provides none, so a card's skills are reported as unavailable, and the operator's own `~/.claude` and `~/.agents` skills never load.
- **An allowlisted shell environment**: the operating-system basics, `PATH` with `aew` first, the bridge coordinates, `AEW_INVOCATION`, `AEW_RUN`, `AEW_WORK_UNIT` and `AEW_SCRATCH`, a private scratch directory for files that belong neither in the workspace nor in evidence. It holds no AEW credential, no provider key and no OpenCode password.
- **The agent's shell** is bash when `SHELL` names one in the launching environment (for example, from Git Bash); otherwise OpenCode uses PowerShell on Windows.
- Project OpenCode configuration and `AGENTS.md` in the workspace are ignored, so nothing in the repository can reconfigure a run.

## Containment

**On Linux** (with bubblewrap) every run, and the Lead's TUI, runs contained: a sandbox per run from its role, checked by a self-test before anything starts, with a network of its own whose only routes out are AEW's provider relay and egress proxy (ADR-0009). A run whose containment fails is refused unless the execution policy says `containment.mode: allow_weaker`, which runs it labelled `workdir_separation_only`.

**The Lead's session** (`aew opencode`) runs in a `lead` sandbox:
- it writes the working tree; `.aew/` and the git metadata are read-only, so a commit fails there while `git status`, `diff` and `log` work, and its Lead `aew` commands still reach the broker, which writes AEW state for it;
- its OpenCode state is its own, under `.aew/local/harness/lead`, kept per project between sessions; your OpenCode configuration and logins are not visible inside, and its first lines name any MCP servers of yours it leaves out;
- its network reaches your providers through AEW's relays and public addresses over https through the egress proxy; a plain `http://` request is refused with the `https://` form to ask for instead;
- the TUI runs on a terminal AEW relays: what you type and what it draws pass unchanged, and your terminal gets its settings back however the session ends.

**Elsewhere** (Windows) AEW provides **workdir separation only**: each run has its own workspace, private harness state and scratch directory. It does **not** contain the filesystem. An agent's shell runs as you, and can read and write anything your account can. Every run record says `containment: workdir_separation_only`, and `aew doctor` warns about it. There, use AEW with models on scratch repositories and clones, not on your only copy of something that matters.

## When something goes wrong

| Symptom | Meaning | What to do |
|---|---|---|
| The TUI crashed or was closed | runs continue; nothing is lost | `aew opencode` again, then `/aew-resume` |
| A run is `lost` or `crashed` | the harness died; the Ticket and credential are unchanged | `aew harness launch INV --expect-rev N`, or `aew invoke cancel` |
| A run is `ended_without_evidence`; `aew harness wait` exits 20 and its result starts with a `headline` | it stopped without its expected output | `aew harness send` a nudge while it runs, relaunch, or cancel |
| A run is `crashed` with `reason_code: provider_auth_failed` | the model provider rejected the key (an expired or revoked key: a 401, which OpenCode does not retry) | put a valid key in the variable the policy's `provider_env` names, then relaunch. A relaunch's server reads the key from the environment of the process that launches it: from inside `aew opencode`, that is the session's own, so restart `aew opencode` with the new key first |
| `HARNESS_INCOMPATIBLE` | no binary, a version that is not V2, a missing API capability, or the pinned model or variant missing from the catalog | the message names the gap; check `AEW_OPENCODE_BIN`, the policy's model ids, and `provider_env` |
| A launch refused with `HARNESS_INCOMPATIBLE`, reason `provider_env` | a variable the policy's `provider_env` names is not set (or holds an AEW credential) in the environment the launch runs in; nothing was dispatched or started | set it in the terminal you start AEW from, then run the command again there. A launch the Lead or its steering loop makes reads the environment the Lead session (`aew opencode`, `aew lead session`) started with: restart the session from that terminal; the message says when it came from a session |
| A dispatch refused with `VALIDATION_FAILED`, field `profiles.<name>.model` | the model id's prefix names another provider than the profile's `provider` | write the id exactly as OpenCode prints it; the message names both ids it may mean |
| `RUN_LIVE` | the latest run may still be running | wait for it, or relaunch with `--replace` |
| `STALE_AUTHORITY` naming a rotation | an old run's credential was replaced | expected: only the latest run can act |
| launch refused, no execution profile | the invocation was dispatched while the policy was unconfigured | configure the policy, then dispatch a new invocation (a pin never changes) |
| A fingerprint error naming `nul` | a file named `nul` in a workspace, made by a Windows-style `> nul` redirect in bash | delete the file (`future-work.md` O1) |

The model catalog and agents load asynchronously when a server starts. Health waits up to 90 seconds for them (`AEW_OPENCODE_CATALOG_S`); a slow provider catalog may need more. A run's whole start, from custody to running, is capped by a deadline derived from these waits and the adapter's other launch timeouts: 620 seconds at the defaults, rising with `AEW_OPENCODE_CATALOG_S`. `AEW_RUN_START_S` replaces it. A start that passes it ends `launch_failed` with a reason naming the variable.
