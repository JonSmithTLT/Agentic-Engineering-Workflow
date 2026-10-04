# Independent-review probes and results

The scripts and result files behind every independent review of AEW, kept beside the review they belong to so a
finding can be re-run rather than taken on trust. The narrative of each review is in `docs/archive/reviews/`; this
directory holds only what the reviewers executed and what came out. Frozen source trees, virtual environments, raw
logs and large protocol dumps were not kept; each probe names the commit it ran against, so a fresh clone at that
commit reproduces it.

Local reviewer paths were replaced by `<reviewer-home>` before publication. Nothing here is authority: a probe that
disagrees with a test or an ADR is a finding to triage, never a rule.

| Directory | Review | Narrative |
|---|---|---|
| `m1-2026-09-26/` | M1 independent review and the focused re-review of its remediation (probe tests and their captured output) | [`m1-independent-review-2026-09-26.md`](../../docs/archive/reviews/m1-independent-review-2026-09-26.md), [`m1-remediation-re-review-2026-09-26.md`](../../docs/archive/reviews/m1-remediation-re-review-2026-09-26.md) |
| `adr-0011/p2a/` … `p2d/` | ADR-0011 phases P2a (cold store), P2b (archival), P2c (history surface and audit), P2d (migration): probe scripts and `jsonl` results | [`adr-0011-p2a-review.md`](../../docs/archive/reviews/adr-0011-p2a-review.md) … [`p2d`](../../docs/archive/reviews/adr-0011-p2d-review.md) |
| `adr-0011/p3/`, `adr-0011/p3-re-review/` | the P3 acceptance gate review (probes, the H1–H4 measurements on Windows, WSL and Rocky 8 userland, source verification) and the fix re-review | [`adr-0011-p3-review.md`](../../docs/archive/reviews/adr-0011-p3-review.md), [`adr-0011-p3-re-review.md`](../../docs/archive/reviews/adr-0011-p3-re-review.md) |
| `adr-0011/e5-fix/` | the probes run on the E5 (Engine collaborators) fix | folded into the P1 PR (#15); no separate narrative |
| `m4-areas-2026-10-03/area1-containment/` … `area5-control-state-persistence/` | the five area reviews of the M4-A/M4-B code (containment, dispatch legality, integration and publication, control-state persistence; the authority review had no probe files) with their reproduction tests and run logs | [`m4-area1-containment-review-2026-10-04.md`](../../docs/archive/reviews/m4-area1-containment-review-2026-10-04.md) and the other `m4-area*` records |
| `architecture-2026-10-04/` | the ground-up architecture review's probes: the outbox log probes (T3), the knowledge-manifest probe (T4), the codebase-map generator and synthetic benchmark (T5, S7), the network-namespace and OpenCode startup probes (T6), the citation test (T7), the OpenCode and Codex request captures (T9), the C/C++ extraction oracle (S1, S1b), the impact-surface probe (S8); `patches/` holds the three prototype branches (T1 typed surface, T4 knowledge manifest, D9 service identity) as `git format-patch` output against `dcd43f1` | [`architecture-review-2026-10-04.md`](../../docs/archive/reviews/architecture-review-2026-10-04.md) and the engagement folder [`architecture-review-2026-10-04/`](../../docs/archive/reviews/architecture-review-2026-10-04/README.md) |

Not kept, and where to find it: the Codex app-server protocol schema (597 KB; regenerate with `codex app-server
generate-json-schema` on `rust-v0.160.0`), the `review-*.log` and `.stderr` captures, the frozen `tree/` clones and
`frozen-head.tar`, and the dashboard review drivers and screenshots (the W05 and W06 reviews themselves are in
`web/docs/`; the work-density checkpoint review belongs to its open pull request).
