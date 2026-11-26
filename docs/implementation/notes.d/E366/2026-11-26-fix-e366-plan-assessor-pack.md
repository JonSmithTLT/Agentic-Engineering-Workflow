**Built (`fix/e366-plan-assessor-pack`, #594): the reviewer's pack fits the scope it is dispatched at.** The reviewer archetype's text (`roles/archetypes/reviewer.yaml`) is now scope-neutral. A reviewer reports findings about what it was dispatched to evaluate, and the scope section names that. It evaluates it against the requirement, its contracts and guardrails, and the accepted plan it carries out where there is one, so the assessor is not told to evaluate the plan against itself. It classifies every finding. The archetype's severity list is gone, since the report format lists the allowed values from the evidence schema. The format's `resolved_findings` placeholder names the open findings, not a change.

`knowledge.context._scope_duties` adds each scope's own duties, each only where the pack delivers its input:
- the duty to evaluate the change (and its check results) where the change is delivered;
- at parent scope, the same duty for each child's integrated diff where the child work carries one, with no check results, since a parent pack has none;
- the re-review duty where the open findings are delivered;
- at `plan_assessment` scope, the assessor's duties: the requirement trace, with its statuses taken from `evidence.schema.json`, the premises, reliance and obligations, and a finding for every gap or failed premise.

The pack's completion criteria follow the same rule. The `plan_assessor` card (version 2) has no responsibilities of its own, so the pack no longer says them three times. A card without responsibilities gets no empty block for them.

**Tests:**
- The scope-fit guard in `tests/unit/test_pack_truth.py` (`test_a_roles_instructions_fit_its_scope`, with planted right, wrong and missing lines at assessment and parent scope) holds that no evaluator's pack names an input its scope does not deliver or a field its record kind refuses. A parent's child diffs count as a diff it may name, never as the change or check output. The guard fails in 13 cases on the old text.
- `tests/integration/test_plan_assessment_dispatch.py` holds that an assessor that fills in its pack's own report format submits an assessment that is recorded.

**Parent scope**, which the row leaves out because its pack carries each child's integrated diff and the aggregate diffstat, gained only that change duty, on the review of #594 (m1). Otherwise it gets the scope-neutral archetype text and the re-review duty, as every review scope does.
