# E231: what the typed Lead surface costs per request, against the shell fallback (2026-11-25)

Status: research, measured at `origin/main` `c08638d4` on 2026-11-25 for the operator. It is evidence for the
operator's decision on E231 (keep, raise, compact or consolidate), not that decision. It changes no cap, no pool record,
no requirement and no product behaviour.

## Summary

- **Fixed cost.** Every contained Lead request carries **38,649 B** with messaging on: system text 9,279 B, guide
  17,338 B, join 2 B and tool list 12,030 B for 16 tools. With messaging off it is **38,162 B**: 9,020 + 17,160 + 2 +
  11,980 B for 15 tools. The cap is 42,971 B. At a rough 4 B per token, which is not a pinned tokenizer, 38.6 KB is
  about 9.7k tokens.
- **Marginal cost of one typed row.** With messaging on (the compact presentation) a row costs a **mean of 751 B** on
  every request, ranging from **304 B** (`resume`) to **2,083 B** (`ticket_draft`), with a median of 730 B. With
  messaging off the mean is 798 B and the range 319 B to 2,143 B. Over the median Lead session of 34 requests, a
  mean-sized row costs about 25.5 KB. That is 0.66 of one extra request at the pool's own size.
- **Reads, in bytes alone.** For a read, the shell route is cheaper per use as well as per request. The typed
  `status` result the model reads is 7,231 B. `aew status` prints 3,520 B. For `work show` the figures are 2,359 B
  against 1,967 B. The difference is the typed tool's JSON payload, not its readable wrapper: the wrapper adds only
  609 B and 211 B. A typed read row therefore never pays for itself in bytes unless the shell route costs the Lead
  extra round trips: a `--help` lookup, a refused command line, or a second command to finish the job.
- **A2.** A `map` row is 605 to 633 B per request, about 20.6 to 21.5 KB per 34-request session. It breaks even only
  where the shell route costs extra requests. If one shell map read in two costs one extra request, A2 breaks even at
  about **1.6 to 1.7 map reads per session**. If every shell map read costs one extra request, it breaks even at
  **0.6 to 0.7**. If no shell map read costs an extra request, it never breaks even. Room is the binding limit, not
  break-even: the pool has no unallocated bytes, and a 17th tool exceeds TLS-21's 16-tool ceiling.
- **The guide's core plus pointers.** This split keeps "Who does what", the step-by-step, "Every command" and
  "Coordination messages", and makes the six other sections pointer lines. It would send 9,529 B of guide instead of
  17,338 B, **saving 7,809 B per request**. That is about 12 A2 rows. A leaner split that also moves the step-by-step
  saves 15,227 B.

## Method

Everything is measured offline and deterministically by one script,
[`tools/perf/lead_typed_vs_shell.py`](../../tools/perf/lead_typed_vs_shell.py), with no model. Two runs on one host
gave byte-identical JSON.

- **Fixed cost.** The script renders the pool as its gate renders it (`tests/unit/test_lead_context_pool.py`
  `render_pool`). It uses the pool record's containment fixture, default policies and push wakes, and an empty
  capability register, with messaging on and off. The tool list is `mcp.advertised_bytes`: compact JSON with ASCII
  escapes.
- **Row cost.** A row costs its entry in the list plus the comma that joins it. The rows' shares sum to the list.
- **Reads.** The script builds a fresh project through the real CLI: `aew init`, a Lead seat, one Class 1 Ticket with
  an accepted plan, and the map that a new project selects at init. It then reads each answer twice:
  - **typed:** with `aew lead tool <name>`, the same catalog and runner as MCP (TLS-22), measuring the MCP text block
    the model reads (`aew.surface.readable`);
  - **shell:** with the `aew` command's stdout.

  Both calls are counted as Responses API input items: a `function_call` item and its `function_call_output` item.
  The call turns are the scripted probe's own (`tools/lead_probe/session.py`, `typed` and `shell`, from #443). The
  item shape is the one its analysis reads back (`tools/lead_probe/measure.py`, `results`).
- **Shell guide lines.** A shell command that the guide does not name today needs a guide line before the Lead can use
  it. That line is derived from the CLI: the command, then its own parser help. It is 0 B when the guide already names
  the command.
- **Unit.** The unit is bytes. No tokenizer is pinned in this repository.
- **CI.** The script's run is an integration test (`tests/integration/test_lead_typed_vs_shell_run.py`), and its
  in-process parts are unit tests. Because the script reads the pool record, a change to that record now runs CI's
  full tier (`tools/ci/tier.py`, `SHARED`).

### What was not run, and why

The scripted OpenCode probe from #443 (`tools/lead_probe`) captures the real provider request. It needs the pinned
OpenCode 2.2.6 Linux binary, which `LEAD_PROBE_LINUX_X64_SHA256` checks, and `ip` with `unshare` for its loopback
namespace. Neither was available where this was measured: the package registry served no 2.2.6, and `ip` was absent.
So this note reuses the probe's turns and item shape, but not its captured wire bodies. Two consequences:

- OpenCode's own system text and built-in tools are not counted. They are paid by every route alike.
- The provider-side form of each AEW tool (its function definition, without MCP annotations) is not measured. The
  pool's MCP bytes are the cap's unit, so this note keeps them.

A probe run on a host with the pinned binary would replace both with captured figures. Its command is in
[harness conformance](../implementation/harness-conformance.md) item 7.

### The break-even model

A typed row is sent on every request. Each use's call and result stay in the conversation and are resent on every
later request until compaction. For a session of N requests and u uses of a read:

```
typed − shell = F·N + u·(D·(N−1)/2 − k·Q)
```

The terms are:
- **F:** the row, plus any typed guide line, minus the guide line the shell route needs (bytes per request).
- **D:** the typed call and result, minus the shell call and result (bytes per use). A use is resent on (N−1)/2
  later requests on average.
- **k:** the extra shell round trips per use: a `--help` lookup, a refused command line, or a second command.
- **Q:** one extra request's bytes. Q = 1× is the pool alone, 38,649 B, a lower bound. Q = 2× allows for OpenCode's
  own text and tools and the conversation so far.

The typed row is no more expensive than the shell route at u* = F·N / (k·Q − D·(N−1)/2). There is no break-even when
the denominator is zero or below.

**Session length.** N = 34 is the median contained Lead session in the M3 audit: 34 model or tool steps, from 29
sessions in 26 hardened runs ([lead workflow efficiency
v0.1](../design/proposals/lead-workflow-efficiency-design-v0.1.md)). That median session made 6 reads and 4
`harness wait` calls. The script also tabulates N = 20 and N = 68.

**Assumptions:**
- Uses are spread evenly across the session.
- Compaction does not run within N requests.
- Bytes are uncached. Provider prompt caching discounts resent bytes. It discounts the fixed rows and the resent
  results alike, so it changes the ratios less than the totals.

## Numbers

Reproduce with the worktree's own source on the path:

```sh
PYTHONPATH=$PWD/src python tools/perf/lead_typed_vs_shell.py          # a text report
PYTHONPATH=$PWD/src python tools/perf/lead_typed_vs_shell.py --json   # every figure below, and the N=20 and 68 columns
```

### Fixed cost per request

| | system | guide | join | tool list | total | tools |
|---|---:|---:|---:|---:|---:|---:|
| messaging on | 9,279 | 17,338 | 2 | 12,030 | **38,649** | 16 |
| messaging off | 9,020 | 17,160 | 2 | 11,980 | **38,162** | 15 |

The cap is 42,971 B. With messaging on, 4,322 B are unused. The pool record's open estimates already reserve that
room and more: E158 1,200 B, E160 300 B, E162 500 B and E176 3,000 B, 5,000 B in all. The pool's slack rule allows
this, because the slack is no more than the open estimates.

### Each row, messaging on (bytes per request, comma included)

| status | resume | work_show | explain | harness_status | harness_wait | checkpoint | steering |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 330 | 304 | 334 | 951 | 318 | 540 | 539 | 661 |

| resolve | ticket_draft | ticket_start | ticket_request_review | ticket_request_verification | ticket_prepare | integration_publish | message_send |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 796 | 2,083 | 803 | 845 | 952 | 914 | 663 | 986 |

### The reads (bytes the Lead's context gains per use)

| read | typed call + result | of which text | shell command | shell call + result | of which stdout | shell guide line |
|---|---:|---:|---|---:|---:|---:|
| status | 85 + 7,596 | 7,231 | `aew status` | 142 + 3,609 | 3,520 | 0 (named throughout) |
| work show | 111 + 2,672 | 2,359 | `aew work show <T>` | 152 + 2,259 | 1,967 | 24 |
| map show | not built (A2) | | `aew map show` | 144 + 2,637 | 2,471 | 105 |
| map search | not built (A2) | | `aew map search core` | 151 + 1,902 | 1,784 | 161 |

The sizes depend on the project's state. The fixture is a new, unconfigured project, so `status` carries its setup
hints in both routes. Most of the typed `status` text is its JSON line, 6,622 B of 7,231 B. That line is the result
the Lead acts on, with its revision, projection and hints. The shell prints the same facts as shorter human text. The
`work show` shell guide line is short because `work show` has no help string of its own.

### Break-even: uses per session at which the typed row costs no more (N = 34)

For each Q, the four figures are k = 0, k = ¼, k = ½ and k = 1 extra shell request per use.

| read | row | F (B/request) | D (B/use) | Q = 1×: k = 0, ¼, ½, 1 | Q = 2×: k = 0, ¼, ½, 1 |
|---|---|---:|---:|---|---|
| status | `status` | +330 | +3,930 | never, never, never, never | never, never, never, 0.9 |
| work show | `work_show` | +310 | +372 | never, 3.0, 0.8, 0.3 | never, 0.8, 0.3, 0.1 |
| map show or search | A2, 605 B | +605 | +413 (est.) | never, 7.2, 1.6, 0.6 | never, 1.6, 0.6, 0.3 |
| map show or search | A2, 633 B | +633 | +413 (est.) | never, 7.6, 1.7, 0.7 | never, 1.7, 0.7, 0.3 |

How to read the A2 rows:
- A2 is one tool for both map reads, so u counts map show and map search together.
- Its D is an estimate: the shell result, plus the smallest typed-over-shell difference measured on a built read
  (`work_show`'s 413 B).
- Its guide line is taken as the same length as the shell route's line, so the two cancel in F. A2 still needs a guide
  line of about 105 to 266 B from the pool on top of its row.

The longer the session, the less an occasional extra request is worth. At N = 68 and Q = 1×, the `work_show` and A2
rows need k ≥ ½ to break even.

**The other twelve rows.** For stages and waits, the shell fallback is several commands. The guide's "Shell fallback"
lines show it: `ticket_start` is an assign, a launch and a transition. A stage that replaces m commands saves about
m − 1 requests per use. With Q = 1×, a mean-sized row (751 B, 25.5 KB per 34-request session) is paid back by one use
per session that saves 0.66 of a request. So any multi-command stage used once per session pays for its row in bytes.

### The guide's core plus pointers

Guide sections, messaging on (bytes; the preamble is 202 B):

| section | bytes |
|---|---:|
| Who does what | 779 |
| Choosing a risk class | 2,818 |
| What each class requires in this project | 2,057 |
| Before the first Ticket | 1,082 |
| A mutating Ticket, step by step | 7,506 |
| Non-mutating Tickets: investigation, research, planning | 833 |
| Stories and Epics | 857 |
| Finished work | 680 |
| Every command | 347 |
| Coordination messages | 177 |

The script tests two splits. Neither is a design:
- **"keep the steps"** keeps "Who does what", "A mutating Ticket, step by step", "Every command" and "Coordination
  messages". The six other sections move behind pointer lines.
- **"lean"** also moves the step-by-step.

Each moved section becomes a one-line pointer under one heading, about 70 to 110 B each. The pointer's command is
hypothetical; only its length counts.

| split | moved | table of contents | guide sent | saving per request | per 34-request session |
|---|---:|---:|---:|---:|---:|
| keep the steps | 8,327 | 518 | 9,529 | **7,809** | 265.5 KB |
| lean | 15,833 | 606 | 2,111 | **15,227** | 517.7 KB |

**The cost of a pointer.** Each on-demand read costs one request, plus the section resent on the remaining
requests. Take "keep the steps": a moved section averages 1,388 B. Read once mid-session, it costs about
38,649 + 1,388 × 16.5 ≈ 61.6 KB at Q = 1×. The split's 265.5 KB per session therefore pays for about four on-demand
reads per session.

**Against A2.** A2's row (605 to 633 B) plus a guide line (about 105 to 266 B) needs about 0.7 to 0.9 KB per request.
The "keep the steps" saving is about nine to eleven times that. The pool's rule for a smaller rendered pool would
lower the baseline and the cap by the saving. So the room exists only if the operator chooses to keep part of the
saving for A2, recorded as an allocation. Freed bytes do not help with A2's other limit: a 17th tool.

## What the evidence supports

This section is evidence for the operator, not a decision.

**The operator's direction (2026-11-25).**
- The rule: "A typed tool should be in place for things a lead does often enough we should give them a more
  structured and consistent way to do it." And: "I think thats a better mechanism than arbitrary caps and bytes."
- The cap's purpose, in the operator's words: "to prevent oh we have unlimited tools add 400. Not because we have some
  magical research."
- Read with this measurement, the byte cap stays an anti-bloat guard. It is raised by measured amounts when a tool
  earns its place by that rule.
- TLS-21's 16-tool ceiling is the designer's requirement. Raising it, excepting a tool from it, or keeping it as it
  is needs the designer's ruling. This note does not change it.

**What the measurement shows:**

1. **Bytes alone do not justify the typed read tools.** A typed read costs more per request (its row) and more per use
   (its JSON result) than `aew` in the shell. It saves bytes only by saving the Lead extra requests. That is the same
   thing the operator's rule names: a structured, consistent way to do a frequent thing, with fewer refusals and
   lookups. Whether a read saves requests is a behavioural question that this offline measurement cannot settle. The
   live probe, or F19's preregistered dogfood (refusals, `--help` lookups and steps per session, TLS-27), can.
2. **The rows are not the largest lever.** One `status` read leaves 7.7 KB in the context for the rest of the session,
   about 3.9 KB more than the shell route. Resent over half a 34-request session, that is about 65 KB: nearly six
   times its row's 11 KB. The size of the typed result payload (its hints and projection) costs more per session than
   the row that offers it. This note measures it; it proposes no change.
3. **A2.** It pays for itself in bytes only if a shell map read often costs an extra request: about 1.6 to 1.7 map
   reads per session with one in two shell reads costing one, and fewer at Q = 2×. Under the operator's rule, the
   question is instead whether the Lead reads the map often enough. The two limits on room are separate from
   break-even: no unallocated bytes in the pool, and TLS-21's ceiling, which only the designer can rule on.
4. **The guide's core plus pointers frees far more than A2 needs.** The conservative split saves 7.8 KB per request.
   Each on-demand section read costs a request, so the split pays off unless the Lead reads more than about four moved
   sections per session.

**Measured now:**
- the fixed pool by part, messaging on and off;
- every row's marginal bytes;
- the four reads' typed and shell bytes on a fixture project;
- the break-even model and its table, including A2;
- the core-plus-pointers saving for two splits.

**Not measured:**
- OpenCode's own request bytes and the provider form of the tool list (the pinned probe binary was unavailable);
- how often a shell read costs the Lead an extra request (k). That needs live sessions;
- the bytes of a built A2 result;
- tokens under a pinned tokenizer;
- the effect of caching and compaction.
