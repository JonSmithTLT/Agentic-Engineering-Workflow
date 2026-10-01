# Proposed AEW skill format 0.1

This is an authoring convention for the candidate package, not a runtime AEW
contract. Normative words below describe conformance to this **proposed format**;
they do not alter invocation authority or accepted workflow semantics.

## Ownership boundary

| Component | Owns | Skill relationship |
|---|---|---|
| Role card and its archetype | Responsibility, permitted operations and outputs within AEW authority | The skill is technique used inside that assignment, never a replacement role. |
| Context pack | Current task, authoritative references, snapshot, constraints, output destination | The skill names input needs; the pack supplies their current values. |
| Capability / execution policy | Available tools, permissions, environment, model and effort selection | The skill uses what is supplied and reports limitations. It cannot install, enable, dispatch, or escalate privileges by itself. |
| AEW contracts and engine | Workflow transitions, credentials, evidence semantics, gates and integration | The skill produces engineering observations; existing mechanisms determine their authority and disposition. |
| Skill | Reusable procedure, choices, checks, counterexamples and stopping conditions | It owns no project truth or workflow state. |

For each instruction, ask: **Could this sentence independently authorize or
redefine a project-state transition?** If yes, remove that effect. Also ask
whether the information belongs in one of the other components above. A sentence
such as "approve the Ticket when these checks pass" fails both tests. A sentence
such as "report which checks ran against which snapshot, their results, and
remaining uncertainty through the supplied output contract" passes.

A skill may help an already authorized role form a review judgment. It must not
invent approval criteria that waive existing requirements, choose an evidence
kind it was not granted, accept its own submission, or equate a judgment with an
AEW transition. No blanket ban on legitimate role operations is introduced.

## Files and disclosure

Each candidate has `SKILL.md`, at least one concrete good and bad example, and
`evals/cases.yaml` plus `evals/rubric.md`. Keep examples inline when short; this
pack uses `examples/good/` and `examples/bad/` so workers can read them only when
needed. Each external runtime resource must have a purpose and an explicit link
from the entrypoint. Avoid empty directories and duplicate manuals.

Optional `references/` holds reusable detail, never a second authoritative copy
of a project's contracts. Optional evaluator fixtures live under `evals/`.
Executable runtime helpers require a separately reviewed need, declared effects,
and validation; this bootstrap pack needs no new runtime tool or dependency.

Discovery needs only `name` and `description`. On use, load `SKILL.md`; load
examples/references only when they resolve a real procedural uncertainty. A
description advises relevance; it does not configure automatic invocation.
Evaluation notes and answer keys are never runtime resources, even if linked
from the candidate's Evaluation section for its author.

## Metadata

```yaml
---
name: adversarial-review
description: Inspect stateful changes for invariant violations across operation sequences, retries, and recovery; skip purely editorial tasks.
metadata:
  version: "0.1.0"
  status: candidate
---
```

| Field | Required | Rule |
|---|---|---|
| `name` | Yes | Stable lowercase letters/digits/hyphens, under 64 characters, identical to directory name. |
| `description` | Yes | One short, discriminating explanation of the class of work and a meaningful non-use boundary. |
| `metadata.version` | Yes | Quoted `major.minor.patch` package version. Pair it with content digests in evaluations; a version string alone proves nothing. |
| `metadata.status` | Yes | `candidate` for this bootstrap. It is an authoring label, not an AEW state or runtime permission. |
| Other metadata | Optional | Owner/contact, deprecation notice or replacement reference if useful. No credentials, tool grants, routing policy, project-state fields, or workflow transitions. |

This metadata is chosen for readability and potential portability. Compatibility
with a specific loader must be checked before installation; this proposal does
not assert that AEW parses it.

## Mandatory body sections

Use the headings in [the template](templates/SKILL.md). Related obligations are
grouped so authors need not repeat dozens of nearly identical fields.

| Section | Must answer |
|---|---|
| Purpose | What engineering outcome changes? What is deliberately outside scope? |
| Task archetypes and target workers | Which recurring tasks? Which observable worker weaknesses or constraints? Concrete model identities, if used, refer to an evaluation profile and do not select a model. |
| Use and non-use | Activation clues, an easy negative control, and how to return to the assignment when irrelevant. |
| Inputs and outputs | Minimum task/context artifacts and exact useful result shape. The invocation's output contract takes precedence over the suggested worksheet. |
| Preconditions | What must be available or known before each dependent action? How is missing information handled without inventing facts or permissions? |
| Procedure and decision points | Ordered actions, concrete branching criteria, a stopping rule, and a response when evidence contradicts the first hypothesis. |
| Verification and evidence | How to substantiate a claim; identity/revision, action or trace, observed versus expected result, reproducibility and limitations. Unrun checks remain unrun. |
| Failure modes and common mistakes | Attractive wrong approaches, false positives, omissions, and anti-patterns with consequences. |
| Abstention and escalation | When to stop a dependent action; what partial result and minimal missing input to report through the normal channel. No new authority path. |
| Authority and interfaces | Explicit relationships to roles, context, capabilities and project authority. Address mutation, evidence disposition, credentials, and scope. |
| Examples | At least one good and one bad example, with why the difference matters. Label synthetic examples. |
| Evaluation | Testable improvement hypothesis, meaningful metrics, regression conditions, reference to evaluator-only cases/rubric, and current evidence status. |

Sections are required; elaborate length is not. A justified "none required" is
better than an invented dependency. Extra sections and references are optional.
Aim for a worker entrypoint readable in a few minutes. Remove text that changes
neither a decision, an action, a check, nor an output. Record actual context cost
in the experiment instead of imposing an unsupported universal token ceiling.

## Evaluation companion

`evals/cases.yaml` uses the proposed `aew-skill-cases/v1` notation: top-level
`format`, `skill`, and `cases`. Each case has a unique `id`, `split`, `purpose`,
`worker`, and `oracle`. `worker` contains `task`, `context`, literal-file
`artifacts`, `capabilities`, and `constraints`. `oracle` contains `activation`,
`required_findings`, `forbidden_findings`, `evidence_requirements`, and
`allowed_alternatives`. `activation` is `use`, `skip`, or `abstain`.

Artifacts are synthetic, self-contained inputs. Materialize only relative paths
inside the isolated case workspace. Workers receive only the worker payload.
The rubric defines how to adjudicate equivalent reasoning, unsupported findings,
and evidence quality. An oracle is an evaluator's expected answer, not project
policy. If it conflicts with supplied facts, invalidate or repair the case and
preserve the discrepancy rather than penalizing a correct worker.

Public `development` cases and `holdout-candidate` seeds are both exposed
development material. A real holdout is separately authored and sequestered.
See the [evaluation guide](evaluation-guide.md) for comparison validity and the
distinction between static completeness and demonstrated behavioral benefit.

## Identity and change

For this proposal, increment patch for editorial clarification, minor for a
compatible procedure/example addition, and major when intended scope or required
inputs/outputs change incompatibly. Behavioral text changes at any level can
invalidate prior evidence: record exact file digests and rerun affected cases.
Keep old evaluation records immutable and link successor records. Deprecation
names the reason, evaluated replacement if any, and scope where old evidence no
longer applies. It never silently swaps content for an active invocation.
