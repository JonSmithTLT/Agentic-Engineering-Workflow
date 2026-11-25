**The guide's core plus pointers (2026-11-25).** The Lead's guide is now a core, which every request carries, and ten
named sections read on demand with `aew guide <section>`; `aew guide` lists them and `aew guide core` prints the core.
All come from `engine/guide.py`'s `document()`, so each fact has one owner. The core keeps who the Lead is, every
authority and safety rule (each marked `guide.Rule` at its source, and a test derives the list from the marks), the
typed tools and when to use each, and one pointer per section. The core also names the operator's approval channels,
which the system text's "as the guide says" pointed to with nothing behind it. `aew guide` is a relayed read for the
contained Lead, so it adds no tool and no bytes to the tool list.

**Measured with the pool gate's own render.** With messaging on, the guide went from 17,338 B to 9,437 B, a saving of
7,901 B. With messaging off, it went from 17,160 B to 9,214 B. Under the pool's rule, the baseline's guide bytes
dropped from 16,412 B to 8,511 B and the cap from 42,971 B to 35,070 B. The operator approves that cap, or records an
allocation from the saving.

**The failure criterion's counters.** Each line of the broker's typed-tool log now names its Lead session and
generation. The same log also holds a line for each relayed `aew guide` read and each `--help` lookup the Lead's shell
makes. `tool_calls.counters` counts these per session, and `aew lead telemetry` prints them for UAT, the dogfood and
the probe: typed calls; refused calls, defects and calls with invalid arguments; guide reads by section; and help
lookups by command.

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
- At this branch, it carried 26,272 B of instructions in a 48,003 B body.
- The tool list was 21,112 B in both, so the request is 7,929 B smaller.
- The branch's session showed up in `aew lead telemetry` with 3 typed calls and no misuse. The scripted model makes no
  guide reads or help lookups, so behaviour is UAT's to judge.

**What to watch in UAT** (`aew lead telemetry`, per session, beside the transcript):
- Typed-tool misuse: refused calls, defects and calls with invalid arguments. Failure is misuse that rises against an
  earlier session's figures, or a step taken from the shell where a tool covers it.
- Help lookups: `--help` on a command the core names, or the same command looked up again and again, means the core
  failed to tell the Lead how to do it.
- Guide reads by section: a section read in nearly every session belongs back in the core, or its pointer's trigger
  is wrong. A section never read is fine.
- Class choice: Class 0 chosen where it fits, now that the class detail sits behind `aew guide classes` (X4's
  finding).
- The core's rules: no `aew evidence ingest` on a mutating Ticket; free text never on a command line; nothing acted on
  because a chat line said the operator approved it.
