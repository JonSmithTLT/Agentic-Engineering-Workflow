<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-46
source: 30-stages/STG-22-U01-upgrade-and-recovery/adopted/u01-r3/U01-POSITION.md
source-sha256: b72f69849bb7bb17381ee98b09590a23d0f7260603c81a5f5ab2674deef8c07c
edits-sha256: none
-->

# Upgrade and recovery, U-01 (PROPOSED, revision 3)

**Namespace:** `U01-`
**Status:** proposed; nothing here is adopted.
- It is a contract for AEW's own upgrade and rollback, for migrating a project's store between formats, for the
  disposition of a format AEW does not read, and for the migration half of a move to another installation.
- It extends one adopted clause by one case: A-45's `O02-07.a` gains a control file that passes its checksum and is
  refused by its format marker (`U01-03.d`). That tightens A-45, and is for the operator to confirm at adoption. It adds
  no D-01 read and no O-01 type.
- It answers A-39's backlog item `I6-B2`, narrowing it: no credential moves (`U01-07.d`).

**Authority:** the operator's decision to start U-01 (`00-governance/decisions/2026-10-29-operator-start-U-01-now.md`),
in the wire track's order (`00-governance/decisions/2026-10-25-operator-wire-track-ahead-of-publication-tooling.md`).
**Threat model:** the security depth reset (`00-governance/decisions/2026-10-24-operator-security-depth-reset.md`): a
contained agent cannot fake an approval, forge an owner fact, read a credential or escape. Malicious code running as the
operator is out of scope (`00-governance/decisions/2026-10-19-operator-G3-threat-model.md`).
- **What is at stake here:** an accepted record lost or reinterpreted by an upgrade, a migration or a rollback; a
  migration or restore an agent can start; a restore point an agent can write; and a credential or a host-bound fact
  carried to another installation.

**Research consulted:** `tools/research_index.py lookup`, by position, requirement and register row.
- **F18:** the air-gap capability study (`aew-phase6-airgap-capability-research-2026-10-01`). Its cold-start acceptance
  list is the offline condition `U01-02.c` and the gate's `U01-Q12` lean on. Its other findings, on providers and the
  bundle's contents, do not bear.
- **The storage investigation** (`adr-0011-storage-investigation-2026-10-01`): it deferred migration timing to the
  implementation, so `U01-05` sets no time bound.
- **A-17:** the containment study. It does not bear.
- **None:** the lookups for `AEW-FR-35`, `AEW-FR-35.a`, `AEW-FR-35.b`, `AS-24`, `WIS-08.d`, `IF13-17`, `I6-B2`,
  `S01-22`, `AEW-FR-39.c`, `AEW-FR-32.a`, A-01, A-08, A-18, A-39, the offline bundle (E99), and the terms "upgrade",
  "migration", "rollback", "air-gap" and "offline".

**Files:**
- this file;
- the regression aid for the gate, not normative: `verify_u01.py` and `u01-cases.json`;
- the inputs: `inputs/fact-map-2026-10-29.md` and `inputs/design-comparison-2026-10-29.md`;
- the answers to round 1: `CHANGES-r2.md`; to the quick check: `CHANGES-r3.md`.

## What the adopted text already decides

- **The outcome:**
  - accepted records keep their accessibility and meaning through a supported upgrade (`AEW-FR-35.a`);
  - a prior format AEW cannot safely read gets a qualified recovery or migration disposition, and is never silently
    read as current (`AEW-FR-35.b`);
  - an approved offline profile keeps local record access across a supported upgrade (`AS-24`, `AEW-FR-34.a`), and
    secrets stay out of general records (`AEW-FR-36.a`).
- **What a migration may not do:** assert new acceptance, assurance or execution guarantees, or hide a legacy
  ambiguity (`WIS-08.d`, `WIS-X23`). A destructive migration needs the responsible authority's confirmation
  (`AEW-FR-39.c`). Recovery keeps accepted state intact, and lets no obsolete authority overwrite it (`AEW-FR-32.a`,
  `AEW-FR-32.d`, `HEB-08.a`).
- **A move and a new version:**
  - a switch of host is no laundering, and "Data migration has an independently governed owner path (U-01), never
    implied by transition" (`IF13-17`);
  - moving a project, and qualifying a host, are not O-01 commands; the install happens outside O-01; the move's
    profile half is `REQUEST_PROFILE_CHANGE` naming the new installation (`I6-09`);
  - a new version or host is a new effective profile, whose protected capabilities are requalified before use, and
    which carries no stale credential access across the transition (`S01-22`, `S01-03`, `HEB-03.o`). Current
    enforcement stays until its replacement is established (`HEB-10.e`). The operator applied this to OpenCode on
    2026-10-24, with no new contract (`00-governance/decisions/2026-10-24-operator-OpenCode-version-currency.md`);
  - the installation and the profile version are separately identifiable (`IF13-02`, `S01-02`).
- **What is bound to a host:** G3's key, PIN hash and lockout state are never copied (`G3-Q05`); a consent names its
  installation (`G3-06`); each G3 approval record is per host (`BOY-05.a`); each host's G4 record is its own
  (`O02-09`); the capability register's base tools ship with every install, as host state outside every sandbox's
  writable binds (`CAPR-04`), and its commands are the operator's only (`CAPR-05`).
- **In an outage:** a control file the reader cannot read makes the read `unavailable` (`O02-07.a`), while a record
  that fails or lacks its pin, or a gap in the log's chain, makes it `partial` (`O02-07.b`, `O02-07.c`, `O02-07.e`).
  The outage reader runs no recovery (`O02-03`), and A-45 leaves recovery and repair to U-01 and the store's writers
  (its "Not covered").
- **Automatic recovery is held:** A-05's parameter row for automated stop, release and recovery is unadopted, so an
  auto-run recovery step waits (`I6-10`).

## The parts

| Part | What it is | Writer | Reader |
|---|---|---|---|
| The store | `.aew/state`: the control file with its checksum, the redo records, the transition log with its hash chain | AEW's host code, under the control lock | AEW's host code; every contained context, read-only |
| The pinned records | the git-kept records under `.aew/` that the control state pins by hash, with the history and archive bundles | AEW's host code, append-only | as the store |
| The envelopes and format markers | each store file's envelope (its integrity check and format marker, and in the control file the store's installation and writer) and the format its marker names: the control state's `schema`, the transition log's, the archives', history's, the manifest's and the Ticket field registry's | the release that writes the file | every reader of that file |
| A release | one installed AEW version, with its format declaration (Interfaces) | its build | every command of that release; doctor |
| The local state | `.aew/local`: rebuildable runtime data | AEW's host code | AEW's host code |
| The restore points | one per migration, a copy of the store as it was before it: host state on the installation that migrated | the migration, under the control lock | the restore |
| Per-host state | outside every project: the capability register, G3's service state and key, OpenCode's logins, each G3 approval record, each G4 record, the restore points | its own owner, on its own host | its own owner |
| The operator's local commands | the migration, its plan, the restore and the move's adoption (Interfaces), run at the operator's terminal | the operator | the operator |

## Rules

**U01-00. Precondition: every file's envelope and format marker are checked before its file is used.** A reader of a store file checks its envelope, then its format marker, before it uses any of the file, and treats a value it does not declare as refused, never as current.
- At `main` this holds for the control file: its checksum, then its closed `schema` list and closed top level; every
  other marker is an exact match (`inputs/fact-map-2026-10-29.md`).
- **A derived index under `.aew/local`** (the history index, the recall substrate) is rebuildable, so it is not a
  format marker here: on a version mismatch it is rebuilt, not refused. The store's bytes are what `U01-03` holds.

**U01-00.a** Each store file has an envelope that no format changes: its integrity check, its format marker and, in the control file, the store's installation (`U01-07.a`), the list of the store's files, and, where recorded, its writer (`U01-03.b`). Every release reads the envelope before the body, so `U01-03.a`'s cases are told apart without reading a body.
- **What a release judges:** exactly the files the control file lists. A file it does not list, such as a leftover
  `U01-06.d` keeps, is neither refused nor read, whatever its name.
- **A changed envelope:** a format that must change one moves its file to a new name, which the control file lists,
  and the new file carries every record of the old (`AEW-FR-35.a`). The old copy stays as history, unlisted. An older
  release refuses the listed file it does not know as `FORMAT_NOT_READ`, never as damage. A listed file that is
  missing is `INTEGRITY_ERROR`.
- **The control file** keeps its name, and its envelope is fixed from the first release built to this position. A
  release from before this position refuses a store migrated by a later one by its format, never as damage.
- **Candidate:** the list's encoding (Interfaces). The first release built to this position adds the installation,
  the writer and the list inside what `main`'s checksum covers, keeping the checksum trailer as the file's last line
  (`src/aew/engine/store.py:228-229`).
- At `main` the transition log's genesis hashes its format name (`src/aew/engine/outbox.py:49`). Under this rule that
  genesis is part of the log's envelope: a later log format keeps it, or moves to a new name (`U01-B8`).

**U01-01. What this position covers: AEW's own upgrade and rollback, a project's migration between formats, the disposition of a format AEW does not read, and the migration half of a move.** Everything else that changes a version or a host is another owner's, as "Not covered" names.

**U01-02. Each release declares its formats.** For each format marker, a release declares the one format it writes, the formats it reads, the formats it migrates from, and the formats it no longer migrates from.
- The declaration ships with the release, and doctor shows it.

**U01-02.a** A supported upgrade is one from a declared format. Through it, every accepted record stays readable with its meaning (`AEW-FR-35.a`): either the new release reads the old format, or it migrates from it.

**U01-02.b** A release that stops migrating from a format declares it so, and every later release keeps declaring it, with the last release that migrates from it. A store in that format is refused as `FORMAT_UNSUPPORTED`, naming that release, and is never attempted. So a format any earlier release wrote is always one this release reads, migrates from, or names the way back for.

**U01-02.c** A migration from a declared format needs no network (`AS-24`, `AEW-FR-34.a`).

**U01-02.d** A format is a marker's value. A change to what a release writes under a marker takes a new value, reached only by the migration (`U01-05`). A change is anything the format's schema, as its readers validate it, does not admit, a key added included, or any change to what a value means. So an ordinary write by a newer release never changes what an older release reads.
- **At `main` the practice is the other one.** `aew/control/v2` grows by addition (ADR-0012 D10), and every commit
  writes the outbox keys whatever the control file's `schema` (`src/aew/engine/store.py:573-586`), so a v1 file carries
  v2-era keys after any write.
- **A format from before this position** is every body `main` reads under its value. The first release built to this
  position migrates from those formats, and ends the practice with ADR-0012 D10's other option, a new value with a
  migration step (`U01-B8`).

**U01-03. A format AEW does not read is never read.** A store file whose format the release does not read is refused before any of it is used, and is read neither as current nor as history (`AEW-FR-35.b`).
- **The refusals** (Interfaces): `MIGRATION_REQUIRED`, `FORMAT_UNSUPPORTED`, `FORMAT_NOT_READ` and, for a damaged
  file, `INTEGRITY_ERROR`. Each names the file, the format found, the formats this release reads, and one next step.
- **What holds:** the store's bytes. A refusal writes nothing.

**U01-03.a** The cases are told apart by the order of the checks, the envelope first (`U01-00.a`): a file the release does not know is `FORMAT_NOT_READ`; a known file that is missing, or fails its integrity check, is damaged (`INTEGRITY_ERROR`); one that passes it, with a format the release migrates from, is `MIGRATION_REQUIRED`; one with a format the release no longer migrates from is `FORMAT_UNSUPPORTED`; any other, including a known marker over a body the release cannot read, which only a release from before this position writes (`U01-02.d`), is `FORMAT_NOT_READ`.

**U01-03.b** From the first release built to this position, a `FORMAT_NOT_READ` refusal names the release that wrote the file, where the store records it. An older release keeps refusing the file, whatever it records.
- **Candidate:** the control file's envelope records the last writer's version and its format declaration's digest
  (`U01-00.a`), so a release reads the record without reading a body it does not read.

**U01-03.c** A command is refused on the store files it uses, naming each refused file with its own refusal, the control file's first. The launch and doctor use every file. Every reader that uses a file gives the same refusal for it.

**U01-03.d** The outage reader reads nothing of a refused file. A refused control file makes the read `unavailable`, the outcome A-45 gives a control file it cannot read (`O02-07.a`); a control file that passes its checksum and is refused by its format marker is this position's addition to that list. For any other refused file, the outage reader answers A-45's own outcomes: a refused transition log makes any history shown `partial` (`O02-07.c`), and a refused file of pinned records makes each item drawn from it `stale`, and the result `partial` (`O02-07.b`, `O02-07.e`).

**U01-04. Upgrading AEW and migrating a project are separate.** Installing a release changes no store: nothing migrates at install, at launch, or on a read.
- **An older format the release reads** is read with its meaning. What the release writes there is exactly that
  format (`U01-02.d`), or the write is refused as `MIGRATION_REQUIRED`.
- **An older format it only migrates from** is refused as `MIGRATION_REQUIRED` for everything but the migration's plan,
  the migration, and a restore's own record (`U01-06.d`).
- **A format from before this position** records no installation (`U01-07.a`), so the release writes nothing in it
  but a restore's own record: every other write and the launch are `MIGRATION_REQUIRED`, and a read continues where
  the release reads the format.
- **The launch:** where the release reads and writes the store's format, the Lead launches once the release's
  qualification, S-01's, passes (`S01-22`, `HEB-03.o`).

**U01-05. The migration is the operator's planned, atomic act.** A migration moves a store from a format the release migrates from to the one it writes, and is the only command that changes a store's format (`U01-02.d`).

**U01-05.a** It is the operator's own act at their terminal: refused in a Lead session and in a worker run, and never started by AEW (`AEW-FR-39.c`, `I6-10`).

**U01-05.b** It is refused while a run may be live, naming the runs.

**U01-05.c** It runs only on the operator's confirmation of its plan (`PLAN_REQUIRED` without one). The plan names the release that made it and its format declaration's digest, the store and its revision, the formats from and to, what it changes, the installation it records (`U01-07.a`), and its restore point. The confirmation names the plan's digest. The migration recomputes the plan and runs that, never a plan file. A confirmation under another release, after the store changed, or whose digest is not the recomputed plan's, is refused as `PLAN_STALE`.

**U01-05.d** It is atomic. After an interruption at any point, exactly one of the two formats is current, and what an unfinished migration wrote is unreferenced and never read (`AEW-FR-32.a`).

**U01-05.e** It is additive. It rewrites no pinned record: what it changes, it writes as new records or annotations, and every pin that held before it holds after it.
- **The clean start:** before it writes, once every check has passed, and under the control lock, it removes what an
  interrupted or a restored migration wrote: records of the kinds a migration writes, which no pin and no current
  record references. That is how a re-run starts clean.
- **Its scope:** each file it removes is listed in the plan the operator confirms (`U01-05.c`). It never removes
  anything under `.aew/local`, a file the release does not write, or a moved file's old copy (`U01-00.a`).

**U01-05.f** It asserts nothing new. Each migrated item keeps exactly its acceptance, assurance, execution guarantees, provenance and recorded limits, and gains none. A legacy ambiguity stays explicit, and is never resolved by a guess (`WIS-08.d`, `WIS-X23`).

**U01-05.g** It is recorded as one transition, attributed to the operator, naming the formats from and to, its restore point, and the restore point's digest.

**U01-06. A rollback never discards accepted state.** A rollback returns a project to the release before an upgrade, and is one of two things only.
- **Before a migration:** the previous release reads the store as it was. Installing changed nothing (`U01-04`), and
  every write since is in a format it reads (`U01-02.d`). The Lead launches once the previous release's qualification
  passes (`S01-22`, `HEB-03.o`).
- **After a migration:** restoring the migration's restore point, then running a release that reads the restored
  format, once its qualification passes. The restore is made with a release that still reads or migrates from every
  format the restore point holds, so it can write the restore's record (`U01-06.d`): the release that migrated, or a
  later one that has not dropped them. A release that has dropped one refuses the restore as `FORMAT_UNSUPPORTED`,
  naming the last release that migrates from it (`U01-02.b`).

**U01-06.a** A restore is the operator's act, under `U01-05.a` and `U01-05.b`, on the installation that migrated.

**U01-06.b** It is refused as `NO_RESTORE_POINT` where the migration declared none, or where its restore point is missing or does not match the digest the migration's transition recorded (`U01-05.g`). The store stays in the new format.

**U01-06.c** It is refused as `COMMITTED_SINCE` where anything was committed after the migration, listing those revisions (`AEW-FR-32.d`). It never discards them. The way forward is the release that migrated, or a later one.

**U01-06.d** After a restore, what the migration added is unreferenced and never read as current, and a file it moved to a new name stays on disk unlisted (`U01-00.a`). The restore is recorded as one transition in the restored store's log, as the next revision, attributed to the operator.
- **Its format:** that record is written exactly as the restored format is written (`U01-02.d`). For a format from
  before this position, that is as `main` writes it, recording no installation and no writer where the format has
  none.
- **Its fields:** every field and value of the record is one the restored format's schema admits. At `main` a
  transition's top level and its event kinds are closed, and its `op` is an open string
  (`src/aew/schemas/transition.schema.json`). So the record names its restore point in `refs`, adds no field, and
  carries no event kind `main` does not admit.
- **The one exception:** it is the one write `U01-04` allows in a format the release only migrates from, and the one
  write that records no installation (`U01-07.a`). So the release before the migration reads the restored store, its
  restore record included.

**U01-06.e** The restore point is host state on the installation that migrated: outside every contained context's writable binds and outside every working tree, as `CAPR-04`'s payloads are. It is kept until the operator removes it, and never travels with a copy of the project (`U01-07.c`).
- **Candidate:** AEW's per-user host state on that installation, in a directory per project.

**U01-07. A move to another installation is explicit, and carries nothing bound to a host.** A project moves by copying its files, the repository and its `.aew/` tree. A move is never implied by opening those files elsewhere (`IF13-17`).

**U01-07.a** Every write but a restore's own record (`U01-06.d`) records the writing installation in the control file's envelope (`U01-00.a`). A writer that finds another installation recorded refuses every write, the migration and the restore as `INSTALLATION_CHANGED` until the operator adopts the move. A store that records none, which only a release from before this position writes, gets one only by the operator's act: the migration from its format names this installation in its plan, and the operator's confirmation records it (`U01-05.c`). An ordinary write never records one where none was. Reads continue, and show every live value recorded on another installation as that installation's, never as live here.

**U01-07.b** Adopting the move is the operator's act, under `U01-05.a` and `U01-05.b` as read on the new installation. It is recorded as one transition naming both installations.
- **The old seat ends.** In that transition the old installation's Lead seat ends, and every credential recorded live
  there, the Lead's and each invocation's, is revoked (`S01-22`).
- **What stays as history.** Every live value recorded on the old installation, such as a custody worker, a validation
  executor, the Lead's uid or a worktree path, stays as history, and each run it names is never live here. What becomes
  of those runs is `HEB-08.a`'s reconciliation, which this position does not change.

**U01-07.c** Nothing bound to a host is copied. Each is established on the new installation by its own owner: the host's profile and every qualification (`REQUEST_PROFILE_CHANGE`, `S01-03`, `HEB-03.o`); G3, with its own key and issuer (`G3-Q05`); the capability register and its payloads; each G3 approval record and each G4 record (`BOY-05.a`, `O02-09`). An approval pending on the old installation stays there, and lapses. The old installation's restore points stay there (`U01-06.e`).

**U01-07.d** No credential moves. The store holds only credential verifiers. After the adoption ends the old seat (`U01-07.b`), the Lead's credential is issued afresh on the new installation, at a new generation, and provider logins are entered again (`AEW-FR-36.a`).

**U01-07.e** The installation's identity is IF-13's and S-01's (`IF13-02`, `S01-02`). This position requires only that a writer records it and compares it, and refuses on a mismatch. Until IF-13's identity is built, a release records a stand-in, named as one. Replacing the stand-in with IF-13's identity is a migration to a new format value, planned and confirmed like any other, and never reads as `INSTALLATION_CHANGED` (`U01-B2`).

**U01-08. The wire: no new type.** A-32's `UPGRADE_OR_ROLLBACK_AEW` and the migration half of `CHANGE_HOST_INSTALLATION` are served by the host's install and the operator's local commands, as `I6-09` serves the move.
- **The local commands** are the operator's only: never on the Lead broker's or a worker's surface, each with its
  surface-map entry (`CAPR-05`'s rule, applied here). Their origin is the operator by where they run: at the operator's
  terminal, outside every sandbox, refused in every contained context (`U01-05.a`).
- **What admits them:** where they run, by a process that can write the store and the host state. They take no Lead
  credential, and are attributed to the operator. This changes `main`'s `aew migrate`, which takes the Lead credential
  (`src/aew/cli/commands.py:96-99`); after a move, the only Lead credential the copied store admits is the old
  installation's, whose seat the adoption ends (`U01-07.b`).
- **The site** shows a refusal as its producer reports it. It starts no migration, restore or move.

## Interfaces

### The format declaration

| Field | What it holds |
|---|---|
| `marker` | the format marker's name, one per store file kind |
| `writes` | the one format this release writes |
| `reads` | every format this release reads, `writes` included |
| `migrates_from` | every format this release migrates from |
| `no_longer_migrates` | every format an earlier release wrote that this release neither reads nor migrates from, each with the last release that migrates from it, kept by every later release (`U01-02.b`) |

**Candidate:** shipped as data in the package, printed by `aew --version --formats` with its digest, which the plan
names (`U01-05.c`), and compared by doctor with the store's markers.

### The envelope

| Field | In | What it holds |
|---|---|---|
| the integrity check | every store file | the file's own check: the control file's checksum trailer, the log's hash chain from its genesis |
| the format marker | every store file | the format's value (`U01-02.d`) |
| the installation | the control file | the installation that last wrote the store, or a stand-in named as one (`U01-07.a`, `U01-07.e`) |
| the file list | the control file | the store's files, which are what a release judges (`U01-00.a`); **Candidate:** each one's name and marker |
| the writer | the control file | **Candidate:** the last writer's version and its format declaration's digest (`U01-03.b`) |

**Candidate:** from the first release built to this position, these fields sit inside what `main`'s checksum covers,
and the checksum trailer stays the control file's last line (`U01-00.a`).

### The refusals

| Name | When (`U01-03.a`) | What it says | Next step |
|---|---|---|---|
| `INTEGRITY_ERROR` | a known file that is missing or fails its integrity check | the file, and that it was damaged or edited outside AEW | restore the file from your own copy (git, where you commit `.aew`, or a backup); or, if the damage followed a migration with nothing committed since, restore its restore point (`U01-06`); with neither, keep the store as it is and report it, since AEW has no repair yet (`U01-B7`) |
| `MIGRATION_REQUIRED` | a format this release migrates from, or one from before this position, and the command is not one `U01-04` allows | the file, the format found, the format this release writes | plan the migration (`aew migrate --plan`) |
| `FORMAT_UNSUPPORTED` | a format this release no longer migrates from, met by a read, a migration or a restore | the file, the format found, the last release that migrates from it | use that release: migrate with it first, or restore with it (`U01-06`) |
| `FORMAT_NOT_READ` | a file this release does not know, any other format, or a known marker over a body this release cannot read | the file, the format found, the formats this release reads, and the release that wrote it where recorded (`U01-03.b`) | run the release that wrote it, or a later one; to come back to this release, restore the migration's restore point from that release if nothing was committed since (`U01-06`) |
| `PLAN_REQUIRED` | a migration with no confirmed plan | the migration | plan, then confirm the plan |
| `PLAN_STALE` | a confirmation under another release, after the store changed, or not matching the recomputed plan | the plan's release and revision, and the current ones | plan again |
| `NO_RESTORE_POINT` | a restore whose restore point is missing, or does not match the digest the migration recorded | the migration | keep running a release that reads the new format |
| `COMMITTED_SINCE` | a restore after later commits | each revision committed since | keep running a release that reads this format: the one that migrated, or a later one |
| `INSTALLATION_CHANGED` | a write, a migration or a restore on a store last written on another installation | both installations | adopt the move (`aew migrate --adopt-move`) |

`MIGRATION_REQUIRED` and `INTEGRITY_ERROR` exist at `main` (`src/aew/errors.py`). The others are new names.

### The plan

The plan names: the release that made it and its format declaration's digest, the store, its revision, each marker's
format from and to, what the migration changes (units archived, records annotated, files added, and each file the
clean start removes, `U01-05.e`), the installation it records, and its restore point's name and place. The confirmation names the plan's
digest. The migration recomputes the plan and runs it only if the digests match (`U01-05.c`).

### The operator's local commands

**Candidate:** `aew migrate --plan`, `aew migrate --confirm <plan>`, `aew migrate --restore <point>` and
`aew migrate --adopt-move`. Each is refused in a Lead session, as `aew migrate` is at `main`.

## The gate

| Check | What it shows | Pass |
|---|---|---|
| **U01-Q01** | Every envelope and format marker is checked before use (`U01-00`, `U01-00.a`) | for each marker, a file with an undeclared value is refused before any of it is read; a listed file the release does not know is `FORMAT_NOT_READ`; a listed file that is missing is `INTEGRITY_ERROR`; an unlisted file is neither refused nor read; no file a newer format wrote is refused as damaged, by a release built to this position or by one from before it |
| **U01-Q02** | Each refusal is the right one (`U01-03.a`) | a damaged, a migrate-from, a dropped, an unknown and a newer-bodied file each give their refusal, with its next step, and write nothing |
| **U01-Q03** | Readers agree, per file (`U01-03.c`, `U01-03.d`) | each command that uses a refused file, doctor and the launch give the same refusal for it, and a command that does not use it is not refused; the outage reader answers `unavailable` for a refused control file and A-45's `partial` outcomes for any other, and reads no refused file |
| **U01-Q04** | Installing changes no store (`U01-04`) | after a new release is installed and launched, the store's bytes are unchanged, and a write outside `U01-04` is `MIGRATION_REQUIRED` |
| **U01-Q05** | The migration is the operator's (`U01-05.a`, `U01-05.b`) | refused in a Lead session, in a worker run, and while a run may be live |
| **U01-Q06** | The plan binds (`U01-05.c`) | a migration without a confirmed plan is refused; a plan made before a commit, under another release, or altered after it was made is `PLAN_STALE` |
| **U01-Q07** | The migration is atomic (`U01-05.d`) | at every fault point of the migration's crash matrix, exactly one format is current, and the next writer's recovery leaves nothing referenced from the other |
| **U01-Q08** | The migration is additive and asserts nothing (`U01-05.e`, `U01-05.f`) | every pin before is a pin after; every migrated item's acceptance, assurance, execution guarantees, provenance and limits read the same before and after; after a restore, the migration runs again, removing only the records its plan lists, and never `.aew/local` or a moved file's old copy; a store migrates twice in a row |
| **U01-Q09** | A restore never discards (`U01-06`) | with no later commit, a restore leaves the old format current, and the previous release reads it, the restore's record included; with one, it is `COMMITTED_SINCE` and lists it; with no restore point, or one changed after the migration, `NO_RESTORE_POINT`; with a release that has dropped the restored format, `FORMAT_UNSUPPORTED`; while a run may be live, refused |
| **U01-Q10** | A move is explicit (`U01-07.a`, `U01-07.b`) | a store copied to another installation refuses writes, the migration and the restore; adopting the move keeps the old installation's live values as history, and no run reads as live; a store that records no installation records one only through the operator's confirmed plan. Open until IF-13's installation identity is built |
| **U01-Q11** | Nothing bound to a host moves (`U01-07.b` to `U01-07.d`) | after a move, the new installation holds no copy of G3's state, a capability payload, an approval record, a G4 record, a restore point or a credential from the old one, and the old Lead secret is refused; the adoption is refused while a run may be live |
| **U01-Q12** | Offline (`U01-02.c`) | a migration from every declared format succeeds with the network unshared |
| **U01-Q13** | The surface (`U01-08`) | each local command is refused on the Lead broker's and a worker's surface, has its surface-map entry, and runs with no Lead credential |
| **U01-Q14** | The restore point's place (`U01-06.e`) | the place is outside every contained context's writable binds and every working tree, checked as `CAPR-04`'s place is |
| **U01-Q15** | A write keeps its format (`U01-02.d`, `U01-04`) | after a newer release's ordinary write, the previous release still reads the store |

## Scenarios

**U01-X01.** Given an approved offline profile and a supported upgrade, the operator installs the new release with no network, plans and confirms the migration, and every accepted record reads as before (`AS-24`, `U01-02.c`).

**U01-X02.** Given a store from before this position whose migration imports work items with duplicate labels and missing source digests, after the migration both limits stay explicit, and no item gains acceptance (`WIS-X23`, `U01-05.f`).

**U01-X03.** Given an old Ticket with unbound test logs, after the migration they are still unbound, never AEV-qualified PASS records, and nothing gains an execution guarantee (`WIS-08.d`, `U01-05.f`).

**U01-X04.** Given a newer release installed over a project, the store is unchanged. If the release reads and writes the project's format, the Lead launches once the release's qualification passes, its ordinary writes keep that format, and a write that needs its own format is `MIGRATION_REQUIRED`. If it only migrates from the project's format, the Lead's launch is refused with `MIGRATION_REQUIRED` and the plan's command (`U01-04`).

**U01-X05.** Given a Lead session that runs the migration, it is refused, and the refusal tells it to ask the operator (`U01-05.a`).

**U01-X06.** Given a migration interrupted at each fault point, the next open finds exactly one format current, and nothing written by the unfinished migration is read (`U01-05.d`).

**U01-X07.** Given a migrated store and the previous release, the previous release refuses it as `FORMAT_NOT_READ`, naming the release that migrated, or, if it predates this position, with its own refusal by schema, never as damage; it reads nothing (`U01-03`, `U01-00.a`).

**U01-X08.** Given a store from before this position, migrated by the first release built to this position, with no later commit, a restore makes the old format current, and `main` reads every record as before, the restore's record included. The migration can then run again (`U01-06`, `U01-06.d`, `U01-05.e`).

**U01-X09.** Given a migrated store with two later commits, a restore is refused as `COMMITTED_SINCE`, listing both, and its next step is the release that migrated (`U01-06.c`).

**U01-X10.** Given a damaged control file, every reader refuses it as `INTEGRITY_ERROR`, and the outage reader answers `unavailable`. Given a damaged transition log beside an intact control file, a status read answers, a history read and the launch are refused, and the outage reader answers the items with the history `partial` (`U01-03.c`, `U01-03.d`).

**U01-X11.** Given a release that no longer migrates from a store's format, however old, the store is refused as `FORMAT_UNSUPPORTED`, naming the last release that does (`U01-02.b`).

**U01-X12.** Given a project copied to another installation with a custody worker recorded live on the old one, a write is refused as `INSTALLATION_CHANGED`. After the operator adopts the move, the worker shows as the old installation's history, its run is never live, the old Lead secret is refused, the operator's Lead credential and G3 are set up afresh, and a restore of a migration made on the old installation is `NO_RESTORE_POINT` (`U01-07`, `U01-06.e`).

**U01-X13.** Given a store from before this position, opened on its own host by the first release built to this position, reads continue, a write and the launch are `MIGRATION_REQUIRED` (never `INSTALLATION_CHANGED`), and the store records no installation until the operator confirms the migration's plan, which names this one (`U01-07.a`, `U01-04`).

**U01-X14.** Given a restore point changed after its migration, by a contained context or anything else, the operator's restore is refused as `NO_RESTORE_POINT`, and the store stays as it is (`U01-06.b`, `U01-06.e`).

**U01-X15.** Given a newer release installed over a project in a format it reads, after its ordinary writes the operator rolls back before any migration, and the previous release reads the store (`U01-02.d`, `U01-06`).

**U01-X16.** Given a newer release whose log format moves the log to a new name, the previous release refuses the store as `FORMAT_NOT_READ`, naming the newer release, and never as damage (`U01-00.a`).

**U01-X17.** Given that newer release's migration restored, with nothing committed since, the moved log stays on disk unlisted, and the previous release reads the store (`U01-00.a`, `U01-06.d`).

**U01-X18.** Given a migration's restore point and a later release that has dropped the format it holds, the restore is refused as `FORMAT_UNSUPPORTED`, naming the last release that can make it (`U01-06`).

## Rulings

**U01-R01.** The scope is what the adopted text leaves open. Harness upgrades are the operator's decision of 2026-10-24; the install, the bundle and doctor's rows are the register's hold group 17 and E99; run recovery is `HEB-08.a`'s; outage reads are A-45's. Of the recovery and repair A-45 leaves to U-01 and the store's writers, U-01 takes the refusals and the restore point. A repair of a damaged store with no copy is the store's writers' (`U01-B7`).

**U01-R02.** No O-01 type. The upgrade is the host's install and the migration a local operator command, which is `I6-09`'s shape for the move and A-32's "host/current grant" for `UPGRADE_OR_ROLLBACK_AEW`. A site-requested migration would give the site a new reach over the store's format, for an act not easily reverted, and is not proposed.
- **At adoption,** A-32's two rows leave its Deferred class:
  - `U10` (`UPGRADE_OR_ROLLBACK_AEW`) for NO_COMMAND, as `L10`'s install did: the host's install and the operator's
    local commands (`U01-08`);
  - `P11` (`CHANGE_HOST_INSTALLATION`) for SERVED, as `C10` is: `REQUEST_PROFILE_CHANGE` at the new installation
    (`I6-09`), then the operator's adoption of the move (`U01-07.b`).
- **The counts** become 4 NO_COMMAND, 3 SERVED and 5 Deferred.
- **The origin:** both rows keep their proposed origin, as `W13`'s does. A local command's origin is the operator by
  where it runs (`U01-08`).

**U01-R03.** An unread format is not read as history either. An engine that does not know a format cannot keep its meaning (`AEW-FR-35.a`), so any reading of it, as history too, risks a wrong one. `AEW-FR-35.b`'s own witness is a reading as current, which `U01-03` forbids as well. The operator's file viewer remains.

**U01-R04.** A restore point, not down-migrations. Additive migration makes a restore cheap, since what it leaves is unreferenced and benign (ADR-0011). A tested reverse for every format step would rebuild what archiving moved.

**U01-R05.** Git is not the restore point. AEW's own commits exclude `.aew`, so the store is in git only where the operator commits it.

**U01-R06.** No credential moves. `I6-B2` lists "credentials" among what a move carries. At `main` the store holds only verifiers, G3's key may never be copied, and secrets stay out of general artifacts. So each credential is established again on the new installation, after the old seat ends (`U01-07.b`). This narrows `I6-B2`, and edits no adopted text.

**U01-R07.** AEW's install and bootstrap design v0.3, adopted in AEW on 2026-10-05 before the rebaseline, is now an input to the register's hold group 17. This position takes its upgrade rules as its own: the upgrade and the migration are separate, nothing migrates silently, a migration is planned with its restore point, and rollback before a migration is the previous release. Its bundle, signature, doctor rows and install sequence stay with hold group 17 and E99.

**U01-R08.** The store's `spec_set` stays a label. It is written once at init and compared by nothing, and it is not a format marker, so this position gives it no meaning.

**U01-R09.** Recording the writer is a Candidate, not a rule. The outcome is a refusal that can name the release needed (`U01-03.b`). The integrity check and the format marker tell damage from a format not read because the envelope is fixed (`U01-00.a`); the writer only says which release to run. Its place is the envelope, so a release that cannot read a body still reads it.

**U01-R10.** An older format the release reads keeps working within that format, written exactly as that format is (`U01-02.d`). At `main` this does not hold: the v2 schema grows by addition, and every commit writes the outbox keys into a v1 file too (`src/aew/engine/store.py:573-586`), so `main` does not meet `U01-04`. The first release built to this position migrates from `main`'s formats rather than writing them, which also gives each store its installation (`U01-07.a`). From then on, a release that adds a key takes a new value.

**U01-R11.** A format is a marker's value (`U01-02.d`), not a body revision under a marker. The value is the one thing every release compares at load, so the declaration needs no body field, and ADR-0012 D10 already names the option. The cost to the operator: every release that writes what the previous release's schema does not admit, or changes what a value means, is one plan and one confirmation at their terminal, which is what makes a rollback before a migration safe. A release that only writes what that schema already admits, with the same meaning, needs none.

**U01-R12.** A store from before this position gets its installation from its first migration under this position, not from its first write, and is not refused as a move. A first write would adopt a copy silently (`IF13-17`), and refusing every write as a move would refuse every project on its own host. The migration is one the operator makes anyway (`U01-R10`), and its plan names the installation.

**U01-R13.** Both a place and a digest for the restore point. The place keeps every contained context from writing it (`U01-06.e`). The digest binds the point to the store's own record of its migration, which no contained context can write either, so a point changed by any route, damage included, is refused (`U01-06.b`).

## Backlog

**U01-B1.** The site's view of a store it cannot open: the site's own, from the producer's refusal.

**U01-B2.** IF-13's installation identity, which `U01-07.a` records and compares. Until it is built, a release records a stand-in (`U01-07.e`), a move is detected only as far as the stand-in tells installations apart, and `U01-Q10` stays open.

**U01-B3.** A site-requested migration: an O-01 type, if the operator ever wants one.

**U01-B4.** An automated migration or restore, once A-05's parameter row for automated recovery is adopted.

**U01-B5.** An export and import package, if a project must ever move without its repository.

**U01-B6.** How long a restore point is kept, beyond the operator's removal (`U01-06.e`): a retention value, with its source.

**U01-B7.** A repair of a damaged store that has no copy and no restore point, such as rebuilding the control state from the transition log and the pinned records: the store's writers', with its own contract. Until then `INTEGRITY_ERROR` says that no repair exists.

**U01-B8.** What the first release built to this position changes at `main`. All five are that release's build items:
- **the control schema** stops growing by addition, and every write records its installation, through a migration
  from `main`'s formats (`U01-02.d`, `U01-R10`);
- **the installation** is recorded as a stand-in until IF-13's identity is built (`U01-07.e`, `U01-B2`);
- **the control file's envelope** gains the installation, the file list and the writer inside what `main`'s checksum
  covers, with the trailer kept last, so `main` refuses a migrated store by its schema (`U01-00.a`);
- **the transition log's genesis** becomes part of its envelope (`U01-00.a`);
- **`aew migrate`** stops taking the Lead credential (`U01-08`).

## Not covered

- **Harness upgrades:** the operator's decision of 2026-10-24, under `HEB-03.o` and `HEB-10.e`.
- **The install, the bundle and doctor's rows:** the register's hold group 17 (F18.3, D2) and E99, at Internal alpha.
- **Qualifying the new release or the new host:** S-01 and IF-13 (`S01-22`, `S01-03`, `I6-09`). This position only
  waits for it (`U01-04`, `U01-06`).
- **Run recovery after session loss:** A-06 (`HEB-08.a`).
- **Repair of a damaged store** beyond its refusal and a restore point: the store's writers' (`U01-B7`).
- **Per-host state's formats:** the capability register's are A-38's (`CAPR-04`), and G3's are its own install's
  (`G3-14`). They are outside every project, so a project's migration never changes them.
- **Outage reads:** A-45, with this position's one addition (`U01-03.d`).
- **The site's rendering.**

## Changes

- Revision 1 (2026-10-29): the first text, from `inputs/fact-map-2026-10-29.md` and
  `inputs/design-comparison-2026-10-29.md`.
- Revision 2 (2026-10-29): the answers to round 1 (`reviews/2026-10-29-U01-review-round-1.md`), each mapped in
  `CHANGES-r2.md`.
  - **New:** `U01-00.a` (the envelope), `U01-02.d` (a format is a marker's value), `U01-03.d` (the outage reader per
    file), the envelope table, gate rows `U01-Q14` and `U01-Q15`, scenarios `U01-X13` to `U01-X16`, rulings `U01-R11`
    to `U01-R13`, and backlog `U01-B7` and `U01-B8`.
  - **Rewritten:** the status line (one addition to A-45's `O02-07.a`), `U01-00`, `U01-02.b`, `U01-03.a`, `U01-03.b`'s
    Candidate, `U01-03.c`, `U01-04`, `U01-05.c` (the plan binds its release; no reversible exemption), `U01-05.e`,
    `U01-05.f`, `U01-05.g`, `U01-06`, `U01-06.a` to `U01-06.c`, `U01-06.e` (host state), `U01-07.a` (the installation
    recorded), `U01-07.b` (the old seat ends), `U01-07.c`, `U01-07.d`, `U01-07.e`, `U01-08`, the refusals' next steps,
    the plan, the gate, `U01-X02` to `U01-X04` and `U01-X07` to `U01-X12`, and rulings `U01-R01` to `U01-R03`,
    `U01-R06`, `U01-R07`, `U01-R09` and `U01-R10`.
- Revision 3 (2026-10-29): the answers to the quick check (`reviews/2026-10-29-U01-check-revision-2.md`), each mapped
  in `CHANGES-r3.md`, applied with no further check on the operator's decision
  (`00-governance/decisions/2026-10-29-operator-U01-r3-no-further-check.md`).
  - **New:** scenarios `U01-X17` and `U01-X18`.
  - **Rewritten:** `U01-00.a` (what a release judges; a moved file's old copy; the control file's envelope fixed),
    `U01-02.d` (what a change is), `U01-04`'s second and third bullets, `U01-05.e` (the clean start's scope), `U01-06`'s
    second bullet (who restores), `U01-06.d` (the restore's own record), `U01-07.a`, `U01-07.e` (the stand-in),
    `U01-08` (what admits the local commands), the envelope table, the `FORMAT_UNSUPPORTED` row, the plan, gate rows
    `U01-Q01`, `U01-Q08`, `U01-Q09`, `U01-Q11` and `U01-Q13`, `U01-X07` and `U01-X08`, `U01-R02` (`P11` is SERVED),
    `U01-R11`, and backlog `U01-B2` and `U01-B8`.
