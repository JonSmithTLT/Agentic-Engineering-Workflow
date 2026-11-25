---
name: test-design
description: Design or improve tests from behavioral contracts and failure mechanisms, including deterministic concurrency checks and conditional TDD for implementation. Use for meaningful coverage and regression work; skip editorial-only changes and acceptance verdicts.
metadata:
  version: '0.3.0'
  status: candidate
---

# Test design

## Purpose

Build checks that distinguish correct behavior from plausible defects, with expected results justified independently of the implementation under test. Test count and line coverage are supporting information, not the objective.

## Task archetypes and target workers

For new behavior, regression tests, characterization, and evaluation of weak existing suites. Helps implementers, reviewers, and verifiers that mirror code in assertions, mock away the relevant effect, or rely on timing luck. The technique is language-independent.

## Use and non-use

Use when selecting, writing, or reviewing meaningful tests. Keep a design-only assignment as design; do not edit or execute without the applicable scope. Skip editorial changes without behavioral impact and routine execution of an adequate existing suite. Acceptance decisions require the governing criteria and evidence, beyond this procedure.

## Inputs and outputs

Inputs: behavior/contract, source or interface, existing tests and runner, relevant failure report, environment, and scope. Output the selected cases or tests, their expected-result basis, covered failure mechanisms, execution evidence if any, and remaining gaps. Prefer the existing test structure over new infrastructure.

## Preconditions

Use this procedure within the assignment's scope and permissions; it grants no additional authority. Establish what defines correctness and what resources a test can affect. Isolate mutable state and external dependencies. Distinguish desired behavior from characterization of current behavior, which can preserve a bug.

## Procedure and decision points

1. **Define the oracle.** State the observable outcome and why it is correct: governing rule, reviewed example, independent reference, or justified invariant. Do not derive expected output by calling the same implementation or copying its algorithm. If semantics are unknown, ask or design explicitly labelled characterization; do not invent acceptance behavior.
2. **Name the defect each case rejects.** Select representative valid, invalid, and boundary inputs around the actual contract. Include state transitions, recovery, permissions, and repeated operations where relevant. For a known defect, cover confirmed siblings sharing its mechanism. Keep valid fixtures internally consistent with domain bounds and dependent identities/locators. Label deliberately invalid cases; a shape inventory is not automatically a complete validation contract. Prefer a few discriminating cases over many examples of one easy path.
3. **Choose the observation boundary.** Use the smallest test level that exposes the risk. Pure logic can use unit tests; serialization, persistence, process lifetime, and component contracts need checks crossing those boundaries. Mock an external dependency when needed for control, but keep the behavior being claimed real. Assert final effects and prohibited effects, not only calls made to a mock.
4. **Control time and state.** Use events, barriers, injected clocks, or fault seams to establish ordering. Sleeps do not prove an interleaving; timeouts only bound failure. Test fresh and reused state when relevant, clean up owned resources even on assertion failure, and prevent tests from relying on order or ambient machine configuration. For source replacement, retirement or cancellation, read [asynchronous lifecycle checks](references/async-lifecycle.md).
5. **Expand only where it pays.** Use property-based generation for broad valid domains, state-machine tests for sequences, and bounded fuzzing for hostile inputs when appropriate tools exist. A round-trip alone can miss paired encoder/decoder defects; combine it with independent examples or invariants. Keep minimized failures and reproduction data. For unchanged/broader/non-narrowing claims, use a seeded differential against a frozen baseline with the contract-defined relation; read [comparative checks](references/seeded-differentials.md). Consider a targeted mutant or negative control to show a test detects the intended fault; use an isolated copy rather than damaging the working tree.
6. **Select the development mode.** For implementation with settled behavioral requirements, prefer the [TDD procedure](references/tdd.md). Load it only for that mode. For an existing correct implementation, characterization, or test-only work, useful tests may pass immediately; demonstrate discrimination with a known faulty baseline or targeted negative control where warranted. Do not delete working code to manufacture test-first history.
7. **Execute and assess honestly.** Run permitted focused tests and required project checks. Confirm discovery, assertions, exit status, skips, and diagnostics; no collected tests is not success. Determine whether a failure is the intended behavior, broken setup, or an unrelated dependency. Do not weaken an assertion to match faulty code. Revise an incorrect test only against its independent oracle. Stop when the selected risks are addressed or a precise gap prevents verification.

## Verification and evidence

Record source/test identities including local changes, environment, command, actual outcome, and the behavior exercised. For concurrency and lifecycle repairs, require failing-before/passing-after evidence; if unavailable, retain an explicit verification gap. Label proposed tests and unrun controls. Coverage measures execution, not whether assertions reject incorrect behavior.

## Failure modes and common mistakes

- Expected values generated by the production function, or round-trips with no independent check.
- Testing the fake while bypassing persistence, process cleanup, or another promised effect.
- Fixed sleeps, retries until green, and skipped failing cases presented as reliability.
- Universal coverage targets, compulsory new tooling, or tests that freeze irrelevant internal structure.

## Abstention and escalation

If the oracle, baseline, environment, or required capability is missing, state the supported test design and exact evidence gap. Do not substitute a different platform or invented business rule silently. Continue independent cases; do not claim the untested promise holds.

## Examples

Synthetic good: for an inclusive capacity limit, test just below, exactly at, and above it; verify rejection leaves persisted state unchanged. Synthetic bad: assert the result equals a helper containing the same comparison, while mocking away the write. Both implementations can share the boundary bug and the test proves no persistence guarantee.
