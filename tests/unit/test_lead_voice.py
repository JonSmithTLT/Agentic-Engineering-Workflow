"""The Lead talks with the operator (the operator's reset of 2026-11-06, slot 2's first item).

In every dogfood run the Lead never asked a question, never said what it was doing and never asked for a
clarification: its system text was all about the tools. The text now tells it to say its plan and ask when something
is unclear, to say what is happening while work runs, and to report what changed, what it skipped and what it noticed.
"""

from __future__ import annotations

from aew.harness.opencode import projection

VOICE = (
    "say in a few lines how you understand it and what you plan to do",
    "ask: one or two focused questions, then wait for the answer",
    "While work runs, say what is happening",
    "report what changed, what you skipped and why, and anything you noticed",
)


def _system(**kwargs) -> str:
    return projection.lead_config("GUIDE", **kwargs)["agents"][projection.LEAD_AGENT]["system"]


def test_every_lead_is_told_to_say_its_plan_ask_narrate_and_report():
    for system in (_system(), _system(contained={"label": "a project"})):
        for line in VOICE:
            assert line in system, line


def test_the_voice_comes_before_the_tool_rules_so_it_reads_as_how_the_lead_works():
    system = projection.LEAD_SYSTEM
    assert system.index(VOICE[0]) < system.index("You never hold or see the Lead credential")
