<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-38
source: 30-stages/STG-15-capability-register/adopted/capr-r2.1/CAPR-POSITION.md
source-sha256: 87a602a7b9b919c06b6a51c7916f89a534aa5051cd42fdcd83d17318bce73429
edits-sha256: none
-->

# The capability register (PROPOSED, revision 2.1)

**Namespace:** `CAPR-`
**Status:** proposed. It amends nothing adopted, and replaces the M6a candidate as the register's design input (`00-governance/reviews/2026-10-24-reset-pass-M6a.md`).
**Authority:** the operator's decisions of 2026-10-24:
- `00-governance/decisions/2026-10-24-operator-AEW-brings-its-tools.md`;
- `00-governance/decisions/2026-10-24-operator-capability-register-position.md`;
- `00-governance/decisions/2026-10-24-operator-capability-register-expandable-and-degradable.md`;
- `00-governance/decisions/2026-10-24-operator-close-M6a-register-commands-in-scope-SPT-as-MCP-store.md`.

**Threat model:** the operator's decision of 2026-10-19, as the security depth reset of 2026-10-24 narrows it: only what a contained agent can reach on its own counts.
**Files:** this file. The stage's `FIRST-BUNDLE.md` and `COVERAGE.md` are build inputs, not rules.

## What the adopted text already decides

- **Discovery and exposure:**
  - discovering a capability is kept apart from exposing it, tools are discoverable and invocable on demand, and routing never bypasses an effect grant (`HEB-09.a`, `HEB-09.b`, `HEB-09.c`);
  - isolation is never weakened for availability (`HEB-09.e`).
- **The agents' tools:** agents get a tool environment for ordinary inspection, building, debugging and testing, with no per-command approvals (`HEB-04.a`). A tool's availability is kept apart from the authority to invoke its protected effects (`HEB-04.g`).
- **Protection:** the executables, runtimes, capability policy and routing that enforce agent limits are protected (`HEB-01.h`). Project or agent configuration never enlarges a harness, tool, plugin or MCP capability (`HEB-01.i`).
- **Credentials:** no access through inherited credentials or provider keys (`HEB-03.e`). Every tool or MCP route of a credential-bearing harness is denied or confined (`HEB-03.q`).
- **Disconnected deployments:** they work, and what is unavailable is said (`AEW-FR-34.a`, `AEW-FR-34.b`).
- **Status:**
  - a capability's status is honest, using the seven semantic statuses `QUALIFIED`, `FUNCTIONAL_ONLY`, `NOT_ESTABLISHED`, `UNSUPPORTED`, `UNAVAILABLE`, `STALE` and `REFUSED` (`S01-04`);
  - a capability matrix is not a grant (`S01-07`);
  - the CLI, the backend, the website and agents read one shared capability source, which nobody silently reinterprets (`S01-21`);
  - work-only endpoints and credentials never travel into general artifacts (`S01-26`).
- **D-01's capabilities read already carries those statuses** (`D01-0.3.4/GET /v1/read/capabilities`, adopted with A-25, not yet built).
- **Evidence:**
  - a result is attributed to its producer (`AEV-05.a`) and admitted on a justified trust basis (`AEV-05.c`);
  - an agent-controlled log alone remains a claim (`AEV-05.g`);
  - protected assurance never requires running untrusted repository configuration privileged outside a confined boundary (`AEV-05.d`). `CAPR-07` extends that to host-placed providers;
  - derived indexes and maps are not authority (`AEW-FR-19.d`).

## The parts

| Part | What it is | Who writes it | Who reads it |
|---|---|---|---|
| The register | provider records, role grants and each capability's status, held as host state outside every sandbox | the operator, through AEW's operator commands; the health checks write status | AEW's host code; the CLI and the site; agents, through their role's catalog |
| The shipped records | the base bundle's provider records, in AEW's own register source | a reviewed AEW release | the register, under the operator's records |
| The operator's records | providers the operator adds, overrides of shipped records, and the preference order where two providers serve one capability | the operator | the register |
| A provider | a CLI tool or an MCP server that serves one or more capabilities | a shipped record, or the operator | the register's resolver |
| A payload | the binary, archive or container image a provider runs | AEW's pinned fetch, or the operator's import | providers, read-only |
| A provider source | where payloads come from: AEW's own bundle; SPT, for every MCP server image AEW imports; or the operator, for any other provider | its own release process, or the operator | the register |
| Agents | the Lead and the workers, each in its sandbox | nothing in the register | their role's catalog |

## Rules

**CAPR-01. Roles ask for capabilities, and the register resolves them to providers.** A role or a skill names a capability, such as `EXACT_CODE_SEARCH`. Replacing its provider changes no role's meaning.
- A capability with no healthy provider is unavailable. It is never served silently by a weaker or unregistered provider.
- When two healthy providers serve one capability, the preference order in the operator's records decides.

**CAPR-02. Each provider has one record.** The record states:
- its type, CLI or MCP;
- its command or entry point;
- the capabilities it serves, as capability IDs in D-01's form (upper case, such as `EXACT_CODE_SEARCH`);
- its placement, in the agent's sandbox or on the host;
- whether it only reads its inputs, or can change them;
- its payload: source, version, and SHA-256 or image digest;
- its health check, a version check and a fixture query;
- the kind of evidence it produces;
- what it needs: network, credentials, or other providers.

**Candidate:** design v0.7's provider record (section 16.1 of `docs/agent-engineering-workflow-design-v0.7.md` in the AEW repository) is a shape the build may start from.

**CAPR-03. A capability's status is per host, honest, and in S-01's terms.** Each capability has one of `S01-04`'s seven statuses, with D-01 0.3.4's wire names:
- **`FUNCTIONAL_ONLY`:** a provider's health check passed. A health check alone never makes a capability `QUALIFIED`.
- **`QUALIFIED`:** only with a qualification record, such as the harness's (the OpenCode version-currency decision).
- **`UNAVAILABLE`:** this host has no provider, or its provider's check fails. The cause says which.
- **`REFUSED`:** the payload does not match its pin, or its record fails validation. The pin is checked at fetch, at import and at every check.
- **`STALE`:** it has not been checked since a new pin, a changed record, or a named host change: the kernel, the C library or the harness version.
- **`NOT_ESTABLISHED`:** it has never been checked on this host.
- **`UNSUPPORTED`:** there is no payload for this host's platform.

The status names the provider, the check and when it ran.
- **One source for everyone:** `aew doctor`, the agents' catalogs and the site read the same status (`S01-21`).
- **On D-01's capabilities read:**
  - the register's status is the read's `observed_status`;
  - the read's `assessment_status` stays `NOT_ESTABLISHED` unless a qualification record exists, which then gives `QUALIFIED` with that record's own issuer, scope, epoch and evidence;
  - where the read carries the provider and the check is the wire track's ("Not covered").
- **Usable means checked:** nothing claims a capability usable unless it is `FUNCTIONAL_ONLY` or `QUALIFIED` (`AEW-FR-34.b`).

**CAPR-04. AEW ships its base tools with every install, pinned.** The base bundle's CLI tools come with AEW whatever the host already has, so AEW works out of the box with versions it knows.
- **Online,** each payload is fetched at install or at first launch, before the first agent run, with no step for the operator beyond the install. It is checked against its pin.
- **Offline,** it arrives in the operator's bundle and is checked the same way.
- **Where it lives:** payloads are host state outside every sandbox's writable binds. Each is bound read-only into every contained context.
- **What the harness gets:** for each base member, AEW's copy is what the harness and the agents get, at the harness's own lookup path. The harness's own tool downloads are turned off.
  - When AEW's copy is absent or refused, nothing serves that name silently.
  - A copy the host has then serves on its own, named in the status and the catalog as an unpinned provider. The capability's status is that copy's own check: `FUNCTIONAL_ONLY` with a limitation naming it unpinned, beside the cause for AEW's copy, or `NOT_ESTABLISHED` until it is checked. The operator may turn host copies off.
  - With no copy at all, the capability is `UNAVAILABLE` or `REFUSED`, with its cause.
- **The project's own tools:** AEW's copy comes first on the path only where the harness needs it (ripgrep). A member whose name has incompatible implementations is offered under an unambiguous name, which the catalog gives. The project's own commands keep the host's tool under the plain name.
- **Two layers of records:**
  - the shipped records are read-only, and change only with a reviewed AEW release;
  - the operator's records override a shipped record of the same name;
  - an upgrade keeps the operator's override, and reports where it differs from the new shipped record.
- **A digest mismatch:** the payload is refused, with the reason. The capability reads `REFUSED`, unless a host copy serves, as above.

**CAPR-05. Only the operator changes the register.** Installing, registering, placing and granting are operator commands, never on the Lead broker's or a worker bridge's tool surface. Each command has its surface-map entry.
- **Project configuration:** project or agent configuration never adds a provider or widens a grant (`HEB-01.i`). Where a project's configuration names a provider, the catalog and doctor say so, and say how the operator imports it (`CAPR-11`).
- **Outside the sandbox:** an agent cannot make AEW run anything outside its sandbox. Every change that adds to or alters what runs outside every sandbox is protected (`CAPR-13`).

**CAPR-06. What a role's catalog lists, and what a grant is for.**
- **Sandbox-placed providers** are bound into every contained context and listed in every role's catalog. Each catalog lists them compactly, and a provider's full interface is exposed on demand (`HEB-09.a`, `HEB-09.b`).
  - They run with the agent's own authority, so a per-role grant would add friction and protect nothing.
  - The operator may drop one from a role's catalog to keep it focused. That hides it, and is not a boundary.
- **Host-placed providers,** every container-backed one included (`CAPR-08`):
  - each role has a plain list of granted capabilities. Its catalog lists them compactly, and a provider's full interface is exposed on demand (`HEB-09.a`, `HEB-09.b`);
  - a request for one outside the grant is refused, saying what was refused, why, and how to ask. The ask reaches the operator as a waiting item that names the exact grant command.
- **A capability grant is not an effect grant:** protected effects stay on their owners' command paths (`S01-07`, `HEB-04.g`, `HEB-09.c`).

**CAPR-07. A provider runs in the agent's sandbox unless the operator places it on the host.**
- **A provider in the sandbox** has only its context's authority. It gets no credential and no network route its context lacks:
  - a record that needs a credential is refused for the sandbox, and is placed on the host instead;
  - widening a context's network for a provider is protected, like host placement (`CAPR-13`).
- **A provider on the host:**
  - exposes typed operations only, never an arbitrary command or arbitrary code;
  - takes as input only what the calling context can already read, staged by AEW, never a path the agent names outside that view;
  - treats the content of its inputs as data, never as configuration, plugins or code it honours (`AEV-05.d`).
    - A tool that cannot be run that way runs confined, with no more than its caller's authority: in the agent's sandbox or, for a container-backed provider, in a container that holds only the staged inputs, with no network, credential or host path.
    - A record that needs a credential and cannot treat its inputs as data has no placement, and validation refuses it;
  - holds any credential itself, scoped to the operation, and never returns it (`HEB-03.e`);
  - never reaches AEW's control plane: no capability creates work, accepts a plan, moves a transition, or acts as the operator.

**CAPR-08. A container runtime never reaches an agent.** A container-backed provider runs on the host side, behind typed operations (`CAPR-07`).
- The runtime's socket stays out of every sandbox, because containment masks `/run` and `/var/run` whole (`CB-03`).
- The register's own launch check fails an agent's launch where a container runtime's socket is reachable from its context. It sits beside containment's socket inventory (A-33), and leaves that inventory's text as it is.

**CAPR-09. A provider's output is evidence of at most its stated kind, never authority.**
- **Attribution:** a call AEW mediates attributes its result to the provider, its version and its inputs (`AEV-05.a`).
- **A ceiling:** the record's kind is the highest kind the result can be admitted as (`AEV-05.c`).
- **Through the agent:** output that passed through the agent is the agent's submission (`AEV-05.g`).
- **Not authority:** a derived index or map stays non-authoritative (`AEW-FR-19.d`).

**CAPR-10. Work stays at work.** A provider record, payload or bundle for a work deployment carries no work-only endpoint, credential or name into a general artifact (`S01-26`). The register's general text names classes of system, never internal ones.

**CAPR-11. An imported MCP provider is validated, and its absence degrades gracefully.** Every MCP server image AEW imports comes from SPT.
- **An SPT image** is pinned by its digest in the operator's records, and is host-placed (`CAPR-08`).
- **Any other MCP server,** such as a local package or a work-only server, is an operator's record under `CAPR-13`, placed by `CAPR-07`. A work-only one stays at work (`CAPR-10`).
- **Every one** is validated on import and at every check, by its health check and fixture query, and integrated through the register like any other provider.
- **When it is missing, failing or refused:** its capabilities read so, as `CAPR-03` says, and the agents' catalogs say so (`AEW-FR-34.b`, `HEB-09.b`).
- **AEW goes on working with its base tools** (`CAPR-12`).

**CAPR-12. No provider is required for AEW to run.** AEW starts, reads its records and runs agents with any provider missing or failing, base or imported: even ripgrep, which the harness all but requires.
- **Only that provider's capabilities degrade.** The catalog and doctor give each one's status, its cause and its fix.
- **A harness tool that needs the missing provider fails.** The catalog and doctor carry the cause; the harness's own error text is the harness's.
- **Within reason: AEW itself is its runtime, the harness, containment's tools and git.**
  - They are host prerequisites, which doctor names.
  - A missing containment tool refuses an agent's launch, and never degrades it (`HEB-09.e`).
  - The harness follows the OpenCode version-currency decision of 2026-10-24.

**CAPR-13. Expanding the register follows the settings path.** Adding, changing or removing a provider or a grant is one well-defined operator act, the same as changing a setting.
- **One record shape** for every provider, shipped or the operator's (`CAPR-02`). Adding a capability ID needs no code change.
- **Validated before it takes effect:**
  - checked are the record's schema, the payload's digest, and the health check with its fixture query. A sandbox-placed provider's check runs contained, as its uses do;
  - a change that fails validation changes nothing, and says why.
- **Recorded and reversible:** each change is recorded with its time and author, and one command restores the previous register.
- **Protected changes:** every change that adds to or alters what runs outside every sandbox:
  - placing a provider on the host, or changing a host-placed provider's payload or operations;
  - granting a host-placed capability to another role;
  - an undo that restores a host-placed provider;
  - widening a context's network for a provider.

  These need the operator's approval: G3, once G3 is established and the change is wired as a protected O-01 action (`CAPR-R05`); the operator's terminal until both.
- **Every other change is ordinary:** a sandbox-placed provider, or a role's catalog. Those run with the agent's own authority.
- **Where it is offered:** the CLI now; the site through the same operator command once the wire carries it ("Not covered"). The site never writes the register itself. It sends the operator command, and shows the result from D-01's capabilities read (`CAPR-03`).

## Interfaces

- **`aew doctor`:** one line per capability, with its status, its provider, its cause where it has one, and when it was checked.
- **The site:** D-01's capabilities read, served from the register (`CAPR-03`). Later, beside it, a register editor that sends the operator commands below (`CAPR-13`).
- **The operator commands.** **Candidate:** `aew capability list`, `check`, `add`, `import <bundle>`, `remove`, `grant`, `revoke` and `undo`. They are the same commands for the CLI and the site.

## The gate

| Check | What it shows | Pass |
|---|---|---|
| **CAPR-Q01** | A shipped payload matches its pin (`CAPR-03`, `CAPR-04`) | a payload with one byte changed reads `REFUSED` with the reason, at import and at the next check |
| **CAPR-Q02** | A contained agent cannot change a payload or the register (`CAPR-04`, `CAPR-05`) | every write from a sandbox is refused, and no broker or bridge operation changes the register |
| **CAPR-Q03** | A role sees only its grant of host-placed capabilities (`CAPR-06`) | an ungranted one is refused, with its reason, and the operator sees a waiting item naming the grant command |
| **CAPR-Q04** | Status follows the health check (`CAPR-03`) | a broken provider reads `UNAVAILABLE` with its cause; a re-pinned payload reads `STALE` until it is checked; a capability never checked reads `NOT_ESTABLISHED` |
| **CAPR-Q05** | An offline host can import (`CAPR-04`) | with no network, a bundle import makes its capability `FUNCTIONAL_ONLY` |
| **CAPR-Q06** | AEW runs with no provider at all (`CAPR-11`, `CAPR-12`) | with every provider removed or failing, base ones included, AEW starts, its commands and an agent's run work, and doctor names each missing capability with its cause and fix. A missing containment tool refuses the launch instead |
| **CAPR-Q07** | Expanding from the CLI is one validated, reversible act (`CAPR-13`) | adding a provider gives one record; an invalid record changes nothing; undo restores the previous register |
| **CAPR-Q08** | The harness never fetches a tool, and nothing serves one silently (`CAPR-04`) | with AEW's payload missing or refused, and with egress open, on a host with its own copy and on one without: the harness downloads nothing; a host copy, if used, is named in the status as unpinned; with none, the status names the cause |
| **CAPR-Q09** | No container runtime reaches an agent (`CAPR-08`) | from every agent context, no container runtime's socket is reachable, and the register's launch check fails if one is |
| **CAPR-Q10** | AEW works out of the box (`CAPR-04`) | on a fresh networked install, with no operator step beyond the install, the base bundle is `FUNCTIONAL_ONLY` before the first agent run |
| **CAPR-Q11** | A credential never reaches a sandbox through a provider (`CAPR-07`) | a sandbox-placed record that needs a credential is refused, saying to place it on the host |
| **CAPR-Q12** | Expanding from the site is the same act (`CAPR-13`). **Waits on the wire action** ("Not covered") | adding a provider from the site and from the CLI gives the same register |
| **CAPR-Q13** | A provider never widens a sandbox's network on its own (`CAPR-07`, `CAPR-13`) | a sandbox-placed record that needs a network route its context lacks is refused, unless the operator approves the widening as a protected change |

## Scenarios

**CAPR-X01.** Given a host without ripgrep, after the install a worker's search works, and `aew doctor` shows `EXACT_CODE_SEARCH` as `FUNCTIONAL_ONLY`, served by AEW's ripgrep (`CAPR-03`, `CAPR-04`).

**CAPR-X02.** Given a project file that names an extra MCP server, no agent gains it. The catalog and doctor say the project names it, and how the operator imports it (`HEB-01.i`, `CAPR-05`).

**CAPR-X03.** Given a role without `BINARY_ANALYSIS`, a host-placed capability, a request for it is refused, saying how to ask. The operator sees a waiting item that names the grant command (`CAPR-06`).

**CAPR-X04.** Given a container-backed provider asked to run a command it does not type, the provider refuses it, and no container starts (`CAPR-07`, `CAPR-08`).

**CAPR-X05.** **Later, with `CAPR-B1`:** given the documentation MCP server stopped, the agents' catalogs mark `OFFLINE_DOCUMENTATION` as `UNAVAILABLE`, and their work goes on with `TEXT_SEARCH` (`CAPR-11`).

**CAPR-X06.** Given a host without ripgrep and ripgrep's payload removed: AEW starts, and agents run. Their glob and grep tools fail, nothing is downloaded, and the catalog and doctor name the cause and how to restore it (`CAPR-04`, `CAPR-12`).

**CAPR-X07.** Given the operator adds a sandbox-placed provider from the CLI, the register changes only through the operator command. **Once the wire carries it,** the same provider added from the site gives the same record (`CAPR-13`).

**CAPR-X08.** Given a host-placed analysis provider asked to read a tree that carries in-tree configuration that would execute, the analysis runs with no execution of it, and reads nothing outside the calling context's view (`CAPR-07`).

**CAPR-X09.** Given the operator adds a sandbox-placed record that needs a token, validation refuses it and says to place the provider on the host, where it holds the token itself (`CAPR-07`, `CAPR-13`).

**CAPR-X10.** Given a project whose build calls `yq` and expects the host's implementation, the project's build gets the host's `yq`, and AEW's copy is under its unambiguous name (`CAPR-04`).

## Rulings

**CAPR-R01.** M6a's reset pass (`00-governance/reviews/2026-10-24-reset-pass-M6a.md`) leaves this position as the register's design.
- **What M6a keeps here:** `CAPR-06`'s role lists; `CAPR-07`'s control-plane rule and credential custody; and the outcomes of M6a's sections 17 and 18 (`CAPR-07`: a host-side tool reads only what its caller can read, and honours none of its content as code); and `CAPR-08`.
- **Kept outside the position:** section 26, reviewer non-mutation, kept by reference to `AEW-INV-ASSURE-005`.

**CAPR-R02. SPT is both an image store and the store of AEW's MCP server images** (the operator, 2026-10-24).
- **Its images are payloads,** pinned by image digest in the operator's records, never in AEW's shipped source, and imported through SPT's own bundles. Its tool-result, job-report and artifact-manifest schemas are its providers' evidence format.
- **AEW is the primary consumer, never the maintainer:**
  - it imports and validates SPT's images (`CAPR-11`), and never builds, forks or patches SPT;
  - what AEW needs from an SPT server goes to SPT's repository as feedback, carrying the register's validation evidence. The operator signs off what is filed, and the fix serves SPT's other users too.
- **The images AEW does not use** stay SPT's, and the register never lists them.

**CAPR-R03.** The first bundle (`FIRST-BUNDLE.md`) is the base bundle `CAPR-04` ships with every install. It is CLI only, placed in the sandbox, offline and credential-free, with ripgrep as its first member. Later providers come under these rules, each measured as section 8 of the research of 2026-10-01 asks:
- host-placed providers under `CAPR-07` and `CAPR-13`;
- MCP servers under `CAPR-11`.

**CAPR-R04.** The capability-discovery design v0.1's lazy expansion, from awareness to the exact schema, is a Candidate for `CAPR-06`'s catalog, not a rule.

**CAPR-R05. Where the register's commands sit in A-32.** This is the fit check, and it was done before the wire track.
- **None of A-32's rows is their home:**
  - `CHANGE_HOST_INSTALLATION` (P11) is, as I-6 reads it, a move to another installation, whose install half happens outside O-01 (STG-14's `I6-PROFILE.md`, its P11 row);
  - `ADOPT_MANIFEST_EDIT` (P14) is scoped by I-6's candidate to IF-13's profile definitions (its P14 row), and the register is not one;
  - `QUALIFY_OR_REVOKE_HOST_PROFILE` (P12) qualifies host profiles, not providers;
  - A-32's origins for its remaining rows are proposals, so no rule here leans on them.
- **So every register command is the operator's expansion of 2026-10-24.** They enter the scope index and O-01's wire after I-7, as the decision record says:
  - `CAPR-13`'s protected changes enter as protected actions, which G3 approves once G3 is established;
  - the others enter as ordinary actions;
  - they are new actions, with no proposed origin to depart from.
- **Until they are wired,** the operator's terminal carries them all. Once they are, the site can make every change, a host-side one through G3.

## Backlog

**CAPR-B1.** Host-placed and MCP providers: semantic navigation, offline documentation, the browser, binary analysis and a debugger (the second bundle).

**CAPR-B2.** Benchmark providers as section 8 of the research asks: correct task completion per cost, on the operator's own workloads.

**CAPR-B3.** Experiment and validation hosts, non-Linux targets among them (the software research workflow study of 2026-10-15).

**CAPR-B4.** Work-system integrations (issue tracker, wiki, CI and code review), once the operator lists which exist at work.

**CAPR-B5.** Knowledge and maps producers as providers, for the knowledge and maps contracts.

**CAPR-B6.** Skills: whether a skill is a register provider, and how one reaches a role. The AEW register's rows on skills (D3, F26, U9) now sit with this stage.

## Not covered

- **The harness binary itself:** it follows the OpenCode version-currency decision of 2026-10-24. The register and the harness share one bundle import.
- **M6a's two gates:** cut by the reset pass. The AEW register's M6a rows close by the operator's decision of 2026-10-24.
- **The register's commands as wire actions** (in scope, by the operator's decision of 2026-10-24; `CAPR-R05`):
  - all of them are new actions in the wire track, after I-7, the protected ones approved through G3;
  - until then, the CLI at the operator's terminal carries them.
- **The site:** D-01's capabilities read is adopted and not yet built, and the register editor waits on the wire actions.
- **Which tools are chosen:** `FIRST-BUNDLE.md` and `COVERAGE.md`.

## Changes

- **Revision 2.1 (2026-10-24):** the quick check's minors and nits, applied with no further check under the reset (`reviews/2026-10-24-CAPR-check-revision-2.md`; every one in `CHANGES-r2.1.md`).
  - **`CAPR-R05`:** every register command is the operator's expansion, the protected ones as protected actions. P11 stays I-6's.
  - **`CAPR-03`:** the register's status is D-01's `observed_status`.
  - **`CAPR-04`:** a serving host copy reads its own check.
  - **`CAPR-07`:** a container-backed provider is confined in its own bare container.
  - **`CAPR-08`:** the socket check is the register's own, and leaves A-33 as it is.
  - **`CAPR-11`:** every MCP server image comes from SPT, the operator's words; other servers are operator's records.
  - **Nits:** `CAPR-01` and the parts table, `CAPR-06`, the `AEV-05.d` line, and `Q13`.
- **Revision 2 (2026-10-24):** the answers to review round 1 (`reviews/2026-10-24-CAPR-review-round-1.md`; every finding, in `CHANGES-r2.md`), and the operator's decisions on SPT and the register's commands of the same day.
  - `CAPR-03` takes `S01-04`'s statuses and D-01's capability IDs.
  - `CAPR-04`:
    - every context gets the bound payload, and the harness never fetches;
    - a host copy serves only as a named, unpinned provider;
    - AEW's copies don't shadow the project's tools;
    - there are two layers of records, and the fetch happens online at install.
  - `CAPR-06`: grants apply to host-placed providers only.
  - `CAPR-07`: a host-side tool reads only its caller's view and honours none of its content as code, and a sandbox-placed provider gets no credential.
  - `CAPR-09`: the evidence kind is a ceiling.
  - `CAPR-11`: MCP servers come from SPT.
  - `CAPR-12`: the prerequisites' boundary.
  - `CAPR-13`: every host-side change is protected.
  - `CAPR-R02` and `CAPR-R05` are new or rewritten, and `CAPR-B6` is new.
  - Gate checks `Q08` to `Q12` and scenarios `X08` to `X10` are new.
- **Revision 1.2 (2026-10-24):** "Not covered" names the register's operator commands as new operator actions. Their wire actions, for the site's editor, wait on the operator's scope decision and the wire track.
- **Revision 1.1 (2026-10-24):** the operator's two requirements of the same day. No provider is required for AEW to run (`CAPR-12`), and expanding follows the settings path, from the CLI or the site (`CAPR-13`). `CAPR-05` now protects what runs outside the sandbox; `CAPR-Q06` removes every provider, and `CAPR-Q07` is new.
- **Revision 1 (2026-10-24):** the first text. It takes in the operator's view of the same day that base tools ship with AEW (`CAPR-04`), and that MCP servers are imported, validated and optional (`CAPR-11`).
