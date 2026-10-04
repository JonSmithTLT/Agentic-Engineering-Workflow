# AEW independent review — Area 2: authority and credential custody

- **Date:** 2026-10-03
- **Reviewed tree:** `Agentic-Engineering-Workflow` at `a6cdc64` (merge of PR #32) plus the uncommitted `impl/m4-b-containment` working tree (containment package, `supervisor.py`, `agentenv.py`, `bridge.py`, `procs.py`, `checks.py` changes). Findings cite the working-tree line numbers.
- **Scope:** `src/aew/engine/authority.py`, `src/aew/harness/bridge.py`, `supervisor.py`, `lead_broker.py`, `agentenv.py`, `runlog.py`, `src/aew/operator.py`, read against ADR-0005 and ADR-0009. Supporting code read where the guarantee depends on it: `harness_ops.py`, `lead_ops.py`, `evidence_ops.py`, `base.py`, `store.py`, `lock.py`, `procs.py`, `contract.py`, `containment/*`, `opencode/adapter.py`, `opencode/lead.py`, `opencode/projection.py`, `cli/main.py`, `workspace/git.py`.
- **Method:** code reading only. No file was modified and no test or process was run, so nothing below is marked reproduced. Severity: blocker / major / minor. Confidence is stated per finding.

## Questions from the brief

| Question | Answer |
|---|---|
| Can an agent obtain, replay or forge a credential, or act for another run? | Not through the bridge or the engine (sound). Yes across runs by reading another run's persisted bridge key and reaching its socket (F2). A Lead model can obtain a Lead credential through the env-gated refusal (F1). |
| Races between rotation or revocation and an in-flight request | Closed: both engine write paths re-check under the control lock; the bridge refuses under `_serial` after close. One residual: an in-flight check outlives termination and seals evidence afterwards (F6, minor). |
| Can a stale or second Lead act after a takeover? | No. Generation fencing and the takeover's post-wait revision check hold. The broker closes on supersession. A pending handoff is wrongly treated as supersession (F5, minor). |
| Does anything model-controlled reach the supervisor's environment or memory? | Request bodies are bounded and typed; request files are authorised through control state. The supervisor's own environment is the Lead's minus scrubbed variables. The broker keeps `AEW_LEAD_TOKEN` in its environment and passes it to in-process git (F4, minor). |

## Findings

### F1. Major — the Lead session's custody fence is an environment variable the Lead model controls

- **Where:** `src/aew/cli/main.py:55`, `src/aew/harness/lead_broker.py:197-198` (`routes`), `lead_broker.py:60-66` (`refuses_locally`), `lead_broker.py:226` (`subprocess.call` for the Lead harness), `src/aew/engine/lead_ops.py:150,267` (credential in the result), `src/aew/operator.py:32-44`.
- **Guarantee:** ADR-0009 custody invariant ("no raw AEW credential ever enters a model-controlled process") and "credential-emitting commands ... refused locally in the session too"; ADR-0005 amendment "no broker or harness can perform [takeover]".
- **Scenario A (no operator involvement):** the Lead harness is started with a plain `subprocess.call`, not a `ProcessTree`, so a background child outlives the TUI. With `--acquire`, `run_session` releases the seat at exit when no invocation is active. A Lead model leaves `nohup sh -c 'sleep 30; env -u AEW_LEAD_BROKER aew lead acquire --expect-rev $(...)' &` behind; the operator quits the TUI; the seat is released; the background process takes it and the new Lead credential is printed into a model-controlled process. With `AEW_LEAD_TOKEN` set, `routes()` is false and every Lead command runs locally, bypassing all broker refusals (handoff offer, release, dispatch without `--launch`).
- **Scenario B (operator prompted):** `env -u AEW_LEAD_BROKER aew lead takeover --expect-rev N --reason x` from the Lead's shell reaches `operator.authorize`. The prompt appears on the operator's own terminal, indistinguishable from a self-initiated takeover. If the operator types the code, the credential is printed to the model's stdout and persisted by the harness. The Lead projection allows `shell` matching `aew *` without asking (`projection.py:159`); whether OpenCode matches that glob against a chained command such as `aew status; env -u ...` should be checked, since it would remove the `ask` as well.
- **Fix:** (1) own the Lead harness tree as the supervisor owns a run (job object / process group plus sentinel), and release an acquired seat only once the tree is dead; (2) make credential-emitting commands write the credential only to the controlling terminal (`/dev/tty` / `CONOUT$`), never to a non-tty stdout; the explicit-credential path for scripts can opt in with a flag the broker refuses; (3) have the takeover prompt name the requesting process's parent chain so an unexpected prompt is recognisable.
- **Confidence:** high on the mechanism, medium on operator behaviour in B. Not reproduced.

### F2. Major (preconditioned) — another run's bridge key is readable at rest, and its socket can be reachable

- **Where:** `src/aew/harness/opencode/adapter.py:167` (agent environment, key included, written into the run's OpenCode session state under `<run>/harness/xdg-data`), `src/aew/harness/containment/layout.py:73-74` (host root bound read-only, only `/tmp` replaced), `src/aew/harness/bridge.py:249-251` (socket directory from `tempfile.mkdtemp` in system temp).
- **Guarantee:** "an agent acts only through its own invocation's credential"; ADR-0009's justification of the bridge key assumes only the run's own processes hold it.
- **Scenario:** on a contained Linux run, run B reads run A's OpenCode database (host root is readable; the layout claims integrity, not confidentiality) and obtains A's `AEW_AGENT_KEY` and endpoint. If `TMPDIR` is anywhere other than `/tmp` (B's own `--tmpfs /tmp` hides only `/tmp`), A's socket directory is visible to B; `connect()` on a Unix socket is not refused by a read-only bind. B then submits evidence and runs checks as A. On an uncontained Linux run (`allow_weaker`) and on Windows (named pipe) the same two steps work without the TMPDIR condition. Windows is inside the accepted same-UID model, but this is a file-read path and ADR-0005 states that custody closes files.
- **Fix:** mask sibling run directories in every layout (tmpfs over `.aew/local/harness/runs`, then bind the run's own directory back); place the bridge socket under a per-run private directory that other layouts hide, not in system temp; add a regression that reads a sibling run's harness state and tries to connect.
- **Confidence:** medium for the contained case, high for uncontained Linux and Windows. Not reproduced.

### F3. Major, or a residual to document — the provider key and server password are readable from inside the run

- **Where:** `src/aew/harness/opencode/adapter.py:80-101` (server environment carries the policy's provider variables and `OPENCODE_PASSWORD`), `adapter.py:157` (spawned inside the run's tree, so inside the sandbox and PID namespace).
- **Guarantee:** ADR-0009: the agent environment carries "no provider secret, no harness password".
- **Scenario:** the OpenCode server spawns the agent's shell, so it is the shell's parent inside the same PID namespace. `/proc/<pid>/environ` is readable by the same UID regardless of Yama (Yama gates attach, not read). `cat /proc/$PPID/environ | tr '\0' '\n'` yields the operator's provider API key and the server password. The environment statement is literally true, but the secret is one command away. Only the supervisor is non-dumpable; the server cannot be made so (dumpable resets on `execve`). The password additionally lets the agent drive its own server's API.
- **Fix:** a real fix needs the server outside the agent's UID or namespace. Short of that, record it under ADR-0009 "Residual risk", prefer OpenCode's stored auth in the private XDG data directory over environment variables where the harness allows it, and make the Linux conformance suite assert what is actually true.
- **Confidence:** high. Not reproduced.

### F4. Minor — the broker keeps `AEW_LEAD_TOKEN` in its environment and in-process git inherits it

- **Where:** `src/aew/harness/lead_broker.py:217`, `src/aew/workspace/git.py:21` (`full_env = dict(os.environ)`).
- **Guarantee:** ADR-0005 amendment: the Lead credential "is removed from the session's environment".
- **Scenario:** `lead.cli` runs integration commands inside the broker process; every git call copies the broker's environment, so the Lead credential reaches hooks of the authoritative repository. Contained Linux runs cannot write that hooks directory, so exposure is Windows only, but it is needless.
- **Fix:** pop the variable after reading it in `run_session`; build git's environment from an allowlist or at least scrub `SCRUBBED_ENV`.
- **Confidence:** high. Not reproduced.

### F5. Minor — a pending handoff permanently closes the Lead session's bridge and misreports it as superseded

- **Where:** `src/aew/harness/lead_broker.py:97-117`, `src/aew/engine/authority.py:137-138`.
- **Guarantee:** ADR-0009: the broker closes "when the held credential stops being the current Lead's". A pending handoff does not end authority; the Lead may cancel it.
- **Scenario:** the operator offers a handoff from their own terminal with the same credential. The watchdog's `require_lead` raises `PermissionDenied` for `handoff_pending`; the broker treats any `AEWError` as loss, closes the bridge, returns, and sets `superseded`. A cancelled handoff never restores the session; `lead.whoami` reports no authority; with `--acquire`, `run_session` neither releases the seat nor says "held".
- **Fix:** close only on `StaleAuthority`; while pending, refuse requests without closing.
- **Confidence:** high. Not reproduced.

### F6. Minor — a terminated run does not end an in-flight check, and the supervisor can exit mid-write

- **Where:** `src/aew/policy/checks.py:75` (checks run in their own `ProcessTree`), `src/aew/harness/supervisor.py:124` (credential bound at call time), `supervisor.py:355-356` (`tree.kill`, `retire_private_git`), `supervisor.py:457-458` (drain bounded to 60 s), `src/aew/engine/evidence_ops.py:624-648` (log sealed before record).
- **Guarantee:** ADR-0009 "The supervisor drains in-flight requests before exiting"; a run that ended records what it did.
- **Scenario:** the Lead stops a run while `check.run` is executing agent-written check code. `_end` kills the harness tree, but the check's tree is separate, so the check runs to its timeout; the handler thread already holds the credential string, so evidence is sealed after the record says `terminated` and after the record's `evidence` list was captured. If the check outlasts the 60 s drain, the supervisor exits with the daemon thread between `create_exclusive` of the log and of the record, leaving an orphan log. `retire_private_git` also removes the private index a running check may be using.
- **Fix:** register the check's `ProcessTree` on the supervisor and kill it in `_end`; drain for the check's timeout; or stage log and record together.
- **Confidence:** medium-high. Not reproduced.

### F7. Minor — custody validation uses `context.read`, which a role card may narrow away

- **Where:** `src/aew/harness/supervisor.py:139`, `src/aew/engine/role_ops.py:348`, `src/aew/engine/authority.py:176-180`.
- **Scenario:** a card whose `restrict.operations` omits `context.read` makes every launch of that card fail "custody refused" and `whoami` refuse. Functional, not a security defect.
- **Fix:** an identity-only custody check, or require `context.read` at card validation.
- **Confidence:** medium. Not reproduced.

## What looks sound

- Token format, verifier-only storage, constant-time comparison; archived credentials reported as stale authority, never unknown.
- Generation fencing in `require_lead` and `require_invocation`; rotated credentials named as such.
- Rotation and run recording in one commit; the superseding stop recorded in the same commit; `--launch` withholds the credential.
- Both engine write paths (`submit`, `check_run` before and after the check) re-check the credential under the control lock; the bridge refuses under `_serial` once closed. The rotation and revocation races named in the brief are closed.
- JSON-only bridge with exact arguments; a request cannot name an invocation, run or credential.
- Redaction on replies, run records, event log, supervisor log and the prompt; the supervisor's `log()` wraps tracebacks.
- Stdin handoff; environment scrubbed by name and by value in the launcher and again in the supervisor; the agent environment is an allowlist.
- Request files are authorised only through control state (digest, kind, once).
- Takeover re-checks revision and generation after the terminal wait; the terminal is the only authorisation path.
- The M3-D11 ordering in the broker (token taken before the read, `close()` waits for the watchdog).

## Process, architecture and efficiency notes (outside the findings)

1. **Trust from the environment.** Security-relevant behaviour keys on environment variables in several places (`AEW_LEAD_BROKER`, `AEW_PAUSE`, `AEW_FAULT`, `AEW_HARNESS_ADAPTERS`, `AEW_RUN_STALE_S`, `AEW_LAUNCH_ACK_S`). Most are test or operator conveniences, but an inventory in ADR-0009 of what is trusted from the environment, and by which process, would have made F1 visible at design time.
2. **Lead harness process ownership.** The invocation harness has `ProcessTree`; the Lead harness does not. Reusing it removes the asymmetry and closes F1-A.
3. **One credential output path.** A single `emit_credential()` that writes to the controlling terminal would centralise custody for `lead acquire|takeover|handoff accept` and dispatch without `--launch`, and let the credential scan cover Lead transcripts.
4. **Containment masks.** The layout masks `~/.ssh` and similar but not agent-tool auth stores (`~/.local/share/opencode`, `~/.config/opencode`, `~/.codex`, `~/.claude`, OpenCode Desktop's directories) nor sibling run directories. The run label says "the host stays readable"; the consequences (F2, provider keys on disk) deserve a sentence in the ADR.
5. **Credential scan.** `scan_for_credentials` reads every file whole; OpenCode databases grow large. Stream in chunks with overlap, and consider UTF-16 transcripts on Windows.
6. **Test gaps.** The adversarial suite proves the bridge-level cross-run refusal (`test_run_a_cannot_act_as_run_b`) but not the read-key-then-connect path, nor the unset-env path in the Lead session, nor a Linux assertion about `/proc/<server>/environ`. All three are cheap regressions, and the third would fail today, which is the point.
7. **Scope of the area.** F2 and F3 live in `opencode/adapter.py` and `containment/layout.py`. Future area-2 briefs should list the adapter's environment construction and the layout among the files to read, since custody is decided there as much as in the bridge.
