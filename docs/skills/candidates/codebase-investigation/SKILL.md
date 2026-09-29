---
name: codebase-investigation
description: Trace a bounded engineering question through current source, configuration, and tests, preserving evidence and uncertainty. Use for unfamiliar behavior or change-impact discovery; skip direct factual lookups already answered by supplied evidence.
metadata:
  version: '0.1.0'
  status: candidate
---

# Codebase investigation

## Purpose

Answer a specific question about a codebase with a small, inspectable chain of evidence. Separate what current artifacts show from what still requires execution or unavailable material.

## Task archetypes and target workers

Use for locating behavior ownership, tracing input to output, identifying relevant mutation/read paths, or estimating the impact of a proposed change. Intended for workers that can search and read source but tend to follow the first matching symbol, trust stale summaries, or collect context without resolving a question. Model selection remains outside this skill.

## Use and non-use

Use when the answer depends on relationships between files, configuration, or execution paths. Skip for a single supplied fact, a formatting request, or an implementation task whose relevant path is already established. A symptom requiring reproduction and competing causal explanations may need a debugging procedure after the ownership trace; this skill does not require loading another skill automatically.

## Inputs and outputs

Inputs: the question and completion criterion; scope and exclusions; current role/assignment; available capabilities; source snapshot identity and applicable context. Ask for or record missing inputs only when they affect the answer.

Output: a concise answer, an evidence-backed path, important alternatives checked, and unresolved limits. For each consequential claim include a source locator and revision/snapshot basis; use line references when available. Label claims **observed**, **inferred**, or **unresolved**. Fit this content into the assignment's output contract; these labels are reporting aids, not new AEW evidence kinds.

## Preconditions

Confirm that the requested reads and any proposed executions fall within the invocation's scope and capabilities. A tool being present is not authorization to use it. Identify the current checkout or supplied snapshot; if source is dirty, distinguish the inspected working tree from the base revision. Do not treat a commit identifier alone as the identity of modified source.

## Procedure and decision points

1. **Turn the question into a bounded trace.** Name the entry/input, the requested output or invariant, and the boundary at which the answer will be sufficient. For impact work, name the proposed changed symbol and which consumers matter. Do not map the entire repository by default.
2. **Find an anchor.** Search scoped paths for the exact symbol, user-facing behavior, route, error text, or configuration key. Read surrounding code, imports, and registration. A name match is a candidate, not proof that the path executes.
3. **Trace the decisive edges.** Follow dispatch/registration, arguments, defaults, branching, state reads/writes, and the output boundary. Keep a compact path such as `entry -> dispatch -> transform -> result`, with evidence for each edge. Inspect callers or writers only when they can alter the answer. For dynamic dispatch, inspect the registration/configuration selecting the target.
4. **Challenge the leading path.** Check the most plausible competing route: an override, feature flag, fallback, retry, alternate caller, or duplicate symbol. If none applies, say which boundary you checked; do not invent exhaustive coverage. A negative text search only establishes absence in the searched paths and pattern, not absence of runtime behavior.
5. **Resolve derived evidence.** Treat indexes, call graphs, generated documentation, and prior reports as leads. Compare their revision and scope with current source. Confirm every consequential edge in current source. If stale, fall back to source; request refresh only if necessary and authorized. Do not rebuild an index or install tooling merely because it exists.
6. **Choose the smallest remaining check.** Source may establish ownership and branch conditions. Runtime claims may require an existing authorized check. If execution is unavailable, report the static conclusion and the specific unverified behavior. Do not claim that reading a test means running it.
7. **Stop with an answer or a named gap.** Stop when the requested path and material alternative are evidenced, or when a missing artifact/capability blocks the next decisive edge. If additional reads do not reduce uncertainty, restate the unanswered question and seek the one missing input instead of hoarding context.

## Verification and evidence

Before reporting, recheck decisive source locations against the inspected snapshot, including relevant local changes. Tie configuration values to their source and distinguish defaults from observed runtime settings. If a check ran, record its command/action, environment assumptions, result, and snapshot. If it did not run, say so. Retain short relevant excerpts or artifact references, not entire source dumps.

An acceptable bounded result may leave unknown consumers outside the assigned scope. State that limit; avoid claiming complete impact coverage unless the evidence supports it.

## Failure modes and common mistakes

- Treating symbol existence or a stale graph edge as evidence of dispatch.
- Reading broad directories after the decisive path is already established.
- Calling a test assertion an observed runtime result without executing it.
- Confusing a default configuration value with the deployed value.
- Converting a plausible inference into a confirmed causal explanation.
- Assuming a search with no matches proves an external or generated path cannot exist.
- Editing source, changing configuration, or fetching restricted artifacts to make investigation easier.

## Abstention and escalation

Return a partial answer and the smallest missing evidence when current revision identity, dynamic resolution, required source, or authorization is unavailable. Explain what the available evidence does establish and what it cannot establish. Request the missing artifact or authorized capability through the existing workflow; do not assign a new role, obtain credentials, widen scope, or mark the work complete yourself.

## Authority and interfaces

The **role card** supplies responsibility and authority; the **context pack** supplies task/project facts; this **skill** supplies a reusable tracing procedure; **capabilities** supply permitted tools/services. These are distinct inputs. This skill does not grant reads, execution, mutation, credentials, model routing, approval, verification status, or workflow transitions. Apply governing contracts and output requirements from the invocation. If they conflict with this procedure, stop the conflicting step and report the conflict rather than inventing an alternate authority path.

## Examples

Read [the bounded trace](examples/good/bounded-trace.md) for an example of source-confirmed dispatch and [the stale-graph mistake](examples/bad/stale-graph.md) for an attractive but unsupported answer. These are synthetic teaching examples, not current project context.

## Evaluation

Candidate only; target-worker benefit has not been demonstrated. Hypothesis: source-confirmed bounded traces increase correct answers with decisive-edge evidence and reduce stale-index errors. The primary outcome is a correct evidence-backed answer; compare unsupported findings, provenance, and scope compliance separately. Extra skill context must justify its cost through better answers or fewer unnecessary reads under the frozen evaluation plan. Authority violations or fabricated evidence veto a recommendation; other losses use its preregistered floors and margins. The direct-lookup control should show no extra investigation. Evaluator resources are [cases](evals/cases.yaml) and [rubric](evals/rubric.md); do not load them as worker context. Public holdout-candidate cases are seeds for unseen cases, not holdouts.
