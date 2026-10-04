# T10 — Installation, bootstrap and integration UX: research and a bounded design

- **Status:** research and design note from the independent architecture review (thread T10, added by the designer's addendum of 2026-10-04). Not governing. Research candidates for the design authority and operator; the design stops at the shape F18 (operator bootstrap and host integration, unscheduled, waits on Q12) will fill.
- **Basis:** `docs/guides/quickstart.md` and `opencode.md` (the install and first-run path as documented today); `src/aew/doctor.py` (what `aew doctor` checks: Python, git, importable modules, libyaml, project policy); `knowledge/discovery.py` (what `aew init` discovers); `knowledge/manifest.py` (what it writes, including `checks.yaml` "not guessed at init"); the OpenCode and Codex configuration documentation read for T9 (layering, `OPENCODE_CONFIG_CONTENT`, `CODEX_HOME`, `--config` overrides, `requirements.toml`); T6's probes (the model catalog is a network fetch; the runtime honours proxy variables); the airgap research §7 (offline bundle and qualification); the register (F18, D2 installer, Q12 hosting, F2 scratch rule); the handoff memory that the SPT py311 offline wheelhouse already carries PyYAML and jsonschema.
- **Evidence classes:** [doc] current documentation; [repo] read from the frozen tree; [probe] T6; [inf] inference; [rec] recommendation.

## 1. Where the first-run path stands today [repo]

`quickstart.md`: create a venv, `pip install -e ".[dev]"`, `aew doctor`, `cd <repo>`, `aew init`, **edit `.aew/policy/checks.yaml` by hand** ("gates stay blocked until you do"), `aew lead acquire` or `aew opencode --acquire`. `opencode.md`: **edit `.aew/policy/execution.yaml` by hand** (harness, provider, model, effort, `provider_env` names), set the provider key in the shell, `aew doctor` (`policy:execution PASS`, `containment WARN`), `aew opencode --acquire`. OpenCode 2.0.18 must be installed separately; on Windows the Desktop app's versioned CLI is found automatically, elsewhere `opencode-cli` on `PATH` or `AEW_OPENCODE_BIN`.

`aew doctor` checks: Python version, `git` on `PATH`, importable modules, libyaml (WARN without), the project's policies (PASS/FAIL per policy), containment (WARN). It does not check the harness binary or version, the protocol shape, the provider key's name being set, the catalog, the network, or generated integration artefacts, and it has no INFO tier.

`aew init` discovers authority **candidates** (ADR directories, contracts, schemas, READMEs, `src/`) by a fixed rule table and writes `OPEN-QUESTIONS.md` with them; it writes `checks.yaml` unconfigured by design ("Not guessed at init: configure it, or gates that need it stay blocked"); it writes no map (T5) and no execution policy values.

**What already matches the addendum's desired direction:** AEW never writes the user's OpenCode configuration or state (`opencode.md`: "never writes to your OpenCode configuration or state"); every run's harness configuration is **per-session generated and inline** (`OPENCODE_CONFIG_CONTENT`), with private XDG state under the run directory. That is the "per-session generated config" ownership model, already chosen for runs. The Lead's TUI is the same (`aew opencode --print-config` shows it).

**What matches the anti-pattern:** two YAML files edited by hand, one environment variable exported, the test command guessed by the operator, and a mismatch (`policy:execution FAIL`, a missing model variant, a missing binary) debugged from error output.

## 2. Survey: patterns worth borrowing [doc], and what each would mean for AEW

Concrete workflows, not visuals. Each row names the pattern, where it is practised, and the AEW translation.

| Pattern | Practised by | Translation |
|---|---|---|
| **Single install command, pinned version, isolated environment** (`pipx install`, `uv tool install`, a static binary on `PATH`) | Python CLIs generally; OpenCode ships a single Bun binary; Codex ships a single binary per platform | `pipx`/`uv tool install aew==X` for connected hosts; a wheelhouse for air-gapped ones (§5). AEW is pure Python with two runtime dependencies, so a wheel is the artefact; no binary is needed. |
| **`doctor` with tiered findings and a fix hint per finding** | `brew doctor`, `flutter doctor`, `gh auth status`, `codex features` | `aew doctor` grows ERROR / WARN / INFO and a one-line remedy per row (§6). |
| **Init that proposes, operator approves, then applies** (`git init` writes nothing surprising; `terraform plan` → `apply`; `npm init` asks and shows the result; `codex` asks before trusting a project) | Terraform, npm, Codex's project trust prompt | `aew init` already proposes authority candidates; extend the same proposal mechanism to the test command, the harness, the model profile and the map, with `aew init --apply <proposal>` or an interactive accept (§4). |
| **Project configuration is a generated, ignored, regenerable fragment; the user's global config is never edited** | Codex's `--config` overrides and private `CODEX_HOME`; OpenCode's `OPENCODE_CONFIG_CONTENT`; direnv's `.envrc` pattern | Already AEW's rule for runs. Extend it to the operator's Lead session and make the generated fragments inspectable on disk under `.aew/local/integration/<harness>/` with their source hash (§4, §5). |
| **Repository detection that reports evidence, not conclusions** (`cargo metadata`, `npm ls`, Dependabot's ecosystem detection; GitHub's language stats from file extensions) | package managers, hosting providers | The T5 generator: build system, test runner and languages from files that prove them, offered as proposals with the file named. |
| **Non-interactive mode is first-class** (`--yes`, `--json`, exit codes, `CI=1`) | every modern CLI; `codex exec --json`; `opencode run --format json` | `aew init --proposal-file` and `--accept-proposal` for CI and for the air-gapped operator who scripts the setup. |
| **Capability and version probing before use, failing closed** | AEW's own OpenCode adapter; Codex `app-server generate-json-schema` | Make the probe a `doctor` row and a `launch` precondition (it is already the latter). |
| **Offline bundle = manifest with hashes + a verifier that proves completeness** | `pip download` wheelhouses; Debian `apt-offline`; Nix closures; signed release manifests | §5: a bundle manifest `aew-bundle.yaml` with every wheel, binary, catalog and skill directory hashed, and `aew doctor --bundle <path>` proving it (airgap research §7 "cold-start acceptance"). |
| **Upgrade that migrates explicitly and can roll back** (schema-versioned state with `migrate` as a command; `brew` keeps old versions; database migrations with down paths) | AEW already: `aew migrate` is one transaction on a quiescent project (ADR-0011 invariant 7) | §6: an upgrade is a new venv or tool version plus `aew migrate`; rollback is the previous version plus the untouched `.aew/` (control schema versions refuse an older engine: "the baseline engine refuses an M4 control file", M4 plan §5). |
| **Trust prompts for project-supplied executable configuration** | Codex (hooks trusted by hash; project trust level), VS Code workspace trust | AEW's rule is stronger and simpler: project harness configuration, plugins, hooks and `AGENTS.md` never load into a run (T9 §B). `doctor` reports their presence as INFO so the operator knows they are being ignored. |

Patterns **not** borrowed: curl-pipe-shell installers (unsigned, network-dependent, incompatible with air gap); auto-update (OpenCode's `autoupdate` is disabled by the projection; AEW should never self-update); writing into `~/.config/opencode` or `~/.codex` (ownership seizure); a GUI installer (F18 is a CLI bootstrap; the dashboard F20 is read-only).

## 3. The proposed workflow

```text
install            pipx/uv tool install aew==X        (connected)      | aew-bundle.yaml verified + wheelhouse install (air gap)
    ↓
aew doctor         ERROR/WARN/INFO over host, runtime, git, harness binaries found, containment capability, bundle completeness
    ↓
cd <repo>; aew init
    ↓  inspects: repository (T5 generator: build system, test runner candidates, languages, generated dirs),
       authority candidates (today), harnesses on PATH or configured (OpenCode Desktop CLI, opencode-cli, codex),
       provider key names present in the environment (names only, never values), existing .aew/ (upgrade path)
    ↓  writes: .aew/ as today, plus .aew/local/init-proposal.yaml   (everything derived, marked proposed)
    ↓
operator reviews the proposal (printed as a table; or `aew init --accept-proposal` non-interactively; or edits the file)
    ↓
aew init --apply   applies accepted proposals: checks.yaml (the test command), execution.yaml (harness, profiles, provider_env names),
                   the first codebase map, accepted authority candidates; refuses to apply anything not in the proposal
    ↓
aew doctor         now checks the project too: policies, the pinned harness version against TESTED_VERSIONS, the protocol shape
                   (a dry probe: start the server, read /openapi.json, stop), the provider key name set (not its value),
                   the model and variant present in the catalog (needs network or a seeded catalog), containment self-test,
                   generated integration fragments fresh (hash of inputs)
    ↓
aew opencode --acquire   (or aew codex --acquire once an adapter exists): the Lead's harness, with the generated projection
    ↓
first useful Ticket     /aew-ticket <objective>  →  draft, plan, accept, dispatch --launch, wait, ingest, DONE
```

What the operator **must decide:** which harness; which provider and model per profile (the profile ids and the routing are proposals, the choice is theirs); whether to accept each authority candidate; whether the test command proposal is right; containment mode if they want `allow_weaker`. What AEW **derives:** build system, languages, generated directories, the map, harness binaries present, key names present. What AEW **proposes and never applies silently:** `checks.yaml`'s command, `execution.yaml`'s profiles, authority classes, the map pointer. What happens **automatically:** `.aew/` structure, the proposal file, the generated integration fragments, the doctor probe. **Restart points:** after `init --apply` nothing restarts (no daemon); after an AEW upgrade the Lead session restarts (the broker is in-process) and `aew migrate` may be required; after a harness upgrade the pinned version changes and `doctor` says so before any launch.

## 4. Configuration ownership model

Six options were listed; the recommendation keeps the one already chosen for runs and names where each artefact lives.

| Artefact | Owner | Where | Regenerated when | Operator-visible |
|---|---|---|---|---|
| Harness configuration for a run | AEW, per run | inline (`OPENCODE_CONFIG_CONTENT`; Codex: a per-run `CODEX_HOME/config.toml` written by the adapter) under `.aew/local/harness/runs/<run>/` | every launch | `aew harness config <harness> <INV>` (exists) |
| Harness configuration for the Lead's session | AEW, per session | inline, plus a written copy `.aew/local/integration/<harness>/lead-config.json` with `inputs_sha256` | every `aew opencode`; stale when policy, roles or AEW version change | `aew harness config <harness> --lead` (exists) |
| MCP server registration for the Lead (T1) | AEW, inside the above | the projection's `mcp.servers.aew` | with the projection | same |
| The operator's own harness configuration (`~/.config/opencode`, `~/.codex`) | the operator | untouched | never by AEW | `doctor` INFO: "your global OpenCode config is not used by AEW runs" |
| Project harness files (`opencode.json`, `.opencode/`, `.codex/`, `AGENTS.md`, `.agents/skills`) | the project | untouched; **not loaded into runs** (T9) | never by AEW | `doctor` INFO lists them as ignored by runs |
| AEW project policy (`.aew/policy/*.yaml`) | the operator, via proposals | `.aew/policy/` (git-tracked) | `init --apply`; hand edits adopted by `manifest adopt` | the proposal table |
| Curated skills for runs (D3) | AEW, from the card's requests | a run-private `.agents/skills` under the run directory | every launch | the run's projection |

Rejected: **patching user configuration** (ownership seizure; the addendum's concern), **a global config** (per-project pins are the point), **a generated include** (OpenCode merges layers, so an include cannot exclude the user's other layers; Codex has `--config` overrides but a project `config.toml` would still merge with `CODEX_HOME`'s). **A wrapper config** is what AEW does: the wrapper is the projection plus `OPENCODE_DISABLE_PROJECT_CONFIG` / a private `CODEX_HOME`.

**Conflict detection** is a doctor row: when a project or global harness configuration exists that would change behaviour if it were loaded (plugins, MCP servers, `AGENTS.md`), doctor says it exists and is ignored by runs; when the operator's Lead TUI *does* load their global configuration (it does today unless `--pure`), doctor says which layers the Lead model can see. **Preserving customizations** is automatic (nothing is edited). **Removal** is `rm -rf .aew/local/integration` plus `aew doctor` (regenerates on next launch); **rollback** of a policy proposal is `git checkout .aew/policy` (tracked). **Regeneration** keys on `inputs_sha256` (AEW version, policy files, role cards, harness version).

## 5. Two profiles

### Connected developer environment

- `pipx install aew==X` (or `uv tool install`); Python 3.11+ from the host; `aew doctor` names the missing pieces with the install command for the host's package manager.
- Harness: the operator installs OpenCode or Codex normally; doctor finds the binary (Desktop CLI, `PATH`, `AEW_OPENCODE_BIN`) and checks the version against `TESTED_VERSIONS`; a newer version is WARN ("untested; the probe decides at launch"), an older or V1 is ERROR.
- Provider: the key in the operator's environment under the name `execution.yaml` lists; doctor checks the **name is set** and, with `--online`, that the catalog lists the pinned model and variant.
- Updates: `pipx upgrade aew`, then `aew doctor`, then `aew migrate` if doctor says `MIGRATION_REQUIRED`.

### Rocky 8 / air-gapped deployment

- **Bundle:** `aew-bundle-<version>-rl8-py311.tar` containing: the `aew` wheel and its two dependencies (PyYAML with libyaml, jsonschema and its deps) as a wheelhouse for py311/x86_64; the pinned harness binary (OpenCode 2.0.18 `opencode-cli`, or the Codex binary) with its `.version` file; **the harness's model catalog as a seeded state file** ([probe] T6 part 3 decides whether this is needed for a configured provider; the built-in catalog serves the `opencode` provider offline); the curated skills directory; `aew-bundle.yaml` with the SHA-256 of every file, the AEW version, the harness version and the spec set; a detached signature (the signing key lifecycle is an ADR-0005 question, as the storage investigation said of history hashes).
- **Install:** `tar -x`, `python3.11 -m venv ~/aew-venv && pip install --no-index --find-links wheelhouse aew`, `aew doctor --bundle aew-bundle.yaml`. Doctor verifies every hash, the Python ABI, `bwrap` and `user.max_user_namespaces > 0`, and that **no network is needed for `serve` to start** ([probe] T6: `opencode-cli serve` starts and answers with `--unshare-net`; its only startup fetch is `models.opencode.ai`, which is `OPENCODE_DISABLE_AUTOUPDATE`-independent and must be absent or seeded).
- **No hidden fetches:** the projection already disables autoupdate, share, LSP and formatter; T6 adds the egress proxy, so a fetch that is not in the allowlist fails visibly in the proxy log instead of hanging. Doctor runs the dry probe with network unshared and reports any attempted connect (T6's strace method, or the proxy log) as ERROR for a bundle claiming offline completeness.
- **Upgrade bundle:** the same shape; `aew migrate` after install; **rollback** = the previous venv (kept beside the new one, `~/aew-venv-<version>`) and the untouched `.aew/`; a newer control schema refuses the older engine, so rollback after a migration is refused with the schema version named, which is the correct fail-closed answer, and doctor says it before the upgrade ("this upgrade migrates control state v2 → v3; rollback after that needs a restore of `.aew/` from before").
- **Deterministic preflight:** `aew doctor --bundle --json` is the acceptance record for a host; it is the airgap research's "cold-start acceptance" in one command.

## 6. `aew doctor`: the rows

ERROR = cannot safely operate (launch refuses); WARN = degraded capability (launch proceeds with a weaker label or without a feature); INFO = optional enhancement unavailable or a fact worth knowing. Each row has a one-line remedy.

| Row | ERROR | WARN | INFO |
|---|---|---|---|
| OS / kernel | unsupported platform | Windows: no OS containment (today's WARN) | kernel version; `max_user_namespaces` value |
| Python / runtime | < 3.11; missing dependency | pure-Python YAML (today) | version |
| Filesystem | `.aew/` not writable; case-insensitive FS with colliding paths | network share detected (locking caveat) | — |
| Git | missing; repo not found; not on the authoritative branch | `core.fileMode`/`core.symlinks` surprises | version |
| Harness binary | none found when `execution.yaml` is configured; V1 | version not in `TESTED_VERSIONS` | which binary and where |
| Protocol shape | dry probe fails (missing operation or field) | — | probe passed; schema hash |
| Containment | `mode: required` and bwrap missing or user namespaces disabled | `allow_weaker` in effect | network containment not provided (until T6) |
| Credentials / gateway | `provider_env` name not set in the environment | model or variant not in the catalog (offline: catalog not seeded) | key present (name only); gateway reachable (with `--online`) |
| Build / test configuration | `checks.yaml` unconfigured when a gate needs it | test command proposal not yet accepted | the detected build system |
| AEW project / schema version | control schema newer than the engine | `MIGRATION_REQUIRED` | spec set, control schema |
| Generated integration config | — | stale (`inputs_sha256` changed) | regenerated on next launch |
| Offline completeness (`--bundle`) | a hash mismatch or missing file; a startup fetch attempted with network unshared | — | bundle version |
| Permissions / account layout | running as root; `.aew/` owned by another user | home secrets present that the layout will mask | which paths are masked |
| Project harness files | — | — | `opencode.json`, `.codex/`, `AGENTS.md`, `.agents/skills` present and ignored by runs |

## 7. First-run failure and recovery UX

- Every refusal names the row and the remedy; doctor's JSON is the same shape as its text so a script can act on it.
- A failed `init --apply` leaves the proposal file and applies nothing (one transaction; `.aew/` is the commit point already).
- A failed launch (`HARNESS_INCOMPATIBLE`, `MIGRATION_REQUIRED`, containment self-test) points at the doctor row that would have predicted it, and doctor is re-run automatically in the error output's last lines.
- "What remains to be fixed" is one list: `aew doctor --todo` prints only ERROR and WARN rows with remedies, in the order to fix them.
- No daemon, so no restart dance: the Lead session is the only long-lived process and it is the operator's terminal.

## 8. Ownership of the work

| Part | Belongs to |
|---|---|
| Proposal mechanism, `init --apply`, `--accept-proposal`, repository inspection (via the T5 generator) | `aew init` (engine) |
| Tiered rows, remedies, `--bundle`, `--online`, `--todo`, the dry probe | `aew doctor` (engine; `doctor.py` grows a row registry) |
| Harness discovery, version check, generated fragments with `inputs_sha256`, per-run `CODEX_HOME`, curated skills directory | harness adapters (ADR-0009) |
| Wheelhouse, bundle manifest, signature, catalog seeding, venv-per-version layout | packaging and release work (CI `nightly`, a `tools/bundle.py`) |
| Host integration under the hosting model (where the operator's session runs, two-account profile, VM) | F18 (after Q12) |
| A first-run checklist view | later UI (F20 is read-only; this is not it) |

## 9. Non-goals

- No installer platform: no GUI installer, no package repository hosting, no self-update, no plugin marketplace.
- No management of the harness's own installation beyond finding and checking it (the operator installs OpenCode or Codex; the bundle ships a pinned binary for the air-gapped case only).
- No editing of any file outside `.aew/` and the run directories, ever.
- No secret storage: provider keys stay in the operator's environment (connected) or the gateway's configuration (air gap, T6 proxy); AEW never prompts for or writes a key.
- No multi-project orchestration or a global AEW state directory beyond what KC §5.1 already allows for caches.
- No attempt to make `aew init` guess a test command and apply it; it proposes with the evidence file named, and the gate stays blocked until the operator accepts (the current rule, kept).

## Questions for the designer

1. Is the proposal file (`.aew/local/init-proposal.yaml`, applied by `init --apply`) the right ceremony, or should `aew init` be interactive by default with `--non-interactive` for CI?
2. Should doctor's dry probe (start the harness server, read its schema, stop) run on every `doctor`, or only with `--harness`? It takes about 1.4 s on the VM ([probe] T6 A1 `start_s`).
3. For the air-gapped bundle, who signs, and is a detached signature over `aew-bundle.yaml` enough (an ADR-0005 key-lifecycle question, as the storage investigation said of hashes)?
