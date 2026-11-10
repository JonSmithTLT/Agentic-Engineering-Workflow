<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-55
source: 30-stages/STG-30-offline-install-bundle/adopted/oib-r1/OIB-POSITION.md
source-sha256: b43d344903215b25844e84e58c74c542d8a2c2b9f0591f1ef0b7d63ab7e3a973
edits-sha256: none
-->

# The offline install bundle (PROPOSED, revision 1)

**Namespace:** `OIB-`
**Status:** proposed revision 1, reviewed: one round and a quick check, for the operator's adoption. It amends nothing adopted by itself. The changes it needs in ADR-0014 (adopted 2026-10-07, ledger-gated), in A-54 and in A-37 are listed under "For the operator", each an operator decision.
**Authority:** the operator's "Start E99" (2026-11-06, the designer's session; `00-governance/decisions/2026-11-06-operator-start-STG-30-offline-install-bundle.md`), on the register's row E99 (AEW `docs/implementation/future-work.yaml`, lines 1246-1269), and the hold-match decision of 2026-11-06 (`00-governance/decisions/2026-11-06-operator-hold-match-batches.md`), which merged F18.3 and D2's installer half into E99 as notes.
**Threat model:** the operator's decision of 2026-10-19, as the security depth reset of 2026-10-24 narrows it, and ADR-0014's own: a process running as the installing user or as root on the installing host is out of scope; a hostile or corrupted bundle, a wrong key and a stale key are in.
**Research consulted:**
- the bundle's contents and its cold-start checks: `aew-phase6-airgap-capability-research-2026-10-01` (AEW `docs/research/`), section 7 and its twelve-check cold-start acceptance list, which the gate's `OIB-Q01` and `OIB-Q10` follow;
- every other decision point and requirement family here: `tools/research_index.py lookup` gave none (`AEW-FR-34.a`, `AEW-FR-34.b`, `AS-24`, `CAPR-04`, `SPB-07`, `S01-26`, `G3-05`, `G3-14`, `U01-R07`).

**Files:** this file. The stage's `STAGE.md`. No schema or fixture yet; the manifest's schema is the build's (`OIB-01`, Candidate).

## What the adopted text already decides

- **The signed release and its verifier** (ADR-0014, AEW `docs/implementation/adr/0014-release-signing-air-gap-bundle.md`):
  - three side-by-side files (the archive, a canonical JSON manifest, a detached signature), the manifest's schema `aew/bundle-manifest/v1`, and its archive, bundle, harness, files and install blocks (its decision D2);
  - the trust root, provisioned through a channel independent of the bundle and the repository (D3); the release key and its custody (D4); the deterministic build, the catalog seed made from a disposable instance, and the rebuild-verify before signing (D5); rotation (D6);
  - the verifier, a standard-library Python 3.11 module carried with the trust root, never the bundle's own copy run first; the archive verified as opaque bytes before any tar parser runs; its bounds (10,000 members, 8 GiB, an uncompressed tar); every refusal named, leaving nothing on disk (D7);
  - the install from the verified staging copy only, with `pip --no-index --require-hashes`, the harness binary not executed before doctor's dry probe with the network unshared, and `aew doctor --bundle --json` as the host's acceptance record (D8);
  - the Ed25519 strictness rules (D9), and the build evidence it lists ("What the build must show"), whose end-to-end install on the Rocky 8 host is run by the operator, the agent never using the host's root.
- **The install design it rests on:** AEW's install and bootstrap UX v0.3, sections 5 and 5.1, is an input to this position, not authority: D1 indexes nothing from it, and ADR-0014 supersedes its manifest-inside-the-tar and its extract-then-verify order.
- **Base tools:** AEW ships its base tools pinned with every install; offline they arrive in the operator's bundle and are checked against their pins (`CAPR-04`, `CAPR-R03`, `CAPR-Q05`). Each provider record states its payload (`CAPR-02`). Getting a payload is an operator act (`CAPR-05`), and AEW downloads no tool without the operator's choice (`00-governance/decisions/2026-11-05-operator-no-download-without-consent.md`). No provider is required for AEW to run; AEW's runtime, the harness, containment's tools and git are host prerequisites (`CAPR-12`).
- **What may travel:** no deployment-only endpoint, credential or name in a general artifact (`CAPR-10`, `S01-26`).
- **The transfer:** one routine transfer carrying AEW's bundle and SPT's routine part under one transfer manifest, each part signed by its own product, antivirus-sensitive data apart, judged by a property test, and a pre-carry check (`SPB-07`); where the transfer manifest lives, the pre-carry check's design, the data transfer and the import of an image moved to it are this position's (`SPB-07`, `SPB-B3`). SPT's signed image bundle is a requirement on SPT (`SPB-04`); mounted payloads are `SPB-10`'s.
- **Upgrade and recovery:** installing a release changes no project store (`U01-04`); rollback before a migration is the previous release, and after one it is the restore point (`U01-06`); nothing bound to a host is copied, and no credential moves (`U01-07.c`, `U01-07.d`); the install, the bundle and the install sequence are hold group 17's and E99's (`U01-R07`).
- **G3:** root sets the PIN on the service, and AEW host code never asks for, receives or stores it (`G3-05`); G3 is installed root-owned under one pinned path, and changing the install is root's administration (`G3-14`); G3 is established only where every agent runs contained (`G3-00`).
- **Disconnected deployments** work, and say what is unavailable (`AEW-FR-34.a`, `AEW-FR-34.b`); an approved offline profile keeps local record access across a supported upgrade (`AS-24`).
- **Operator decisions this position applies, not re-asks:**
  - conda-forge as the route for the hard group, under conditions, and the licence items: GPL sources carried; CodeQL, Semgrep's rules and Microsoft cpptools not bundled; GitNexus only as SPT's image (`00-governance/decisions/2026-11-01-operator-airgap-kit-conda-forge-and-licences.md`);
  - antivirus-sensitive data travels apart (`2026-11-01-operator-transfers-cheap-except-AV-sensitive-data.md`);
  - AEW's platforms are Linux and Windows (`2026-11-01-operator-supported-platforms-Linux-and-Windows.md`);
  - AEW brings its own tools (`2026-10-24-operator-AEW-brings-its-tools.md`); the harness version currency (`2026-10-24-operator-OpenCode-version-currency.md`); an offline host gets the built harness binary, never a source build (`2026-10-30-operator-AEW-may-patch-its-own-OpenCode-build.md`, ruling 8);
  - the kit is carried: the operator preferred carrying the research's tools, and the designer ruled the kit carried in full (`30-stages/STG-15-capability-register/AIRGAP-KIT-PLACEMENT.md`, its first lines and its ruling);
  - the notifier's system packages and the Windows toast go in E99 (`BOY-B5`; `2026-10-28-operator-adoption-BOY-r2.1.md`, Q7).

## The parts

| Part | What it is | Who writes it | Who reads it |
|---|---|---|---|
| The one manifest | every requirement of an install, per target: what each artifact is, where it comes from, its pin, its licence, which step consumes it, required or optional | a reviewed AEW change | the build; the release checks; the preflight |
| A payload entry | one carried artifact's record in the one manifest (`OIB-02`) | a reviewed pin change | the build; a provider record, which names it |
| The bundle manifest | ADR-0014's signed per-target manifest, generated from the one manifest | the build; the release operator signs it | the verifier |
| An AEW part | one three-file signed release: the install part, or a numbered kit part (`OIB-03.a`, `OIB-03.b`) | the build and the release operator | the verifier; the guided sequence (install part only); the operator's import (kit parts) |
| The trusted bootstrap | a POSIX sh launcher that checks the host baseline (`OIB-00.a`), and the standard-library entry point it then runs, which runs steps 1 and 2 before AEW exists (`OIB-04.b`) and is the root step's entry (`OIB-08`) | a reviewed AEW release, carried with the verifier through the organization's channel | the operator; root, through `sudo` |
| The transfer manifest | the carry list of one transfer (`OIB-14`) | the operator's assembly, on the connected side | the pre-carry check; the operator; the import's record |
| The staging copy | the verifier's verified copies and extraction (ADR-0014 D7); the root step's own fresh copy (`OIB-08`) | the verifier | the guided sequence; doctor |
| The install record | each step's completion and what it placed, per tool environment (`OIB-11`) | the guided sequence; its root part, the root step | the guided sequence; the summary; undo |
| The guided sequence | the operator's install command (`OIB-04`) | a reviewed AEW release | the operator |
| Agents | the Lead and the workers | nothing here | nothing here |

## Rules

**OIB-00. Precondition: the trust root, the trusted verifier and bootstrap, and a Python 3.11 with tarfile's data filter are on the host before the bundle is used.** The verifier, the bootstrap (`OIB-04.b`) and the trust root arrive through the organization's own channel (ADR-0014 D3, D7), and the host has a Python 3.11 whose `tarfile` module has `data_filter` (3.11.4 or later), which the verifier needs before any byte of the bundle is trusted.
- Without them the sequence cannot start, and the launcher (`OIB-00.a`) says which is missing and prints the one command that supplies them. Nothing from the archive is used to supply them (`OIB-R04`).
- **The Python check is a test, not a version string:** the launcher, the verifier and the preflight report a Python 3.11 without `tarfile.data_filter` as missing, never as found.
- **The host baseline is a root action outside the sequence:** installing Python 3.11 and placing the trust root, the verifier and the bootstrap under `/etc/aew/` (ADR-0014's convention) is one root command, the baseline's, printed by the launcher, or the host's configuration management doing the same, before step 1. It falls outside the sequence's single root prompt ("For the operator", questions 5 and 7).

**OIB-00.a** The channel-carried entry is a POSIX sh launcher, which checks the host baseline before any byte of the bundle is read, and only then runs the Python bootstrap (`OIB-04.b`).
- **What it checks:** that `python3.11` is present and its `tarfile` has `data_filter`, tested by import; and that the trust root, the verifier and the bootstrap exist under `/etc/aew/` with ADR-0014 D7 step 1's ownership and modes.
- **When any is missing or wrong,** it stops, names each missing piece, and prints one baseline root command: a baseline script carried with it, which installs `python3.11` from the host's own distribution source with the host's signature checking on, or from the packages the channel carries where the host has none ("For the operator", question 5), and places the `/etc/aew/` files with D7 step 1's ownership and modes. It changes nothing itself.
- **When every check passes,** it executes the Python bootstrap from `/etc/aew/`.

**OIB-01. One manifest names every requirement of an install, per target.** It lives in the AEW repository, changes only by a reviewed change, and names for each target:
- AEW's wheel and its complete wheelhouse closure, with a hash-pinned pip wheel (`OIB-06.a`);
- the harness's built binary for each qualified pin, a patched build included (the 2026-10-30 decision);
- the base bundle's payloads (`CAPR-R03`), per platform;
- G3's service and confirmer files and G3's own wheel set (`G3-14`);
- the system packages per target: bubblewrap and git (containment's tool and AEW's prerequisite, `CAPR-12`), the G3 confirmer's (gtk3, python3-gobject), the notifier's (`BOY-B5`), the container tools where SPT images are used (`SPB-05`), and a host package only where validation finds it missing on the target's reference profile (`OIB-03`; the kit placement's HOST rule);
- the harness's offline catalog seed (`OIB-16`);
- each GPL binary's source;
- the kit's carried layers (REG, B1, PROJ) as entries, and the data layer's entries for the data transfer (`OIB-14.b`).
- **Each entry says** which target it serves, which step consumes it, and whether it is required or optional.
- **Candidate:** a YAML file beside the release tooling, with its schema, from which `tools/release/bundle.py` reads.

**OIB-01.a** A build's new prerequisite goes into the one manifest: the build refuses an artifact the one manifest does not name, as `NOT_IN_MANIFEST`, and the gate plants one.

**OIB-01.b** Every other list is generated from the one manifest, never written beside it: ADR-0014's bundle manifest per target, the hashed requirements files (AEW's, and G3's, which absorbs `g3/requirements-offline.txt`), and the payload pins the shipped provider records state. A check fails on any difference.

**OIB-01.c** No AEW part carries a credential, the release key, host-bound state, antivirus-sensitive data, or an item the 2026-11-01 licence decision keeps out.
- Credentials of any kind, the relay's client certificate included (`U01-07.d`).
- Host-bound state, such as G3's key, PIN hash and ledger, or a capability register (`U01-07.c`).
- Deployment-only endpoints, credentials and names (`CAPR-10`, `S01-26`).
- Antivirus-sensitive data (`SPB-07`).
- CodeQL, Semgrep's rules, Microsoft cpptools and GitNexus (the 2026-11-01 licence decision); SPT's images (`SPB-07`).

**OIB-02. Each carried artifact has one payload entry, and its pin changes only by a reviewed, validated bump.** The entry states: the source, the version, per platform the size and SHA-256, the licence and any source obligation, the upgrade feed, the layer, and for a data set its build date.
- **A provider record states its payload** (`CAPR-02`), and names the payload entry that payload is generated from (`OIB-01.b`).
- **Validation before adoption:** a proposed pin is validated on the Linux targets' reference profiles (`OIB-03`), and on Windows where the entry has a Windows payload, by the record's health check and its smoke test where one is named. A pass becomes the reviewed bump; a failure keeps the old pin and records why.
- **Where validation runs:** unprivileged, on an offline CI runner of the reference profile; on Windows, a Windows host or CI runner. Only a system-package entry needs root to validate, and its root part is run by the operator on the reference host. A pass produces a validation record (the entry, its pin, the host's profile, each check and its result, the date), which the reviewed bump cites.
- **The harness pin is the exception:** it follows the 2026-10-24 version-currency decision (outcome 3).
- **Several environments, several locks:** a tool set whose packages conflict (the kit's reverse-engineering Python set) gets one locked entry per environment.
- **The data's date** is what a scanner's status reports (`SPB-10`, `CAPR-03`).

**OIB-02.a** An artifact whose upstream publishes no checksum is pinned by AEW's own SHA-256, recorded at intake, with its upstream signature checked where one exists.

**OIB-02.b** A licence obligation travels with its artifact: a GPL binary's entry names its source, which rides in the same AEW part, and nothing is fetched from conda-forge until the record of Anaconda's terms (the 2026-11-01 decision) is referenced from the one manifest.

**OIB-03. Each target is built apart: the Linux targets are a list in the one manifest, `rl8-py311` first, and Windows's target waits on the operator's answer to question 3.**
- **Linux targets:** each entry of the list names its architecture, glibc, Python and reference profile, and has its own resolved package set and its own dated repository state, pinned like `SPB-05`'s pair. The first is x86_64, glibc 2.28, Python 3.11, named `rl8-py311` by ADR-0014. A further managed Linux host is a further entry, never a variant of the first. Carried packages keep their distribution signatures (`OIB-08`).
- **The reference profile:** for `rl8-py311`, a Rocky Linux 8.10 x86_64 install from the 8.10 DVD image, the "Server with GUI" environment (the confirmer needs a desktop, `G3-05`), with no updates applied. Its installed package list is recorded as a build input, and "missing on the reference profile" (`OIB-01`) is read against that list.
- **Windows:** the one manifest's Windows entries (payloads with a Windows build, the harness's Windows binary, the toast's dependencies under `BOY-B5`) are served by the consented online fetch, or the operator's import (`CAPR-04`). No offline Windows bundle is built in this revision. This clause narrows E99's no-network install to Linux, a scope change, so it takes effect only on the operator's answer to "For the operator", question 3; until then the Windows offline target stays open (`OIB-B1`).
- **A platform the one manifest does not name** reads `UNSUPPORTED` for its payloads (`CAPR-03`), and the preflight says so.
- **A target's split by platform** (a browser set that is a container image on Rocky 8 and a directory on Windows) is two entries, one per platform.

**OIB-03.a** AEW releases, per Linux target, the install part, which the guided sequence consumes, and kit parts (`OIB-03.b`), which carry the kit's carried-but-unregistered layers and are imported by the operator's own commands, never by the sequence; every part is an ADR-0014 release under the same key, and `OIB-00` and `OIB-05` apply to a kit part as to the install part.
- **The trusted verifier runs first** over a kit part's three files, and the operator's import reads only its staging copy, never the archive as carried.
- **An import of a kit archive that has not passed the verifier,** or whose staging copy differs from its manifest, is refused, and nothing is imported.
- How many signed parts the routine transfer then holds is "For the operator", question 4.

**OIB-03.b** The kit is split into numbered kit parts, each within ADR-0014 D7's adopted bounds: the build assigns entries to parts and refuses a part over either bound, as `PART_OVER_BOUNDS`, naming the part and the bound.

**OIB-03.c** Each Linux target's system packages are resolved once, when the one manifest's entry changes, into a pinned package list (each package's name, version, release, architecture, URL and SHA-256) against its reference profile and repository state; the build reads that list and never resolves.
- **So the rebuild-verify** (ADR-0014 D5) recomputes nothing on the release operator's machine: it fetches the listed files by their pins.
- **The install part carries the listed package files as they are,** and the root step installs them as local packages; no repository metadata is generated.
- **A listed package that would upgrade one already present** on the host is shown as an upgrade, and is recorded as not undoable unless its predecessor is carried (`OIB-08.a`, `OIB-12`).

**OIB-04. One guided sequence installs AEW, as one local operator command.** It is never on the Lead broker's or a worker's tool surface, and has its surface-map entry (`CAPR-05`, `U01-08`). Its steps, in order:
1. verify the bundle (`OIB-05`);
2. install AEW into its own environment (`OIB-06`);
3. the preflight (`OIB-07`);
4. the root step (`OIB-08`);
5. the PIN (`OIB-09`);
6. the self-tests, ending in one screen (`OIB-10`);
7. the summary: what was installed, where, and how to undo it (`OIB-12`).
- **Each step's precondition** is the previous step's recorded completion (`OIB-11`).
- **A step that does not apply** (a host that already has every package, G3 already holding a PIN, a Windows host) is recorded as not needed, with its reason, and the sequence says so; G3's reinstall is never skipped when AEW's commit changed (`OIB-13.a`).
- **On a connected host,** step 1 does not apply, and step 2 is the connected install (`OIB-04.a`); steps 3 to 7 are the same, the root step taking its sources as `OIB-04.a` says.

**OIB-04.a** On a connected host, step 2 installs AEW with `pipx install aew==X` (or `uv tool install`) on the host's own Python 3.11 or later, and the sequence owns the connected install's checks and its update path.
- **The preflight** names each missing piece with the install command of the host's package manager.
- **The harness binary** is found (the Windows Desktop CLI, `PATH`, `AEW_OPENCODE_BIN`) and its version checked against `TESTED_VERSIONS`: a newer version is a warning (untested; the probe decides at launch), and an older one or V1 is an error.
- **The root step's sources on a connected Linux host:** the host's own enabled repositories, with the host's signature checking on; and G3's wheel set and the same-commit AEW wheel, fetched by their pinned hashes under the operator's consent (`E171`, the 2026-11-05 decision) into a fresh root-owned directory, a mismatch refusing the step.
- **A connected update** is `pipx upgrade aew`, then `aew doctor`, then `aew migrate` when doctor says `MIGRATION_REQUIRED` (U-01's command, `U01-05.a`).

**OIB-04.b** Before AEW exists, steps 1 and 2 are run by the trusted bootstrap: a standard-library-only entry point that travels with the verifier through the organization's channel (`OIB-00`), is run by the launcher once the host baseline passes (`OIB-00.a`), runs the verifier, performs ADR-0014 D8's install from the staging copy, records steps 1 and 2 in the install record, and then executes `aew setup` from the new environment.
- The bootstrap's copy inside the bundle never runs first, as for the verifier (ADR-0014 D7).

**OIB-05. On a verifier refusal the sequence stops at step 1, and the staging copy is host state outside every sandbox's writable binds and every project tree.** Step 1 runs the trusted verifier (`OIB-00`) over the three files; what it checks, what a refusal leaves, and that later steps read only the verified copy are ADR-0014 D7's and D8's.

**OIB-06. AEW goes into its own environment, per version, and the bundle's payloads go to AEW's payload store.**
- **AEW's environment:** created and filled as ADR-0014 D8 says, under a versioned path that is host state outside every sandbox's writable binds and every project tree (`HEB-01.h`). The previous version's environment is kept until the operator removes it (`U01-06`).
- **The harness binary** is placed as ADR-0014 D8 says; on a host installed from a bundle, the bundle's harness pin is the one the launch selects.
- **The base payloads** are imported through `CAPR-04`'s bundle import, the one the harness's bundle import shares (the 2026-10-24 decision, ruling 2). That import's payload kinds beyond today's (raw executables, a `.tar.xz` archive, a wheel) are the capability register build's third pull request (STG-15's), a prerequisite of this step and of `OIB-Q01`'s green screen.
- **The harness binary's first run** is as ADR-0014 D8 says ("For the operator", question 2.5).

**OIB-06.a** Every environment the install creates, AEW's and G3's root-owned one, is created without the host's pip and filled by a hash-pinned pip wheel from the staging wheelhouse, run in isolated mode, so no host pip, pip configuration or index is read.
- **Candidate:** `python3.11 -m venv --without-pip`, then the pinned pip wheel run as `python <pip wheel>/pip install --isolated --no-index --require-hashes --no-cache-dir ...` with `TMPDIR` inside the target environment's path; for G3, a change to `g3/install.sh` that this build makes.

**OIB-07. The preflight lists every prerequisite as found or missing, with the exact command, offline, as the operator.** It reads the one manifest's entries for this target and the host.
- **Each line:** the prerequisite, found (with its version and where) or missing, required or optional, and for a missing one the exact command that supplies it with no network.
- **A missing system package's command** is the root step's (`OIB-08`), written in full.
- **The package transaction:** before the root prompt, the preflight lists the root step's transaction, computed as the operator from the pinned list (`OIB-03.c`) against the host's package database: each package new, or an upgrade of one already present, marked not undoable.
- **Disk:** the preflight counts, for each of the two staging directories (`OIB-05`, `OIB-08`), the archive's size plus the extracted size, both read from the verified manifest, since each keeps the verified archive copy beside its extraction (ADR-0014 D7 steps 5, 8 and 9); then the kit parts' and the environments' room. It names the filesystem each lands on, root's staging included, and checks each filesystem's free space against what lands there.
- **A pinned transaction that cannot resolve on this host** (a host updated from its own mirror, or on another minor release): the preflight names each unresolved dependency, or each package that differs from the pinned plan, and offers the operator the graceful path, chosen at the preflight and recorded: the root step takes the system packages from the host's own enabled repositories, with the host's signature checking on, as on a connected host (`OIB-04.a`), and the transaction the preflight lists is that one.
- **Host settings** the preflight finds wrong (user namespaces, subordinate ID ranges, SELinux labels) are named with their commands, and the sequence never changes them (`OIB-R05`).
- **It runs as the operator.** It runs doctor's checks for this target's entries, and doctor's root row applies to it: run as root, it refuses, and that row stays an error (`OIB-08`). Doctor's rows themselves are F18.2's row.

**OIB-08. Root is asked for once, in one command at the operator's own terminal, which does only the system part.** On a terminal outside containment, `aew setup` invokes `sudo` itself on the root step's entry, the root-owned trusted bootstrap under `/etc/aew/` (`OIB-04.b`), so the operator answers one password prompt and copies nothing. The operator account the root step records and hands the PIN step to is the invoking account, read from `sudo`'s `SUDO_UID`, never uid 0; a missing `SUDO_UID`, or uid 0, refuses the step. The root step:
- runs the trusted verifier again, from the kept verified copies of the three files, into a fresh root-owned staging directory, and consumes only that copy;
- only then runs its own code from that copy;
- installs the missing system packages from that copy (on the graceful path of `OIB-07`, from the host's own enabled repositories instead), with the host's own package signature checking on, against the distribution keys the host already trusts: a package that fails it is refused even when its bundle hash matches; a resolved transaction that differs from the one the preflight listed refuses the step;
- where the host's package database lacks the distribution key, imports it only from the host's own `/etc/pki/rpm-gpg/` file, never from the bundle, and without a prompt, so the root command raises no prompt but `sudo`'s;
- installs G3, its confirmer and their units (`G3-14`), from that copy;
- decides whether G3 already holds a PIN, which only root can read (as `g3/install.sh` does), and records it;
- then hands the terminal to the PIN step (`OIB-09`).
- **It does nothing else:** no host setting, no AEW project work, no doctor run.
- **Inside an AEW-contained context, or off a terminal,** the unprivileged `aew setup` refuses before it calls `sudo`, as `OPERATOR_STEP_REQUIRED`, changes nothing, and prints the command, in full with absolute paths, for the operator to run at their own terminal. The check is positive: the process's no-new-privileges flag (`NoNewPrivs` in `/proc/self/status`) or containment's own marker, never an environment variable. The command is printed only on that refusal, or when the operator asks for it.
- **Candidate:** where the package database lacks it, `rpm --import /etc/pki/rpm-gpg/RPM-GPG-KEY-rockyofficial`; then `dnf --disablerepo='*' --setopt=localpkg_gpgcheck=1 install <root staging>/rpms/<the listed files>`, run first with `--assumeno` to compare the transaction. On the graceful path (`OIB-07`), `dnf --setopt=gpgcheck=1 install <the listed names>` against the host's enabled repositories.

**OIB-08.a** The root step records exactly what it installed, for the summary and for undo.
- **Packages:** the packages it added (never one already present), and those it upgraded, marked not undoable unless their predecessors are carried (`OIB-03.c`); and the distribution key it imported, if any, named as the host's own and kept.
- **G3's paths, each named:** the `/opt/aew-g3` tree (its environment, `aew_g3`, `aew_g3_confirm`, `bin`, `etc/deployment.json` where it placed it, and the environment's `.pth`); the units in `/etc/systemd/system`; the `.wants` links `systemctl enable` makes; `/usr/local/sbin/aew-g3`; the confirmer's link in `/usr/local/bin`; the desktop entries in `/usr/share/applications` and `/etc/xdg/autostart`.
- **Not its own:** G3's state directory, which the service creates at its first start (`OIB-12`).
- **Its outcome for the PIN:** whether a PIN was already held, and `set-pin`'s exit status (`OIB-09`).

**OIB-08.b** The root step writes its intended package transaction to its root record before it runs the transaction, and the package manager's history id of that transaction after it, so an interrupted root step resumes without losing what it added.
- **On a rerun,** the step compares the host against the intended transaction less what that history id installed, and records the packages it added from that history, never counting them as already present.
- **An interruption after the packages and before G3's install** resumes at G3's install, with the packages' record intact.

**OIB-09. The operator sets the PIN at their own terminal, and the installer never sees it.** The root step hands its terminal to G3's `set-pin`, which reads the PIN itself (`G3-05`).
- **The installer** reads, pipes, stores and logs none of it, and passes nothing to `set-pin` but its terminal.
- **Where the root step found a PIN already held** (`g3/install.sh` leaves G3's state alone on a reinstall; whether that is a rule is "For the operator", question 6), the step is recorded as not needed, and says how root resets it.
- **Inside an AEW-contained context, or off a terminal,** it refuses as `OPERATOR_STEP_REQUIRED` before calling `sudo`, on the same positive check as `OIB-08`, and names the operator's command.
- **On a resume** where the root step is done and its record shows no PIN set, root is asked for the PIN step alone, and that step's outcome is recorded the same way.

**OIB-10. The self-tests end in one screen, each piece green or red.** They run as the operator, and their record is ADR-0014 D8's acceptance record.
- **The pieces:** the verification and its key fingerprint; AEW's environment; the harness's dry probe with the network unshared, and no connection attempted; containment's launch self-test; each base capability's status (`CAPR-03`); G3 (the `g3` line of the STG-03 hand-off's addendum 7, a designer ruling under A-37); the notifier (`BOY-B5`); the catalog seed (`OIB-16`); each system package the one manifest names.
- **An attempted connection is observed, not inferred:** a connect in an unshared network namespace just fails, so the probe runs where every attempt is seen. An attempt is any `connect`, `sendto` or `sendmsg` to an `AF_INET` or `AF_INET6` address by any process of the probe's tree; local `AF_UNIX` traffic is not counted. **Candidate:** a namespace whose only default route leads through a dummy interface to a local sink that logs every attempt.
- **Each line** says required or optional, and a red line gives its cause and its fix.
- **The screen is green** only when every required piece is green. An optional red piece never makes it red (`CAPR-12`).

**OIB-11. A rerun resumes at the first unfinished step.** The install record is host state per tool environment, outside every sandbox's writable binds, and holds each step's completion with the verified manifest's digest; its root part is written by the root step (`OIB-08.a`).
- **Each step is safe to rerun:** a rerun of a finished step changes nothing.
- **A different bundle:** a rerun whose manifest digest differs from the record's refuses to resume, as `INSTALL_RECORD_MISMATCH`, naming both digests, and names the abandon path (`OIB-11.a`).

**OIB-11.a** A partial install is abandoned by undo from its record, then the new bundle's install (`OIB-13`).
- **Undo reads the record as far as it goes** (`OIB-12`), the root step's intended transaction and history id included (`OIB-08.b`), and removes only what it holds.
- **`INSTALL_RECORD_MISMATCH` names that undo command** and then the new bundle's command.

**OIB-12. The sequence ends with what was installed, where, and how to undo it.** One line per item the install record holds, with its path and its undo command, in reverse order of installing.
- **Undo removes** only what the sequence placed: the packages the root step added, by the exact recorded list and never by dependency clean-up (`OIB-08.a`); G3's files and units, or, where a previous release is still installed, restores that release's G3 instead (`OIB-13.b`); AEW's environment; the payloads it imported; and the staging copies. Undoing a root item is itself the operator's root command, named. An upgraded package is named as not undone.
- **Undo never touches** a project store (`U01-04`), or G3's state: what the service created is left to root's administration (`G3-14`), and the summary says so.

**OIB-12.a** Undo refuses to remove an AEW environment while any project store holds a format that no other installed release reads or migrates from, as `ENVIRONMENT_STILL_NEEDED`, removing nothing and naming U-01's restore command (`U01-06`).
- **The projects it checks:** each whose migration was made with that release (its restore point, host state under `U01-06.e`), and each the operator names; a project whose markers it cannot read is counted as needing the environment.

**OIB-13. An upgrade or a fix is a new bundle through the same sequence.** Routine transfers are cheap, so a fix is made outside and carried in by the next one (the 2026-11-01 transfers decision). Installing it beside the previous release, migration and rollback, the register's overrides and the harness's re-qualification are as `U01-04`, `U01-06`, `CAPR-04` and the 2026-10-24 version-currency decision's outcomes 3 and 6 say.

**OIB-13.a** Every AEW upgrade runs the root step's G3 part, one root prompt per upgrade, because G3's environment holds the same-commit AEW wheel: the "not needed" rule (`OIB-04`) never skips G3's reinstall when AEW's commit changed.

**OIB-13.b** Rolling back to, or undoing back to, a previous release restores that release's G3 from its own kept root staging copy, as one root command the summary names, and keeps G3's state.
- **Undoing an upgrade's root part** restores the previous release's G3 rather than removing G3 (`OIB-12`).
- **A rollback without undo** (`U01-06`) is the same root command.
- **Each installed release's root staging copy** is kept until that release's environment is removed, so the restore reads only verified bytes.
- **G3's state is kept:** its ledger, key and PIN hash are not touched (`OIB-R06`).

**OIB-14. The transfer manifest is a carry list beside the parts, never a trust root.** It lists, for one transfer, each part's file names, producing product, release, size and SHA-256, and the pre-carry check's result.
- **Where it lives:** at the transfer's root, beside the parts it lists; on import its digest is recorded with each part's acceptance record.
- **Trust:** each part is verified by its own product's signature on import (ADR-0014 for AEW's parts, `SPB-04` for SPT's), and the transfer manifest is consulted for nothing a signature decides.
- **SPT's images** travel in SPT's one-layout signed part (`SPB-07`), listed as one part.

**OIB-14.a** The pre-carry check runs on the connected side, before the carry, over every part of the routine transfer, and refuses the items `SPB-07`'s property test marks, as `CARRY_REFUSED`, naming the item.
- **The detector:** the item's declared metadata (SPT's declaration for an image, the payload entry for AEW's items), and a scan of each layer or archive for the listed database file signatures; an item with no declaration is refused.
- **It reads OCI layouts as plain files,** since no container engine is assumed on the connected side.
- **The check moves nothing:** it refuses, and the operator acts on the refusal.
- **A refused SPT item** refuses SPT's whole part, which goes back to SPT for a new release, since moving an image out would break SPT's signature over its layout.
- **A refused loose AEW data item,** one authenticated by its pin (`OIB-14.b`, "For the operator", question 2.7), is moved by the operator to the data transfer, as `SPB-07` says.
- **A refused member of a signed AEW part** refuses that whole part back to the build, as for SPT, since moving it out would break the part's signature; `OIB-01.c`'s release check should already have kept it out.

**OIB-14.b** The data transfer has its own transfer manifest of the same shape, marked as data, and carries only data payload entries, each with its build date (`SPB-07`, `SPB-10`).
- **AEW's own data payloads** (the scanners' databases) are authenticated by their pins in a signed AEW part: each has an entry in the kit part's signed manifest with its SHA-256 and build date, and an import checks the data item against that pin and refuses a mismatch ("For the operator", question 2.7).

**OIB-14.c** An image moved to the data transfer is imported by the same register import as any other (`CAPR-11`), against the same pinned digest; the transfer that carried it changes nothing in its validation.

**OIB-15. On Windows, the sequence runs its operator steps, and has no root step and no PIN step.** Steps 2, 3, 6 and 7 run; the screen and the summary say that G3 and the operating system's containment are absent on Windows, and that its launches run labelled (the STG-03 hand-off's addendum 7, a designer ruling under A-37).
- Its prerequisites, Git for Windows among them, are preflight lines like any other.
- Its payloads come as `OIB-03` says.
- **The harness line** reads "not checked", with its reason (Windows has no network namespace for the dry probe), labelled as containment is, and is never green.

**OIB-16. The bundle build makes the offline catalog seed from a clean disposable instance of the exact harness pin, sanitized, pinned by its SHA-256 and treated as compatibility data, and never copies it from an operator profile.** It is made as ADR-0014 D5's build makes it, and is an entry of the one manifest (`OIB-01`) with its pin.
- **A seed that does not match its pin** is refused at verification (ADR-0014 D7), and the self-tests show its line (`OIB-10`).
- **A later qualified pin** with an official offline-catalog mechanism uses that mechanism in place of the seed.

## Interfaces

- **The guided sequence.** **Candidate:** `aew setup`, with `--bundle <dir>` for a host with no network; before AEW exists, steps 1 and 2 are the trusted bootstrap's (`OIB-04.b`), which then executes `aew setup` from the new environment.
- **The trusted bootstrap.** **Candidate:** a POSIX sh launcher and its baseline script (`OIB-00.a`), and a second standard-library module beside `tools/release/verify_bundle.py`, all carried with it.
- **The root step.** **Candidate:** `sudo /etc/aew/<the trusted bootstrap> root-step <the kept verified copies of the three files>`, invoked by `aew setup` itself (`OIB-08`); the bootstrap verifies into root's fresh staging directory and only then runs the root step's code from that copy. The sequence prints the command in full with absolute paths only on refusal or on request.
- **Doctor:** `aew doctor --bundle <staging> --json` is ADR-0014 D8's acceptance record; the self-tests' screen is its rendering, with the base capabilities' and G3's lines.
- **The release checks** that `OIB-01.b`, `OIB-01.c`, `OIB-03.b` and `OIB-14.a` need: in AEW's release tooling (ADR-0014 D5's `tools/release/`). The deployment-only names check reads a private list supplied at release time from the private repository, and refuses to run without it.

## The gate

**The operator-run rows** (each row whose pass says "run by the operator") are one scripted operator session on the reference host, whose recorded output closes them all; `OIB-Q01`'s run is ADR-0014's operator-run end-to-end install. Payload validation (`OIB-Q18`) runs unprivileged in CI, apart from a system-package entry's root part (`OIB-02`).

| Check | What it shows | Pass |
|---|---|---|
| **OIB-Q01** | The install needs no network (`OIB-01`, `OIB-05`, `OIB-06`) | run by the operator on the reference profile (`OIB-03`) with the host baseline applied by the launcher's printed command (a root action outside the sequence's single prompt, `OIB-00`, `OIB-00.a`), no route out and a fresh operator account: the sequence goes from the three files to a green screen, and no process of the sequence's tree, the root step included, makes a `connect`, `sendto` or `sendmsg` to an `AF_INET` or `AF_INET6` address; local `AF_UNIX` traffic is not counted. Observed either with the operator's steps under `strace -f -e trace=connect,sendto,sendmsg`, filtered on the address family, and the root step as its printed command under its own root-run `strace` with the same filter, since a traced `sudo` loses setuid; or, for every step, an auditd rule on those syscalls keyed to the inet families, installed by the operator before the run |
| **OIB-Q02** | ADR-0014's build evidence holds for the extended manifest | ADR-0014's "What the build must show" passes on the install part and a kit part: every adversarial-archive case, two identical rebuilds, the signing refusals, the operator-run end-to-end install, and no trace of the release key |
| **OIB-Q03** | pip installs from staging alone (ADR-0014's probe P3) | on the reference host, every wheel installs with `--no-index --require-hashes --no-cache-dir` and `TMPDIR` set inside the target environment's path, as `OIB-06.a`'s candidate runs it, and a file-open trace (`strace -f`, a test-only tool carried beside the bundle where the reference profile lacks it, never in the install part) shows the venv and the install opening no wheel, archive, index or pip configuration file outside the staging directory; any such open fails |
| **OIB-Q04** | Every list is generated, and a new prerequisite is named (`OIB-01.a`, `OIB-01.b`) | a planted extra wheel, package or payload fails the build as `NOT_IN_MANIFEST`; a hand edit to a generated list, G3's requirements file included, fails the check |
| **OIB-Q05** | Nothing forbidden is carried (`OIB-01.c`, `OIB-02.b`) | the release check refuses a part holding a planted credential-shaped file, a planted deployment-only name from the private list supplied at release time, an item `SPB-07`'s property test marks, or a GPL binary without its source; run without the private list, it refuses to run |
| **OIB-Q06** | Root is asked once for the system part, and does only that (`OIB-07`, `OIB-08`) | run by the operator on `OIB-Q01`'s host baseline: the sequence asks for root in one command; host settings and the baseline's root actions are counted outside it (`OIB-R05`, `OIB-00`); every other step runs as the operator; the preflight or doctor run as root refuses; under named roots (`/opt/aew-g3`, `/etc/systemd/system`, `/usr/local`, `/usr/share/applications`, `/etc/xdg/autostart`), the root step's file changes equal what it recorded, and its package changes, compared by `rpm -qa`, equal its record; logs, caches and the package database's files are excluded |
| **OIB-Q07** | A package is checked twice (`OIB-08`) | run by the operator on the Rocky 8 host: a test package that matches its bundle hash but fails the distribution signature check is refused, and nothing is installed |
| **OIB-Q08** | The installer never sees the PIN (`OIB-09`) | with a known test PIN typed at `set-pin`, it appears in no file the installer wrote, no log, and no argument or environment of any process the installer started, and the installer read nothing from its standard input during the step |
| **OIB-Q09** | Operator steps refuse inside containment (`OIB-08`, `OIB-09`) | run from an AEW-contained context, the root and PIN steps refuse as `OPERATOR_STEP_REQUIRED` before calling `sudo`, name the command, and change nothing; where that check is bypassed, `sudo`'s own failure under no-new-privileges is accepted as the second line |
| **OIB-Q10** | The screen tells the truth (`OIB-10`) | planted faults each turn their line red with a fix: no bubblewrap (required: screen red), G3 not installed (optional: screen green), a base payload with one byte changed (`REFUSED`), a harness stand-in that attempts a connection, seen by the probe's sink (required: screen red) |
| **OIB-Q11** | Resume (`OIB-11`, `OIB-11.a`, `OIB-08.b`) | stopped after each step in turn, a rerun resumes at the first unfinished step and ends green, with no step done twice; a rerun stopped after the root step asks for root once more, for the PIN step alone (`OIB-09`), and that is the resume's only extra root prompt; stopped inside the root step after its packages and before G3's install, a rerun resumes at G3's install, and the record lists every package the step added; a different bundle's rerun refuses as `INSTALL_RECORD_MISMATCH` and names the undo command; running that undo, then the new bundle's install, ends green, and undo removed exactly what the partial record held |
| **OIB-Q12** | The summary is complete, and undo works (`OIB-12`, `OIB-12.a`) | run by the operator on the Rocky 8 host: every file, package and unit the install added appears in the summary; after the undo lines run, `OIB-Q06`'s named roots and the package set (`rpm -qa`) equal the before state, except G3's state, named as kept, and upgrades named as not undone; every project store is byte-identical; with a project migrated by the newer release, undo of that release's environment refuses as `ENVIRONMENT_STILL_NEEDED` and names U-01's restore command |
| **OIB-Q13** | The preflight's commands work (`OIB-07`) | run by the operator on the reference profile: each missing package or file line's command, run as written with no network, turns that line found; host-setting lines are counted outside the sequence's single root prompt (`OIB-R05`) and are not part of this check; with root's staging filesystem planted too small for its archive and extraction, the preflight names that filesystem and the room missing, and the root step is not started |
| **OIB-Q14** | An upgrade keeps the way back (`OIB-13`, `OIB-13.a`, `OIB-13.b`) | run by the operator on the Rocky 8 host: a new bundle's install keeps the previous environment, which still runs, runs G3's reinstall, and keeps G3's PIN; then a rollback to the previous release, and separately an undo of the newer release, each leave G3's installed AEW wheel at the previous release's commit, keep the PIN, and let one approval go through the confirmer; `U01-Q04` is run on the same install |
| **OIB-Q15** | The pre-carry check is a check (`OIB-14.a`) | planted items each fail as `CARRY_REFUSED`: an image with a baked vulnerability database (refusing SPT's whole part), a loose AEW data item a `risk_flags` entry marks (refused; the operator then moves it to the data transfer, where it imports against its pin), a marked member of a signed AEW part (refusing that whole part), an image with no declaration; a clean data set that the property test does not mark passes, and a clean routine transfer passes |
| **OIB-Q16** | The transfer manifest is not trust (`OIB-14`, `OIB-14.b`, `OIB-14.c`, `OIB-03.a`) | for AEW's parts: an edited transfer manifest changes no import outcome; a part with one byte changed fails its own signature check; a kit part imported without the verifier run first, or from a tampered archive, is refused and nothing is imported; a data item with one byte changed is refused against its pin on import, and nothing is imported; an image moved to the data transfer imports to the same pinned digest as from its part. SPT's part is checked once `SPB-04`'s signed bundle exists |
| **OIB-Q17** | Windows says what it lacks (`OIB-15`) | on a connected Windows host, steps 2, 3, 6 and 7 run, steps 4 and 5 are recorded as not needed, the screen names G3 and containment as absent, and the harness line reads "not checked" with its reason |
| **OIB-Q18** | A pin moves only after validation (`OIB-02`, `OIB-02.a`) | a proposed pin whose health check fails on the reference profile leaves the old pin with its reason; a passing one produces its validation record and becomes a reviewed change citing it; an artifact whose upstream publishes no checksum is pinned at intake by AEW's own SHA-256, with its upstream signature checked where one exists, and a planted bad upstream signature refuses the intake |
| **OIB-Q19** | The catalog seed is made, not copied (`OIB-16`) | two builds give the same seed digest from a disposable instance of the exact pin; a seed with a planted operator-profile value fails the build's sanitization check; a seed with one byte changed is refused at verification |
| **OIB-Q20** | Each kit part fits the verifier (`OIB-03.b`) | the real kit is built into its numbered parts, and each part's member count and size are within ADR-0014 D7's bounds and pass the verifier; a planted part over either bound fails the build as `PART_OVER_BOUNDS` |
| **OIB-Q21** | The connected install says what is missing (`OIB-04.a`) | on a connected Linux host, `pipx install` then the preflight names each missing piece with the host package manager's command; a newer harness reads as a warning, an older one or V1 as an error; `pipx upgrade` then doctor names `MIGRATION_REQUIRED` for a project in an older format; the connected root step fetches G3's wheel set and the same-commit AEW wheel by their pinned hashes only after the operator's consent, a wheel with one byte changed at its source refuses the step with nothing installed, and a declined consent fetches nothing |
| **OIB-Q22** | The host baseline is checked first and supplied by one command (`OIB-00`, `OIB-00.a`) | run by the operator on the reference profile: each of a missing `python3.11`, a `python3.11` stand-in without `tarfile.data_filter`, a missing trust root, and a group-writable trust root stops the launcher before any bundle byte is read, names the missing piece, and prints the baseline command; running that command as written, with no network, turns the check found, and the launcher then runs the bootstrap |
| **OIB-Q23** | A host off the reference profile has a guided path (`OIB-07`, `OIB-08`) | run by the operator on a host whose pinned transaction cannot resolve (a planted package newer than the pinned list's dependency): the preflight names each unresolved dependency and offers the host-repository path; chosen, the root step installs from the host's own enabled repositories with signature checking on, and the record shows the choice; on a host whose package database lacks the distribution key, the root step imports it from `/etc/pki/rpm-gpg/` with no prompt but `sudo`'s |
| **OIB-Q24** | Host state sits outside every sandbox (`OIB-05`, `OIB-06`, `OIB-11`) | the staging directories, AEW's environments and the install record each resolve outside every contained context's writable binds and every project tree, checked as `CAPR-04`'s place is (as `U01-Q14` checks its own) |
| **OIB-Q25** | The reference profile is a build input (`OIB-03`) | the build reads the reference profile's recorded package list and records its digest among its inputs; a build without the list refuses; a planted host package entry for a package the list shows already installed fails the release check (`OIB-01`'s host-package clause) |

## Scenarios

**OIB-X01.** Given a Rocky 8 host of the reference profile with no network, the host baseline applied (`OIB-00.a`), and the install part copied in, the operator runs the sequence, enters root once and the PIN at their own terminal, and sees a green screen and the summary (`OIB-04`).

**OIB-X02.** Given the operator closed the terminal after the root step, the rerun starts at the PIN step and asks for root for it alone (`OIB-09`, `OIB-11`).

**OIB-X03.** Given the Lead, in its contained session, runs the root step, it refuses as `OPERATOR_STEP_REQUIRED` and the operator sees the command to run (`OIB-08`).

**OIB-X04.** Given an archive with one member added, step 1 refuses with the verifier's code, and nothing is extracted, installed or run (`OIB-05`).

**OIB-X05.** Given a connected Windows host, the sequence installs AEW, fetches the base tools the operator chooses, and its screen says G3 and containment are absent there (`OIB-15`).

**OIB-X06.** Given a new release's bundle, the operator installs it beside the old one; every project still reads with the old release until the operator plans a migration (`OIB-13`).

**OIB-X07.** Given a routine transfer holding a refreshed rule pack a `risk_flags` entry marks, the pre-carry check refuses it as `CARRY_REFUSED`, the operator moves the rule pack, a loose data item, to the data transfer, and the routine transfer carries on (`OIB-14.a`).

## Rulings

**OIB-R01. F18.3 and D2 are absorbed into E99, as the hold match decided, and no build grows.**
- **F18.3:** the signed bundle, the verifier and `aew doctor --bundle` are built inside E99's pull requests, to ADR-0014; `OIB-05`, `OIB-06`, `OIB-10` and `OIB-Q02` carry them. Its tool-upgrade clause is U-01's (`U01-R07`).
- **D2:** its installer half is the guided sequence (`OIB-04` to `OIB-12`). Its harness-integration half (installed commands, one control surface) does not come here; its nearest row is E129.

**OIB-R02. The sequence is re-derived from the inputs, not the register's sketch.** The register row's four steps are the Lead's sketch. This sequence follows the install design's section 5 and 5.1 order as ADR-0014 corrects it (verify, then install, then doctor), and A-37's adopted G3 text. A-37 retired G3's qualification gate, so there is no G3 qualification step. The register row's "operator sets the PIN" is read through `G3-05`: root's `set-pin`, at the operator's own terminal.

**OIB-R03. One manifest, one owner.** The one manifest owns every requirement, and ADR-0014's bundle manifest is its signed per-target projection, generated (`OIB-01.b`), so each fact has one owner.

**OIB-R04. AEW's runtime is the host's Python 3.11, and its installer is pip.** The verifier needs Python 3.11 before the bundle is trusted, so it cannot come from the bundle. A standalone CPython build and uv, the kit's two candidates, are not used for the offline install: each would be another executable to trust before verification. How the carried Python 3.11 packages are verified is "For the operator", question 5.

**OIB-R05. The sequence changes packages and G3 only.** A host setting (user namespaces, subordinate ID ranges, SELinux) is named with its command and left to the operator, because changing one is the host's administration and widens what root does in the sequence. Each such command is a root command of its own, counted outside the sequence's single root prompt, as are the host baseline's one command (`OIB-00.a`), each upgrade's G3 part (`OIB-13.a`), a G3 restore on rollback (`OIB-13.b`), a resumed PIN step (`OIB-09`) and undo's root commands (`OIB-12`): "root once" means one root command for the system part per sequence run. That reading narrows E99's row, so it takes effect only on the operator's answer to "For the operator", question 7.

**OIB-R06. The installer's undo removes only what the sequence placed.** G3's service-created state (its ledger, key and PIN hash) is not placed by the sequence, so undo never removes it, and the summary leaves it to root's administration (`G3-14`); the PIN step is skipped when the root step finds a PIN held (`OIB-09`). Whether a reinstall keeps G3's state as a rule is "For the operator", question 6.

**OIB-R07. ADR-0014's changes are the operator's.** Every change this position needs in ADR-0014 is listed under "For the operator", and nothing here takes effect against ADR-0014's text before the operator adopts it.

## Backlog

**OIB-B1.** A Windows bundle for a Windows host with no network, and its verifier, if the operator asks for one (question 3).

**OIB-B2.** The feed watcher: reads each entry's upgrade feed and proposes a pin bump, never adopts one (`OIB-02`).

**OIB-B3.** The multi-file payload kind and the installed-tree check, with micromamba as a pinned payload, built when the first conda-forge tool is selected (the kit placement, and the 2026-11-01 conda-forge conditions).

**OIB-B4.** The Python 3.11 packages carried for the host baseline (`OIB-00`), verified as the operator answers question 5.

## Not covered

- **The release key, its custody, rotation and the verifier's arithmetic:** ADR-0014's D1 to D9.
- **Which tools are carried and where they are placed:** the capability register's first bundle and the kit placement (STG-15's `FIRST-BUNDLE.md` and `AIRGAP-KIT-PLACEMENT.md`, build inputs); registering a carried tool is `CAPR-13`'s.
- **SPT's images, their signing, their one-layout form, and which transfer keeps a manifest digest:** A-54 (`SPB-04`, `SPB-05`, `SPB-07`, `SPB-B6`).
- **Doctor's general rows** (remedies, `--todo`, `--online`, stable finding ids): F18.2's row.
- **The provider-access profile, and doctor verifying it without exposing secrets:** E123, into which F18.4 merged, with the doctor row F18.2's.
- **Project migration and its restore point:** U-01 (`U01-05.a`, `U01-06`).
- **Starting AEW in one step:** E129.
- **An SBOM, per-wheel provenance and a signature over the spec pin:** later manifest additions, as ADR-0014 says.

### For the operator

The complete list of operator-only questions, each with the designer's recommendation first.

1. **Adopt this position** as revision 1. Recommend yes.
2. **The changes in ADR-0014**, each one a decision, numbered from 2.2.

   **A note, not a decision (formerly 2.1):** the build moved from F18.3 to E99 by the operator's hold-match decision (`00-governance/decisions/2026-11-06-operator-hold-match-batches.md`), and ADR-0014's status line becomes a pointer citing it.

   2. **D2's file types and blocks**, which D7 step 4 refuses unless D2 lists them: add `system_package` (a distribution package, kept with its signature, installed as a local package, `OIB-03.c`), `source` (a source tarball tied to its binary's entry), `service` (G3's service and confirmer files) and `bootstrap` (the trusted bootstrap's in-bundle copy, `OIB-04.b`); and for the kit parts `conda_channel` (channel files and their lockfiles), `npm_tarball` (a locked npm tarball set), `oci_layout` (an OCI layout's files) and `browser_dir` (a browser directory, pinned by AEW's own hash). A kit part's manifest has no install block, so D2 gains a `kit` block in its place, naming the part's number and its entries, with one hashed requirements file per locked Python environment. ADR-0014's limits clause reads schema additions as not changing the ADR; they are listed because D2 enumerates the types and D7 refuses unlisted ones. D7's bounds are not changed: each kit part is held within them (`OIB-03.b`, `OIB-Q20`), since no measured size of the whole kit exists yet. Recommend yes.
   3. **D2's install block:** a second hashed requirements file, for G3's root-owned environment (absorbing `g3/requirements-offline.txt`), the pinned pip wheel (`OIB-06.a`), and the root step's inputs. Recommend yes.
   4. **D5's build:** it also takes system packages from each Linux target's pinned package list (`OIB-03.c`), base payloads and sources by URL and SHA-256, all from the one manifest, which generates the bundle manifest; and it builds the kit into numbered parts. Recommend yes.
   5. **D8's install, its order and its scope:** it grows from the environment and the harness binary to the payload import, the root step (a fresh verification into root's own staging copy, packages with the distribution signature check on, then G3's install, from staging only) and the PIN hand-over. The order is stated: AEW's own code runs from step 3 (the preflight); G3's install, its packages' scriptlets and its service's start are allowed at step 4; the harness binary does not execute before step 6's dry probe with the network unshared, which is what D8's clause covers. D8's "nothing outside the staging directory is consulted" stays, apart from the host's own package database and distribution keys, and, on the graceful path of `OIB-07` only, the host's own enabled repositories. Recommend yes.
   6. **D2's naming:** a part name, for the install part and each numbered kit part (question 4). Recommend yes, if question 4 is yes.
   7. **D2's pins for items carried elsewhere:** a block of entries for AEW's data payloads, each with its SHA-256 and build date, in the signed kit manifest but not members of its archive, so that D7 step 7's "listed paths equal members" reads only the files block; a data item is checked against its pin on import (`OIB-14.b`). Recommend yes.
   - **Not changed:** D1, D3, D4, D6 and D9; D7's text, apart from what it reads from D2's lists; the transfer manifest is not a trust object, so it needs no change.
3. **Windows scope.** E99's row asks for an install with no network, and `OIB-03` serves Windows, a connected Windows host, online only, so E99's no-network install would be met on Linux alone. Recommend: Windows is a connected target for Internal alpha (AEW's environment, the harness's Windows binary, the base tools' Windows payloads, the toast's dependencies; no root step, no PIN, no G3). The alternative, a Windows host with no network, needs ADR-0014's D7 to gain Windows trust-root checks in place of its POSIX ones, and a Windows bundle name (`OIB-B1`).
4. **AEW's signed parts in the transfer (an A-54 amendment).** Carrying the kit is already answered (the kit placement's first lines; the designer ruled it carried in full). What is open: with the kit in its own signed parts, the routine transfer holds AEW's install part and its numbered kit parts beside SPT's part, where `SPB-07` and the 2026-11-01 STG-29 decision (answer 5) define two signed parts, one per product. Recommend: amend `SPB-07` to read "each product's signed parts", AEW's release being its install part and its kit parts. The alternative is to carry the kit inside AEW's one part, which then must fit D7's bounds together with the install part, or D7's bounds change.
5. **How the carried Python 3.11 packages are verified.** `g3/install.sh` tells root to `dnf install python3.11`. Whether the reference profile (`OIB-03`) lacks it is read from that profile's recorded package list (`rpm -q python3.11` on it), which is owed with the profile and not yet recorded; the Rocky 8 host measured so far, in the tool inventory of 2026-11-01, is not that profile, since python3.11 was added to it after its install. The open question is how a package outside ADR-0014's three files is verified, since the verifier itself needs Python. Recommend: the baseline command (`OIB-00.a`) installs python3.11 from the host's own distribution source first (its installation media or its mirror), under the host's own distribution signature check; only where the host has none do the Python 3.11 packages travel with the verifier, the bootstrap and the trust root through the organization's channel (the HOST rule of the kit placement; `OIB-B4`), checked by the same signature check against the distribution keys the host already trusts. Consequence: that is part of the baseline's one root command before step 1, outside the sequence's single root prompt (`OIB-00`, question 7).
6. **G3's state across a reinstall (an erratum to A-37).** `g3/install.sh` leaves G3's state alone on a reinstall, so an earlier PIN, key and ledger are kept, but no adopted text says so (`G3-11` covers a restart), and U-01's "Not covered" assigns G3's state to its own install (`G3-14`). Recommend: an erratum to A-37 stating that a reinstall keeps G3's ledger, key and PIN hash, and that only a separate root command removes them. Until then, `OIB-09` and `OIB-R06` describe the installer's behaviour only.
7. **What "asks for root once" means (a narrowing of E99's row).** E99's row says the install asks for root once. This position counts one root command per sequence run, for the system part (`OIB-08`), and counts outside it: the host baseline's one command on a first install (`OIB-00.a`), each host setting's command, each upgrade's G3 part (`OIB-13.a`), a G3 restore on rollback (`OIB-13.b`), a resumed PIN step (`OIB-09`) and undo's root commands (`OIB-12`). The baseline cannot join the root step, since the verifier needs Python 3.11 before any bundle byte is trusted, and host settings are the host's administration (`OIB-R05`). Recommend: accept one root command per sequence run, with the baseline one printed command on a first install only.

**Already answered, not re-asked:** conda-forge and the licence items (`00-governance/decisions/2026-11-01-operator-airgap-kit-conda-forge-and-licences.md`); antivirus-sensitive data apart (`2026-11-01-operator-transfers-cheap-except-AV-sensitive-data.md`); the container tools carried as Rocky 8 packages (`SPB-05`); F18.3 and D2 into E99 (`2026-11-06-operator-hold-match-batches.md`); Linux and Windows only (`2026-11-01-operator-supported-platforms-Linux-and-Windows.md`); carrying the kit (the kit placement's first lines).

### Placement

- **Milestone:** Internal alpha, per E99's row. Its order in the Now list (item 13, which the operator's decision of 2026-11-02 on the personal alpha placed early) is the Lead's.
- **The limit on half-built work:** under the operator's N = 12 (`00-governance/decisions/2026-11-06-operator-board-decisions-concurrency-steering-maps-knowledge.md`, item 4 and its last pointer), a new system starts only when the count, with it added, stays at most 12. The count is 16, as the build board of 2026-11-06 and its systems check compute it; E99's own system on the board is designed only, so it is not in that count. So the build is placed, not started, and starts only when the count, with it added, stays at most 12.
- **A consequence of the confirmed limit:** while the E99 build waits on the count, so do the personal alpha's order of 2026-11-02 (the bundle before the work step) and Now item 13.
- **Size:** E99's own estimate, 2 to 4 pull requests, plus F18.3's and D2's 2 to 3. No plan is given beyond that.

## Changes

- **Revision 1, after the review round (2026-11-06):** every finding of the one review round answered, as `CHANGES-r1-review.md` lists. A network attempt is an inet `connect`, `sendto` or `sendmsg`, local traffic not counted (finding R1). The host baseline gets a launcher, one printed command and a gate row: `OIB-00.a`, `OIB-Q22` (R2). G3 follows a rollback or an undo: `OIB-13.b`, `OIB-Q14` extended (R3). The disk count covers each staging directory's archive and extraction (R4). An interrupted root step and an abandoned install resume: `OIB-08.b`, `OIB-11.a`, `OIB-Q11` extended (R5). Gate rows for every rule without one: `OIB-Q16`, `OIB-Q18`, `OIB-Q21` extended, `OIB-Q24`, `OIB-Q25` (R6). A host off the reference profile has a guided path, the distribution key is imported without a prompt, and the system packages install as local packages with no generated repository metadata: `OIB-07`, `OIB-08`, `OIB-Q23`, question 2.2 (R7). `aew setup` invokes `sudo` on the trusted bootstrap itself (R8). The root-count narrowing is question 7 (R9). Validation runs in CI, and the operator-run rows are one session (R10). The pre-carry check refuses and moves nothing (R11). Wording, restated bounds and dead references (R12, R13, R14).
- **Revision 1 (2026-11-06):** the first text. "For the operator" and "Placement" are third-level sections under "Not covered", since the template allows no other second-level section.
