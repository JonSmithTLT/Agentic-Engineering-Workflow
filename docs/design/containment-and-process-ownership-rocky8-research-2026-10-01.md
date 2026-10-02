# Research: filesystem containment and process ownership on Rocky Linux 8

- **Status:** research input for the designer, not governing. §8 records the designer's decisions on Q3 and E13 (2026-10-01); nothing here is implemented.
- **Date:** 2026-10-01, after M3's acceptance.
- **Feeds:**
  - `future-work.md` F2 (real filesystem containment) and its gate, "before real-repository dogfood";
  - Q3 (is containment required for personal real-project dogfood?);
  - E13 (POSIX process ownership) and its gate, "before Linux runs rely on stop";
  - the isolation design's §6.4, §6.6, §12 and §16 (`execution-workspace-and-isolation-design-v0.1.md`).
- **Verified against:** published documentation (sources at the end). **Not yet run on the Q7 Rocky 8.10 distro.** §6 lists the probes that would confirm it.

## 1. Summary

1. **One mechanism can close both gaps.** A run wrapped in unprivileged **bubblewrap** (`bwrap`) gets two things:
   - a mount namespace, so the protected checkout is read-only at the OS boundary (F2);
   - a PID namespace with `--die-with-parent`. Every process the run starts, including one that calls `setsid` or double-forks, dies when the run is stopped or the supervisor dies (E13).

   Rocky 8 supports unprivileged bubblewrap in its default configuration.
2. **Bind mounts cost almost nothing at any repository size.** Nothing is copied, so this fits the million-file repositories the isolation design worries about (§3.2). Overlay or copy-on-write (§6.4) is a separate question with a weaker answer on Rocky 8 (§4).
3. **Git worktrees are the hard part, not the sandbox.** A worktree writes to the main repository's `.git` (its per-worktree directory, the shared object store and refs). A naive read-only bind of the protected checkout either breaks git in the worktree or, if `.git` is left writable, leaves refs writable. §3.3 proposes a per-run object directory that solves this.
4. **What Rocky 8 lacks:**
   - Landlock (RHEL 9.6 and later only);
   - unprivileged cgroups, because RHEL 8 defaults to cgroup v1;
   - probably native rootless overlayfs, whose backport to 8.5 was planned and not confirmed.

   None of these is needed for the recommendation.
5. **Windows stays "workdir separation only".** It is the development environment, and nothing equivalent is that cheap there. The job object already covers its process ownership.

## 2. The two gaps today

| Gap | Today | Why it matters |
|---|---|---|
| **Filesystem (F2)** | Workdir separation only (`AEW-INV-ISO-001`): the agent's shell runs as the operator's user and can write anywhere that user can. M3's live run showed a verifier writing into the real AEW repository (isolation design §3.1). | Gates real-repository dogfood and internal alpha. |
| **Process ownership (E13)** | POSIX: one new process group plus a sentinel that kills the group when the supervisor's pipe closes (`src/aew/harness/procs.py`). A descendant that calls `setsid` leaves the group and survives `stop`. The live conformance test `stopping_a_run_ends_every_process_it_started` fails on Rocky 8.10. | Authority is unaffected (it lives in the credential), but leftover processes keep running, keep resources, and can keep writing files. |

## 3. Candidate: a bubblewrap run boundary

### 3.1 What bubblewrap provides on Rocky 8

- **Unprivileged.** Flatpak's documentation says RHEL 8 or newer supports unprivileged bubblewrap in its default configuration. `bwrap` is not setuid there; it relies on unprivileged user namespaces. `user.max_user_namespaces` defaults to a RAM-dependent value, usually tens of thousands. Only RHEL 7 and older need setuid mode. [S1]
- **Namespaces.** It provides mount, PID, IPC, UTS, network, user and cgroup namespaces, plus seccomp filtering. [S2]
- **`--die-with-parent`** ties the sandbox to its parent through the kernel's parent-death signal.
- **`--unshare-pid`** makes the sandbox's first process PID 1 of a new PID namespace. When it exits, the kernel kills every process left in that namespace. No `setsid` or double fork leaves a PID namespace, so this closes E13 by construction rather than by walking process trees.
- **Precedent.** Codex's Linux sandbox uses bubblewrap and seccomp (cited in the M6 provider research, S34 and S35). Flatpak is built on it.

### 3.2 Layout of one run (a sketch to evaluate, not a design)

```text
bwrap --die-with-parent --unshare-pid --unshare-ipc --unshare-uts
      --ro-bind / /                                   # the host, read-only
      --dev /dev --proc /proc --tmpfs /tmp
      --bind <ticket workspace> <same path>           # writable: the invocation's workspace
      --bind <run scratch> <same path>                # writable: the run's private scratch (isolation §11)
      --bind <run dir> <same path>                    # writable: OpenCode's private XDG state (M3 already per-run)
      --tmpfs <operator's home secrets, e.g. ~/.ssh>  # hidden, not just read-only
      --ro-bind <bridge socket dir> <same path>       # the custody bridge stays reachable
      -- opencode-cli serve ...
```

- **Network stays shared** (no `--unshare-net`). The harness needs the model API, and the supervisor talks to the private server over loopback. Network containment is a separate question.
- **The bridge.** The custody bridge's AF_UNIX socket sits in a 0700 directory (`bridge.py`). It must be visible inside the sandbox. A read-only bind of the directory is enough to connect, since connecting needs no write access to the directory.
- **Same paths inside and out.** Binding everything at the same path means the run record, evidence paths and the agent's view agree. No path translation is needed in AEW.
- **Ownership.** With the user namespace mapping the operator's uid to itself, files the agent creates belong to the operator, as today.

### 3.3 The git worktree problem

AEW gives each mutating Ticket its own worktree (ADR-0004). A linked worktree's `.git` is a file pointing at `<main repo>/.git/worktrees/<id>/`, and ordinary git commands in the worktree write to three places:

| Written by | Location | Under a read-only main repository |
|---|---|---|
| `git add`, `commit`, `stash` | the shared object store, `<main>/.git/objects` | fails |
| index, `HEAD`, logs of the worktree | `<main>/.git/worktrees/<id>/` | fails |
| `commit` on the worktree's branch | shared refs, `<main>/.git/refs/heads/...` | fails, which is what we want |

Options:
1. **Make all of `.git` writable.** Git works, but an agent can then move any ref, including the authoritative branch. ADR-0004's compare-and-swap would catch a moved ref as a stale candidate, but the protected state would no longer be protected. Rejected.
2. **Writable `.git/worktrees/<id>/` and `.git/objects`, read-only refs.** Git works, except that commits on the worktree's branch fail. Agents don't need to commit, because the engine commits at `prepare`. Writes to the shared object store remain: they're unreferenced objects, harmless to correctness, but the agent can grow the store without bound.
3. **A private object directory per run (recommended to evaluate).** Set `GIT_OBJECT_DIRECTORY=<run scratch>/objects` and `GIT_ALTERNATE_OBJECT_DIRECTORIES=<main>/.git/objects` in the agent's environment. Reads fall back to the shared store and writes go to the run's own store. The main `.git` is read-only, except `.git/worktrees/<id>/`.
   - This works because the engine never relies on the agent's objects. It fingerprints and commits from content, in its own temporary index outside the sandbox (`snapshot/fingerprint.py`; ADR-0002).
   - **Must be tested** against every git command the roles run, and against the engine's `prepare` running on a workspace whose agent wrote only to the private store.

Reviewers and verifiers on a mutating Ticket share the implementer's live workspace (M3-B6). Under bubblewrap they can get it **read-only** plus their own scratch. That turns today's after-the-fact `WORKSPACE_MUTATED` refusal into an OS-level refusal, and is the isolation design's §10 role-sensitive isolation at no extra cost.

### 3.4 Against the containment regression gate (isolation §12)

| §12 probe | Expected under §3.2 |
|---|---|
| Absolute-path write outside writable roots | `EROFS` |
| `..` traversal | Resolved by the kernel; the target is still read-only: `EROFS` |
| Symlink escape | The same; symlinks don't cross mount permissions |
| Rename or move across the boundary | `EXDEV` or `EROFS` |
| `mkdir` outside writable roots | `EROFS` |
| Temporary file outside scratch | `/tmp` is a private tmpfs, discarded with the run; other paths `EROFS` |
| Python `open()` and shell redirect outside | `EROFS` |
| Tool touching another worktree or checkout | `EROFS` (not bound writable) |

Every row needs to be **run** on Rocky 8.10 before any claim. The table is the expected result, not evidence.

## 4. What else is on Rocky 8, and why it isn't the first choice

| Mechanism | On Rocky 8 | Assessment |
|---|---|---|
| **Landlock** (unprivileged path access control) | No. Mainline 5.13; Red Hat enabled it from RHEL 9.6 (`kernel-5.14.0-568.el9`). [S3] | Would be ideal (no namespaces needed), but not on this target. Revisit for a RHEL 9 or 10 target. |
| **Rootless overlayfs** (§6.4, copy-on-write) | Native rootless overlay needs mainline 5.11 or later. Red Hat planned a backport for RHEL 8.5 [S4], **not confirmed**. fuse-overlayfs works from a user namespace on 4.18 or later. [S5] | Probe whether the native backport landed in 8.10. FUSE on a million-file tree is a performance question to measure, not assume. Not needed for containment; only for a copy-on-write strategy. |
| **Rootless podman** | Supported (fuse-overlayfs storage, or native overlay if the backport is present). [S4][S5] | Heavier: images, storage and startup. Valuable for the M6 toolchain bundle (the provider research §7), not required for containment. |
| **cgroups** for process ownership | RHEL 8 boots cgroup v1 by default. Unprivileged delegation (`systemd-run --user --scope`) is reliable only on v2. | Not portable to the default Rocky 8 configuration. The PID namespace gives the needed guarantee without it. |
| **`PR_SET_CHILD_SUBREAPER`** (Linux 3.4+) | Available. | A fallback for E13 where user namespaces are disabled. Orphans reparent to the supervisor, which can then kill them all. But they escape if the supervisor itself dies, and killing races with forking. Weaker than a PID namespace; label it as such. |
| **seccomp** | Available. bwrap takes a compiled filter. | Defence in depth (for example, block `ptrace` of the supervisor). Not needed for filesystem containment. |

## 5. Failing closed and labels

- **Probe at launch, as M3 does for harness capabilities.** If `bwrap` is missing, user namespaces are disabled (`user.max_user_namespaces = 0`, which some hardened hosts set), or the probe sandbox fails a quick self-test, there are two cases:
  - a policy that **requires** containment refuses to launch (isolation invariant 8: fail closed);
  - a policy that allows the weaker mode launches, labelled `workdir separation only` as today.
- **Separate labels for separate guarantees.** Filesystem containment and process ownership are different, and a run should report each:
  - `filesystem: os_readonly_roots | workdir_separation_only`;
  - `process_ownership: pid_namespace | job_object | process_group`.

  This fits the isolation design's rule that the guarantee is described accurately (invariant 10, `FALSE_CONTAINMENT_CLAIM`).
- **The containment self-test is the §12 gate in miniature.** At launch, write to one known outside path from inside the sandbox and require `EROFS`. The full §12 suite runs in CI's Linux lane and on the Q7 distro.

## 6. Probes to run on the Q7 Rocky 8.10 distro

1. `rpm -q bubblewrap`, `bwrap --version`, and `sysctl user.max_user_namespaces`.
2. `bwrap --ro-bind / / --unshare-pid --die-with-parent -- sh -c 'setsid sleep 600 & sleep 600'`: kill the outer `bwrap` and confirm both sleeps are gone. Repeat with the supervisor killed by `SIGKILL`.
3. Rerun the failing live test `stopping_a_run_ends_every_process_it_started` with the run under bwrap.
4. OpenCode 2.0.18 `serve` inside the §3.2 layout: health probe, a session, a shell tool call, the bridge reachable, and `aew check run` through the bridge.
5. The §3.3 option 3 git layout: every git command the role packs use, then the engine's `prepare` and fingerprint on that workspace.
6. The §12 probe list from inside the sandbox.
7. Whether native rootless overlay is present (`unshare -rm mount -t overlay ...`), and fuse-overlayfs's cost on a large tree, only if copy-on-write is pursued.
8. Startup cost of the bwrap wrapper (expected milliseconds) next to the server's startup.

## 7. Questions for the designer

1. **Q3:** is the bubblewrap boundary, once it passes §12 on Rocky 8.10, enough for personal real-project dogfood? Is internal alpha a separate, higher bar?
2. Should E13 be closed by the PID namespace (one mechanism with F2), or separately by the subreaper first, as a smaller change before containment?
3. Option 3 in §3.3 (a private object store per run): acceptable, or should agents never run git write commands at all?
4. Should reviewers and verifiers get read-only workspaces by default under containment (§3.3, last paragraph)?
5. Network containment: out of scope for F2, or a sibling entry?

## 8. Designer's decisions (2026-10-01)

Recorded as given:

> **Q3 / F2:** Strong OS/runtime filesystem containment is required before any personal real-repository dogfood as well as internal alpha. The proposed unprivileged bubblewrap boundary is sufficient for personal dogfood once the Rocky 8 containment, OpenCode/bridge, Git-layout, fingerprint/prepare, fail-closed launch, and process-ownership probes pass. Internal alpha additionally requires representative isolation performance/operability acceptance.
>
> **E13:** Close POSIX process ownership through the same bubblewrap PID-namespace boundary. Do not implement a separate subreaper unless a pre-F2 Linux evaluation has a demonstrated need for reliable stop. Until the PID-namespace test passes, Linux process-group mode must not be represented as complete process ownership.

These answer §7's questions 1 and 2. The probes the decision names map to §6: containment (§6 items 1, 2 and 6), OpenCode and the bridge (item 4), the Git layout and fingerprint/`prepare` (item 5), fail-closed launch (§5), and process ownership (items 2 and 3). Questions 3 to 5 (agents' git write commands, read-only reviewer and verifier workspaces, network containment) are still open.

Follow-up decisions, recorded as given:

> **Q7 classification:** Real-project provenance does not by itself trigger F2. A sanitized/disposable SPT-derived fixture counts as scratch only when the execution environment also has no writable non-disposable project state or secrets within the run's host-level reach. A disposable clone on the normal development host does not count as scratch. F19 follows the same rule.
>
> **F2 scheduling:** Move F2 from an unscheduled gate to early M4 / before first normal-host Q7 or real-repository dogfood. Run the Rocky 8 bubblewrap feasibility probes immediately, in parallel with other pre-M4 work. Implement F2 and E13 together if those probes succeed.

## Sources

Retrieved 2026-10-01.

- S1: [Flatpak wiki, User namespace requirements](https://github.com/flatpak/flatpak/wiki/User-namespace-requirements)
- S2: [bubblewrap](https://github.com/containers/bubblewrap)
- S3: [Rocky Linux bug 7987, "Enable Landlock"](https://bugs.rockylinux.org/view.php?id=7987); [Landlock news #5](https://landlock.io/news/5/)
- S4: [Red Hat blog, "Podman is gaining rootless overlay support"](https://www.redhat.com/en/blog/podman-rootless-overlay)
- S5: [fuse-overlayfs](https://github.com/containers/fuse-overlayfs)
- In the repo: `src/aew/harness/procs.py`, `src/aew/harness/bridge.py`, `src/aew/snapshot/fingerprint.py`, ADR-0002, ADR-0004, ADR-0009, `execution-workspace-and-isolation-design-v0.1.md`, `future-work.md` E13 and F2.
