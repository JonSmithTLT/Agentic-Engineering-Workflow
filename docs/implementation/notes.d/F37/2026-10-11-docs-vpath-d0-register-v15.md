**D4 binds this row (the designer's Decision Record of 2026-10-12 on the publication path, relayed by the operator).**
Verbatim:

```text
D1 — APPROVED: The vertical gate does not require implementing F33, F37, or an external publication capability that
does not currently exist.

D4 — BINDING FUTURE CONDITION: Before enabling any authorized external-publication path, enforce F37 sanitization and
trusted operator publication authorization, including applicable previously authorized publication envelopes.
```

Before any authorised external-publication path is enabled (F33's push, for example), this row's sanitisation is
enforced on it, with the operator's publication authorisation. Reading D4's "previously authorized publication
envelopes" as pre-granted publish authority, so that a publication grant reaching an external path (E6b's grants, M4-H's
sealed-manifest `PUBLISH_IF_CLEAN` grant) passes this row's sanitisation too, is the Lead's reading, not a ruling: see
the notes on F47 and F15.5, which leave it to be confirmed with the designer. Under D1 the vertical gate does not
require this row, and nothing schedules it; its target is unchanged.

**The canonical outbound sanitiser is now in this row's scope (the designer's decisions of 2026-10-12 on the Lead's
experience-log batch 3, relayed by the operator).** The proposal was a new engine-owned sanitiser on every publish and
comment path; the ruling assigns it here instead, explicitly integrated with M6's egress restrictions, with no parallel
subsystem. It is the same owner as the one canonical redaction-pattern source in the earlier note (AIR-59): every egress
path uses one F37 policy, internal evidence stays byte-exact, and sanitised copies are traceable. It fails closed on
protected terms (Decision 2, approved as the Lead recommended):

| Detected | Behaviour |
|---|---|
| Credentials, tokens, secrets | Block |
| Configured private names and terms | Block |
| Local filesystem paths | Deterministic redaction permitted |
| A path containing a configured private term | Block |
| An ambiguous or unsafe redaction | Block |

1. A refusal never echoes the matched term or the sensitive excerpt.
2. Path redaction produces a separately recorded, traceable output; the original evidence is not modified.
3. Publication validates the actual outgoing content, after any permitted transformation.
4. The operator may correct the content and resubmit; ordinary publication never silently overrides a block.
5. F37 is the canonical sanitiser owner, with no parallel subsystem.

A sanitiser does not close the boundary while the shell or the network can bypass it: that is this row together with
M6's egress work. The authenticated half is the vertical path's B6; the unauthenticated half is F51.
