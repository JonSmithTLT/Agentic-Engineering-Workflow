# AEW Companion Design Review Integration Bundle — 2026-09-28

This bundle incorporates the combined review of the AEW companion design documents.

## Suggested Opus read order before more dogfooding

1. `failure-class-registry.md`
2. `invariant-index.md`
3. `hierarchy-intent-revision-and-replanning-design-v0.1.md`
4. `lead-operator-interaction-design-v0.1.md`
5. `execution-workspace-and-isolation-design-v0.1.md`
6. `AEW_Live_Coordination_and_Assumption_Propagation_Design_v0.1.md`
7. `external-agent-workflow-lessons-2026-09-28.md`

## Highest-priority decisions/hardening

- stop passing authored semantic text through shell-interpreted command strings;
- make recursive dispatch absent from normal worker capabilities;
- label current filesystem guarantee as `workdir separation only`;
- require real containment before real-repository dogfood/internal alpha;
- use fail-closed classification where lighter categories reduce ceremony;
- compare Story/Epic revision drift against the approved baseline;
- represent supersession as lineage over existing terminal states;
- centralize failure names and invariant discovery to prevent cross-document drift.

The Live Coordination design remains future work. Review integration does not pull it into M3.
