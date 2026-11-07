---
name: c-development
description: Implement, repair, or refactor C code with explicit ownership, checked sizes, defined behavior, and target-aware verification. Use for C libraries, systems, embedded code, and native boundaries; skip C++-only and editorial work.
metadata:
  version: '0.2.0'
  status: candidate
---

# C development

## Purpose

Deliver a bounded C change whose memory, error, and portability contracts are explicit. Work within the target's compiler, C dialect, ABI, and resource limits; this is not a whole-project security audit or C++ modernization procedure.

## Task archetypes and target workers

For C libraries, applications, systems, embedded components, and native interfaces. Targets workers that produce compiling happy-path code while missing ownership on failure, integer bounds, undefined behavior, or target assumptions. No model selection is implied.

## Use and non-use

Use when implementing or repairing C, or refactoring its interfaces and internals. For a review-only assignment, apply the checks without editing. Skip C++-only code, prose-only changes, and direct factual questions. A `.h` suffix alone does not establish that a file is C; inspect its consumers and build configuration.

## Inputs and outputs

Inputs: requested behavior, affected source/callers, ownership and error conventions, supported targets, compiler/dialect, build/test configuration, and scope. Output the change or findings, important ownership/ABI decisions, checks actually run, and unresolved limits using the assignment's output contract.

## Preconditions

Use this procedure within the assignment's scope and permissions; it grants no additional authority.

Identify the source revision and local changes; inspect build flags, headers, and the target environment. Establish hosted versus freestanding constraints, allocation policy, and concurrency requirements when relevant. Use the existing build system. Resolve an unknown lifetime or ABI contract before encoding a dependent assumption.

## Procedure and decision points

1. **Pin the boundary.** Trace relevant callers and define valid inputs, lengths/capacities, output state on success/failure, and public ABI obligations. Establish a failing witness for a repair or preserved behavior for a refactor. If a caller disproves the initial assumption, adjust the design before editing more code.
2. **Fix the defect class.** After establishing the mechanism, search sibling callers, adapters, and parallel implementations for the same violated invariant. Check reachability and existing guards; repair confirmed siblings within the assignment and cover them with regression cases. Report related defects outside scope rather than silently broadening the work. A matching spelling alone is not the same defect.
3. **Account for ownership.** For each touched allocation, handle, and borrowed pointer, identify owner, lifetime, transfer point, and cleanup on every exit. Allocate using the pointed-to type's size. Preserve the original pointer on `realloc` failure with a temporary; define zero-size behavior explicitly. Commit outputs only after success when failure must leave caller state unchanged. Use the project's cleanup pattern, including a cleanup label when it makes partial initialization auditable.
4. **Prove sizes before use.** Check multiplication and addition before allocation or copying, including terminator space. For positive element size, reject `count > SIZE_MAX / element_size` before multiplying; reject signed negatives before conversion to `size_t`. Check narrowing conversions. A pointer plus length is the boundary, not an assumed NUL terminator. Distinguish empty input from invalid pointers according to the API; avoid even zero-length library calls or pointer arithmetic on invalid pointers.
5. **Keep behavior defined.** Check initialization, array bounds, alignment, aliasing, signed overflow, and shift ranges on affected paths. Use `memcpy` or explicit decoding for unaligned byte data rather than casting a byte buffer to a typed pointer. Specify byte order for external formats; do not serialize raw struct layout. Match format specifiers to argument types and preserve header declarations and ABI unless a change is requested.
6. **Handle failure at its origin.** Check allocation and I/O results; handle short operations and interruptions according to the actual API. Preserve meaningful error information before cleanup can overwrite it. Do not retry operations blindly. In shared state, identify the synchronization protecting each invariant; `volatile` is not a lock or atomicity guarantee. Respect ISR, signal-handler, and real-time restrictions where applicable.
7. **Exercise the dangerous paths.** Use existing tests for normal operation, zero/maximum/oversized lengths, malformed input, partial initialization, and allocation/I/O failure as relevant. Verify failure leaves outputs and ownership as promised. Use an existing fault-injection seam or a small permitted test harness; do not provoke real resource exhaustion. Test portable code on host while preserving target-specific validation needs. For parsers of untrusted bytes, add or reuse a deterministic fuzz entrypoint over bytes plus length; handle empty/truncated inputs and reset/free per-input state. Run a bounded coverage-guided campaign with available sanitizers, seeded by valid samples and edge cases. Bound time, input size, and memory; keep the harness free of external side effects. Minimize and replay failures as regression tests. Record corpus, command, budget, and findings; an unavailable fuzzer or a short clean run is not proof of parser safety.
8. **Build, diagnose, and stop.** Build with the project's C standard and warnings; investigate new warnings rather than silencing them with casts. Where supported, use a separate diagnostic build with AddressSanitizer/UndefinedBehaviorSanitizer for memory and UB risks, or ThreadSanitizer for races. Instrument compilation and linking; inspect diagnostics as well as exit status. Run required project checks. Profile representative workloads before optimization. Stop when the requested contract is met and checks are accounted for.

## Verification and evidence

Record the snapshot including dirty changes, compiler/version, target, relevant flags, commands, and results. A sanitizer-clean run covers exercised paths, not all inputs; UBSan can report errors while execution continues. Host tests cannot certify device behavior, ABI, timing, or all target-width arithmetic. Separate static proof, compilation, execution, and unavailable target checks.

## Failure modes and common mistakes

- Assuming compilation proves correctness, `size_t` arithmetic cannot wrap, or adding a cast repairs a range error.
- Freeing a borrowed pointer, losing the old allocation on failed growth, or exposing half-initialized output.
- Introducing POSIX calls, heap allocation, C++ constructs, or a newer dialect into an incompatible target.
- Replacing the build system or requiring every diagnostic tool regardless of availability and relevance.

## Abstention and escalation

Pause a dependent change when lifetime, target, or ABI semantics cannot be established. State the safe partial result and minimal missing contract or capability. If target execution is unavailable, provide permitted host/static checks and name the remaining validation; do not claim target readiness or acquire new access.

## Examples

Synthetic good: a buffer-growth fix checks size overflow before multiplication, uses a temporary allocation result, and updates the pointer/capacity only on success; tests confirm failure preserves the old buffer. Synthetic bad: `buf = realloc(buf, count * sizeof *buf)` followed by a null check loses the original allocation on failure and checks no overflow. Checking the result alone is insufficient.
