"""Harness adapters: AEW invocations executed by replaceable agent harnesses (ADR-0009).

AEW owns the workflow, authority, evidence and state. A harness (OpenCode first) owns only the model
loop, tools and a disposable session. The boundary is :class:`aew.harness.base.HarnessAdapter`; the run
supervisor (:mod:`aew.harness.supervisor`) holds the invocation credential and acts for the agent
through a run-scoped custody bridge (:mod:`aew.harness.bridge`).
"""
