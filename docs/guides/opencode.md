# Running AEW with OpenCode

How to install, configure and use OpenCode as AEW's harness. The design is ADR-0009 (the harness boundary and the adapter) and ADR-0010 (execution profiles); `m3-opencode-v2-rebaseline.md` records the OpenCode V2 facts they rest on.

## What you get

- **The Lead in OpenCode's TUI.** `aew opencode` starts OpenCode with AEW's Lead agent and commands. The Lead's credential stays in a broker process: the model acts through `aew`, and never holds or sees a credential.
- **Every role as a harness run.** A dispatch with `--launch` starts the role in its own private OpenCode server, with its pinned model, its launch contract, and only the permissions its role allows. The role acts through a run-scoped bridge and never holds a credential either.
- **Disposable harness state.** Everything OpenCode stores is local and deletable. Losing it loses a conversation, never the project: `aew resume` rebuilds the Lead's context from `.aew/`.

## Requirements

- **OpenCode V2, version 2.2.6.** It is the only version tested (`capabilities.TESTED_VERSIONS`). V1 is not supported, and a server that is not V2 is refused.
- **Windows** is where real runs are tested. On Windows, AEW uses OpenCode Desktop's versioned CLI at `%APPDATA%\ai.opencode.desktop\cli\2.2.6\opencode-cli.exe`. Elsewhere it uses `opencode-cli` (or `opencode`) on `PATH`. To use another copy, set `AEW_OPENCODE_BIN` to its path.
- **Linux** is covered in CI by a fake V2 server that serves the real pinned API description, and the real binary passed the conformance suite on Windows and on the Rocky 8 VM, and the containment self-test on the VM except one host-scoped row (`host_tmp`, the VM's own X11 socket), when the pin moved to 2.2.6 (`tools/harness_qualify`).
- A provider account for the models you configure.

AEW never contacts OpenCode Desktop's own background service, and never writes to your OpenCode configuration or state.

**What a launch checks, whatever the version.** Each run's server must load AEW's agent as projected: the system text, the pinned model and effort, the step limit, and AEW's permission rules in order as the last block that can grant anything. A server may append its own rules after AEW's only if they deny (2.0.22 appends `browser: deny`); an `allow` or `ask` there refuses the launch. A server that serves stored credentials (`GET /api/credential`, from 2.0.22) must hold none, because the agent can reach its own server. A newer version still runs as untested until it is added to `TESTED_VERSIONS` after a live-lane run.

## 1. Configure execution (once per project)

`aew init --model openai/gpt-6-sol` configures it in that one call, before it pins: one profile named `default`, with the provider's key variable named in `provider_env`, and there's nothing to adopt ([the quickstart](quickstart.md#operator-initialize-a-project) has its bounds). Without `--model`, `aew init` writes `.aew/policy/execution.yaml` as an unconfigured template. Until it is configured, `aew harness launch` and `--launch` refuse. A minimal configuration by hand, which is also the route for a proxy variable or a provider `--model` doesn't know:

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
- **`provider_env`** lists the *names* of the environment variables OpenCode's server needs. Never put a key in this file. An explicit value comes from whoever launches the run. On contained Linux the relay can also use a saved OpenCode API-key login for the pinned provider under the conditions below. On the relay route the server receives a sentinel. A built-in provider does not require another built-in provider's key variable. A missing required variable is refused before anything starts, naming the variable; `aew doctor`'s `provider-env` line says the same beforehand. Behind a proxy, list the variable OpenCode reads for your provider's scheme here too: `HTTPS_PROXY` for an `https://` provider, `HTTP_PROXY` for an `http://` one (OpenCode 2.0.18 does not read `ALL_PROXY`, and `HTTP_PROXY` never applies to `https://`). AEW then adds `127.0.0.1`, `localhost`, `::1` and `[::1]` to `NO_PROXY`, keeping any entries you pass (a `NO_PROXY` of `*` is left as it is), so OpenCode's loopback traffic never goes through the proxy. AEW's own calls to the run's server ignore proxy settings in any case. `aew opencode --provider-env` does the same for the Lead's OpenCode.
- **Routing** is most specific first: card, then risk class, then archetype, then default. The profile is pinned on each invocation at dispatch, so editing the policy never changes work already dispatched. The Lead can override one dispatch with `--profile NAME` or `--model PROVIDER/MODEL [--effort E]`.

For a manual edit of the pinned execution policy, follow the quickstart's
[pinned settings steps](quickstart.md#edit-pinned-settings-or-classify-authority-candidates). Once you've adopted the
edit at your terminal and released the seat, start the Lead with plain `aew opencode`.

Then check the project:

```bash
aew doctor
```

`policy:execution`, `model-refs` and `provider-env` should be PASS (`provider-env` checks the terminal you run doctor in; a Lead session already running keeps the environment it was started with). Doctor exits 1 when any line is FAIL, in text and `--json` alike; WARN lines leave it 0. `containment` is always WARN, and that is expected: see [Containment](#containment). On Windows, the first line is `platform`: WARN, "Windows: UNQUALIFIED (excluded from the enforced gate)", with the reason.

## 2. Set the provider key

AEW needs a provider key and a paid model, and does not use OpenCode's free models. OpenCode Zen's published rule (https://opencode.ai/docs/zen/) is "Free-tier chat models require OpenCode; use paid models or Go from other clients", and a run through AEW's provider relay is another client. On Linux a worker launch whose provider would get no key is refused before anything starts (`provider_key_missing`), naming the variable, and `aew doctor`'s `provider-key` line says the same beforehand.

**OpenCode Zen's Console library on Windows.** OpenCode fetches the session instructions and skills set in your OpenCode Console account whenever an `OPENCODE_API_KEY` is set. A contained run on Linux refuses that fetch. On Windows, where AEW provides no network containment, a Zen run receives them, and AEW neither blocks nor records them. If you don't want them in AEW's runs, keep your Console account's instructions and skills empty.

**A provider that requires a client certificate** (mTLS) is reached through AEW's provider relay, which presents the certificate; OpenCode and the agents never get it. Name the provider's API address and its three files in the execution policy, by the profile's provider:

```yaml
containment:
  network:
    upstreams: {mtls: "https://models.example/v1"}
    client_certs:
      mtls: {cert: ~/certs/client.pem, key: ~/certs/client.key, ca: ~/certs/provider-ca.pem}
```

The key is a PEM private key with no passphrase. The relay reads the three files at each launch, so a renewed certificate, or a CA file swapped in at the same path when a change is announced, is picked up by the next one; AEW never copies them. The provider's own certificate is checked against that CA file alone. The certificate and key are hidden from every contained run, and the launch's self-test checks they can't be read from inside. A certificate that can't be used (expired, not yet valid, not matching its key, a key with a passphrase, a file that can't be read, or an upstream that isn't `https://`) refuses the launch with one line per problem, each naming its file (the key by its policy field), and `aew doctor`'s `client-cert` line shows the same lines beforehand, with the certificate's expiry when it passes. Only the relay presents the certificate, so this needs Linux with `containment.network.mode: proxy_only` (the default) and containment that works: a run with no relay is refused, whether its network is `shared` or `isolated`, it runs on Windows, or its sandbox can't be established and `containment.mode: allow_weaker` would run it uncontained (doctor's line is WARN under `allow_weaker` for that reason). The contained Lead relays such a provider too, with no key, offering the models your OpenCode profiles pin for it. One no profile pins a model of isn't relayed, and the Lead's start says what to pin. A Lead with no relay says at its start which providers it can't use. A Lead whose only provider takes a certificate is refused when it would have none to use: its profiles pin no model of it, or its sandbox can't be established under `allow_weaker`. AEW requires no key variable for a provider of its own id; whether OpenCode serves one from its address alone, and needs a placeholder key for it, is checked at its first run. One AEW knows a key variable for (such as `openai`) still needs it.

On contained Linux, an API-key worker can use a stored API-key login from a fresh shell when the policy names that provider's key variable, its other names are set or are other built-in providers' key variables, and the run uses the built-in upstream through the relay. One login decides per provider for the Lead and workers. If that login is refreshing, export the provider's API key for API-key workers. If no deciding login needs to be preserved, set up the API-key method at your own terminal with `opencode auth login`. This covers Anthropic, Google, OpenAI and paid OpenCode models. Doctor and the launch record name the source. Rotating the API-key login affects the next worker launch.

The execution policy's provider defaults live under `credentials`. For example, `credentials: {openai: plan_login}` makes OpenAI profiles use the plan by default. A profile can override that choice with `credential: api_key` or `credential: plan_login`. Adopt the policy before dispatching. Adoption of `plan_login` requires qualification at the pinned OpenCode version. The Lead can select any adopted profile with `--profile`. An explicit `--model` dispatch uses an API key.

Plan workers use the operator's stored ChatGPT login through the built-in relay on contained Linux. AEW reads it for each request and never refreshes it. The worker receives no provider key variable and the relay tries one credential. Any Lead on the same login shares the plan's usage limits. Doctor names the pot and time left, and a launch is refused if the login cannot outlive its deadline. After expiry, renew at your own terminal with `opencode auth login openai` and choose ChatGPT. Use the relaunch or cancel command for the active invocation shown by `aew status`.

A usable export for the named variable takes precedence. Use the shell-only forms in [the quickstart](quickstart.md#giving-aew-the-lead-credential), with the variable's name in place of `AEW_LEAD_TOKEN`, for an override or a launch outside the stored-login route. Never a persistent variable or a startup file: a persistent variable reaches every process you start, and a startup file is a plain file in your home directory, like history. Off the relay, the harness server receives a named export directly.

The Lead's own model is different. By default it uses the credentials OpenCode has stored for you (`opencode auth login`), and its environment holds no provider key.
- **On Linux** the Lead that `aew opencode` starts runs contained (see [Containment](#containment); the general `aew lead session` does not, and is refused there unless the policy allows weaker runs): AEW reads your stored logins on the host, never inside the sandbox, and gives each provider whose key OpenCode reads from a variable (openai, anthropic, google) a relay of its own; inside, that variable holds only a stand-in the relay swaps for the key. `aew opencode --provider-env NAME` feeds that provider's relay from your environment instead, and the Lead's shell still never sees the key. Your ChatGPT login (openai) is relayed as stored: AEW reads it on each request and never refreshes it, so when it expires the Lead's request fails with a message, `opencode auth list` at your own terminal refreshes it, and the Lead's next request works with no restart. When it has 24 hours or less left (the execution policy's `containment.lead.login_warning_h` changes that), the session's start says so: log in again then (`opencode auth login openai`), and the Lead uses the fresh login from its next request. The session's first lines say which logins are relayed, how long a refreshing one has left, and why any is not: a stored opencode key is not served yet (the Lead's configuration switches OpenCode's own `opencode` and `opencode-go` providers off), and a login your OpenCode stored in a shape AEW does not know is not used, never guessed at. A provider key set in your environment is named too: pass it with `--provider-env` to use it. On a machine where you have not logged in to OpenCode, log in first with your own `opencode auth login`, or pass a key with `--provider-env NAME`: with no provider relayed, `aew opencode` is refused at start (`provider_key_missing`), after its first lines say what it found.
- **Elsewhere** (Windows) `aew opencode --provider-env NAME` passes a key to the Lead's OpenCode; the Lead's shell can then read that key, and the command says so.

## 3. Start the Lead

From the project's main worktree:

```bash
aew opencode
```

- Plain `aew opencode` takes a vacant Lead seat inside the session when the shell has no exported Lead credential.
  It resumes a seat it took itself when the previous session is gone, the host and user match, and no handoff is
  pending. When work is carried or processes may still run, the operator's terminal asks for one confirmation code.
  `--acquire` explicitly selects the same route even if a credential is exported. The credential stays in the
  broker's memory. The seat is released after a clean exit when nothing is in flight and no acknowledged process
  may still run. `--keep-seat` keeps it held. An unknown leftover outcome or a nonzero Windows process count
  keeps the seat held across sessions. To free it instead of resuming it, run `aew lead takeover` at your own
  terminal, then `aew lead release`.
- With `AEW_LEAD_TOKEN` set in your shell, `aew opencode` uses that Lead credential. Use `--prompt-token` to
  enter an existing credential at the hidden prompt. `--prompt-token` and `--acquire` cannot be combined.
  The broker holds the credential in memory and removes it from OpenCode's environment. Set the variable for
  this shell session only, with a form that echoes nothing and leaves nothing in history:
  - bash: `read -rsp 'Lead token: ' AEW_LEAD_TOKEN; echo; export AEW_LEAD_TOKEN`
  - PowerShell 7: `$env:AEW_LEAD_TOKEN = Read-Host "Lead token" -MaskInput`
  - Windows PowerShell 5.1: `$s = Read-Host "Lead token" -AsSecureString; $env:AEW_LEAD_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)); Remove-Variable s`

  Never a persistent variable or a startup file: a persistent variable reaches every process you start, and a startup file is a plain file in your home directory, like history. Once the session is running, AEW never asks for the Lead credential inside the Lead's own window: a prompt there is not AEW's.
- Extra OpenCode TUI arguments go after `--`. `--server` and `--standalone` are refused: AEW starts the Lead's server itself, in the Lead's curated environment, and connects the TUI to it.
- At your own terminal with a display, once the Lead seat is held and validated, AEW also starts the read-only dashboard on **127.0.0.1:4280**, for this session's lifetime, and opens its first session directly in your browser: no typed-back code, and AEW never prints or saves the session URL. `AEW_DASHBOARD_AUTOSTART=off` turns this off. With no display (SSH), nothing starts and the start line names `aew dashboard serve`. An occupied port or a browser/start failure is named and never fails the Lead session; an occupied port offers `aew dashboard serve --port 0` to explicitly request an ephemeral port (or pass a free port you choose), never an automatic move. A running dashboard is reused without minting or opening another session; `aew dashboard open` requests one with its code where that server accepts later opens. **Later opens against an auto-started server refuse on Windows too:** end the session, then run `aew dashboard serve` in a terminal of its own for more browser sessions. Auto-start refuses a Lead session by the same dev-grade check as endpoint auto-start. See [the dashboard guide](dashboard.md).
- A pasted image reaches the Lead's model without its path or file name, so the Lead can't name it, read it again or hand it to a worker (OpenCode sends no local path to a server it doesn't treat as local; register E211). To keep the path for a file in the project, attach it with an `@` mention, or type its path and ask the Lead to read it.
- If the Lead's server dies, nothing restarts it: the session ends, `aew opencode` exits non-zero, and its result says how to go on, which depends on the seat. If it never starts, `aew opencode` exits non-zero and names its log; `aew doctor` checks the rest.
- AEW wakes the Lead when a run needs it, by posting to the session you last viewed, so the Lead ends its turn after a dispatch and you can talk to it meanwhile; `aew status` shows each wake under "Lead wakes".
- **To turn wakes off,** set `lead.push_wake: "off"`, quoted, in `.aew/policy/execution.yaml`, and adopt it at your own terminal: `aew manifest adopt --reason ... --expect-rev N`, with the revision from `aew status`. That needs the Lead credential: with it in your shell (`AEW_LEAD_TOKEN`) posts stop within seconds, in a running session too. A session that took the seat itself holds the only credential, so end that session first. While an edit isn't adopted, no wake is posted, and `aew status` says the last pass failed. The Lead's next steps go back to waiting with `harness_wait`, and a Lead already idle stays idle until you talk to it. A project that doesn't name the key has wakes on. Turning them back on takes effect at once in a session that started with them on, and at the next launch otherwise.
- Wakes have these limits:
  - **`/new`:** no session exists between `/new` and your first prompt, and the server gives no signal for that gap. A wake in it goes to the session you left and spends a turn there, and it doesn't show in the TUI. `aew status` shows it was posted, and to which session.
  - **A restart:** a wake before your first prompt in this launch is held for it, and `aew status` shows it outstanding. Nothing shows in the TUI until you type.
  - **Windows:** no wake is posted, whatever the switch says, so the Lead waits with `harness_wait` (register E210).

In the TUI, the agent is `aew-lead`, with these commands:

| Command | What it does |
|---|---|
| `/aew-resume` | rebuild the Lead's context from AEW (`aew resume`) |
| `/aew-status` | work, Lead authority and harness runs, with proposed next actions |
| `/aew-ticket <objective>` | draft a Ticket and a plan for an objective, show them to you, and create them only after you agree |
| `/aew-next <id>` | take the next step on a unit: dispatch with `--launch`, wait, ingest, advance |
| `/aew-usage` | the workers' usage and cost from `aew usage show`, with what is unpriced or reads as a floor |
| `/aew-handoff` | record a checkpoint for a handoff. The handoff itself (`aew lead handoff offer`) is yours, at your own terminal. |

**The Lead's guide.** The Lead's system text includes the project's guide to how AEW works (`aew guide`, rendered from this project's own gates policy when `aew opencode` starts): what each risk class requires and still guarantees, the Ticket lifecycle, and the typed tool for each step, with its shell command as the fallback. The default-policy version is [`lead-guide.md`](lead-guide.md).

The Lead's permissions: reading and searching, `aew`, and `git status|diff|log|show` are allowed; editing files and subagents are denied; any other shell command or tool asks you.

### When AEW's default for a switch has moved

An existing project keeps what its files hold, so at `aew opencode`'s start your terminal may ask about a default AEW has
since changed: the mutating concurrency, or a price table if the project has none. Each prompt says what changes and
whether a stage open now would stop. Type the code it shows to take it, as your decision. Enter alone keeps what you have
and AEW won't ask again; anything else changes nothing and asks again next start. A value other than AEW's old default
is never offered. `aew doctor` shows what is pending or declined, and how to take a declined one by hand. A Lead session
is never asked.

## 4. Runs

The Lead's stages launch a mutating Ticket's runs. From the shell, the Lead dispatches with `--launch` on `work assign`, `work dispatch`, `work redispatch` and `invoke create`. Each starts run 1 of the new invocation. Then:

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

**On Linux** (with bubblewrap) every run, and the Lead's TUI that `aew opencode` starts, runs contained: a sandbox per run from its role, checked by a self-test before anything starts, with a network of its own whose only routes out are AEW's provider relay and egress proxy (ADR-0009). A run whose containment fails is refused unless the execution policy says `containment.mode: allow_weaker`, which runs it labelled `workdir_separation_only`. The general Lead command, `aew lead session`, runs the harness named after its `--` as it is, so on Linux it is refused unless the policy says `containment.mode: allow_weaker`: `aew opencode` is the contained Lead (G3 addendum 7). Every launch that runs weaker is entered in this host's register of weaker contexts while it runs, so G3 can tell that something weaker ran here.

**Your secrets** are hidden from every contained run: the credential directories AEW knows (`~/.ssh`, `~/.aws`, `~/.config/gh`, your OpenCode's directories and others) are empty inside, or not there at all where they do not exist yet, and a credential file (`~/.netrc`, `~/.git-credentials` and others) is not there at all, whether or not it exists yet, so one your own tools replace or create during the session stays hidden. The execution policy's `containment.hide` adds paths, hidden the same way. A directory a secret is left out of shows the rest of what it held at the launch: an entry made there during the session is seen from the next launch, and one replaced there shows what it held at the launch until then. In your project, or a worker's workspace, a secret is masked in place and read-only, and the launch names it (see the table below). So is a secret directly under `/`, or in a directory your account cannot list, which cannot be emptied and refilled: one replaced or first created there during the session is seen until the next launch, and a write there needs root, or a directory you cannot read. A mask covers its path only, not a committed copy of the file: the project's history, or a worker's checkout.

**The Lead's session** (`aew opencode`) runs in a `lead` sandbox:
- it writes the working tree; `.aew/` and the git metadata are read-only, so a commit fails there while `git status`, `diff`, `log` and `show` work, and its Lead `aew` commands still reach the broker, which writes AEW state for it;
- its `aew status`, `resume`, `harness status`, `harness wait`, `map show` and `map diff` read what its sandbox hides (the runs' records, the notifier, the steering loop, the maps), so the broker runs them on your machine and passes back what they print; a write it cannot make (such as `history compact`) is refused before it starts, and is yours to run in your own shell;
- its OpenCode state is its own, under `.aew/local/harness/lead`, kept per project between sessions; your OpenCode configuration and logins are not visible inside, and its first lines name any MCP servers of yours it leaves out;
- your TUI preferences (theme, keybinds and the like) come from your own OpenCode at each start, without its plugins; one you change inside the Lead lasts that session, so change them in your own OpenCode. Your recent models are copied in once, when the Lead's state is first made; your prompt history never is;
- its network reaches your providers through AEW's relays and public addresses over https through the egress proxy; a plain `http://` request is refused with the `https://` form to ask for instead;
- the TUI runs on a terminal AEW relays: what you type and what it draws pass unchanged, and your terminal gets its settings back however the session ends.

**Elsewhere** (Windows) AEW provides **workdir separation only**: each run has its own workspace, private harness state and scratch directory. It does **not** contain the filesystem. An agent's shell runs as you, and can read and write anything your account can. Every run record says `containment: workdir_separation_only`, and `aew doctor` warns about it. There, use AEW with models on scratch repositories and clones, not on your only copy of something that matters.

## When something goes wrong

| Symptom | Meaning | What to do |
|---|---|---|
| The TUI crashed or was closed | runs continue; nothing is lost | `aew opencode` again, then `/aew-resume` |
| A run is `lost` or `crashed` | the harness died; the Ticket and credential are unchanged | `aew harness launch INV --expect-rev N`, or `aew invoke cancel` |
| A run is `ended_without_evidence`; `aew harness wait` exits 20 and its result starts with a `headline` | it stopped without its expected output | `aew harness send` a nudge while it runs, relaunch, or cancel |
| A run is `crashed` with `reason_code: provider_auth_failed` | the model provider rejected the selected key | replace the stored API-key login or update the explicit export, then relaunch. A broker using an export must restart with the new environment. Each relaunch resolves the source again. |
| `HARNESS_INCOMPATIBLE` | no binary, a version that is not V2, a missing API capability, or the pinned model or variant missing from the catalog | the message names the gap; check `AEW_OPENCODE_BIN`, the policy's model ids, and `provider_env` |
| A contained launch refused with `CONTAINMENT_UNAVAILABLE`, reason `mask_holds_the_run` (Linux) | an `XDG_*_HOME` puts one of OpenCode's directories over your project, your home directory or AEW's own, and a contained run hides OpenCode's directories whole; a link in one of the directories a contained run hides points at such a directory; or `OPENCODE_DB` (or `XDG_DATA_HOME`) puts OpenCode's login database in your project or a worker's workspace, where OpenCode makes its `-wal` and `-shm` files as it runs and no mask covers them | do the one step the message gives for each: move OpenCode's files and unset the variable; point the link elsewhere or remove it; or close OpenCode, move the database with its `-wal`, `-shm` and `-journal` files, and set `OPENCODE_DB` to its new path. It holds for every contained launch, workers included |
| A contained launch says paths are "masked in place, read-only, in the tree this run writes" (Linux) | a secret lies in your project or a worker's workspace (a policy `containment.hide` entry there, `OPENCODE_CONFIG`'s file, or what a link in a hidden directory such as `~/.ssh` points at): there it is masked as it is at the launch, read-only, and a write to it fails; a file the host replaces by rename, or first creates there, during the session is seen inside until the next launch, and one absent at the launch is not masked | edit such a file at your own terminal, or keep the real file outside the project (for ssh, an `Include` from your real `~/.ssh/config`) |
| A contained launch says a path is masked in place "as it cannot be left out of its directory" (Linux) | a secret lies directly under `/` or in a directory your account cannot list, which a contained run cannot empty and refill: it is masked as it is at the launch, read-only, and one absent at the launch is not masked; a file replaced or first created there during the session is seen inside until the next launch | move the secret into a directory your account can list, or keep it as it is: a write there needs root, or a directory you cannot read |
| A contained launch refused: "policy containment.writable root ... would let every contained run write ..." (Linux) | the root holds a path containment protects, such as a secret's, which counts whether or not the secret exists yet, so `~/.cache`, `~/.config` and `~/.local` are refused as roots; the message names each secret by what it is | list the narrower directory the message names instead (such as `~/.cache/<tool>`), or take the root out of `containment.writable`. It holds for every contained launch, workers included |
| A contained launch refused: "this launch needs N arguments for bubblewrap, more than the 9000 ..." (Linux) | the directories a secret is left out of hold so many entries that putting each back passes bubblewrap 0.4.0's maximum of 9,000 arguments (about 2,950 entries in all) | move entries out of the largest directory the message names into a subdirectory. It holds for every contained launch, workers included |
| A write inside the contained Lead refused with `PERMISSION_DENIED`, reason `lead_masked` (Linux) | the path is one of the masks in your project that the launch line named | edit it at your own terminal, or keep the real file outside the project |
| A contained launch refused: "a ... socket is reachable ... no process AEW can read holds" (Linux) | a socket of yours that a contained run could reach, whose server AEW can't see. On WSL that server may be in another distro: `/mnt/wsl` and the socket table are shared across distros, so a listener in one refuses launches in another | stop what serves it, or have it listen under a masked path or off the shared mount; `aew doctor` names the socket and where it can listen. Otherwise set `containment.mode: allow_weaker` to run labelled weaker |
| A launch refused with `CONTAINMENT_UNAVAILABLE`, reason `client_cert_unusable` | the provider's client certificate can't be used: the message has one line per problem, naming the file (an expired certificate, one not matching its key, a key with a passphrase, a file that can't be read, a CA file with no certificate, an upstream that isn't `https://`) | fix what each line names (`aew doctor`'s `client-cert` line checks it), then launch again: the relay reads the files at each launch |
| A launch refused with `CONTAINMENT_UNAVAILABLE`, reason `client_cert_no_relay` | the provider needs a client certificate, and the run would have no relay to present it (a `shared` or `isolated` network, Windows, or a sandbox that couldn't be established under `containment.mode: allow_weaker`) | run it on Linux with `containment.network.mode: proxy_only` and containment that works (`aew doctor` names what is missing). Otherwise, for a worker, pin a profile whose provider needs none; for `aew opencode`, give the Lead another provider: log in with your own OpenCode at your own terminal (`opencode auth login`), or pass a key with `--provider-env NAME` |
| `aew opencode` refused with `HARNESS_INCOMPATIBLE`, reason `client_cert_no_model` | the Lead's only provider takes a client certificate, and no OpenCode profile pins a model of it, so the Lead would have none to choose (its configuration names only the models the profiles pin for such a provider) | pin one: a profile with `provider:` that provider and its `model`, then start `aew opencode` again |
| A run's provider request answered 502 with `X-AEW-Refusal: client_cert_refused`, `client_cert_required` or `upstream_untrusted` | the provider refused the relay's client certificate, or asked for one and the policy names none; or the provider's certificate isn't signed by the policy's CA file | check the certificate with `aew doctor`; for `upstream_untrusted`, put the provider's current CA in the file `containment.network.client_certs.<provider>.ca` names, and launch again |
| A launch refused with `HARNESS_INCOMPATIBLE`, reason `provider_env` | a named export is missing or unusable on the environment path, or a required custom or proxy variable is missing; nothing was dispatched or started | set it in the terminal you start AEW from, then run the command again there. A launch the Lead or its steering loop makes reads the environment the Lead session (`aew opencode`, `aew lead session`) started with: restart the session from that terminal; the message says when it came from a session |
| A launch refused with `HARNESS_INCOMPATIBLE`, reason `provider_key_missing` | the relay has no usable key for the pinned provider. This is also the reason when its selected export is unset and an eligible stored login cannot supply it | Use the named export if the deciding login is refreshing, with an upstream override, or when containment falls back without a relay. For an eligible provider with no refreshing login to preserve, run `opencode auth login <provider>` at your own terminal and choose the API-key method. |
| A dispatch refused with `VALIDATION_FAILED`, field `profiles.<name>.model` | the model id's prefix names another provider than the profile's `provider` | write the id exactly as OpenCode prints it; the message names both ids it may mean |
| `RUN_LIVE` | the latest run may still be running | wait for it, or relaunch with `--replace` |
| `STALE_AUTHORITY` naming a rotation | an old run's credential was replaced | expected: only the latest run can act |
| launch refused, no execution profile | the invocation was dispatched while the policy was unconfigured | configure the policy, then dispatch a new invocation (a pin never changes) |
| A fingerprint error naming `nul` | a file named `nul` in a workspace, made by a Windows-style `> nul` redirect in bash | delete the file (`future-work.md` O1) |

The model catalog and agents load asynchronously when a server starts. Health waits up to 90 seconds for them (`AEW_OPENCODE_CATALOG_S`); a slow provider catalog may need more. A run's whole start, from custody to running, is capped by a deadline derived from these waits and the adapter's other launch timeouts: 620 seconds at the defaults, rising with `AEW_OPENCODE_CATALOG_S`. `AEW_RUN_START_S` replaces it. A start that passes it ends `launch_failed` with a reason naming the variable.
