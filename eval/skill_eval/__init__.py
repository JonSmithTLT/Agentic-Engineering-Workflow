"""The skill evaluation's runner (register E135; SYS-22): paired runs of one shipped skill, on F19's instrument.

The evaluation asks three things of a skill AEW's install serves (the register row): whether it helps the weaker models
AEW's workers would use, whether such a model picks the right skill from descriptions, and what a listing and its loads
cost, taken from paired runs' usage. The method is the skill evaluation guide's (``docs/skills/evaluation-guide.md``):
two arms that differ in the candidate's exposure alone, every case run in both, in an order drawn before any outcome.

This package is the mechanical part, and owns no measurement machinery of its own. A preregistration, its frozen
schedule, the attempt ledger, a case's fixture, the run record and the model arm are F19's (``eval/aew_eval``); what a
run may reach of a skill, its copy and its hash are ``aew.skills``'s; the rules and the ``skills`` entry are the
OpenCode projection's; ``loaded`` is the adapter's. What it adds:

* :mod:`skill_eval.cases`: a candidate's public cases (``aew-skill-cases/v1``) as F19 cases, worker fields only, with
  the oracle side kept apart in an evaluator's key;
* :mod:`skill_eval.arms`: the two arms, F19's ``raw`` and ``scripted`` arms with a skill exposure;
* :mod:`skill_eval.plan`: the rules a paired preregistration meets before anything is registered;
* :mod:`skill_eval.run`: the schedule, cell by cell, under the preregistered budget;
* :mod:`skill_eval.report`: the pairs, the blinded grading packets, and the three measures.

It is a measuring instrument, never authority: no result here labels a skill, changes a card or satisfies a gate, and
running it is the operator's act, with a keyed, paid model they approve for that event (register E135's note of
2026-11-06). ``README.md`` beside this file states what the runner leaves to the experiment's owner.
"""

__version__ = "0.1.0"
