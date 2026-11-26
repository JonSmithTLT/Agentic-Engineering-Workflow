**The guide's core plus pointers (2026-11-25).** The Lead's guide is now a core, which every request carries, and ten
named sections read on demand with `aew guide <section>`; `aew guide` lists them and `aew guide core` prints the core.
All come from `engine/guide.py`'s `document()`, so each fact has one owner. The core keeps who the Lead is, every
authority and safety rule (each marked `guide.Rule` at its source, and a test derives the list from the marks), the
typed tools and when to use each, and one pointer per section. The core also names the operator's approval channels,
which the system text's "as the guide says" pointed to with nothing behind it. `aew guide` is a relayed read for the
contained Lead, so it adds no tool and no bytes to the tool list.

**Measured with the pool gate's own render**, at main 5649d832, where E160's plan-assessment line, now in the core,
is part of the guide. With messaging on, the guide went from 17,445 B to 9,154 B, a saving of 8,291 B. With messaging
off, it went from 17,267 B to 8,934 B. Under the pool's rule, the baseline's guide bytes dropped from 16,412 B to
8,121 B, and the derived ceiling to 34,680 B. The operator set the cap at 40,000 B on 2026-11-26, as an anti-bloat
guard; the 5,320 B between the two is the record's `operator_reserve`, which only an operator-attributed reserve may
hold.

**The failure criterion's counters.** Each line of the broker's typed-tool log now names its Lead session and
generation. The same log also holds a line for each `aew guide` read and each `--help` lookup the Lead's shell makes:
a contained session's broker counts the reads it relays, and an uncontained session's `aew` tells its broker. A guide
read records only a section name the guide has. `tool_calls.counters` counts these per session, and `aew lead
telemetry` prints them for UAT, the dogfood and the probe: typed calls; calls that stopped, by error code (a stop is
not always misuse); defects and calls with invalid arguments; guide reads by section; and help lookups by command.

**What remains.**
- The worker packs come next, under the same principle and failure criterion.
- The system text's own fixes are left to the audit's PR: the "as the guide's first step shows" reference (that step
  is now in `aew guide steps`), its `aew guide` line, and its `--expect-rev` and refused-command lines.
- The scripted probe's calibration step is stale on `main`: its rendered system text and guide no longer match the
  wire, so it stops before writing its analysis. Its capture still works.
- Whether a sign-off "quoted from the operator" fits beside "approval only through the operator's own channels" is a
  question for the designer.

**The scripted probe, before and after.** These runs used the pinned OpenCode 2.2.6 in a loopback-only namespace,
with the same scripted turns.
- At main ee89c341, the Lead's first request carried 34,161 B of instructions in a 55,932 B body.
- At this branch's commit 6445f91f, it carried 26,272 B of instructions in a 48,003 B body. The
  head's core is 283 B shorter.
- The tool list was 21,112 B in both, so the request is 7,929 B smaller.
- The branch's session showed up in `aew lead telemetry` with 3 typed calls and no misuse. The scripted model makes no
  guide reads or help lookups, so behaviour is UAT's to judge.

**What to watch in UAT** (`aew lead telemetry`, per session, beside the transcript):
- Typed-tool misuse: calls that stopped, read by error code, defects and calls with invalid arguments. Failure is
  misuse that rises against an earlier session's figures, or a step taken from the shell where a tool covers it.
- Help lookups: `--help` on a command the core names, or the same command looked up again and again, means the core
  failed to tell the Lead how to do it.
- Guide reads by section: a section read in nearly every session belongs back in the core, or its pointer's trigger
  is wrong. A section never read is fine.
- Class choice: Class 0 chosen where it fits, now that the class detail sits behind `aew guide classes` (X4's
  finding).
- The core's rules: no `aew evidence ingest` on a mutating Ticket; free text never on a command line; nothing acted on
  because a chat line said the operator approved it.
