# Premium composition assessment

Evaluator-only. Historical assessment of candidate 0.2.0; its captured digests do not identify 0.3.0. No premium compatibility revalidation is claimed for 0.3.0. Inspected installed frontend-design-premium 1.4.0 on 2026-10-12. This is a static composition assessment and an actual resolver check, not a paired worker pilot or release approval. Neither installed skill nor compatibility metadata was modified.

## Reproducible result

After reading the installed resolver source, ran:

```text
python -X utf8 <premium-skill-dir>/scripts/resolve_frontend_design.py --path <candidate-dir> --status
```

The explicit path resolved to this candidate. Exit code: 1. Status: **UNTRUSTED**, because docs/skills/candidates is outside the resolver's supported installation roots. This is a location classification, not a finding of malicious content or a behavioral compatibility verdict. No remote-check flag was used. See [captured evidence and digests](premium-compatibility.json).

The candidate's LF-normalized entrypoint digest also differs from premium's recorded tested digest. From the resolver's code, those same bytes at a supported root would be UNTESTED under the inspected metadata, not MATCH. This latter statement is a source-derived prediction, not an installation experiment. The same skill name only enables discovery.

The installed premium SKILL.md describes `scripts/validate_skill.py --strict` and `VERSIONING.md`, but neither file exists in the installed package, and a package-wide filename search found neither. Therefore strict release validation was not run; its advertised behavior is documented, not independently verified here. Obtain the matching validator/release materials from the premium maintainer before a release compatibility claim.

## Instruction composition

| Concern | Assessment and pilot obligation |
|---|---|
| Project contracts | Both prioritize maintained product/design contracts over aesthetic defaults. The candidate now makes this explicit and preserves uncertainty, provenance, units and freshness. Check semantic fidelity in FD-09. |
| Visual direction | Candidate supplies task-specific composition and preserves identity for refinements; premium derives visuals from the base/project system. No obvious static conflict in this division. |
| Product behavior | Candidate offers a general floor; premium has more specific rules for validation, loading, search, overlays and shared ownership. In a jointly assigned product task, apply relevant premium detail within governing project instructions. Do not treat the shorter base as permission to omit it. |
| Read-only and small assignments | Candidate forbids mutation during review and avoids unnecessary design documents. Premium includes proactive DESIGN.md creation and fix/audit instructions. The assignment must keep read-only tasks read-only; paired negative controls must detect unwanted writes or scope growth. A generic premium workflow cannot grant mutation authority. |
| Verification limits | Candidate distinguishes static, rendered and interaction evidence. Premium requires additional audit/project commands. Report any unavailable capability or failed check; do not silently waive a premium requirement and declare the composition verified. |
| Cost | Premium's references and audits substantially expand the work beyond the concise base. Measure actual loaded context, tool use and outcome quality in the paired arm; base word count is not combined context cost. |

## Before switching a distribution

1. Freeze both packages and all runtime resources; the resolver hashes only the base entrypoint, so its MATCH alone cannot cover this candidate's conditional references.
2. Acquire and inspect the missing release-validation materials. Use the supported integration process without patching the trusted-root check or labelling a new digest tested merely to turn the check green.
3. Run controlled base-only versus base-plus-premium workers on FD-09, read-only FD-05, and capability-limited FD-08, plus private representative application tasks. Exercise actual themes/zoom/interactions and record semantic fidelity, regressions and cost. Keep any existing-upstream comparison on frozen matching bytes.
4. Resolve observed instruction conflicts, then have the responsible distribution owner record the tested package/digests through its normal release process. Re-run strict validation with the intended installed dependency. A worker pilot and a resolver match answer different questions; both need evidence.

Current result: plausible behavioral composition, unresolved release compatibility, no installation switch and no empirical performance claim.
