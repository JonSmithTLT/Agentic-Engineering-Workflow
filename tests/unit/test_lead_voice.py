"""The Lead talks with the operator (the operator's reset of 2026-11-06, slot 2's first item).

In every dogfood run the Lead never asked a question, never said what it was doing and never asked for a
clarification: its system text was all about the tools. The text now tells it to say its plan and ask when something
is unclear, to say what is happening while work runs, and to report what changed, what it skipped and what it noticed.
"""

from __future__ import annotations

import pytest

from aew.harness import contract as K
from aew.harness.opencode import projection
from aew.surface.contract import MESSAGING

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


@pytest.mark.parametrize("messaging", [False, True], ids=["messaging-off", "messaging-on"])
@pytest.mark.parametrize("push", [False, True], ids=["waits", "woken"])
def test_the_lead_s_wake_guidance_is_generated_from_the_wake_guide_and_nowhere_else(messaging, push):
    """In every variant (a Lead that waits and one AEW wakes; messaging off and on): the entries are the wake guide's,
    together and in its order, right after the one line that says how to take each return and what to tell the operator
    (``K.wake_report``, E367: one line for the eight `Tell the operator` lines), and no other line gives such guidance.
    A woken Lead is told of the reasons only a wake gives, and its own timed-out line (the audit of 2026-11-25, U1)."""
    system = projection.lead_system(frozenset({MESSAGING}) if messaging else frozenset(), push_wake=push)
    lines = system.split("\n")
    generated = projection.wake_guide_lines(messaging, pushed=push)
    kinds = K.wake_guidance(messaging, pushed=push)
    # The kinds of return a wait gives today (a wake's own too, where AEW wakes the Lead), in the enum's order, then
    # the timeout (no `why`). The guide holds every `why`; the Lead is told of one only once it can be returned.
    whys = [*K.waited_on(messaging), *(K.PUSHED_ONLY if push else ())]
    assert list(kinds) == [*(w for w in K.WHY if w in whys), K.TIMED_OUT] and K.TIMED_OUT not in K.WAKE_GUIDE
    assert generated == [f"    - {K.wake_line(key, messaging, pushed=push)}" for key in kinds]
    start = lines.index(generated[0])
    assert lines[start:start + len(generated)] == generated  # the entries, in the table's order, together
    intro = lines[start - 1]
    assert intro.endswith(f"{K.wake_report()}:")  # right after the line that introduces them
    assert ("decision point" in intro) is not push and system.lower().count("tell the operator in a line") == 1
    for line in lines:
        if line not in generated and line != intro:
            assert not any(w.lower() in line.lower() for w in WAKE_WORDS), line
    for key, wake in kinds.items():  # what each entry means and asks reaches the Lead
        assert all(part in system for part in (f"`{key}`", wake.means, wake.act[1:]))
    assert K.WAKE_GUIDE[K.RUN_ENDED].tell in intro  # an ended run's report names its evidence
    timed_out = kinds[K.TIMED_OUT].act
    assert ("otherwise end your turn" in timed_out) is push and K.WAIT_AGAIN in timed_out


def test_a_wait_s_returned_steps_take_their_text_from_the_wake_guide():
    timed_out, ended = K.WAIT_TIMED_OUT, K.WAKE_GUIDE[K.RUN_ENDED]
    again = K.wait_step(["R-1", "R-2"], again=True)
    assert again.startswith(f"R-1, R-2 are still working ({K.TIMED_OUT}): {K.NOT_POLLING}.")
    # The wait command sits right after the default action, before the conditional ones (E122 review, m2).
    assert f"{K.WAIT_AGAIN[1:]} (`aew harness wait R-1 R-2 --any`). {K.WAIT_OR_ELSE[0].upper()}" in again
    assert timed_out.act == f"{K.WAIT_AGAIN}; {K.WAIT_OR_ELSE}" and timed_out.tell in again
    assert K.run_ended_step("ingest it") == f"ingest it. Tell the operator in a line {ended.tell}"
    assert K.WAIT_RULE in K.wait_step(["R-1"]) and "still working" not in K.wait_step(["R-1"])


def test_a_returned_next_step_names_every_steering_command_whole_so_it_parses():
    """A wait's ``next_action`` is offered to be run as given, so each command in it must parse on the live parser
    (D2's O-CMD, E140's triage): the wake guide's bare `aew harness send` and `aew harness interrupt` are mentions in
    the Lead's system text, and a returned step writes them with their run. Judged by D2's own rule, over every kind
    of wake and both timed-out shapes, with messaging off and on. Each command is also run through the printed-command
    check, which holds every placeholder to its table (#547 review m1: a step over several runs named `<run>`)."""
    import printed_commands as P
    from discovery import rules

    def o_cmd(step: str) -> list[str]:
        return [f.detail for f in rules.check(rules.Output(site="unit", payload={"next_action": step}))
                if f.rule == "O-CMD"]

    parsed = 0
    for messaging in (False, True):
        steps = [K.trigger_step([why], "R-1", others, messaging=messaging)
                 for why in K.waited_on(messaging) for others in ([], ["R-2"])]
        steps += [K.wait_step(runs, again=True, messaging=messaging) for runs in (["R-1"], ["R-1", "R-2"])]
        for step in steps:
            assert not o_cmd(step), (step, o_cmd(step))
            for command, fenced in P.commands(step):
                if command.startswith("aew "):
                    P.parse(command, fenced=fenced)  # raises PrintedCommandError, saying why, if it does not run
                    parsed += 1
    assert parsed and f"`aew harness send {K.NAMED_RUN} --text <message>`" in K.wait_step(["R-1", "R-2"], again=True)
    stepped = K.trigger_step([K.OUT_OF_SCOPE], "R-1", [])
    assert "`aew harness send R-1 --text <message>`" in stepped and "`aew harness interrupt R-1`" in stepped
    # The planted defect: the guide's own bare text, returned as a step, is what the rule catches.
    assert o_cmd(K.WAKE_GUIDE[K.OUT_OF_SCOPE].act)
