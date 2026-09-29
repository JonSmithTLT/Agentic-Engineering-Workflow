# Proposed AEW skill-authoring package

Status: **proposal and unevaluated candidates**, version 0.1.0. This package is
documentation for review, not an amendment to the frozen AEW contracts, an
installed skill catalog, or an implementation of skill loading.

## 1. Executive summary

A skill supplies reusable engineering procedure. The role card supplies the
invocation's responsibility and authority; the context pack supplies the current
assignment and project knowledge; capabilities supply the permitted tools and
services. AEW continues to own identity, credentials, state transitions, evidence
ingestion, review, verification, reconstruction, and integration.

The first pack contains exactly three candidates: `codebase-investigation`,
`debugging-root-cause-analysis`, and the reference implementation,
`adversarial-review`. They address different work: finding the relevant paths,
explaining an observed failure, and testing whether valid operations can compose
into an invariant violation. Their names are retained from the brief because
those distinctions make selection and evaluation practical. Invariant tracing
and small regression probes are techniques within these procedures; separate
skills for them are deferred until evidence supports the extra selection cost.

The design makes four deliberate choices:

- Use a small Markdown contract with explicit decision points and authority
  boundaries, not a new runtime schema or permission language.
- Package each candidate with materialized examples and evaluator-only cases.
  Keep current project facts in the invocation's context, not the skill.
- Measure each intended worker against itself, with and without the skill. A
  frontier author or reviewer cannot establish benefit for a cheaper worker.
- Require evidence of useful behavior across cases, including non-use and
  abstention, before recommending adoption. All three candidates remain
  **unevaluated**; expected benefits in case descriptions are hypotheses.

Existing boundaries used in this proposal:

| Source | Constraint carried into this package |
|---|---|
| [Workflow Contract v0.7, §15.3](../agent-engineering-workflow-design-v0.7.md#153-skills-as-reusable-engineering-capabilities) | Skills are reusable technique, not workflow authorities. |
| [Workflow Contract, §§16.6, 16.10–16.12](../agent-engineering-workflow-design-v0.7.md#166-role-capability-grants) | Capability grants and availability remain external; adapters add no authority. |
| [Knowledge Contract v0.4, §15](../aew-knowledge-contract-v0.4.md#15-role-context-assembly) | Role contexts are assembled from relevant knowledge; review preserves independence. |
| [ADR-0006](../implementation/adr/0006-role-archetypes-and-cards.md) | Archetype authority and role-card restrictions stay authoritative; specialist expertise adds no parallel authority. |
| [ADR-0002](../implementation/adr/0002-evaluated-snapshot-fingerprint.md) | Evidence for a different evaluated snapshot cannot satisfy the current gate. |
| [ADR-0009](../implementation/adr/0009-harness-boundary-and-opencode-v2.md) | M3 records unavailable card skills; runtime telemetry and harness success do not move AEW state. |

These are references to the local accepted design, not copied replacement
contracts. The implementation may evolve alongside this proposal. Source docs
were inspected at repository HEAD `92fecc5d318c8cfba54a63b03a52ea7426a36819`;
recheck the cited decisions when adopting the package.

## 2. Proposed directory/layout

```text
docs/skills/
├── README.md                         # this review entrypoint
├── specification.md                  # proposed authoring format and boundaries
├── authoring-guide.md
├── evaluation-guide.md
├── templates/
│   ├── SKILL.md                      # reusable, intentionally unfilled
│   ├── eval-plan.yaml                # evaluator-owned experiment plan
│   └── eval-result.yaml              # evaluator-owned run/result record
└── candidates/
    ├── codebase-investigation/
    ├── debugging-root-cause-analysis/
    └── adversarial-review/
        ├── SKILL.md
        ├── examples/good/
        ├── examples/bad/
        └── evals/
            ├── cases.yaml            # worker inputs plus hidden-from-worker oracle
            └── rubric.md
```

Each candidate follows the reference directory's basic layout. Optional
`references/` or fixture files are justified by actual use, not created empty.
Authoring and evaluation files remain in this proposal directory. A future
experiment copies only an explicitly selected skill's runtime files into its
isolated worker environment; `evals/`, templates, and guides stay evaluator-only.
Do not point a worker's skill search path at this whole tree.

## 3. Canonical SKILL.md template

The [actual reusable template](templates/SKILL.md) and
[field specification](specification.md) define mandatory and optional material.
All candidates use the same twelve body sections. Authors can use short answers
or `none, because …` where justified; silence must not conceal a boundary.

## 4. Skill Authoring Guide

The [authoring guide](authoring-guide.md) walks from a recurring worker failure
to a procedure, evidence contract, examples, static critique, and evaluation. It
includes authority rewrites, stopping rules, negative knowledge, versioning, and
a handoff checklist for another author or reviewer.

## 5. Skill Evaluation Guide

The [evaluation guide](evaluation-guide.md) specifies controlled paired
comparisons, metric definitions, routing and procedure experiments, contamination
controls, uncertainty, regression rules, and a documentary candidate lifecycle.
Use the [plan](templates/eval-plan.yaml) before running and the
[result record](templates/eval-result.yaml) to preserve the outcome, including
failures and invalid runs. These YAML files are proposed experiment notation,
not AEW schemas or engine artifacts.

## 6. Bootstrap skills

| Candidate | Intended behavioral change | Review entrypoints |
|---|---|---|
| Codebase investigation | Replace plausible repository summaries with bounded, revision-linked traces and explicit unknowns. | [Skill](candidates/codebase-investigation/SKILL.md), [cases](candidates/codebase-investigation/evals/cases.yaml), [rubric](candidates/codebase-investigation/evals/rubric.md) |
| Debugging root cause analysis | Replace the first plausible fix with competing hypotheses and a discriminating observation. | [Skill](candidates/debugging-root-cause-analysis/SKILL.md), [cases](candidates/debugging-root-cause-analysis/evals/cases.yaml), [rubric](candidates/debugging-root-cause-analysis/evals/rubric.md) |
| Adversarial review — primary reference | Trace authority, evidence, and durable state across crashes, retries, alternate paths, and operation ordering. | [Skill](candidates/adversarial-review/SKILL.md), [cases](candidates/adversarial-review/evals/cases.yaml), [rubric](candidates/adversarial-review/evals/rubric.md) |

The reference skill is intended to be sufficiently complete for a reviewed
target-model experiment. Its runnable or inspectable synthetic artifacts are
test subjects, not claims about defects in AEW. Public cases are development
material and cannot establish unseen-case performance.

## 7. Secondary skill outlines

These are possible later slices, not additional installed candidates:

| Topic | Narrow procedure worth extracting | Evidence needed before a separate skill |
|---|---|---|
| C engineering | Map ownership and lifetime across error exits; check sizes and cleanup ordering in one changed path. | Fewer demonstrated lifetime/overflow defects on unseen tasks without excessive false findings. |
| Python engineering | Trace exception, resource, and data-shape boundaries; test one contract change through its callers. | Better outcomes on project-representative Python tasks than the generic investigation/debugging pack. |
| Regression-probe authoring | Convert a causal sequence into an isolated failing assertion and a counterexample that should pass. | Probes distinguish faulty and repaired fixtures, avoid timing dependence, and stay within granted tools. |
| Invariant tracing | Connect one declared invariant to every relevant mutation and recovery path. | Additional benefit beyond adversarial review sufficient to justify another skill and its context cost. |

Do not expand these into generic language manuals. Measure the missing behavior
first and reuse an existing procedure when it already covers the task.

## 8. Future skill-extraction workflow

1. Identify a procedure repeated successfully across distinct assignments.
   Preserve failures and the conditions under which success was observed.
2. A human or frontier author extracts decisions, discriminating observations,
   and stopping rules. Remove project identifiers, credentials, transient state,
   and unearned claims of causality.
3. Create a versioned candidate, counterexamples, and a testable hypothesis about
   the intended worker's behavior. Check whether a context-pack correction or
   capability improvement would address the problem more directly.
4. Independently critique authority boundaries and prepare private evaluation
   cases. Compare the target worker with and without the frozen candidate.
5. Recommend acceptance, revision, or rejection of the **skill package** based on
   results. The existing authorized owner decides any distribution change;
   extraction and evaluation do not dispatch work or accept project evidence.

Record successful and unsuccessful variants so a later author can distinguish
measured improvement from an attractive story. No autonomous extraction service,
production feedback loop, or new persistent project knowledge store is proposed.

## 9. Architectural concerns / decisions needing Lead review

These decisions are intentionally open; none requires changing M3 in this task.

| Decision | Proposed review position | Why it must remain explicit |
|---|---|---|
| Distribution and resolution | Keep this as a candidate package; decide catalog ownership, naming, and mapping separately. | Merely adding files must not make an unavailable skill available or broaden a role. |
| Identity and reproducibility | Pin runtime file digests in experiments; decide whether/how future invocation records bind skill bytes. | Role-card pinning is not proof that skill content or supporting files were pinned. No engine fields are invented here. |
| Selection and composition | Select per assignment through existing ownership; test combinations before recommending a bundle. | `use_when`, candidate status, and evaluation success must not become dispatch or model-routing policy. |
| Loading and isolation | Confirm exactly which runtime files and examples the chosen harness exposes. | Ambient skills, mutable paths, or leaked answer keys invalidate comparisons. M3 exposure observations are not a portable loader contract. |
| Target workers and economics | Experiment owner selects concrete model versions/settings and per-task cost tolerances. | The intended budget and weakest useful worker are not specified by this proposal. |
| Evidence packaging | Keep procedural worksheets inside the invocation's already permitted output format. | A skill must not create new authoritative evidence kinds or replace sealed/ingested AEW evidence. |
| Adoption threshold | Review preregistered case mix, risk tolerances, and independent holdouts before claiming benefit. | A local pass or frontier-model smoke check cannot establish target-worker improvement. |
| Compatibility and retirement | Review package-format changes and remove deprecated versions only through the existing distribution owner. | Silent replacement breaks reproducibility and can change active worker behavior. |

Review can accept the authoring approach while leaving every bootstrap skill an
unevaluated candidate. Adoption recommendations must name the exact evaluated
skill version, worker profile, and task scope.
