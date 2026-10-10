# F9-A MS0: how OpenCode 2.0.18 delivers a Lead input (probe results)

The probe ran on 2026-10-09 and 2026-10-10 on both MS0 hosts, and its results decide
[ADR-0017](../../0017-coordination-messages.md) D8's transport. This page is the sanitized form of the probe's report;
the per-run data are the tables and JSON files beside it ([README](README.md)).

- **Windows:** the pinned OpenCode Desktop CLI 2.0.18 (sha256
  `78f454c0a1581b66ce4f264f42bfaee6207c887053d8e4b02c4c9cfb74e90668`). Every process ran with `CREATE_NO_WINDOW` inside
  AEW's own `ProcessTree` job.
- **The Rocky 8 reference host** (Rocky 8.10, kernel 4.18, SELinux enforcing, bubblewrap 0.4.0): the pinned Linux CLI
  2.0.18 (sha256 `67d8275630aa3dfe5409c6c2e1bb44ab0cf0d9558a6593e769342b9f1dc93f4b`). Every server ran inside AEW's own
  bubblewrap layout (`layout.for_run`, an investigator role with a read-only workspace).

Both binaries report `opencode v2.0.18`, and `/api/info` returned `2.0.18` in every run; the probe stops on any other
version.

**The model was a scripted fake** OpenAI-compatible server on 127.0.0.1, not the free model MS0 specified: no
provider and no credential were used (the departure is recorded in ADR-0017 D8 and in the probe's docstring). AEW's
code was a frozen export of `origin/main` at `2baf431`, imported read-only.

There were 31 cases, each run twice on each host: 124 runs. Every pair agrees, and the two hosts agree on every
behaviour.

## The answer

**`delivery: "queue"` is not admitted at the next step boundary. `steer` is.**

- **Queue.** OpenCode 2.0.18 admits a queued input only when the agent's loop would otherwise end: after a model step
  that makes no tool call (the model's final answer). The input then reopens the loop in the same execution.
  - The probe posted during a 30 s shell step and during a 15 s model call.
  - The queued input was admitted only after 1 further model request (a one-step turn) or 3 (a turn with two more tool
    steps).
  - With a real model, "queue" means "after the worker has finished its turn", not "at the next step".
- **Steer** is admitted at the next step boundary, 0.04 to 0.08 s after the running step ends, with no model request
  in between.
  - It never aborted or truncated a tool. A 30 s shell ran to the end; two parallel shells (30 s and 4 s) both ran to
    the end; a model call in flight was answered.
  - Five rapid steer posts arrived in post order, all in the next model request.

So the transport is `POST /api/session/{id}/prompt` with `delivery: "steer"`. It works on both hosts; neither is
`unsupported`.

**D-22's bound is 90 s.** OpenCode's shell tool has a fixed 120,000 ms default timeout for foreground commands, and no
configuration key changes it. Commands of 120, 300 and 600 s with no `timeout` argument all returned at 119.9 to
120.1 s with "Command exceeded timeout of 120000 ms", and the command was killed. An explicit `timeout` is honoured,
and `timeout: 0` disables it. The model chooses that argument, so the default is the binding case:
min(600, 120 − 30) = **90 s**.

## P1 and P2: mid-turn `queue` and `steer`

"After step end" is the time from the end of the step running when the input was posted (the shell's end marker, or
the delayed model call's answer) to the `session.inbox.delivered` event. Per-run rows: [`table-windows.md`](table-windows.md)
and [`table-rocky8.md`](table-rocky8.md).

| Case (2 runs per host) | Delivery | Posted during | Model requests between the step and admission | After step end (Windows / Rocky) | Running tool |
|---|---|---|---|---|---|
| p1-queue-shell | queue | a 30 s shell step | 1 (the model's final answer) | 0.06 s / 0.09–0.13 s | completed (30.1 s) |
| p1-queue-shell-multi | queue | a 30 s shell step, then 2 more tool steps | 3 | 0.12–0.14 / 0.19–0.21 | completed |
| p1-queue-model | queue | a 15 s model call | 1 | 0.06 / 0.11–0.12 | n/a |
| p1-queue-model-multi | queue | a 15 s model call, then 2 more tool steps | 3 | 0.11–0.13 / 0.23–0.26 | n/a |
| p2-steer-shell, p2-steer-shell-multi | steer | a 30 s shell step | **0** | **0.045–0.054 / 0.046–0.053** | completed, full output ("slept 30 s") |
| p2-steer-model, p2-steer-model-multi | steer | a 15 s model call | **0** | **0.042–0.045 / 0.065–0.079** | the model call was answered, not aborted |
| p2-steer-parallel | steer | two parallel shells (30 s and 4 s), posted after the short one ended | **0** | **0.046 / 0.040–0.043** | both completed |

The queue latency looks small only because the fake model answers instantly; what matters is the column of model
requests in between: a queued input waits for every remaining step of the turn.

- **The REST check works for both modes.** `GET /api/session/{id}/message/{msgID}` answers 404 while an input is
  queued and 200 from admission, within the 0.2 s poll after `session.inbox.delivered` in every run.
- **The source agrees** (`src-excerpts.txt`): `SessionRunner.drain` promotes only `steer` items between steps, and
  `queue` items only when the loop would complete, one at a time.

## P3: idle sessions

- **(a) Held after a Lead interrupt** (`p3a-held`, `p3a-held-steer`). The interrupt aborts the running shell ("Tool
  execution interrupted") and the adapter goes to `held`. An input posted with `resume: false` stays in the inbox, with
  the session inactive, for at least 8 s. The next post with the default `resume` wakes the session, and the staged
  input is delivered first (with queue, one per model round; with steer, both together in order in one request).
- **(b) The closing window.** An input posted during the final model call is delivered right after that step, in the
  same execution. An input posted just after `session.execution.succeeded`, while the adapter was still `running`,
  starts a new execution 0.04 to 0.08 s later; the adapter's two-poll rule waits for it and ends the run correctly.
- **(c) `resume: false`.** On an idle session the input is held (at least 8 s) and delivered first at the next wake. On
  a busy session it has no effect: the running loop delivers it like any other input.

## P4: ordering

| Case | Delivered order (both hosts, both runs) |
|---|---|
| p4-five-queue (O1 to O5, posted in under 50 ms) | O1 > O2 > O3 > O4 > O5, one per model round, all after the turn's final step: 5 extra model requests |
| p4-five-steer (S1 to S5) | S1 > S2 > S3 > S4 > S5, all at the next step boundary in one model request |
| p4-mixed (M1q, M2s, M3q, M4s, M5q) | **M2s > M4s > M1q > M3q > M5q**: steer overtakes queue |

Order is kept within one delivery mode, never across modes.

## P5: the same id posted twice, and 409s

- **A re-post is idempotent per session.** The same id to the same session never gets a 409: it gets **200 with the
  first post's inbox item** (same id, `time.created`, text and delivery), and any changed text or delivery is ignored.
  This holds while the item is still queued and after it was admitted.
- After admission, a re-post with the default `resume` returns the delivered message as the item and **wakes the idle
  session into an empty execution** (`execution.started`, then `succeeded`, then a new `idle` message), with no model
  request and no second message.
- **A 409 `ConflictError`** (`resource` set to the id) means the id belongs to a different record: another session, or
  an assistant or idle message.
- A session that does not exist gives 404 `SessionNotFoundError`; a malformed id gives 400 `InvalidRequestError`.
- Exactly one message with the id existed in every run. The source shows why: `SessionInbox.reconcile` returns an
  existing item whenever the session and the type match, and the conflict becomes the 409 only when the id belongs to a
  different record.

**The response bodies, with ids only** (from each run's `posts.jsonl` by `p5_table.py`; no message text). "Same"
compares the returned item with the one the first post (X-1) returned; after admission (X-4) OpenCode returns the
delivered message, whose `time.created` is its admission time.

| host | run | post | delivery sent | status | answer (ids only) |
|---|---|---|---|---|---|
| windows | p5-duplicate-1 | X-1 | queue | 200 | item `msg_28013508f9dfa1b23b30658b` (same id: yes; same `time.created`: yes; same text: yes; delivery `queue`) |
| windows | p5-duplicate-1 | X-2-same | queue | 200 | item `msg_28013508f9dfa1b23b30658b` (same id: yes; same `time.created`: yes; same text: yes; delivery `queue`) |
| windows | p5-duplicate-1 | X-3-changed | steer | 200 | item `msg_28013508f9dfa1b23b30658b` (same id: yes; same `time.created`: yes; same text: yes; delivery `queue`) |
| windows | p5-duplicate-1 | X-4-after-delivery | queue | 200 | item `msg_28013508f9dfa1b23b30658b` (same id: yes; same `time.created`: no; same text: yes; delivery `queue`) |
| windows | p5-duplicate-1 | X-5-other-session | queue | 409 | `ConflictError`, names `msg_28013508f9dfa1b23b30658b` |
| windows | p5-duplicate-1 | X-6-assistant-id | queue | 409 | `ConflictError`, names `msg_12402293f001UhgABMXCEgocZr` |
| windows | p5-duplicate-1 | X-7-idle-id | queue | 409 | `ConflictError`, names `msg_124027a04001bN4SjzahBjJSWO` |
| windows | p5-duplicate-1 | X-8-no-session | queue | 404 | `SessionNotFoundError`, names `ses_00000000000000000000000000` |
| windows | p5-duplicate-1 | X-9-bad-id | queue | 400 | `InvalidRequestError` |
| windows | p5-duplicate-2 | X-1 | queue | 200 | item `msg_3d825e2f5d3fd378ad642dd3` (same id: yes; same `time.created`: yes; same text: yes; delivery `queue`) |
| windows | p5-duplicate-2 | X-2-same | queue | 200 | item `msg_3d825e2f5d3fd378ad642dd3` (same id: yes; same `time.created`: yes; same text: yes; delivery `queue`) |
| windows | p5-duplicate-2 | X-3-changed | steer | 200 | item `msg_3d825e2f5d3fd378ad642dd3` (same id: yes; same `time.created`: yes; same text: yes; delivery `queue`) |
| windows | p5-duplicate-2 | X-4-after-delivery | queue | 200 | item `msg_3d825e2f5d3fd378ad642dd3` (same id: yes; same `time.created`: no; same text: yes; delivery `queue`) |
| windows | p5-duplicate-2 | X-5-other-session | queue | 409 | `ConflictError`, names `msg_3d825e2f5d3fd378ad642dd3` |
| windows | p5-duplicate-2 | X-6-assistant-id | queue | 409 | `ConflictError`, names `msg_12402ae10001osDrbqMKBikjVR` |
| windows | p5-duplicate-2 | X-7-idle-id | queue | 409 | `ConflictError`, names `msg_12402fec9001BtyfQW1hCAcBF2` |
| windows | p5-duplicate-2 | X-8-no-session | queue | 404 | `SessionNotFoundError`, names `ses_00000000000000000000000000` |
| windows | p5-duplicate-2 | X-9-bad-id | queue | 400 | `InvalidRequestError` |
| rocky8 | p5-duplicate-1 | X-1 | queue | 200 | item `msg_52a07b3d8a1f2d0ec9dd3aee` (same id: yes; same `time.created`: yes; same text: yes; delivery `queue`) |
| rocky8 | p5-duplicate-1 | X-2-same | queue | 200 | item `msg_52a07b3d8a1f2d0ec9dd3aee` (same id: yes; same `time.created`: yes; same text: yes; delivery `queue`) |
| rocky8 | p5-duplicate-1 | X-3-changed | steer | 200 | item `msg_52a07b3d8a1f2d0ec9dd3aee` (same id: yes; same `time.created`: yes; same text: yes; delivery `queue`) |
| rocky8 | p5-duplicate-1 | X-4-after-delivery | queue | 200 | item `msg_52a07b3d8a1f2d0ec9dd3aee` (same id: yes; same `time.created`: no; same text: yes; delivery `queue`) |
| rocky8 | p5-duplicate-1 | X-5-other-session | queue | 409 | `ConflictError`, names `msg_52a07b3d8a1f2d0ec9dd3aee` |
| rocky8 | p5-duplicate-1 | X-6-assistant-id | queue | 409 | `ConflictError`, names `msg_124407901001OGeaJCOGWSZgay` |
| rocky8 | p5-duplicate-1 | X-7-idle-id | queue | 409 | `ConflictError`, names `msg_12440c812001vNLBhmyXA0uzVz` |
| rocky8 | p5-duplicate-1 | X-8-no-session | queue | 404 | `SessionNotFoundError`, names `ses_00000000000000000000000000` |
| rocky8 | p5-duplicate-1 | X-9-bad-id | queue | 400 | `InvalidRequestError` |
| rocky8 | p5-duplicate-2 | X-1 | queue | 200 | item `msg_73634059e4e560ed28503268` (same id: yes; same `time.created`: yes; same text: yes; delivery `queue`) |
| rocky8 | p5-duplicate-2 | X-2-same | queue | 200 | item `msg_73634059e4e560ed28503268` (same id: yes; same `time.created`: yes; same text: yes; delivery `queue`) |
| rocky8 | p5-duplicate-2 | X-3-changed | steer | 200 | item `msg_73634059e4e560ed28503268` (same id: yes; same `time.created`: yes; same text: yes; delivery `queue`) |
| rocky8 | p5-duplicate-2 | X-4-after-delivery | queue | 200 | item `msg_73634059e4e560ed28503268` (same id: yes; same `time.created`: no; same text: yes; delivery `queue`) |
| rocky8 | p5-duplicate-2 | X-5-other-session | queue | 409 | `ConflictError`, names `msg_73634059e4e560ed28503268` |
| rocky8 | p5-duplicate-2 | X-6-assistant-id | queue | 409 | `ConflictError`, names `msg_12440fc72001DJt6qOgb1B4Quo` |
| rocky8 | p5-duplicate-2 | X-7-idle-id | queue | 409 | `ConflictError`, names `msg_124414b84001S53b9WBuXssYO3` |
| rocky8 | p5-duplicate-2 | X-8-no-session | queue | 404 | `SessionNotFoundError`, names `ses_00000000000000000000000000` |
| rocky8 | p5-duplicate-2 | X-9-bad-id | queue | 400 | `InvalidRequestError` |

## P6: what the worker sees

- **The text arrives verbatim**, as a plain user message: D-23's framing, the body and the reply line.
- **Metadata never reaches the model.** None of `aew_message`, `aew_thread` or a probe key appeared in any model
  request, on either host.
- **Metadata is stored.** `GET /api/session/{id}/message/{msgID}` and `/api/session/{id}/context` return it on the user
  message, so D-23's "correlation only" holds.
- The framing's effect on a real model was not measured: a scripted model cannot answer that.

## P7: session loss

- **Killing the server with an input queued:** the adapter's `_server_gone` ended the run 1.1 to 2.1 s later on
  Windows (exit 1) and 0.10 to 0.26 s later on Rocky (exit −9); REST is refused after that.
- **A new server on the same private state** (which AEW never does): the session and the inbox item are still there,
  but nothing is resumed or delivered within 15 s. AEW discards a run's state, so an undelivered input is lost with it,
  which D-29's "sent to an earlier run; delivery unconfirmed" covers.
- **The two 404s can be told apart:** a missing session gives `SessionNotFoundError` on every path, including the
  prompt endpoint; an unknown message id on a live session gives `MessageNotFoundError`. The adapter's `_poll` reads any
  404 on a message as "still queued" today; the `_tag` separates the two.

## P8: platform parity

Every result holds identically on Windows and on the Rocky 8 host under bubblewrap. The server ran inside AEW's layout
and was reached on 127.0.0.1, and it reached the fake model on host loopback: the layout's shared network namespace
works as the plan assumes. No SELinux denial was seen and every run worked, but the audit log needs root, so the
absence of AVCs is not proven.

## P9: the shell tool's timeout (D-22)

| Command (2 runs per host) | Windows: tool returned after | Rocky: tool returned after | Outcome |
|---|---|---|---|
| sleep 120 s, no `timeout` | 120.00–120.02 s | 120.06–120.11 s | "Command exceeded timeout of 120000 ms…"; no end marker |
| sleep 300 s, no `timeout` | 119.96–120.10 | 120.07–120.10 | the same |
| sleep 600 s, no `timeout` | 119.92–119.99 | 120.06–120.07 | the same |
| a 5 s heartbeat for 300 s, no `timeout` | 120.04–120.06 | 120.06–120.07 | the last heartbeat was at 116.8 to 117.2 s: **the command is killed** |
| sleep 300 s, `timeout: 360000` | 300.11 | 300.08–300.12 | completed |
| sleep 600 s, `timeout: 0` | 600.2–603.3 | 600.11–600.17 | completed (the timeout is disabled) |

The source has `gy=120000`, applied as `N.timeout ?? gy` for foreground commands, with no configuration lookup.

## Further finding: a delivered input restarts the step limit

With `steps: 4`, a run without a message made 4 model requests, and the 4th tool call was refused ("Tools are disabled
after the maximum agent steps"). With one steer delivered after step 1, it made 5. The counter restarts at every
promoted input (source: `if(pe>0)ee=1`), on both hosts (`p2-steps-none`, `p2-steps-steer`). So the profile's
`max_steps` bounds each delivered input, not the run: register row E54, against ADR-0010 and the harness.

## The decision rule applied

- **Transport: `steer`.** Queue fails P1: admission comes after 1 to 3 further model requests (the end of the turn),
  not within the current step's end plus 5 s. Steer passes P2 on both hosts, and P4 shows its order kept.
- **Held case: stage with `resume: false`.** It holds until the next wake on both hosts, and is delivered first.
- **P5: no 409 ever marks a duplicate.** A re-post is idempotent; a 200 returns the first item.
- **D-22's bound: 90 s.**
- **No host reports `unsupported`.** A host would only if the chosen transport failed its question (P2 and P4 for
  steer) or P3, P5 or P7 contradicted the rule built on them; queue failing P1 does not make a host unsupported.

## Limits

- **A fake model, not a free one** (above). The mechanics and timings are OpenCode's own. Model behaviour was not
  measured: how a real model reacts to the framing (P6), or how it spends the steps a queued input waits behind. MS7's
  live check covers steer's mechanics with a real model.
- **Containment on Windows** was AEW's job object; on Rocky, AEW's bubblewrap layout with no bridge. The supervisor
  process itself was not used.
- **Whether a shell-timeout kill also ends the shell's children** was not measured (P9's kill check ran its heartbeat
  in the shell itself). U1's S0 probe measures it; ADR-0017 D8's rule for `message.wait` holds either way.
- **Probe defects fixed along the way,** each followed by rerunning the affected case on both runs: a Windows
  file-lock race when reading a marker file (one `p3a-held` run, rerun); and on Rocky, the first `p7-kill` runs could
  not start the restart server (the killed server had led the process group, and the fresh-state directory sat outside
  the layout).
