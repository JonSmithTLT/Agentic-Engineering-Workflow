---
name: python-development
description: Implement, repair, or refactor Python code while preserving runtime compatibility, API behavior, resource lifetimes, and project tooling. Skip non-Python work and editorial-only changes.
metadata:
  version: '0.4.0'
  status: candidate
---

# Python development

## Purpose

Deliver a bounded Python change that works in the project's actual environment. Emphasize behavior at boundaries and failure paths; do not turn a feature or fix into a tooling migration.

## Task archetypes and target workers

For applications, libraries, services, scripts, and Python sides of native bindings. Targets workers that write plausible happy-path code but miss compatibility, cancellation, shared state, or packaging behavior. No model selection is implied.

## Use and non-use

Use for Python implementation, repairs, and behavior-preserving refactors. For a review-only assignment, apply the checks without editing. Skip prose-only edits, direct syntax questions, and other languages; return to the original assignment without loading more procedure.

## Inputs and outputs

Inputs: requested behavior, relevant code/callers, supported Python versions, dependency/build configuration, existing checks, and assignment scope. Infer these from available artifacts before asking. Output the change or review findings, compatibility decisions, checks actually run, and remaining limits through the supplied output contract.

## Preconditions

Use this procedure within the assignment's scope and permissions; it grants no additional authority.

Identify the source revision plus local changes. Read relevant project instructions, package metadata, lockfiles, and CI commands; determine the intended interpreter/environment. Missing optional tools do not block useful work. Resolve missing API semantics or runtime constraints before making a change that depends on them.

## Procedure and decision points

1. **Pin the contract.** Inspect the changed boundary and its callers. Establish accepted input, output, exceptions, side effects, and compatibility requirements. For a bug, identify a failing witness; for a refactor, identify observable behavior that must survive. If evidence contradicts the initial explanation, revise it before widening the patch.

   Check the CI matrix's minimum Python, including stdlib behavior and AST/source-position assumptions, not only supported syntax. Run version-sensitive helpers there; a local newer interpreter is insufficient.

   Make file and subprocess encodings explicit when the protocol requires them; Windows defaults vary with locale/runtime. For byte-stable UTF-8/LF artifacts, use `encoding="utf-8", newline="\n"` or binary I/O. Python `-I` ignores `PYTHONIOENCODING`: configure the controlled child with `-X utf8` or explicit stream encoding, and decode consistently in the parent. Parent-side decoding does not configure the child. Preserve format-mandated newline rules.
2. **Fix the defect class.** After establishing the mechanism, search sibling callers, adapters, and parallel implementations for the same violated invariant. Check reachability and existing guards; repair confirmed siblings within the assignment and cover them with regression cases. Report related defects outside scope rather than silently broadening the work. A matching spelling alone is not the same defect.
3. **Use the existing environment.** Keep the project's runner, dependency manager, formatter, type checker, and test framework. Do not upgrade Python or replace working tools incidentally. For a new project, choose a supported runtime and minimal configuration appropriate to a script, application, or distributable package; add dependencies only for an actual need. For tooling or configuration changes, read [effective settings and controls](references/tool-config-changes.md).
4. **Make boundaries explicit.** Annotate changed public interfaces in the project's typing style using syntax supported by its minimum Python. Validate external data at entry; annotations and casts do not perform validation. Preserve distinctions such as missing, `None`, zero, and empty. Avoid shared mutable defaults; use per-instance factories where needed. Choose plain functions and existing data structures before introducing a new abstraction.
5. **Preserve failure semantics.** Catch exceptions only where they can be handled or translated meaningfully; preserve the original cause when translating. Do not turn malformed input or an internal defect into apparent success with a broad fallback. Close owned resources with context managers or `finally`; do not close borrowed resources. Keep import-time work free of unintended I/O and process-wide configuration changes. For AST rewriting, import hooks, or audit hooks, read [instrumentation hygiene](references/instrumentation.md).
6. **Own child lifetimes.** Assign each child an owner: drain piped output without deadlock, wait/reap, and on timeout or cancellation terminate the owned descendants as well as the direct child, escalating within a bounded cleanup deadline. Establish containment at launch: a dedicated POSIX session/process group where appropriate, or a Windows Job Object/equivalent tree-lifecycle facility. Do not signal a shared group. Use `CREATE_NO_WINDOW` for noninteractive Windows console children; this hides a console, not descendants, and is not a cleanup mechanism. A reaped leader does not prove descendants exited.
7. **Choose concurrency deliberately.** Keep synchronous code synchronous unless the workload or interface calls for concurrency. In async code, avoid blocking the event loop, bound fan-out, define task ownership and timeout behavior, and await task termination during cleanup. Propagate cancellation after cleanup unless suppression is explicitly part of the contract. Use structured task groups only where the supported runtime and desired sibling-failure behavior fit. Moving work to a thread does not make its underlying operation cancellable.
8. **Test the changed promise.** Use the existing test style. Select normal, boundary, and relevant failure cases, including repeated calls/shared state or cancellation when affected. Prefer observable results over implementation-shaped mocks; isolate filesystem, clock, randomness, and network dependencies. For concurrency and lifecycle repairs, require a regression that fails before and passes after; prove ordering with events, barriers, or controlled seams, never sleeps. Timeouts bound a failed test; they do not establish ordering. For other repairs, demonstrate before/after failure when practical. If the baseline or required runtime is unavailable, report the repair as unverified rather than waiving this requirement. Run a supplied reviewer reproducer against the repair as well as your regression test. Use isolated copies for ablation; never reset a dirty working file to undo a test mutation. Never relax assertions merely to make a run green.
9. **Verify proportionately and stop.** Run focused checks, then required project checks. Include shipped CI YAML and documented commands; when adding an enumerated member, find and run the guards that enumerate that domain. Check typing/linting with existing configuration. When packaging changes, build and test the installed artifact in an isolated environment so source-tree imports cannot mask missing files or dependencies. Optimize only against a representative measured bottleneck. Stop when the requested contract is met and required checks are accounted for; report unavailable checks explicitly.

## Verification and evidence

Record the interpreter/environment, inspected snapshot including dirty changes, command, result, and relevant test scope. Separate static reasoning from execution. A type-check pass does not establish runtime validation; a unit test does not establish installed-package behavior. Distinguish pre-existing failures from regressions using a comparable baseline when available.

## Failure modes and common mistakes

- Imposing a preferred toolchain, Python version, universal coverage percentage, or async architecture on an unrelated change.
- Masking errors with `except Exception: return None`, or hiding type errors with unjustified `Any`, casts, or ignores.
- Retrying side effects without understanding idempotency, or abandoning background tasks after a timeout.
- Claiming performance, compatibility, or test success from code inspection alone.

## Abstention and escalation

Pause only the dependent step when essential contract information, execution capability, or authorization is missing. Return the useful partial result and smallest missing input. For an unavailable target runtime, report what was checked locally and what remains unverified; do not silently raise the supported version.

## Examples

Synthetic good: a Python 3.9 parser fix retains its synchronous API, rejects malformed rows with a meaningful exception, and tests valid, empty, and malformed inputs using the existing runner. Synthetic bad: the same fix upgrades to 3.11, adds an async client, and catches every exception to return an empty result. The latter changes compatibility and hides the very failure being repaired.
