<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-54
source: 30-stages/STG-29-AEW-SPT-boundary/adopted/spb-r6.1/SPB-POSITION.md
source-sha256: 114216fa87504d7f52dc02842d4756b6efc7e4b116c3487514fcb11f19c4d8a5
edits-sha256: cf4f12ad07a95522deeaa0575f876e8569ce01795849056967c5aee2d26240a6
-->

# SPB: the AEW–SPT boundary (PROPOSED, revision 6.1)

**Namespace:** `SPB-`
**Status:** proposed.
- **What it answers:** where A-38's capability register ends and SPT begins:
  - the end state;
  - what crosses the line;
  - the shape and the container bound of an agent's use of an SPT image;
  - who builds what;
  - the base;
  - the transfer, and the data that travels apart;
  - the line between AEW as SPT's consumer and AEW as a product working on SPT.
- **How it amends:** by addition to A-38, except for four changes, each the operator's (`SPB-R01`). Three are to `CAPR-R02`, and one is to `CAPR-07` and `CAPR-04`:
  - what AEW needs goes to SPT as requirements, not feedback (`SPB-04`);
  - the operator may override files in an SPT image inside the air gap, an exception to "never patches" (`SPB-09`);
  - the operator may import an image rebuilt inside the air gap as an operator's record, an exception to "through SPT's own bundles", and for an MCP image to `CAPR-11`'s "comes from SPT" (`SPB-09`);
  - a mounted payload (`SPB-10`) is bound read-only only into the containers of the records that name it, beside the staged inputs. This is an addition to `CAPR-07`'s confined container, and an exception to `CAPR-04`'s bind into every contained context.
- **What it leaves:**
  - SPT's own modernization, and when the operator selects it;
  - the register's build;
  - E99's transfer manifest;
  - any change to ADR-0014.

**Authority:** the operator's request and four answers (`00-governance/decisions/2026-11-01-operator-start-STG-29-AEW-SPT-boundary.md`), building on A-38. The other operator records it rests on:
- the reason for a Rocky 8 base (`00-governance/decisions/2026-11-01-operator-SPT-images-maintainable-inside-the-air-gap.md`);
- the transfer fact (`00-governance/decisions/2026-11-01-operator-transfers-cheap-except-AV-sensitive-data.md`);
- the answers on the air-gap kit (`00-governance/decisions/2026-11-01-operator-airgap-kit-conda-forge-and-licences.md`);
- the container tools (`00-governance/decisions/2026-11-01-operator-podman-and-buildah-for-SPT-images.md`);
- the transfer compression (`00-governance/decisions/2026-11-01-operator-SPT-image-transfer-compression.md`);
- rootless containers, and the gate's whole-clause registry (`00-governance/decisions/2026-11-01-operator-SPT-containers-rootless-and-whole-clause-gate.md`).

**Threat model:** the operator's G3 threat model (`00-governance/decisions/2026-10-19-operator-G3-threat-model.md`), under the security depth reset (`00-governance/decisions/2026-10-24-operator-security-depth-reset.md`).
**Research consulted:** `tools/research_index.py lookup`, 2026-11-01:
- SPT, `CAPR-R02`, `CAPR-11`, "air-gap" and "container" returned none;
- A-38 returned the airgap capability research of 2026-10-01, its selection input;
- the designer's read-only research of 2026-11-01 is `BASE-AND-GLIBC-FACTS.md`.

**Files:**
- this file;
- its gate, `check_spb.py`, a derivation check with no model;
- `SPT-FACTS.md`, the read of SPT at `3bf796b` this position rests on;
- `BASE-AND-GLIBC-FACTS.md`, the facts outside SPT about the Rocky 8 base image and glibc floors.

## What the adopted text already decides

- **SPT is a store, and AEW its consumer** (`CAPR-R02`, the operator's decision of 2026-10-24):
  - SPT holds images AEW does not use, and the MCP server images AEW imports;
  - SPT's images are payloads, pinned by digest in the operator's records and imported through SPT's own bundles;
  - AEW never builds, forks or patches SPT;
  - what AEW needs goes to SPT's repository as feedback, carrying the register's validation evidence, which the operator signs off;
  - SPT's tool-result, job-report and artifact-manifest schemas are its providers' evidence format.
- **Every MCP server image AEW imports comes from SPT** (`CAPR-11`), validated at import and at every check. Its absence degrades gracefully (`CAPR-12`).
- **Outside the sandbox there are two routes, and only two** (`CAPR-07`):
  - a host-placed provider exposes typed operations only, takes only staged inputs, and treats their content as data (`AEV-05.d`);
  - a tool that cannot run that way runs confined, with no more than its caller's authority: for a container, one holding only the staged inputs, with no network, credential or host path.
- **A container-backed provider refuses a command it does not type,** and no container starts (`CAPR-X04`).
- **A container runtime never reaches an agent** (`CAPR-08`). Every container-backed provider is host-placed, so a role needs a grant for it (`CAPR-06`).
- **AEW's own bundle** is sandbox-placed CLI tools, pinned (`CAPR-04`, `CAPR-R03`).
- **Changes to what runs outside every sandbox are protected** (`CAPR-13`). Work stays at work: SPT is public, so nothing work-only crosses into it (`CAPR-10`, `S01-26`).
- **A provider's output is evidence of at most its stated kind** (`CAPR-09`, `AEV-05.a`, `AEV-05.c`).

## The parts

| Part | What it is | Who writes it | Who reads it |
|---|---|---|---|
| The register | A-38's provider records, grants and statuses | the operator, through AEW's commands | AEW's host code, the site, agents through their catalogs |
| AEW's sandbox bundle | the first bundle and later sandbox providers (`CAPR-04`); STG-15's `BASE` and `REG` layers | a reviewed AEW release, or the operator's records | agents, in their sandbox |
| An SPT image | a container image in SPT's bundle, pinned by digest in the operator's records | SPT's release | the register, as a payload (`CAPR-R02`) |
| A mounted payload | an entry a provider's record names, of a kind `SPB-10` lists | the data transfer, the routine transfer, or the operator | the image's containers, read-only |
| A provider's output | the evidence a job writes, and a code index, copied out after the job exits (`SPB-02`) | the provider's container | the register, and the same context's service, which gets the index copied in |
| A requirement | what AEW needs from an SPT image, with its acceptance test | AEW as a product working on SPT, or the operator; signed off by the operator | SPT's maintainers |
| The transfer | what crosses the air gap: the routine transfer and the data transfer | AEW's release, SPT's release, and the data refresh on the connected side | the operator, then the register's import |

## Rules

**SPB-00. The end state.** AEW reaches SPT only through the register, as SPT's primary consumer, and SPT is a supplier that builds to AEW's requirements. Every tool has one owner, by its use:
- **AEW's sandbox bundle:** the tools an agent runs on its own work, with its own authority (`CAPR-04`);
- **SPT's host-placed providers:** heavy, long-running or container-only work, reached through typed operations, with evidence in SPT's schemas (`CAPR-07`, `CAPR-08`);
- **the project's environment:** the toolchain a project builds and tests with (STG-15's `PROJ` layer).

A tool may sit in two tiers for two uses: gdb in the sandbox for an agent's own debugging, and SPT's crash-triage image for a triage job. Each use is its own provider, with its own capability ID (`SPB-03`).

**SPB-01. What crosses the line, and nothing else.**
- **Into AEW, per SPT image:**
  - its digest, in the operator's records (`CAPR-R02`);
  - the capability IDs it serves, with each operation's typed form;
  - its evidence, in SPT's tool-result, job-report or artifact-manifest schema (`CAPR-R02`). Which an image writes is `SPT-FACTS.md`'s to say, and `SPB-03`'s table derives from it. A typed MCP service writes none of them while serving: its evidence is each operation's typed response, which the register records at no more than its stated kind (`CAPR-09`).
- **Into SPT:** requirements, each with its acceptance test (`SPB-04`).
- **Never:**
  - AEW imports no SPT code or library, and reads no SPT internals;
  - SPT reads no AEW register, record or state;
  - a requirement names classes of system, never an internal one (`CAPR-10`).

**SPB-02. Every call into an SPT image is a typed operation, in one of three shapes, inside one container bound.**
- **Typed, always, for every shape:**
  - each operation has its argument schema in the provider's record (`CAPR-02`);
  - the record lists every operation the provider exposes, and the register calls no other;
  - a call that names no typed operation is refused, and no container starts (`CAPR-X04`);
  - no operation passes an argument vector through;
  - every setting of the image that would run code, load anything not in its mounted payloads, alter its inputs, or pass arguments through is off, empty or bound to its inputs, and pinned in the record.
- **What a container holds, for every shape** (`CAPR-07`'s confined branch, with `SPB-R01`'s fourth change):
  - AEW stages the inputs the calling context can already read, as a copy under the copy rule below, into a fresh register-owned directory outside every sandbox's writable binds. Staging leaves out the paths the record lists as the image's own prior output; for `spt-gitnexus` that is `.gitnexus/`;
  - staging reads only the context's view, from a list. Its roots are the calling context's own project, workspace and scratch directory, as that launch's recorded layout names them. Any other named path is left out and named. Inside a root, the deepest recorded entry decides:
    - what the launch hid or masked is left out and named. Under a mask, only a root stays in: a project, workspace or scratch directory bound back there is in, and anything else bound back there, such as the run's harness directories, is left out and named;
    - a mask in a tree the run writes is also matched by what it is. The launch records its device and inode, and staging leaves out and names anything whose identity, taken on what it opened, matches one, at any path. It does not walk into such a directory;
    - in a directory the launch left a secret out of, only what the launch put back is in. An entry made there since is outside the view;
  - staging refuses with no recorded layout, or one that lacks its roots, an in-tree mask's identity, or what it put back. It refuses, with its cause, when every named input is left out, or the stage holds no file;
  - the register's directory is the read-only bind's source, never the context's own tree, and an input's digest is taken over it;
  - the staged inputs and the provider's mounted payloads (`SPB-10`) are the container's only host paths, all read-only. A bind's label relabels only the register's staged copy (`:ro,Z`) or a mounted payload (`:ro,z`), never a context's own tree;
  - the runtime's own per-container mounts, the bound's measured list below, are not host paths in `CAPR-07`'s sense. They are kernel filesystems, or the runtime's own files in the container's directory under its store or run root, and hold nothing of a context's, the operator's or the register's;
  - what the register binds is readable by the image's user: directories `0555` and files `0444`, keeping the execute bit, inside a parent closed to others;
  - where an image writes into its inputs, or needs a derived input, the register copies those inputs into the container before it starts. The copy is the container's own, and no host path. An input the image writes into is owned by, and writable by, the image's user, as the output directory is. An index is a staged input of the same context, derived only by that context's own job;
  - before a job starts, the register also copies in a fresh, empty output directory under a new name, which the copy gives to the image's user, and the record's variable names it to the image. So the image can write with no host path. A copy into a directory the image already has leaves that directory's owner unchanged (measured, `PODMAN-CAPTURE.md`). That needs no change to SPT's images. The image's own ownership of its output directory is a requirement on SPT (`SPB-04`).
- **Every copy across a trust boundary** (staging, a copy in, a copy out, and delivery):
  - admits regular files and directories only, within caps the record states on bytes, entries and depth;
  - leaves out, and names in the evidence, anything else: a link, a device node, a FIFO, a socket, a setuid or setgid bit, an absolute or climbing name, or a name holding a control character. The copy goes on; only a cap stops it;
  - is read and written by the register one path component at a time, without following links: each open is relative to its parent, refuses a link, and checks the type on what it opened. An `lstat` followed by an open by path does not meet this;
  - lands only in a directory the register creates exclusively, and it refuses if the name exists.
- **A typed job:**
  - `CAPR-07`'s confined branch, because the job runs or reads the staged target;
  - the job writes only inside its own container. SPT's `/artifacts` is a path inside the container;
  - after it exits, the register copies its output into a fresh, empty directory created for that job alone. The directory is register-owned host state outside every sandbox's writable binds, beside the `HOST`-set store and not inside it (`SPB-05`);
  - nothing else is kept in that directory: no record, grant, status, or other job's output. The register reads the job's evidence (in `SPB-01`'s schemas) and any index only from the named job's directory;
  - the register delivers results to the calling context by copying them into a fresh directory it creates there, under the same copy rule. It writes nothing else into the context.

  This is the shape for SPT's analysis work: a fuzzing campaign, crash triage, a binary export, symbolic execution, a scan, a code index.
- **A typed MCP service:**
  - a host-placed MCP provider whose image SPT supplies (`CAPR-11`), exposing typed operations only;
  - it runs in `CAPR-07`'s confined branch too, and speaks MCP to the register over standard input and output;
  - one instance per calling context, so no state crosses between contexts, and the record states a size cap on each response.
  - **For SPT's Ghidra MCP image:**
    - the service is `bridge` over standard input and output, calling a headless Ghidra server in the same container on the container's own loopback, never the default `smoke`, which serves nothing;
    - on that server, script execution (`GHIDRA_MCP_ALLOW_SCRIPTS`) is off, and the file root (`GHIDRA_MCP_FILE_ROOT`) is the staged inputs.

    SPT's image runs either the bridge or the server, not both, so the pair in one container is a requirement on SPT (`SPB-04`).
  - **For SPT's GitNexus image:**
    - its mode is `GITNEXUS_MODE=mcp`. The default `version` serves nothing, and `serve` is a web interface;
    - its index is the output of this calling context's own run of `RELATIONSHIP_INDEX_JOB`, a typed job of the same image (`SPB-03`), and that run's job report must show success. The register copies the staged inputs and that index into the service's container before it starts;
    - the index job runs `analyze` on the register's copy of the staged inputs, with `GITNEXUS_FIXTURE_REPO=0` and `GITNEXUS_OFFLINE=1` pinned and its argument settings empty;
    - before it launches the service, the register checks that the index and the required LadybugDB extensions payload (`SPB-10`) are present. With either absent, it refuses, with the cause "no index" or "no data set".

    These checks are the register's, not the image's. SPT's wrapper checks the extensions only in its `analyze` mode, and copies out any `.gitnexus` folder it finds whether or not `analyze` succeeded.
- **A typed toolbox run:**
  - an image built for tools an agent reaches for mid-task;
  - each tool it carries is one or more typed operations;
  - each call runs as a typed job does, `CAPR-07`'s confined branch;
  - it is container-backed, so it is host-placed and granted per role like the others (`CAPR-06`).
- **What its evidence is worth:**
  - every operation of a container-backed provider records its evidence at no more than the agent's submission (`AEV-05.c`, `AEV-05.g`, `CAPR-09`);
  - the operator's record may lift that cap for one operation, with a reason, as a protected change (`CAPR-13`);
  - a lift is keyed to the capability ID, the operation and the image's digest. It lapses when the digest changes, when an override is placed, or when the image is rebuilt inside;
  - the register holds a list of IDs whose operations can never be lifted. Each executes staged content, loads code from it, honours it as configuration, or copies it into its output: `FUZZING_JOB`, `CRASH_TRIAGE_JOB`, `SYMBOLIC_EXECUTION_JOB`, `SAST_SCAN_JOB`, `RELATIONSHIP_INDEX_JOB`, `RELATIONSHIP_DISCOVERY` and `BINARY_ANALYSIS`;
  - a new ID joins that list unless this position names it liftable;
  - today no ID is liftable. `YARA_SCAN_JOB` and `BINARY_EXPORT_JOB` copy staged file names unescaped into their evidence at `3bf796b`. Each becomes liftable only when an `SPB-04` requirement for structured evidence with escaped names passes a hostile-name acceptance case;
  - a capped finding counts as more than a claim only when confirmed by an observation the executed content cannot set. A numeric exit code, a clean exit, or a rerun of a capped operation never confirms;
  - the observation that would confirm is the signal that ended a replay of artifact digest D, on input digest I, running as the container's only process, as the runtime's wait status reports it to the register. Measured on podman 4.9.4 under `tini`, SPT's entrypoint: a child's signal death and a plain exit with the same number give the same state and the same event. A signal death of the container's first process itself is not measured. So nothing confirms, and a finding stays a claim. A replay that confirms is a future requirement (`SPB-B6`).
- **The container bound, for every shape** (rootless, the operator's decision of 2026-11-01). Podman's own defaults are not the bound. The register starts every container with one fixed set of options:
  - rootless, under the operator's user, in the operator's rootless user namespace;
  - its own process, IPC, UTS, mount and cgroup namespaces (`--cgroupns=private`, which holds on Rocky 8's default cgroups v1);
  - no network (`--network=none`, which leaves only the container's own loopback): no slirp4netns, and no proxy variables (`--http-proxy=false`);
  - no volume from the image (`--image-volume=ignore`), so an image's `VOLUME` adds no host path;
  - a pinned `--hostname`, and no generated hosts file (`--no-hosts`);
  - an environment that is exactly one list: the variables the record names, the image's `ENV` at its pinned digest, and the runtime's own additions, `container`, `HOSTNAME` and `HOME` (measured, `PODMAN-CAPTURE.md`). A record's variable wins over the image's of the same name;
  - no new privileges (`--security-opt=no-new-privileges`);
  - the default SELinux label, and the default masked and read-only paths;
  - no added kernel capability, and the runtime's default seccomp profile;
  - no host device beyond the runtime's standard `null`, `zero`, `full`, `random`, `urandom` and `tty` nodes, and never `--privileged`;
  - a `--timeout` and `--ulimit` values the record states;
  - only the read-only binds this rule names, and the runtime's own per-container mounts, measured on stock Rocky 8 as a list (`PODMAN-CAPTURE.md`):
    - its kernel filesystems: `/proc`, `/dev`, `/dev/pts`, `/dev/mqueue`, `/sys` and `/sys/fs/cgroup`;
    - `/dev/shm`, `/run/.containerenv` and `/etc/hostname`;
    - each entry is matched by destination, kind and source: a kernel filesystem by its type, the rest from the container's own directory under the store or run root. Any mount not on the list, or from another source, is refused. `--no-hosts` removes `/etc/hosts`, and `--network=none` generates no `/etc/resolv.conf`;
    - the list is the register's, and adding an entry is a change to this position, which the operator adopts.

  **Podman's own configuration is the register's too:**
  - `CONTAINERS_CONF` and `CONTAINERS_STORAGE_CONF` are set to register-known files;
  - `CONTAINERS_CONF_OVERRIDE`, `CONTAINER_HOST` and `CONTAINER_CONNECTION` are unset;
  - the mounts file is empty (`--default-mounts-file`: the key in `containers.conf` was not honoured, measured), and there is no hooks directory;
  - there are no additional image stores until `SPB-B7` rules on them.

  **Before it starts the container,** the register compares what would run with this set, plus the closed list's deltas, and refuses to start on any difference. It compares:
  - the rootless flag;
  - network, namespaces and ID mappings;
  - the image and its digest;
  - the command, user and label;
  - capabilities and environment;
  - in the runtime's generated spec: mounts, devices, hooks, masked and read-only paths, seccomp and no-new-privileges.

  The exact field names are in `PODMAN-CAPTURE.md`.

  **A relaxation comes only from a closed list** that the register's schema holds:
  - today the list has one entry: `--cap-add=SYS_PTRACE`, with the rest of the fixed set unchanged. In the container's own process namespace, it reaches only the container's own processes;
  - the register's validation refuses any relaxation not on the list;
  - adding an entry is a change to this position, which the operator adopts;
  - a relaxation from the list is stated in its requirement (`SPB-04`) and carried as a field of its record. Placing or changing it is a protected change (`CAPR-13`).

  **A host setting** is a `HOST` prerequisite the operator sets and doctor reports, never a container privilege. The host settings are the operator's subordinate user and group ranges, the image store's location (`SPB-05`), rr's `perf_event_paranoid` and AFL++'s `core_pattern`. Work that needs more than the bound and the list is not a job.
- **There is no fourth shape.** No interactive shell into a container, and no container runtime reachable from an agent (`CAPR-08`).

**SPB-03. One capability ID is sandbox-served or host-served, never both.**
- **The reason:** a sandbox provider is on every role's catalog (`CAPR-06`). If it served a host-placed ID, that ID's grant would protect nothing.
- **Where it is enforced:** the register's validation refuses a record that would serve an ID already served at the other placement, saying which record holds it (`CAPR-13`'s "validated before it takes effect"). That check is new validation code.
- **The form:**
  - a typed job's IDs end in `_JOB`;
  - a typed toolbox's IDs end in `_CONFINED`;
  - a typed MCP service's IDs name the service;
  - no sandbox ID ends in `_JOB` or `_CONFINED`.
- **The IDs below are proposals.** The register's records fix them. The evidence column is the one `SPT-FACTS.md` finds each image writing.

| SPT image | Shape | Capability IDs (proposed) | Evidence |
|---|---|---|---|
| `spt-fuzzing` | typed job | `FUZZING_JOB` | tool result, job report |
| `spt-crash-triage` | typed job | `CRASH_TRIAGE_JOB` | tool result, job report |
| `spt-symbolic` | typed job | `SYMBOLIC_EXECUTION_JOB` | tool result, job report |
| `spt-yara` | typed job | `YARA_SCAN_JOB` | tool result, job report |
| `spt-semgrep` | typed job | `SAST_SCAN_JOB` | tool result, job report |
| `spt-ghidra-exporter` | typed job | `BINARY_EXPORT_JOB` | tool result, job report |
| `spt-ghidra-mcp` | typed MCP service | `BINARY_ANALYSIS` | none while serving; tool result, job report in smoke mode |
| `spt-gitnexus` | typed MCP service | `RELATIONSHIP_DISCOVERY` | none while serving; tool result, job report in CLI modes |
| `spt-gitnexus` | typed job | `RELATIONSHIP_INDEX_JOB` | tool result, job report in CLI modes |

  - `BINARY_ANALYSIS` is the host-placed example `CAPR-X03` already names.
  - `spt-gitnexus` is used at work through SPT's image, as it is, by the operator's decision of 2026-11-01, which takes its licence risk (`SPB-R07`). One image serves two providers: the index job runs its `analyze` mode, and the service its `mcp` mode.
  - A row's evidence is `SPT-FACTS.md`'s for the image. A typed job of an image that also serves names the clause for its own mode.
  - `spt-codeql` runs only under the site's own entitlement, and the register lists no SPT image AEW does not use (`CAPR-R02`).

**SPB-04. What AEW needs from SPT is a requirement, with its acceptance test.** This amends `CAPR-R02`'s "feedback" (the operator, 2026-11-01). A requirement states:
- the capability ID and each operation's typed form (`SPB-02`, `SPB-03`);
- the evidence schemas it returns (`SPB-01`);
- its acceptance test:
  - the test ships in the image as a named entry point, and the requirement carries its specification;
  - it runs a health check, a fixture query, and a bounded smoke test of every operation AEW calls, each a fixture run of seconds, never a campaign;
  - it runs offline on a stock Rocky 8 host with the `HOST` container runtime (`SPB-05`);
  - it includes a case in which the operation's data set is absent, and the operation fails rather than succeeds (`SPB-10`);
- its runtime needs: any relaxation from `SPB-02`'s closed list, and any host setting, each named;
- an output directory the image's user owns, with an acceptance case that this user can write there;
- structured evidence with escaped names, with a hostile-name acceptance case;
- the maintainability items of `SPB-05` the image must meet;
- a signed image bundle, in the released form `SPB-07` names, whose signature covers the layout's index and each manifest, so that an upgrade carrying only some layers is still checked; SPT's image bundle carries a checksum only today;
- the register's validation evidence, where an earlier version failed, as `CAPR-R02` already asks.

**Who files it:** AEW as a product working on SPT (`SPB-08`), or the operator. The operator signs off what is filed, as `CAPR-R02` already says. AEW's running code never files anything.

**What AEW checks:** the operator's record names the image's acceptance entry point and its fixture inputs. The register runs it as the provider's health check, at import and at every check (`CAPR-11`). So what SPT built to and what AEW validates are one test.

**SPB-05. Every SPT image AEW imports, and every image in SPT's routine transfer, can be rebuilt and patched inside the air gap.** Two kinds are excepted:
- `SPB-06`'s interim images: before SPT's rebuild, and after it while a component waits on a source build;
- `spt-gitnexus`, which the operator takes as it is (`SPB-R07`).

The operator's reason: the site's packages, tooling and binaries are all Rocky 8 era, and an image from another family has no update path there. No Rocky 8 base image published upstream carries errata newer than 8.10's release, and 8.10 is the last minor release. Errata arrive only as packages (`BASE-AND-GLIBC-FACTS.md`).

**Each such image:**
- is built on SPT's derived Rocky 8 base, pinned by digest. That base is built from a pinned pair:
  - the upstream Rocky 8 base image's digest;
  - a dated state of Rocky 8's BaseOS and AppStream repositories, which SPT makes and carries.

  The base upgrades from that state with no network. An errata refresh is a new pair, and a new pin adopted as `SPB-07` says. The status shows the base's errata date;
- is layered:
  - the base;
  - then, where conda-forge is the source, a locked conda-forge layer meeting STG-15's conditions 1, 3, 5 and 6 (the operator's answer of 2026-11-01), and otherwise Rocky 8 packages or source builds;
  - then a thin layer of SPT's own code and configuration;
- refers to every base and builder stage by digest, from its shipped inputs. A data-only carrier image with no executable runtime need not be Rocky 8, but is pinned the same way;
- ships its build inputs in SPT's bundle:
  - the derived base's pinned pair;
  - any build frontend its build file needs;
  - its build file and its sources;
  - its slice of the conda-forge channel;
  - the Rocky 8 packages it needs;
  - the locked dependency closure of every language package a source build needs (npm, pip, Maven, Cargo, Gradle), each pinned by hash;
  - every other file the build downloads today, with its checksum;
- records the licence of each shipped input. An input whose licence restricts redistribution goes to the operator before it ships;
- rebuilds offline on a Rocky 8 builder from those inputs, with no other download. A rebuild is judged by outcome: it installs the same package set and passes the same acceptance test (`SPB-04`), whether or not its digest matches;
- bakes in no data that trips antivirus. Data sets are mounted (`SPB-10`).

**A component built only for a newer glibc than Rocky 8's** (`BASE-AND-GLIBC-FACTS.md`) is a requirement on SPT to build it from source on Rocky 8. Until that build passes its acceptance test, the image stays in `SPB-06`'s interim tier.

**The builder's tools:**
- the container runtime, the container build tool and the image copier are `HOST` prerequisites, which doctor reports, carried in the kit as Rocky 8 packages (STG-15's `HOST` rule): podman, buildah and skopeo, from Rocky 8's `container-tools:rhel8` stream (the operator's decision of 2026-11-01);
- the compilers a source build needs are the project-toolchain layer's (STG-15's `PROJ`);
- where the rootless image store lives is a `HOST` setting, which doctor reports. It is never the operator's home by default: the home is small (the operator's decision of 2026-11-01). It is set by `rootless_storage_path` in the register's storage file, since rootless podman ignores `graphroot` and `runroot` (measured), and the run root stays under the user's runtime directory;
- doctor tests the store's filesystem by what it can do: a `podman unshare` `chown` to a subordinate ID, read back, and a user-xattr write. One that fails is refused, whatever its device; a networked block device carrying a local filesystem may pass. Whether the operator's networked storage passes is measured, not assumed (`SPB-B7`);
- the store and its run root are never under any context's bind, and a launch refuses if they are;
- image bundles in transfer are ordinary files. They may live on any storage, networked storage included, and are imported from there.

**The conformance evidence:** a test build under buildah, offline, from the shipped inputs, of each image `SPB-04` names. It is owed by SPT's first-project work, or is a run the operator approves (`SPB-B6`).

**SPB-06. The base, and the order.**
- **Agent-facing images** (the typed toolbox, and every new job or service image) are built on SPT's derived Rocky 8 base (`SPB-05`).
- **The rebuild of SPT's images onto Rocky 8 is SPT's modernization.** It is AEW's first real project (the operator, 2026-10-25), and selecting it is the operator's, outside this position.
- **Until then,** SPT's current images are interim.
  - **Which:** the typed jobs, and the two MCP services, of `SPB-03`'s table.
  - **How they come in:** importable once the operator's record gives each a health check and a fixture query (`CAPR-11`), with `SPB-04`'s acceptance test owed.
  - **What they must still meet:** `SPB-02`'s typed calls and container bound.
  - **How they read:**
    - each record carries the field "maintainable inside: no", derived from its base not being Rocky 8;
    - the status shows that field beside it;
    - the register shows each as `FUNCTIONAL_ONLY` at best (`CAPR-03`).
  - **They get no new investment.**
- **After the rebuild,** an image whose component waits on a source build (`SPB-05`) stays interim. Its record also names:
  - the glibc floor and its source;
  - when to look again: an upstream release, or Rocky 8's end of life on 2029-05-31.

  `spt-gitnexus` stays interim (`SPB-R07`).

**SPB-07. One transfer for tools, in two signed parts; antivirus-sensitive data travels apart.**
- **The routine transfer** carries AEW's bundle and SPT's routine part under one transfer manifest. It is validated once, on stock Rocky 8.
  - **SPT's routine part** carries only images that bake in no antivirus-sensitive data. That is judged by property: a baked vulnerability database, or any data a `risk_flags` entry marks. Today's `spt-image-scanner` is excluded on that ground.
  - **Mounted payloads that are not antivirus-sensitive** ride the routine transfer, as do SPT's carried build inputs and repository states: acceptance fixtures, and GitNexus's LadybugDB extensions.
  - **A pre-carry check** verifies the routine transfer holds no antivirus-sensitive data, so "the quick kind" is checked, not asserted. An item that fails it moves to the data transfer. How an image moved that way is imported is `SPB-B3`'s.
  - **Signing:** each part is signed and released by its own product, so SPT's other users are not tied to AEW's releases. SPT's signed image bundle is a requirement (`SPB-04`).
- **How SPT's images travel** (the operator's decision of 2026-11-01):
  - as one deduplicated OCI layout, so layers shared between images are carried once;
  - zstd is the released form: SPT publishes images with zstd layers, the pin is that manifest's digest, and nothing recompresses between SPT's release and the import;
  - an upgrade carries only the layers the inside store lacks, each checked against the pinned digests at import;
  - pruning inside never removes a layer that a current pin references.
- **The data transfer** carries vulnerability databases, advisory feeds, signatures and such rule packs, as payload entries (`SPB-10`). It goes through the site's process, on its own and rarer cadence.
- **One pin-and-validate process:**
  - an SPT image's digest is in the operator's records (`CAPR-R02`);
  - a new digest is adopted by an operator command after validation, a protected change (`CAPR-13`);
  - an image that fails validation keeps the previous digest, and says why.
- **Where the manifest lives** is E99's design. Any change to ADR-0014 is the operator's.

**SPB-08. AEW as consumer, and AEW as a product working on SPT.**
- **As consumer** (`CAPR-R02`, kept apart from the operator's exceptions in `SPB-09`):
  - AEW's code imports, validates, registers and runs SPT's images;
  - it never builds, forks or patches them;
  - no AEW release waits on an SPT change, and no SPT release waits on AEW's.
- **As a product,** once the operator selects SPT as a project, AEW works on SPT's repository as on any project: its own Work, its own review, SPT's own release.
  - What it produces reaches AEW the consumer only as an SPT release, imported by digest like any other (`SPB-01`).
  - It never writes AEW's register, AEW's shipped records, or AEW's code on SPT's behalf.
- **The operator's inside fixes** are a separate path, the operator's own (`SPB-09`).

**SPB-09. A fix made inside the air gap is recorded, protected, and folded back.**
- **Routine transfers are cheap,** so a defect is normally fixed outside and carried in by the next transfer.
- **Where waiting costs more, the operator has two paths.** Both are the operator's exceptions to `CAPR-R02`, adopted with this position (`SPB-R01`). Neither applies to `spt-gitnexus` (`SPB-R07`).
  - **An override:**
    - the operator places override files for one SPT image, held as `SPB-10` holds every mounted payload;
    - placing, changing or removing an override is a protected change (`CAPR-13`);
    - the image's status shows the override, and every result's evidence names it.
  - **An inside rebuild:**
    - an image rebuilt inside the air gap (`SPB-05`) is imported as an operator's record, pinned by its own digest, a protected change (`CAPR-13`);
    - its status reads "rebuilt inside, not an SPT release" until an SPT release folds the fix in;
    - for an MCP image this is also the operator's exception to `CAPR-11`.
- **The return trip:** every fix made inside is recorded with what broke, its evidence and what changed, sanitized under `CAPR-10` and `S01-26`.
  - If data may leave, it goes to SPT as a requirement (`SPB-04`).
  - If nothing may leave, the record is what is redone outside.
  - The next SPT release folds the fix in, and the override or the inside rebuild is removed.

**SPB-10. What is mounted beside an SPT image is held like a payload, and its absence is honest.**
- **What it covers:** a mounted payload is an entry named in a provider record's mounted-payloads field.
- **Its kinds, and no others:** a data set (a rule pack, a vulnerability database, an advisory feed, signatures, or extensions), an override file, or an acceptance fixture. Validation refuses a record that names any other kind.
- **How `CAPR-04` reads it:** the bind into every contained context skips every entry a record names here. Several records of one image may name one entry.
- **Each entry:**
  - is held as a payload entry is (`CAPR-04`): host state outside every sandbox's writable binds. It is bound read-only only into the containers of the records that name it, never into any other context (`SPB-R01`);
  - is pinned by the hash of every file. A manifest that hashes nothing, such as SPT's `metadata-only` mode, is refused;
  - is hash-checked at each container launch, and a mismatch refuses that launch;
  - is named, with its identity and build date, in every result's evidence (`CAPR-09`).
- **Change class:** placing or replacing a mounted payload is a protected change (`CAPR-13`), since it changes what a host-placed provider honours.
- **When a data set is absent:** the capabilities that need it read `UNAVAILABLE`, with the cause "no data set" (`CAPR-03`). Their operations refuse, rather than report success. Today SPT's YARA job reports success with nothing found when it has no rules, so this is a requirement on SPT (`SPB-04`).
- **When a data set is old:** past its tool's documented age, the capability reads `FUNCTIONAL_ONLY`, with a limitation naming the data's build date. That is STG-15's offline-data rule.

## Interfaces

- **No O-01 or D-01 byte changes.**
- **A-38:**
  - `SPB-R01`'s four changes:
    - to `CAPR-R02`, three: requirements for feedback; the override; and the inside rebuild, which is also an exception to `CAPR-11` for MCP images;
    - to `CAPR-07` and `CAPR-04`, one: a mounted payload, bound only into the containers of the records that name it (`SPB-10`);
  - the register's records gain the capability IDs of `SPB-03` (no code change);
  - they also gain the fields that `SPB-02`, `SPB-04`, `SPB-05`, `SPB-06` and `SPB-10` name:
    - the list of operations, each with its argument schema, and any lift of the evidence cap with its reason;
    - any relaxation from the closed list, the environment list, the `--timeout` and the `--ulimit` values;
    - the acceptance entry point and fixtures;
    - the copy rule's caps, the staging exclusions, which inputs are copied in, and the service's response cap;
    - "maintainable inside", the glibc floor and when to look again;
    - the base's errata date;
    - the mounted payloads;
  - the register's validation gains `SPB-03`'s cross-placement check, `SPB-02`'s comparison of what would run with the fixed option set and the closed list, and `SPB-10`'s kind check (new code). Its launch gains `SPB-02`'s staging, read through the calling launch's recorded layout, which gains what that needs (its roots, each in-tree mask's identity, and what it put back), its copy-in and copy-out under the copy rule, and the service's presence checks;
  - nothing else in A-38 changes.
- **STG-15's air-gap placement:**
  - its `SPT` and `DATA` layers follow this position;
  - its proposed sandbox IDs keep to `SPB-03`'s form;
  - its `HOST` layer holds podman, buildah and skopeo, and the operator's subordinate user and group ranges for rootless containers; the kit carries the derived base's pinned pair. The inventory's rows are the designer's (`SPB-B5`).
- **E99:** the transfer manifest, the pre-carry check, the separate data transfer, and the one-layout image transfer (`SPB-07`).
- **SPT's repository:** requirements in `SPB-04`'s form, filed under `SPB-08`, once the operator selects SPT as a project.

## The gate

| Check | What it verifies | Read from | Covers |
|---|---|---|---|
| **SPB-Q01** | Every SPT image in `SPB-03`'s table names a shape `SPB-02` defines that its kind in `SPT-FACTS.md` allows (a job: a typed job; an MCP server: a typed MCP service; an MCP server or CLI: either); every shape's bullet says "typed"; each row has at least one capability ID; each service row's evidence equals the evidence `SPT-FACTS.md` finds for that image, and each job row's equals it or names its own mode's clause | `SPB-03`'s table; `SPB-02`; `SPT-FACTS.md` | every row and shape |
| **SPB-Q02** | The host-served IDs in `SPB-03`'s table and the sandbox-served IDs are disjoint. The sandbox set is `FIRST-BUNDLE.md`'s IDs and the leading ID of each `BASE` or `REG` note in STG-15's placement table, and must hold every `FIRST-BUNDLE.md` ID. A typed job's IDs end in `_JOB`, a toolbox's in `_CONFINED`, and no sandbox ID ends in either | `SPB-03`; `FIRST-BUNDLE.md`; `AIRGAP-KIT-TABLE.md` | every ID |
| **SPB-Q03** | Every SPT image named in `SPB-03`'s table is one `SPT-FACTS.md` finds in SPT at `3bf796b` | `SPB-03`; `SPT-FACTS.md` | every row |
| **SPB-Q04** | `SPB-04`'s acceptance test names its entry point, the bounded smoke, offline, and the data-absent case; its list names runtime needs and the signed bundle. `SPB-05`'s own list items name the derived base pinned by digest, the pinned pair, every base by digest, the build inputs, the dependency closure, the offline rebuild judged by outcome, and the antivirus exclusion | `SPB-04`; `SPB-05` | each item |
| **SPB-Q05** | Every `CAPR-` ID cited is defined in A-38's frozen copy | the whole file; `adopted/capr-r2.1/CAPR-POSITION.md` | every citation |
| **SPB-Q06** | The gate table lists every check `check_spb.py` runs, and no other | this table; `check_spb.py` | every row |
| **SPB-Q07** | Every non-blank line of the file, the title, tables, headings and change log included, is registered in order, with its section, its depth and its full text, in `check_spb_clauses.tsv`, and each row's hash matches its text. So any edit, insertion, deletion, move or re-nesting fails until `--pin` regenerates the registry, and the regeneration is a diff of whole lines a reviewer reads (the operator's decision of 2026-11-01) | the whole file; `check_spb_clauses.tsv` | every line |

## Scenarios

**SPB-X01.** Once gdb is registered as a sandbox provider (STG-15's `REG`), an agent debugging its own code runs it in its sandbox through `DEBUGGER_BATCH`, with no grant. A crash-triage job on a fuzzer's crashes goes through `CRASH_TRIAGE_JOB`, which the role must be granted (`SPB-03`, `CAPR-06`).

**SPB-X02.** SPT's fuzzing image is missing from the host. `FUZZING_JOB` reads `UNAVAILABLE` with its cause, and the agent's work goes on with its sandbox tools (`CAPR-12`).

**SPB-X03.** A defect in SPT's YARA image blocks a review, and the next transfer is a week away. The operator places an override as a protected change. The image's status shows the override, and each result names it. The next SPT release folds the fix in, and the override is removed (`SPB-09`).

**SPB-X04.** YARA's rule pack is refreshed. It travels in the data transfer, through the site's process, as a payload entry. The routine transfer that week carries no rule pack, passes its pre-carry check, and stays quick (`SPB-07`, `SPB-10`).

**SPB-X05.** Before SPT's Rocky 8 rebuild, the operator imports today's crash-triage image with a health check and a fixture query in the operator's record. It validates, and reads `FUNCTIONAL_ONLY` with "maintainable inside: no" beside it (`SPB-06`).

**SPB-X06.** SPT's YARA image is imported before its rule pack arrives. `YARA_SCAN_JOB` reads `UNAVAILABLE` with the cause "no data set", and a call refuses, rather than returning a clean result (`SPB-10`).

**SPB-X07.** After SPT's Rocky 8 rebuild, the operator rebuilds SPT's crash-triage image inside the air gap with a fix, from its carried build inputs. It is imported as an operator's record pinned by its new digest, as a protected change. It reads "rebuilt inside, not an SPT release" until SPT's next release carries the fix (`SPB-05`, `SPB-09`).

**SPB-X08.** A crash-triage requirement asks for a perf device, a seccomp change allowing `perf_event_open`, and `--pid=host` so that gdb can attach anywhere. The register refuses the record: none of them is in the fixed option set or the closed list. rr's host setting is a `HOST` prerequisite. Recording with hardware counters, if it needs more than the bound and the list, is not a job unless the operator adopts a new list entry (`SPB-02`).

**SPB-X09.** A month of Rocky 8 errata comes out. SPT makes a new dated repository state and rebuilds its derived base and the images on it. The routine transfer carries the new state and only the zstd layers the inside store lacks. The operator adopts each new digest by an operator command after validation. Layers the old pins still reference stay until those pins go (`SPB-05`, `SPB-07`).

## Rulings

**SPB-R01. How A-38's changes are adopted is the operator's.** Four changes are not additions:
- requirements for feedback (`SPB-04`), a change to `CAPR-R02`;
- the override (`SPB-09`), a change to `CAPR-R02`;
- the inside rebuild (`SPB-09`), a change to `CAPR-R02`, and an exception to `CAPR-11` for MCP images;
- a mounted payload, bound read-only only into the containers of the records that name it (`SPB-02`, `SPB-10`). It adds to what `CAPR-07`'s confined container holds, and is an exception to `CAPR-04`'s bind into every contained context. That keeps a rule pack carrying exploit text out of every agent's sandbox.

There are two forms:
- by precedence: `SPB-02`, `SPB-04`, `SPB-09` and `SPB-10` are read with `CAPR-R02`, `CAPR-04`, `CAPR-07` and `CAPR-11`, with A-38's bytes untouched and a pointer line on its record;
- or A-38 gets a revision 2.2 and a new frozen copy.

The adoption proposal asks, recommending the first, as A-51's and A-52's additions were read.

**SPB-R02. SPT builds the agent-facing images, not AEW** (the operator's Q1). One base image, one stream of fixes and one supply chain, and AEW stays a consumer. The alternative, AEW building its own image on SPT's base, would make AEW a container build and release system, and split the supply chain.

**SPB-R03. The Rocky 8 base is the operator's** (Q3). The designer had recommended Ubuntu containers for now, on cost and order. The operator's reason, maintaining images inside the air gap, removed that recommendation's premise (`SPB-05`).

**SPB-R04. A typed toolbox is still granted.** It is container-backed, and `CAPR-06` makes every container-backed provider host-placed and granted per role. Treating it as sandbox-placed would amend A-38 for no route gained.

**SPB-R05. The overlap creates no security finding.** A tool that sits in both tiers runs with the agent's authority in the sandbox, and inside `SPB-02`'s bound in SPT's image. Neither copy can approve, forge an owner fact or reach a credential, and every byte of a mounted payload is pinned and checked at launch (`SPB-10`).

**SPB-R06. A relaxation comes from a closed list of exact changes, because what a job runs is the agent's choice.**
- **Why:** a typed job runs or reads a target an agent staged. A host device, a host path, a network, or a capability that acts outside the container would give that target more than its caller's authority, which `CAPR-07` forbids. The operator cannot approve it as a protected change either, because `CAPR-13` protects host-side changes; it does not waive `CAPR-07`.
- **Why a list of exact changes, not a description:** "stays inside the container's namespaces" cannot be checked against a seccomp profile. Some system calls reach past the container (kernel keyrings, performance counters, new user namespaces). And a list of named relaxations is not enough on its own: `--pid=host` relaxes none of them. So the bound is one fixed option set, and each entry is one exact run option. Validation compares what would run with both.
- **What is on it:** `--cap-add=SYS_PTRACE`, with the rest of the fixed set unchanged. In the container's own process namespace, it reaches only the container's own processes. That stays within the caller's authority: the agent's own debugger already traces the agent's own processes in its sandbox (`SPB-X01`).
- **The alternative** was a further change to `CAPR-07`. It would let a host device reach agent-staged code, so it is not proposed.

**SPB-R07. GitNexus is taken as it is.**
- **What the operator decided:** "Use SPT's image at work as is. The licence risk is yours." (2026-11-01).
- **The designer's reading:** "as is" governs AEW's use inside the air gap. So for `spt-gitnexus`:
  - `SPB-05`'s carried sources and inside rebuild do not apply;
  - nor do `SPB-09`'s override and inside rebuild;
  - it stays interim (`SPB-06`).
- **What SPT builds is SPT's.** A source build of its LadybugDB addon on Rocky 8 is a requirement on SPT like any other (`SPB-05`, `SPB-B1`). The image AEW imports would still be SPT's image.
- **The glibc floor:**
  - current GitNexus releases need glibc 2.34 for that addon (`BASE-AND-GLIBC-FACTS.md`);
  - the floor of SPT's pinned 1.6.3 is not known.
- **Applying `SPB-05` or `SPB-09` to it inside the air gap** is the operator's licence call, outside this position.

**SPB-R08. The base pin is a pair.**
- **Why:** no published Rocky 8 base image carries errata newer than 8.10's release, and the repositories change in place (`BASE-AND-GLIBC-FACTS.md`). A digest alone would be stale, and a build from live repositories would not be reliably reproducible.
- **So:** the upstream digest plus a dated repository state SPT makes and carries is what a rebuild needs, and what an errata refresh changes.
- **Why judge by outcome:** nobody has shown that a rebuild reproduces byte-identical layers (`BASE-AND-GLIBC-FACTS.md`). The same packages and a passing acceptance test are what the rule needs.

**SPB-R09. A job's output is copied out, not mounted, and the copy admits only plain files.**
- **What `CAPR-07` allows:** the confined branch holds "only the staged inputs, with no network, credential or host path". A mounted payload is `SPB-R01`'s declared fourth change. A writable output mount would be a host path, and one more change, so it is not made.
- **So:** the job writes inside its own container, and the register copies the output out after the job exits.
- **What the copy admits:** what the target ran could have written anything into the output. So the copy takes regular files and directories only, within `SPB-02`'s caps on bytes, entries and depth, and leaves out, and names, absolute and climbing names. The register reads it one path component at a time without following links, into a fresh directory for that job alone, and delivers it the same way. A link or device the target left behind is left out and named, and is never followed on the host.
- **What it gives:** the staged inputs stay read-only. No contained context can rewrite the output between the job's write and the register's read, or reach a host path through it.
- **Inputs copied in:** for the same reason, an image that writes into its inputs gets a copy inside its container, never a writable host path.
- **Staging, one step earlier:** the bind's source is the register's own copy, made under the same rule, so nothing in a context's tree decides what a job can read. A host-side reader acting for a contained context reads no more than that context's view, so staging takes its roots, and what it leaves out, from that launch's recorded layout. The root list is narrower than `CAPR-07`'s "can already read": a context copies anything else it can read into its own workspace first, or its scratch directory where the workspace is read-only.

**SPB-R10. What runs the target cannot vouch for itself, and the cap fails closed.**
- **The route:** a job that executes staged content holds that content in the same container as its own output. Copy-out cannot help, because the target may have written the output before the job exited.
- **Why fail closed:** a classification the record's author asserts fails open when it is wrong. So every container-backed operation is capped at the agent's submission (`AEV-05.c`, `AEV-05.g`). The operator lifts the cap per operation, with a reason, as a protected change, and never for an operation that runs staged content, loads code from it, honours it as configuration, or copies it into its output (`SPB-02`).
- **What confirms:** only an observation the executed content cannot write. A rerun of the same capped job would be forged the same way. Under podman 4.9.4 nothing confirms yet, so a finding stays a claim.
- **The cost is small:** a crash or a finding is still reported, as a claim, until it is confirmed.

**SPB-R11. SPT's containers run rootless** (the operator's decision of 2026-11-01).
- **What it gives:** podman runs under the operator's user, in the operator's rootless user namespace, so an escape lands as that user, not as root.
- **What it does not give:** an escape can still read and write every file the operator can, the register's state included, so the bound, the copy rule and the evidence cap are not relaxed by it.
- **The costs:**
  - subordinate ID ranges for the operator's account (a `HOST` prerequisite);
  - slower storage on Rocky 8's kernel for image builds and imports, which are rare. Jobs that are compute-bound run at about the same speed;
  - no cgroup limits under cgroups v1 rootless, as the designer understands it, so the bound carries a `--timeout` and `--ulimit` values, and doctor reports the rest;
  - a store location outside the operator's home, on a filesystem that can keep a rootless store (`SPB-05`).

## Backlog

**SPB-B1.** Which SPT images are built first, as agent-facing images on the Rocky 8 base, once the operator selects SPT as a project. The known source builds:
- CASR, whose release binary is built on Ubuntu 22.04, so its floor is inferred above Rocky 8's;
- GitNexus's LadybugDB addon, a requirement on SPT (`SPB-R07`).

**SPB-B2.** The requirement's file form in SPT's repository, and its template.

**SPB-B3.** E99's transfer manifest. It covers:
- the pre-carry check;
- the separate data transfer;
- the one-layout image transfer;
- how an image moved to the data transfer is imported.

**SPB-B4.** How each SPT evidence schema maps to `AEV-05`'s kinds, for the register's evidence ceilings (`CAPR-09`), and whether SPT's service images should also write SPT's schemas for each call they serve.

**SPB-B5.** The inventory's rows for the container tools (podman, buildah and skopeo, as Rocky 8 packages), the Rocky 8 base image, and micromamba. They were recorded on 2026-11-01 in the designer's tool inventory, with the versions re-checked.

**SPB-B6.** The conformance evidence:
- the buildah test build (`SPB-05`), owed by SPT's first-project work, or a run the operator approves;
- the three transfer measurements, recorded once after the Rocky 8 rebuild, owed by SPT's first-project work (`SPB-07`, the operator's decision of 2026-11-01): separate saves against one layout, gzip against zstd, and a typical upgrade;
- one captured run of SPT's YARA image under `SPB-02`'s fixed option set, on stock Rocky 8, done on 2026-11-01 with the operator's approval (`PODMAN-CAPTURE.md`). It is repeated on SPT's Rocky 8 images, and on one image that needs `SYS_PTRACE`. It gave:
  - the created container's inspection and generated spec, which fix the comparison's field names;
  - the runtime's added variables, and its own per-container mounts, with their sources;
  - that the image's user can read each bind, write to a copied-in output directory under a new name, and write a copied-in input;
  - that `--userns=auto` and `--userns=nomap` both run the job. Whether one joins the fixed set is decided when the register is built;
  - that under `tini` a child's signal death reads as a plain exit. The first process's own signal death is measured on the rerun;
- which transfer keeps an image's manifest digest. `podman save` and `load` change it and keep the image ID (measured), and a mismatch refuses the import.

**SPB-B7.** Two measurements on the operator's networked storage, before either is ruled in or out (the operator's decision of 2026-11-01): a rootless image store there, and podman's read-only additional image stores there. The same run settles whether a moved store needs a SELinux file context under enforcing mode. Moved within the home filesystem, with its label, it needs none (measured, `PODMAN-CAPTURE.md`). A local store outside the home is measured in the same run.

## Not covered

- **SPT's modernization:** its schedule and its selection are the operator's, outside this position.
- **The register's build,** its slices and the multi-file payload kind.
- **ADR-0014,** and any change to it.
- **SPT's images AEW does not use:** they stay SPT's (`CAPR-R02`), except that none of them rides SPT's routine part if it bakes in antivirus-sensitive data (`SPB-07`).
- **GitNexus's licence:** the operator's (`SPB-R07`).
- **SPT's images AEW does not use, beyond `SPB-05` and `SPB-07`:** where one rides SPT's routine transfer, `SPB-05` asks that it can be rebuilt inside, and `SPB-07` that it bakes in no antivirus-sensitive data. Nothing else here reaches them.

## Changes

- **Revision 1 (2026-11-01):** the first text, after the advisor's check of its shape (`STAGE.md`).
- **Revision 2 (2026-11-01):** answers round 1's eighteen findings (`CHANGES-r2.md`).
- **Revision 3 (2026-11-01):** answers the quick check's nine findings, and the designer's own check before the narrow check. It also folds in the designer's rulings on the base image, and the operator's decisions on the container tools and the transfer compression (`CHANGES-r3.md`).
- **Revision 4 (2026-11-01):** answers the narrow check's eight findings, with the operator's decisions on rootless containers and the whole-clause gate (`CHANGES-r4.md`).
- **Revision 5 (2026-11-01):** answers the check of revision 4's thirteen findings (`CHANGES-r5.md`).
- **Revision 6 (2026-11-01):** answers the one-question check of revision 5's three findings, and takes in the operator-approved podman capture (`CHANGES-r6.md`, `PODMAN-CAPTURE.md`). Revision 6.1 folds in the diff-only check's one clause.
