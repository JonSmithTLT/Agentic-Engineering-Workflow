"""The Lead talks with the operator (the operator's reset of 2026-11-06, slot 2's first item).

In every dogfood run the Lead never asked a question, never said what it was doing and never asked for a
clarification: its system text was all about the tools. The text now tells it to say its plan and ask when something
is unclear, to say what is happening while work runs, and to report what changed, what it skipped and what it noticed.
"""

from __future__ import annotations

from aew.harness import contract as K
from aew.harness.opencode import projection

VOICE = (
    "say in a few lines how you understand it and what you plan to do",
    "ask: one or two focused questions, then wait for the answer",
    "Before you wait on runs, say which runs you are waiting on and what each is doing",
    "report what changed, what you skipped and why, and anything you noticed",
)


def test_asking_never_turns_a_command_into_a_chat_approval():
    """#348 review m1: "ask, then wait" must not read over the command rule (OpenCode's prompt is the one approval)."""
    system = projection.LEAD_SYSTEM
    ask = system.index("ask: one or two focused questions")
    assert system.index("A command your rules ask about is not one of these: request it by running it", ask) > ask
    assert "do not wait for a reply in chat first" in system


def _system(**kwargs) -> str:
    return projection.lead_config("GUIDE", **kwargs)["agents"][projection.LEAD_AGENT]["system"]


def test_every_lead_is_told_to_say_its_plan_ask_narrate_and_report():
    for system in (_system(), _system(contained={"label": "a project"})):
        for line in VOICE:
            assert line in system, line


def test_the_voice_comes_before_the_tool_rules_so_it_reads_as_how_the_lead_works():
    system = projection.LEAD_SYSTEM
    assert system.index(VOICE[0]) < system.index("You never hold or see the Lead credential")


# What the Lead does when a wait returns has one owner, the wake guide (E122): the system text lists its entries, and no
# other line of it gives such guidance. The phrases a hand-written wake rule would use, kept out of every other line.
# A phrase list catches the likely restatements, not every one: a rule worded otherwise passes (E122 review, n1).
WAKE_WORDS = ("still working", "times out", "timed out", "when one ends", "when a run ends", "wait again",
              "evidence shows", "Tell the operator")


def test_the_lead_s_wake_guidance_is_generated_from_the_wake_guide_and_nowhere_else():
    lines = projection.LEAD_SYSTEM.split("\n")
    generated = projection.wake_guide_lines()
    kinds = K.wake_guidance()
    # The kinds of return a wait gives today, in the enum's order, then the timeout (no `why`). The guide holds every
    # `why`; the Lead is told of one only once a wait can return it.
    assert list(kinds) == [*K.WAITED_ON, K.TIMED_OUT] and K.TIMED_OUT not in K.WAKE_GUIDE
    assert list(K.WAITED_ON) == [w for w in K.WHY if w in K.WAITED_ON]
    assert generated == [f"    - {K.wake_line(key)}" for key in kinds]
    start = lines.index(generated[0])
    assert lines[start:start + len(generated)] == generated  # the entries, in the table's order, together
    assert "decision point" in lines[start - 1]  # right after the voice line that introduces them
    for line in lines:
        if line not in generated:
            assert not any(w.lower() in line.lower() for w in WAKE_WORDS), line
    for key, wake in kinds.items():  # every part of every entry reaches the Lead
        assert all(part in projection.LEAD_SYSTEM for part in (f"`{key}`", wake.means, wake.act[1:], wake.tell))


def test_a_wait_s_returned_steps_take_their_text_from_the_wake_guide():
    timed_out, ended = K.WAIT_TIMED_OUT, K.WAKE_GUIDE[K.RUN_ENDED]
    again = K.wait_step(["R-1", "R-2"], again=True)
    assert again.startswith(f"R-1, R-2 are still working ({K.TIMED_OUT}): {K.NOT_POLLING}.")
    # The wait command sits right after the default action, before the conditional ones (E122 review, m2).
    assert f"{K.WAIT_AGAIN[1:]} (`aew harness wait R-1 R-2 --any`). {K.WAIT_OR_ELSE[0].upper()}" in again
    assert timed_out.act == f"{K.WAIT_AGAIN}; {K.WAIT_OR_ELSE}" and timed_out.tell in again
    assert K.run_ended_step("ingest it") == f"ingest it. Tell the operator in a line {ended.tell}"
    assert K.WAIT_RULE in K.wait_step(["R-1"]) and "still working" not in K.wait_step(["R-1"])
