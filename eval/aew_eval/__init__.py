"""The shared evaluation instrument (register F19; the evaluation component design v0.2).

A measurement instrument, never workflow authority: nothing here mutates project control state or satisfies a gate
(design §1.1, decision 8). Slice 1 is the part that makes paid runs impossible to lose or redefine after the fact:

* :mod:`aew_eval.schemas`: ``aew/eval-case/v1``, ``aew/eval-prereg/v1``, ``aew/eval-attempt/v1`` and
  ``aew/eval-run/v1``;
* :mod:`aew_eval.prereg`: freezing a preregistration (canonical hash, materialized schedule) and refusing a run whose
  material inputs changed;
* :mod:`aew_eval.ledger`: the append-only attempt ledger (an attempt is registered before any provider action, a
  result is finalized once and immutably, a runner that dies leaves a visible ``runner_lost`` attempt);
* :mod:`aew_eval.compat`: the deterministic mapping of the M3 dogfood records (``aew/dogfood-run/v1``).

Slice 2 adds :mod:`aew_eval.fixture` (a case's fixture hashed and built), :mod:`aew_eval.arms` (the scripted arm)
and :mod:`aew_eval.runner` (one preregistered cell, registered before it runs and finalized once). Slice 3 adds
:mod:`aew_eval.hidden`, the hidden-evaluator channel. The lower-bound qualification lane (agent-effectiveness
adoption, delta D3) adds the ``raw`` arm (OpenCode's own agent, its session database kept for the evaluator-side
reader) and :mod:`aew_eval.profiles` (``aew/eval-profile/v1``: a model's capability class and qualification state).
The aew arm, metrics and reports come later (design §8). Hidden oracles never live in this repository: a
preregistration holds only their content hashes.
"""

__version__ = "0.1.0"
