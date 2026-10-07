# T10 — Installation, bootstrap and first-run UX: frozen bounded design (v0.3)

- **Status:** **Adopted** by the designer and the operator, 2026-10-05 (merging this promotion records it; F18.1 and F18.2 are unblocked). The text is the frozen v0.3 of 2026-10-04, unchanged apart from this line, which read "Design frozen — proposed for operator adoption, 2026-10-04". This v0.3 adds the organization integration seam required by the deployment environment: exact organization-qualified harness pins, an organization launch provider, and an OpenAI-compatible provider-access profile whose mTLS/PKI material remains outside model-controlled harnesses. Host/account placement still waits for F18/Q12. **Q12 was decided on 2026-10-06** ([decision record](decisions-2026-10-06-q12-hosting-and-lead-attachment.md)): where this text says Q12 is open (§1.1 principle 10, the §8 table, §10 decision 13 and the closing line), the host, account and session topology is now chosen by the F18 hosting design within that decision's boundary. **The F18 hosting design v0.6** ([`f18-harness-hosting-attachment-authority-design-v0.6.md`](f18-harness-hosting-attachment-authority-design-v0.6.md), adopted 2026-10-06) sits alongside this one: this design keeps governing `aew init`, `aew doctor` and preflight, and it governs hosting, security principals and the attachment lifecycle. No requirement here is silently superseded. Two collided with v0.6's deployment model, and the designer amended this design narrowly on 2026-10-06 ([decision record](decisions-2026-10-06-f18-2-f18-8-hosting-reconciliation.md) §1, F18.2): where §7 says there is no daemon and the Lead session is the operator's terminal (IBU-16), AEW requires no always-on harness or model daemon but a production attachment may need attachment-scoped or socket-activated supervisor-side services, and the operator terminal is the operator's control surface, not the Lead session; where §6 makes a `.aew/` owned by another user a doctor ERROR (IBU-14), doctor instead validates an ownership and permission matrix against the configured authority boundary, and another owner is not in itself an error; the same matrix judges §6's "`.aew/` not writable" row per principal, never by making `.aew/` writable to the Lead host (the lead developer's reading, record §3); and doctor runs the F18-B0 negative checks, or a bounded equivalent, against the actual Lead-host identity.
- **Basis:** `docs/guides/quickstart.md` and `opencode.md` (the install and first-run path as documented today); `src/aew/doctor.py` (what `aew doctor` checks: Python, git, importable modules, libyaml, project policy); `knowledge/discovery.py` (what `aew init` discovers); `knowledge/manifest.py` (what it writes, including `checks.yaml` "not guessed at init"); the OpenCode and Codex configuration documentation read for T9 (layering, `OPENCODE_CONFIG_CONTENT`, `CODEX_HOME`, `--config` overrides, `requirements.toml`); T6's probes (the model catalog is a network fetch; the runtime honours proxy variables); the airgap research §7 (offline bundle and qualification); the register (F18, D2 installer, Q12 hosting, F2 scratch rule); the handoff memory that the SPT py311 offline wheelhouse already carries PyYAML and jsonschema.
- **Evidence classes:** [doc] current documentation; [repo] read from the frozen tree; [probe] T6; [inf] inference; [rec] recommendation.

## 1. Where the first-run path stands today [repo]

`quickstart.md`: create a venv, `pip install -e ".[dev]"`, `aew doctor`, `cd <repo>`, `aew init`, **edit `.aew/policy/checks.yaml` by hand** ("gates stay blocked until you do"), `aew lead acquire` or `aew opencode --acquire`. `opencode.md`: **edit `.aew/policy/execution.yaml` by hand** (harness, provider, model, effort, `provider_env` names), set the provider key in the shell, `aew doctor` (`policy:execution PASS`, `containment WARN`), `aew opencode --acquire`. OpenCode 2.0.18 must be installed separately; on Windows the Desktop app's versioned CLI is found automatically, elsewhere `opencode-cli` on `PATH` or `AEW_OPENCODE_BIN`.

`aew doctor` checks: Python version, `git` on `PATH`, importable modules, libyaml (WARN without), the project's policies (PASS/FAIL per policy), containment (WARN). It does not check the harness binary or version, the protocol shape, the provider key's name being set, the catalog, the network, or generated integration artefacts, and it has no INFO tier.

`aew init` discovers authority **candidates** (ADR directories, contracts, schemas, READMEs, `src/`) by a fixed rule table and writes `OPEN-QUESTIONS.md` with them; it writes `checks.yaml` unconfigured by design ("Not guessed at init: configure it, or gates that need it stay blocked"); it writes no map (T5) and no execution policy values.

**What already matches the addendum's desired direction:** AEW never writes the user's OpenCode configuration or state (`opencode.md`: "never writes to your OpenCode configuration or state"); every run's harness configuration is **per-session generated and inline** (`OPENCODE_CONFIG_CONTENT`), with private XDG state under the run directory. That is the "per-session generated config" ownership model, already chosen for runs. The Lead's TUI is the same (`aew opencode --print-config` shows it).

**What matches the anti-pattern:** two YAML files edited by hand, one environment variable exported, the test command guessed by the operator, and a mismatch (`policy:execution FAIL`, a missing model variant, a missing binary) debugged from error output.

## 1.1 Frozen bootstrap principles

1. **Bootstrap proposes; the operator authorizes.** Repository inspection may derive facts and propose configuration, but it does not silently create authority, choose a provider/model, or execute project code.
2. **One proposal, one attributable apply.** Every applied proposal has an id/digest, the accepted fields are explicit, and `init --apply` commits policy atomically or not at all.
3. **Static discovery only before trust.** `aew init` may read/parse repository metadata but must not execute package-manager hooks, project scripts, imports, build systems, tests, or arbitrary repository code while producing proposals.
4. **AEW owns only AEW-scoped integration state.** User/global harness configuration is never rewritten. Supported AEW sessions use isolated generated harness configuration/homes.
5. **Generated config is non-secret and regenerable.** Provider credentials are never written into proposal/config artifacts. On Linux `proxy_only`, the configured environment-variable name is a credential source for the supervisor/provider relay, not a value forwarded into the model-controlled harness.
6. **Doctor diagnoses; it does not mutate.** Every finding has a stable id, severity and remedy. Any repair/apply action is a separate explicit command.
7. **Supported means qualified pin.** Harness discovery is not support. Launch requires the adapter's pinned-version/schema/conformance requirements from T9.
8. **Air-gap completeness is an artifact property.** Bundle verification proves exact inventory, platform/pin compatibility and absence of required network fetches before launch.
9. **Upgrade and project migration are separate.** Installing a new AEW version does not silently migrate `.aew/`; schema/spec migration is explicit, quiescent and recoverable according to its migration plan.
10. **Q12 remains open.** This design defines commands, artifacts and ownership semantics but does not choose the final host account/service/session topology.
11. **Harness launch and model access are separate integration contracts.** AEW may use an organization-specific launcher for binary selection/PKI/service-account ceremony while independently using an organization provider-access profile for model transport.
12. **Organization qualification is allowed but cannot bypass AEW conformance.** A harness pin qualified internally may be selected without waiting for a new AEW release, provided its qualification manifest satisfies AEW's minimum pinned-version/schema/capability/conformance contract and AEW re-verifies the effective process after launch.
13. **Corporate PKI is supervisor-side infrastructure.** mTLS certificates, private keys, trust material and organization launcher credentials are never projected into model-controlled shells merely because the organization wrapper uses them.

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

What the operator **must decide:** which supported harness pin/qualification and launch provider; provider-access/model/profile choices; acceptance/classification of authority candidates; whether a proposed project check command is correct; and any deliberate weakening of containment. What AEW **derives without executing project code:** build/language/generated-directory evidence, harness binaries present, credential-source variable names present, and optional map inputs. What AEW **proposes and never applies silently:** check commands, execution profiles, authority classifications and any map pointer. What happens automatically: local bootstrap structure, the proposal file, non-secret generated integration fragments and deterministic doctor probes. **Restart points:** after `init --apply` nothing restarts (no daemon); after an AEW upgrade the Lead session restarts (the broker is in-process) and `aew migrate` may be required; after a harness upgrade the pinned version changes and `doctor` says so before any launch.

## 3.1 Organization launch and provider-access integration

T10 supports deployments in which the organization already owns a wrapper around harness launch, PKI and access to an internal OpenAI-compatible/LiteLLM-style model gateway. AEW does not replace that machinery; it consumes it through two narrow contracts.

### Harness launch provider

The execution profile selects a **qualified harness pin**, not merely an executable path:

```yaml
harness:
  adapter: opencode
  version: 2.0.18
  qualification: org-opencode-2.0.18-2026-10
  launch_provider: organization
```

A launch provider may be:

```text
direct_binary
airgap_bundle
organization
```

The organization launch provider may resolve/install/select the exact approved binary, perform organization-specific PKI/service-account/bootstrap ceremony and start the process. It does **not** decide AEW workflow state or satisfy conformance by assertion.

After launch, AEW independently verifies the effective harness identity and required properties: reported version, artifact/qualification identity where available, pinned protocol/schema fixture, required capabilities, generated configuration, containment/custody checks and readiness. A wrapper statement that it launched version X is not a substitute for effective verification.

### Harness qualification manifest

Qualification data is external to adapter source code so an organization can validate and adopt a new harness pin without waiting for an AEW code release:

```yaml
schema: aew/harness-qualification/v1
harness: opencode
version: 2.0.18

artifact:
  platform: linux-x86_64
  sha256: ...

protocol:
  fixture_sha256: ...

capabilities:
  transport.mcp.local: pass
  tools.filter.per_agent: pass
  config.isolation: pass

conformance:
  suite_version: ...
  rocky8: pass

qualified_by:
  authority: organization
  reference: ...
```

Allowed qualification sources are AEW-shipped and organization-approved. Both must satisfy the same mandatory minimum conformance contract. Organization qualification may add stricter requirements; it may not waive AEW-required custody, authority or compatibility properties.

### Provider access profile

Model access is configured separately from harness launch:

```yaml
provider_access:
  profile: corp-llm
  protocol: openai_compatible
  transport: organization
  auth: mtls_relay
```

This represents a deployment capability, not secret material. Project policy stores the profile/id and non-secret requirements only.

For the current organization environment, the expected path is:

```text
OpenCode / Codex
    ↓ ordinary OpenAI-compatible request
secretless local provider endpoint
    ↓ AF_UNIX / T6 shim
supervisor-owned provider relay
    ↓ organization mTLS helper / cert + key + CA
internal OpenAI-compatible / LiteLLM-style gateway
    ↓
approved model
```

The provider relay owns the organization authentication mechanism. The model-controlled harness does not receive the mTLS private key, client credential material, organization bearer tokens, or equivalent PKI secrets. If an SDK syntactically requires an API key, the harness receives only non-secret placeholder material while the supervisor-side relay applies the real organization authentication.

The organization wrapper may implement both the launch-provider and provider-access contracts, but they remain distinct AEW concepts. A deployment may therefore use the same project/harness qualification with a direct binary on one host and the organization launcher on another without changing workflow semantics.

### Organization integration qualification gate

Before organization-specific launcher/provider integration is considered supported, one bounded live qualification must prove:

1. one exact organization-qualified harness pin launches through the real organization wrapper;
2. AEW independently verifies the effective pin/schema/capabilities;
3. the harness completes a real model request through the internal OpenAI-compatible gateway;
4. one real AEW-relevant tool/function-call round trip succeeds through that gateway;
5. the production path uses the supervisor-side mTLS/provider relay;
6. corporate client key/cert secrets and launcher credentials are absent from model-controlled environment/files/process-visible state;
7. run termination cleans up the harness/wrapper children according to the process-ownership contract.

Existing operational use of the internal gateway establishes that basic model access and normal harness operation are not architectural unknowns. The live gate is therefore an **integration/custody qualification**, not a new provider-protocol research program.

## 4. Configuration ownership model

Six options were listed; the recommendation keeps the one already chosen for runs and names where each artefact lives.

| Artefact | Owner | Where | Regenerated when | Operator-visible |
|---|---|---|---|---|
| Harness configuration for a run | AEW, per run | inline (`OPENCODE_CONFIG_CONTENT`; Codex: a per-run `CODEX_HOME/config.toml` written by the adapter) under `.aew/local/harness/runs/<run>/` | every launch | `aew harness config <harness> <INV>` (exists) |
| Harness configuration for the Lead's session | AEW, per session | isolated generated config/private harness home; optional non-secret rendered copy under `.aew/local/integration/<harness>/` with `inputs_sha256` | every Lead launch | `aew harness config <harness> --lead` |
| MCP server registration for the Lead (T1) | AEW, inside the above | the projection's `mcp.servers.aew` | with the projection | same |
| The operator's own harness configuration (`~/.config/opencode`, `~/.codex`) | the operator | untouched | never by AEW | `doctor` INFO: "your global OpenCode config is not used by AEW runs" |
| Project harness files (`opencode.json`, `.opencode/`, `.codex/`, `AGENTS.md`, `.agents/skills`) | the project | untouched; **not loaded into runs** (T9) | never by AEW | `doctor` INFO lists them as ignored by runs |
| AEW project policy (`.aew/policy/*.yaml`) | operator-authorized project policy | `.aew/policy/` (git-tracked) | attributable `init --apply` or existing policy-adoption path | proposal/diff + resulting policy |
| Qualified curated skills for runs (D3/F19) | AEW, only when accepted/qualified by the relevant capability policy | run-private skill directory under the invocation | every launch | run projection / capability receipt |
| Harness qualification manifests | AEW release authority or organization qualification authority | AEW-shipped registry / organization-managed trusted location | when a harness pin is qualified/revoked | `doctor` shows source, digest, pin and conformance status |
| Organization launch-provider configuration | organization/operator | organization-owned wrapper/configuration; AEW stores only provider id/non-secret selection | organization policy | `doctor` shows selected provider and effective launched pin |
| Provider-access profile | organization/operator | AEW policy stores profile id/protocol/auth kind only; PKI material stays supervisor/wrapper-side | when deployment access profile changes | `doctor` shows profile and custody mode, never secret values |

Rejected: **patching user configuration** (ownership seizure; the addendum's concern), **a global config** (per-project pins are the point), **a generated include** (OpenCode merges layers, so an include cannot exclude the user's other layers; Codex has `--config` overrides but a project `config.toml` would still merge with `CODEX_HOME`'s). **A wrapper config** is what AEW does: the wrapper is the projection plus `OPENCODE_DISABLE_PROJECT_CONFIG` / a private `CODEX_HOME`.

**Conflict detection** is a doctor row. Supported AEW worker **and Lead** sessions use isolated generated harness configuration and do not inherit user/project `AGENTS.md`, plugins, hooks, MCP servers, skills or harness policy layers unless a specific qualified AEW capability explicitly projects them. The operator's ordinary harness configuration remains untouched and is reported as ignored by supported AEW sessions.

An explicit future `--allow-user-config`/customized mode may exist for operator convenience, but it must be truthfully labelled **customized / outside supported conformance**, must not be used for AEW evaluations, and cannot silently become the default.

**Preserving customizations** is automatic because AEW edits none of them. **Removal/regeneration** applies only to `.aew/local/integration`; deleting it is safe and the next launch regenerates it. Generated input hashes include the AEW/adapter version, harness pin/schema fixture, relevant policy/card/catalog inputs and capability projection; they exclude secret values.

## 5. Two profiles

### Connected developer environment

- `pipx install aew==X` (or `uv tool install`); Python 3.11+ from the host; `aew doctor` names the missing pieces with the install command for the host's package manager.
- Harness: the operator installs OpenCode or Codex normally; doctor finds the binary (Desktop CLI, `PATH`, `AEW_OPENCODE_BIN`) and checks the version against `TESTED_VERSIONS`; a newer version is WARN ("untested; the probe decides at launch"), an older or V1 is ERROR.
- Provider: policy selects a provider-access profile. A simple connected profile may name an environment-variable credential source; an organization profile may name an mTLS/PKI-backed relay profile. Doctor verifies that the selected profile is available **without exposing/logging secret values**. Under T6 `proxy_only`, the supervisor/provider relay consumes the real credential/PKI material and the model-controlled harness receives no real provider key or mTLS private material. `--online` may verify bounded gateway/model readiness separately.
- Updates: `pipx upgrade aew`, then `aew doctor`, then `aew migrate` if doctor says `MIGRATION_REQUIRED`.

### Rocky 8 / air-gapped deployment

- **Bundle:** `aew-bundle-<version>-rl8-py311.tar` contains the AEW wheel + complete wheelhouse, only **qualified supported harness pins**, any qualified optional capability assets, and a canonical `aew-bundle.yaml`. For OpenCode 2.0.18, any offline catalog seed is generated from a clean disposable instance of the exact pin, sanitized, checksum-pinned and treated as compatibility data (T6), not copied from an operator profile. The manifest records every consumed artifact's relative path, type, size, SHA-256, platform/ABI, AEW version, harness pin/schema fixture and spec set.
- **Install:** extract into a staging directory, verify the signed manifest **before consuming bundle executables/wheels**, then create the versioned venv and install only manifest-listed wheelhouse entries. The verifier rejects absolute/`..` paths, duplicate entries, unexpected file types and missing/hash-mismatched consumed artifacts. Doctor verifies ABI/platform, `bwrap`/user namespaces, the qualified harness pin/schema fixture and the no-network startup condition.
- **No hidden fetches:** the projection already disables autoupdate, share, LSP and formatter; T6 adds the egress proxy, so a fetch that is not in the allowlist fails visibly in the proxy log instead of hanging. Doctor runs the dry probe with network unshared and reports any attempted connect (T6's strace method, or the proxy log) as ERROR for a bundle claiming offline completeness.
- **Upgrade bundle:** installing the new tool environment and migrating a project are separate operations. Before an irreversible project/schema/spec migration, `aew migrate --plan` (or the governing migration command) states the compatibility boundary and required backup/restore point. The previous venv alone is a valid rollback only **before** project migration. After migration, rollback requires the exact pre-migration project-state snapshot/restore procedure or is refused fail-closed.
- **Deterministic preflight:** `aew doctor --bundle --json` is the acceptance record for a host; it is the airgap research's "cold-start acceptance" in one command.

## 5.1 Bundle signature and trust root

The bundle signing key is **release/distribution authority**, not a Lead/provider/runtime credential and not automatically part of ADR-0005's invocation-credential lifecycle.

A detached signature over the canonical `aew-bundle.yaml` is sufficient for v1 **if and only if**:

- the trusted verification public key/fingerprint is provisioned independently of the bundle being verified;
- the signed manifest commits to every artifact AEW will consume, including path, file type, size/hash and compatibility metadata;
- the verifier rejects path traversal, duplicates and missing/hash-mismatched consumed files;
- installation consumes only verified manifest-listed artifacts.

The build/release pipeline or designated release operator signs; the runtime never possesses the signing private key. Exact organizational key custody/rotation can be a release-engineering policy/ADR without blocking the bootstrap semantics.

## 6. `aew doctor`: the rows

ERROR = cannot safely operate (launch refuses); WARN = degraded capability (launch proceeds with a weaker label or without a feature); INFO = optional enhancement unavailable or a fact worth knowing. Each row has a one-line remedy.

| Row | ERROR | WARN | INFO |
|---|---|---|---|
| OS / kernel | unsupported platform | Windows: no OS containment (today's WARN) | kernel version; `max_user_namespaces` value |
| Python / runtime | < 3.11; missing dependency | pure-Python YAML (today) | version |
| Filesystem | `.aew/` not writable; case-insensitive FS with colliding paths | network share detected (locking caveat) | — |
| Git | missing; repo not found; not on the authoritative branch | `core.fileMode`/`core.symlinks` surprises | version |
| Harness qualification / launch provider | selected pin/qualification unavailable; wrapper launch fails; effective launched pin mismatches qualification | discovered pin exists but is not qualified | qualification source/digest, launch provider, effective pin |
| Harness binary | no usable binary/launcher target for selected qualification | discovered but unqualified binary | effective binary/path only when meaningful |
| Protocol / supported pin | qualified-pin/schema probe fails or required capability absent | discovered but unqualified version | pin + schema/capability-fixture hash |
| Containment | `mode: required` and bwrap missing or user namespaces disabled | `allow_weaker` in effect | network containment not provided (until T6) |
| Provider access / gateway | selected access profile unavailable; mTLS/provider credential leaked into model-controlled state; required gateway handshake fails | qualified model/profile unavailable | profile id/protocol/auth kind; bounded gateway readiness with `--online` |
| Build / test configuration | `checks.yaml` unconfigured when a gate needs it | test command proposal not yet accepted | the detected build system |
| AEW project / schema version | control schema newer than the engine | `MIGRATION_REQUIRED` | spec set, control schema |
| Generated integration config | generated config contains secret material or unsupported ambient layer | stale (`inputs_sha256` changed) | regenerated on next launch |
| Offline completeness (`--bundle`) | a hash mismatch or missing file; a startup fetch attempted with network unshared | — | bundle version |
| Permissions / account layout | running as root; `.aew/` owned by another user | home secrets present that the layout will mask | which paths are masked |
| Project harness files | — | — | `opencode.json`, `.codex/`, `AGENTS.md`, `.agents/skills` present and ignored by runs |

### 6.1 Doctor execution semantics

Default `aew doctor` runs all **local, bounded, non-mutating** checks needed to predict launch safety, including the harness dry start/schema probe when execution policy is configured. The ~1–2 second cost is acceptable and avoids the worst UX: learning at launch that the pin/protocol is incompatible.

The dry probe is run with AEW-generated isolated config and the narrowest available network mode; it must not rely on arbitrary internet access. Provider/gateway reachability and anything that sends external traffic remain opt-in under `--online`.

Expensive checks may be cached by an `inputs_sha256`, but a launch never trusts an old cache in place of its own required launch-time probe.

Exit semantics:

- any ERROR => non-zero;
- WARN-only => zero by default, non-zero with `--strict`;
- `--json` emits the same stable finding ids/severities/remedies as text;
- doctor never auto-fixes or rewrites policy.

## 7. First-run failure and recovery UX

- Every refusal names the row and the remedy; doctor's JSON is the same shape as its text so a script can act on it.
- A failed `init --apply` applies nothing. The proposal remains inspectable with its original digest. A stale proposal (repository/policy inputs changed) is refused and regenerated/re-reviewed rather than partially rebased.
- A failed launch (`HARNESS_INCOMPATIBLE`, `MIGRATION_REQUIRED`, containment self-test, credential-relay readiness) points at the corresponding doctor finding id. It may suggest the exact doctor command; launch does not secretly perform repairs.
- "What remains to be fixed" is one list: `aew doctor --todo` prints only ERROR and WARN rows with remedies, in the order to fix them.
- No daemon, so no restart dance: the Lead session is the only long-lived process and it is the operator's terminal.

## 8. Ownership of the work

| Part | Belongs to |
|---|---|
| Proposal mechanism, `init --apply`, `--accept-proposal`, repository inspection (via the T5 generator) | `aew init` (engine) |
| Tiered rows, remedies, `--bundle`, `--online`, `--todo`, the dry probe | `aew doctor` (engine; `doctor.py` grows a row registry) |
| Harness discovery, version check, generated fragments with `inputs_sha256`, per-run `CODEX_HOME`, curated skills directory | harness adapters (ADR-0009) |
| Harness qualification manifests and effective-pin verification | harness capability registry / adapter conformance |
| Organization harness launch (PKI, internal distribution, service/account ceremony) | organization launch provider behind AEW launch contract |
| Internal model-gateway access (mTLS/OpenAI-compatible relay) | organization provider-access implementation + T6 supervisor relay |
| Wheelhouse, bundle manifest, signature, catalog seeding, venv-per-version layout | packaging and release work (CI `nightly`, a `tools/bundle.py`) |
| Host/account/session topology, service installation, two-account profile, VM placement | F18 after Q12; deliberately not decided by T10 |
| A first-run checklist view | later UI (F20 is read-only; this is not it) |

## 9. Non-goals

- No installer platform: no GUI installer, no package repository hosting, no self-update, no plugin marketplace.
- No generic replacement for organization harness-distribution/PKI infrastructure. Direct installs, air-gap bundles and organization launch providers are interchangeable acquisition/launch mechanisms under the same qualification contract.
- AEW does not own or persist organization PKI private material. It may invoke/use an organization provider-access implementation from the supervisor-side custody boundary.
- No AEW bootstrap mutation of user/project files outside AEW-owned project/local/run state. Package installation itself is performed by the chosen tool environment/release procedure, not by rewriting user harness configuration.
- No persisted provider-secret storage in AEW project/generated harness config. A connected deployment may source a credential from the operator/service environment into the supervisor-owned T6 provider relay; air-gapped deployments may source it from gateway/service configuration. AEW never writes the secret into model-controlled state.
- No multi-project orchestration or a global AEW state directory beyond what KC §5.1 already allows for caches.
- No attempt to make `aew init` guess a test command and apply it; it proposes with the evidence file named, and the gate stays blocked until the operator accepts (the current rule, kept).

## 10. Frozen designer decisions

1. **Init UX:** `aew init` always materializes a proposal. In an interactive TTY it may immediately present that proposal and offer explicit review/apply; in non-interactive mode it does not apply consequential choices unless a reviewed proposal is supplied explicitly. There is no blanket `--yes` that silently accepts provider/model/authority/check-command decisions.
2. **Proposal integrity:** proposals carry `proposal_id` + `inputs_sha256`; apply is atomic and rejects stale or expanded proposals. Manual edits are treated as explicit operator choices and are shown in the apply diff, not mistaken for AEW-derived facts.
3. **Static-before-trust:** proposal generation never executes repository code. Proposed check commands are evidence-backed strings until explicitly accepted.
4. **Lead isolation:** supported Lead sessions use AEW-generated isolated harness configuration/private state just like worker runs. Ambient user/project plugins, instructions, MCP servers and skills are not silently inherited. A future customized mode must be explicit and outside normal conformance/evaluation.
5. **Doctor default:** run the local harness pin/protocol dry probe on normal project doctor when execution policy exists. Use `--online` only for external gateway/catalog checks. Cache for speed if desired; launch still revalidates required capabilities.
6. **Bundle signing:** use a separate release/distribution signing identity. A detached signature over the canonical complete manifest is sufficient when the trust root is provisioned independently and installation consumes only verified listed artifacts.
7. **Air-gap catalog:** for OpenCode 2.0.18 use the sanitized exact-pin checksum-pinned seed accepted in T6; prefer an official offline-catalog mechanism on future qualified pins.
8. **Harness qualification:** support is by qualified pin, not product name or discovery. Qualification manifests may be AEW-shipped or organization-approved, but both must pass AEW's mandatory conformance contract. This allows internally validated harness versions to be slotted in without waiting for an AEW release.
9. **Organization launch/provider seams:** organization wrappers and PKI are first-class launch/provider-access implementations, not ad-hoc exceptions. Harness launch and model access remain separate contracts; neither gains workflow authority.
10. **Internal model gateway:** treat the existing organization OpenAI-compatible/LiteLLM-style gateway plus mTLS helper as the intended provider-access path. The remaining required evidence is one AEW-relevant tool-call/custody qualification through the real path, not broad protocol research.
11. **Codex packaging:** ship Codex only after a pin passes T9 support qualification. Discovery/installability is not support.
12. **Upgrade/rollback:** tool upgrade and project migration are separate. Previous-env rollback is guaranteed only before project migration; after migration, rollback requires the declared pre-migration restore point or is refused.
13. **T5/Q12 dependencies stay soft:** bootstrap can ship without project maps, and this document does not choose host account/session topology. Map generation is an optional derived proposal when T5 exists; host integration waits for Q12/F18.

No further designer-level question blocks the bootstrap/doctor implementation shape. F18 remains intentionally unscheduled until Q12 settles where these processes live.

### Targeted follow-up evidence

No broad research thread is required. If the independent researcher is used, give it one bounded live task: exercise a qualified harness pin through the real organization wrapper/provider path and record the exact endpoint family used, tool-call round trip, effective model/profile, mTLS helper interface/custody boundary, and absence of PKI material from the model-controlled process. That result becomes organization-integration qualification evidence for this design; it does not reopen T10 unless it contradicts the launch/provider contracts above.
