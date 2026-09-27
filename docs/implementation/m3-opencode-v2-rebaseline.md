# M3 step 0 — OpenCode V2 re-baseline and spike

- **Status:** complete, 2026-09-27. Gate result: **the spike confirmed the candidate interface and every lifecycle operation M3 needs, so the plan is unchanged** (operator rule: stop only if the plan changes).
- **Why this exists:** the designer found that the OpenCode material given for M3 mixed V1 and V2 API details. Every concrete OpenCode API detail from before this document is **non-authoritative**. That covers the M3 brief's examples, the M1 plan's M3 sketch, and early planning notes. What follows was confirmed against the installed V2 binary, tag `v2.0.18` source, and the V2 docs.
- **Invariant, unchanged:** AEW owns workflow, authority, evidence and durable engineering state. OpenCode V2 is execution infrastructure.
- **Evidence:** the spike scripts are `eval/m3/spike/*.py`. Results, with home paths sanitized, are in `eval/m3/spike/results/*.json`. Every run used a **private** server with isolated XDG state and free `opencode/*` models. The user's Desktop background service was never contacted.

## 1. Version examined and targeted

| | |
|---|---|
| Installed | OpenCode **2.0.18**, bundled with OpenCode Desktop (Windows). `opencode-cli --version` = `opencode v2.0.18`. It is not on PATH and not installed in WSL. |
| Pinned binary | `%APPDATA%\ai.opencode.desktop\cli\2.0.18\opencode-cli.exe`, a version-specific copy. The Desktop auto-updates its `resources\` copy, not this one. |
| Served API | `GET /openapi.json`: `opencode HttpApi` **0.0.1**, *"Experimental HttpApi surface for selected instance routes"*, 138 operations. The operation list and spec sha256 are in `results/openapi-2.0.18.ops.json`. |
| Docs | V2 docs at `opencode.ai/v2/docs` (migrate-v1, cli, config, agents, permissions, commands, skills, instructions, models, build/client, build/sdk, plugins). The main docs site still describes V1 (npm CLI 1.18.32, which is also GitHub's "latest release"). |
| Stability | V2 publishes **no stability or versioning policy**. The session, message, permission and event route groups are tagged experimental. `@opencode/client` calls itself a "private generation target" generated from the same contract. |

## 2. Integration surfaces compared

Required lifecycle:
- launch;
- correlate session ↔ AEW invocation;
- workspace/location;
- model/effort;
- results and events;
- interrupt/terminate;
- reconstruction after harness loss.

Also required:
- no new runtime on the offline Rocky 8 target;
- no version skew with the installed binary;
- mid-run message delivery (for future coordination);
- disposable state.

| Surface | Decision | Why |
|---|---|---|
| **A. HTTP+SSE against a private `opencode-cli serve` process, from the Python standard library** | **Selected** | This is the published contract that `@opencode/client` wraps, and the binary serves it. It needs no JS runtime, uses exactly the installed binary, and covers every lifecycle operation (§4). |
| B. `@opencode/client` in a Node/Bun shim | Rejected | Same contract, plus a JS runtime and npm packages to ship offline. The package itself says it is a private generation target. |
| C. `@opencode/sdk` embedded host | Rejected | It hosts the OpenCode core (native dependencies: node-pty, watcher, tree-sitter) in a JS process AEW would own, and would be version-skewed against the installed binary. It defaults to an in-memory DB, but provider credentials would live in-process. |
| D. CLI: `run --standalone --format json`, `session export/import`, `api`, `stats` | **Kept for diagnostics and the raw-OpenCode dogfood baseline** | As a lifecycle interface it has no mid-run delivery, interrupts only by signal, and allows no pre-launch model or skill inspection. Per-turn `run` would have coupled AEW against the frozen coordination design's live delta delivery. |

There is **no official non-JS V2 client.** The V1 Python package `opencode-ai` targets the V1 API and does not work against 2.0.18.

## 3. V1 assumptions that are no longer valid

| V1 assumption (from earlier M3 material) | V2 2.0.18 reality |
|---|---|
| `task` tool and child sessions as the subagent mechanism | permission action `subagent`; children inherit session permissions |
| OpenCode todo lists to deny | V2 has **no todo tool** |
| permission keys `bash`, `write`, `patch`, `doom_loop`, `lsp`; a permission object map | ordered `permissions: [{action, resource, effect}]`, last match wins, default `ask`; `shell`; `edit` covers write and patch; `doom_loop` and `lsp` are gone |
| `prompt_async`, `/message`, `abort`, `/session/status` | `POST /api/session/{id}/prompt` returns an inbox item (`delivery: steer\|queue`); `POST …/interrupt`; `GET /api/session/active`, plus `outcome` and `idle` messages |
| `/event`, `/global/event`, `/doc`, `/global/health` | `GET /api/event` (volatile, no replay); `GET /openapi.json`; `GET /api/info` |
| messages as `{info.role, parts[]}` | typed timeline: `assistant{model{id,providerID,variant}, tokens, cost, finish, content[]}`, `shell`, `idle{outcome}`, and so on |
| `run --attach/--dir/--variant/--command` | `run --server/--standalone`; the cwd is the directory; `provider/model#variant` |
| config `agent`, `prompt`, `maxSteps`, `small_model`, `instructions` | `agents`, `system`, `steps`, `agents.title.model`; the `instructions` array is not loaded; only `AGENTS.md` loads |
| `OPENCODE_PERMISSION`, `OPENCODE_DISABLE_CLAUDE_CODE`, `OPENCODE_SERVER_USERNAME` | not in the binary |
| `opencode export` | `opencode session export` |
| V1 plugin hooks; `@opencode-ai/sdk`; Python `opencode-ai` | new plugin API; the V1 packages are incompatible |
| sampling parameters per agent | preserved but **not sent** in V2 |

## 4. Spike results (every required operation)

| # | Question | Result | Evidence |
|---|---|---|---|
| 1 | Private server, auth, lease | `serve --stdio --port 0 --hostname 127.0.0.1` prints one `{"url"}` line in **~0.19 s**. Without the password, requests return **401**. Closing stdin makes it exit in **~0.05 s**. The server strips `OPENCODE_PASSWORD` from its own env, so the agent's shell **cannot call its own server API** (`STATUS 401` from inside the session shell). | `probe_surface.json`, `probe_exposure.json` |
| 2 | Session create, model/variant, location, permissions, metadata; completion; effective model and usage | Session create takes about 75 ms. A pinned `variant` is recorded on the session, on `session.step.started` and on every assistant message. Completion: `session.execution.succeeded` plus `POST /api/experimental/session/{id}/wait` → 204 plus an `idle{succeeded}` message. Per-message `tokens{input,output,reasoning,cache}` and `cost` are recorded. First model step took 4–7 s, a short task 17 s. | `probe_lifecycle.json`, `probe_misc.json` |
| 3 | Interrupt; mid-loop delivery | `POST …/interrupt` → `{interrupted:true}` → `session.execution.interrupted`, reason `user`. **`delivery: steer` injected into a running loop was acted on ("first done / STEERED"), and a `queue` prompt ran after it ("QUEUED").** | `probe_lifecycle.json` |
| 4 | Shell env control | `PUT /api/session/{id}/environment` **replaces** the shell env. A server-env secret was **not** visible to shell commands; the curated canary was. (The shell adds benign variables such as `PWD`, `SHLVL`, `HOMEDRIVE`, `OPENCODE_TERMINAL`. On this host the shell is Git Bash.) | `probe_lifecycle.json` |
| 5 | Permissions | An `ask` with no reply **blocks indefinitely**: the session stays active past 10 s with the request pending. A `reject` reply ends it `interrupted`. The `subagent` deny removed the tool (the model reported that no subagent tool exists). **An `edit` deny did not stop file creation: the model used the shell.** Harness permissions are defense in depth, never a boundary. | `probe_lifecycle.json` |
| 6 | Instructions and skills under isolation | Skill exposure was observed from the model, because `/api/skill` returned an empty list in every variant. **By default the session is told about the user's global `~/.claude/skills`** plus project and ancestor skills. The controls: `OPENCODE_DISABLE_PROJECT_CONFIG=1` removes `AGENTS.md` (instruction key `core/instructions` absent) and project `.opencode` skills, but **not** global `~/.claude` skills. `"plugins": ["-opencode.config.compatibility"]` removes global and project `.claude`/`.agents` skills (confirmed; previously only inferred). A `skill` deny removes all skill guidance. | `probe_exposure.json` (+ model answers recorded in §6) |
| 7 | Process-tree ownership without the lease | Setup: a supervisor in a **Windows job with KILL_ON_JOB_CLOSE**, whose server's shell started a detached grandchild. Result: when the supervisor was hard-killed (`TerminateProcess`), **the server and the grandchild both died**. A grandchild started with `CREATE_BREAKAWAY_FROM_JOB` did not survive either. With no AEW job, a process started from a session shell command **survives** the command's normal exit and the server's exit, which is the property `aew harness launch` needs when a Lead runs it from OpenCode. | `probe_process.json` |
| 8 | Agent reaches its own server | No: 401 (see #1). | `probe_exposure.json` |
| 9 | `run --standalone --format json` baseline | Exit 0 in about 5 s. JSON lines `step_start`, `text`. A short reply emitted no `step_finish`, so baseline token usage has to be read from the isolated session store after the run. | `probe_misc.json` |
| 10 | Server killed mid-run; in-memory DB | The client sees SSE `ConnectionResetError` and refused requests. After restart on the same state, the session exists with `outcome: null` and is not active, which is detectable as **lost**. `OPENCODE_DB=:memory:` leaves no DB files, and the session is gone after restart. | `probe_misc.json`, `probe_lifecycle.json` |

**Credential-leak baseline** (`probe_lifecycle.json` → `leak_scan`):
- A value that lives only in the server env never reached the OpenCode data directory.
- A value **printed by a shell command** was stored in `opencode.db` **and** in `shell/<hash>/<id>.out`.

This is the direct evidence for the operator's custody requirement. Anything a model-controlled process can print is persisted by the harness. So raw AEW credentials must never be in a model-controlled process at all (M3 plan §2.3).

## 5. V2 behaviour the adapter must handle (found by the spike or in source)

1. **The model catalog loads asynchronously.** The first `GET /api/model` on a fresh state returned `[]`, and 8 models appeared 0.6–5 s later. Health polls with a deadline and never treats an early empty catalog as "model missing".
2. **Invalid models and variants are accepted at session create** (200) and fail only at execution (`provider.no-route: Variant unavailable`). AEW validates the pinned `providerID/id#variant` against `GET /api/model` **before prompting** and refuses the launch otherwise. There is never a silent fallback.
3. **Windows 8.3 short paths break project and home detection.** A workspace given as `C:\Users\JONSMI~1\…` was treated as outside `C:\Users\Jon Smith`: `AGENTS.md` was not loaded and `subpath` was a long `../` chain. AEW passes `os.path.realpath` long paths as `location.directory`.
4. **An agent's configured model is not applied to API-created sessions.** Session create without `model` got the catalog default. AEW sets `model{providerID,id,variant}` on create.
5. **Session-create `permissions` are appended last** (last match wins), so they can override agent rules. AEW sends the complete rule set on create, and every rule is allow or deny, never `ask`.
6. **Completion is confirmed three ways:** terminal execution event, `…/wait`, and the message list or `outcome`. This mirrors the official `run`. The SSE stream is volatile, and `…/log?after=<seq>&follow=true` replays gaps.
7. **Shell outputs are persisted** under the data dir (`shell/…/*.out`) as well as in the DB. A per-run data dir makes them disposable, and the run's post-run scan covers them.

## 6. Model answers used for #6

The prompt was "list the exact names of every skill you have been told is available to you", sent to `opencode/longcat-2.5-preview-free` on the 2.0.18 private server. The workspace was under the home directory, with an ancestor `.claude` skill and project `.opencode` and `.agents` skills:

| Configuration | Skills the session was told about |
|---|---|
| project config on, everything allowed | ancestor-claude-skill, built-in-browser, chrome-browser, computer-use, deep-research, docs, docx, google-workspace, import-memory, morning, opencode, pdf, pptx, project-agents-skill, project-opencode-skill, report, skill-creator, xlsx |
| project config **off** | built-in-browser, chrome-browser, computer-use, deep-research, docs, docx, google-workspace, import-memory, morning, opencode, pdf, pptx, report, skill-creator, xlsx (**the user's global skills still leak**) |
| project config off + **compatibility plugin disabled** | opencode, report (built-ins only) |
| project config off + **`skill` denied** | NONE |
| project config on + compatibility plugin disabled | opencode, project-opencode-skill, report |

**Decision:** AEW invocation runs use all three controls: project config off, compatibility plugin disabled, and `skill` denied except for the card's skills. A card's skills must be supplied explicitly through config `skills` entries. AEW authors none in M3; an unmapped skill is reported as `unavailable` (WC §16.10). The Lead's own TUI runs in the operator's normal OpenCode environment, whose skills are the operator's choice.

## 7. Known gaps (reported, not emulated)

- There is **no stability guarantee** for the V2 HTTP API or clients. Mitigation: pinned binary; a capability probe (required operations and fields in the served OpenAPI) at every launch; a live conformance lane.
- `serve --stdio` is **undocumented**: it appears only in help and source. `run --standalone` is documented and uses it. AEW uses the lease when present, but **does not depend on it**: the supervisor owns the process tree through a job object (Windows) or a process group (POSIX).
- There is **no documented isolation recipe**. The XDG, `OPENCODE_DISABLE_PROJECT_CONFIG` and plugin-disable combination was established by this spike.
- `wait`, `log`, export, import and stats are **experimental** routes.
- **`/api/skill` returned an empty list** even when skills were demonstrably exposed. Skill exposure therefore cannot be verified through the API. It is controlled by config and permissions, and checked in conformance by asking the model.
- An escape from the job object through an out-of-tree spawner (WMI, scheduled tasks) is outside the harness boundary. It is irrelevant to authority: rotation and revocation close the credential bridge (M3 plan §2.3).

## 8. Effect on the plan

- **HarnessAdapter contract:** unchanged and harness-neutral (`health`, `launch`, `send`, `interrupt`, `terminate`, `inspect`, `collect`). V2 changes the implementation only: `interrupt` → `/interrupt`; `send` → prompt `delivery: queue`. `steer` works, but M3 does not expose it; it is reserved for coordination.
- **Disposability:** improved. Each run gets private XDG state, or `OPENCODE_DB=:memory:`. Destroying session state is deleting a directory. AEW never reads harness state to reconstruct.
- **Future coordination:** V2 can deliver a bounded delta into a running loop (`steer`, confirmed). Nothing in M3 blocks the frozen coordination design, and per-turn `run` was rejected partly for that reason.
- **No lifecycle operation assumed by the plan is unsupported by V2.**
