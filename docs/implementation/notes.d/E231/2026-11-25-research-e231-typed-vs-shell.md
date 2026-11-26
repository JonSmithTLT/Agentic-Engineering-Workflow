**The combined measurement, for the operator's decision
([research](../../../research/e231-typed-vs-shell-2026-11-25.md), 2026-11-25).** Measured offline by
`tools/perf/lead_typed_vs_shell.py` at `c08638d4`.

- **Fixed cost per request:** 38,649 B with messaging on (system 9,279 B, guide 17,338 B, join 2 B, tool list
  12,030 B, 16 tools) and 38,162 B with it off, under the 42,971 B cap.
- **One typed row:** a mean of 751 B per request, from 304 B to 2,083 B, which is about 25.5 KB over the median
  34-request Lead session.
- **Reads:** for status and work show, the shell route is cheaper per request and per use. A typed read row breaks
  even only when the shell costs extra requests (`--help` lookups, refusals, more commands). A multi-command stage used
  once a session pays for its row.
- **A2 (`map`, 605 to 633 B):** it breaks even at about 1.6 to 1.7 map reads per session if one shell map read in two
  costs an extra request. It never breaks even on bytes if none does. Its limits are room in the pool and TLS-21's
  ceiling.
- **The guide's core plus pointers:** keeping the step-by-step and moving six sections behind pointers saves an
  estimated 7,809 B per request, about 12 A2 rows. Under the pool's rule, a saving lowers the cap unless the operator
  records an allocation from it.

**The operator's direction (2026-11-25).** The rule: "A typed tool should be in place for things a lead does often
enough we should give them a more structured and consistent way to do it." And: "I think thats a better mechanism
than arbitrary caps and bytes." On the cap's purpose: "to prevent oh we have unlimited tools add 400. Not because we
have some magical research." So the byte cap stays as an anti-bloat guard, raised by measured amounts when a tool
earns its place. TLS-21's 16-tool ceiling is the designer's requirement and needs the designer's ruling. This note
does not change the cap, the pool record or TLS-21.

**Still not measured:**
- OpenCode's own request bytes and the provider form of the tools: the pinned 2.2.6 probe binary was not available,
  so `tools/lead_probe` was not run;
- how often a shell read costs the Lead an extra request, which needs live sessions or F19;
- a built A2 result;
- tokens under a pinned tokenizer;
- caching and compaction.

The keep, raise, compact or consolidate choice remains the operator's.
