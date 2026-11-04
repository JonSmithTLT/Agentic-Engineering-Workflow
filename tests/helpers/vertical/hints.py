"""The command a projection hint prints, as the scripted Lead follows it (E116; the placeholder #319 printed).

A hint prints a command for a reader, with placeholders where the reader's own values go. The Lead fills the ones it
holds a value for: the revision (named by its owner, ``aew.harness.contract.REVISION``), the subject (``<T>``,
``<unit>``), and its own words for a reason (``<reason>``, ``<why>``). Anything else is **not followable**: the value is
a choice the Lead has no basis for (``<card>``, ``<CLASS>``, ``<n>``, ``<a|b>``, ``--to A|B``) or one it would have to
go and read (``<invocation from aew harness status>``). A placeholder never goes through as literal tokens.

Filling works on the text, before it is split: a placeholder of several words is several tokens afterwards, and nothing
can tell them from the command's own. The revision always goes last, whatever the hint's order, because the retries in
``Lead.gap_hint`` take it off the end.
"""

from __future__ import annotations

import shlex
from typing import Any

from printed_commands import ANGLE

from aew.harness import contract as K

REASON = "the projection offers nothing else, and its hint names this command"  # the Lead's own words
SUBJECTS = ("<T>", "<unit>")
REASONS = ("<reason>", "<why>")
EXPECT_REV = "--expect-rev"
NOT_FILLED = frozenset("<>{}|")  # a piece of a placeholder (`<x`), the projection's `{evidence}`, or alternatives
ELIDED = "..."  # run as printed it records "...": the reader cannot know it stands for a value (#319 review, F4)
PARSE_FAILED = ": error: "  # how argparse ends a usage message: `aew work transition: error: ...`
USAGE_CODE = "USAGE"  # aew.errors.UsageError's code


class NotFollowable(ValueError):
    """A hint's command the Lead cannot complete; the message says what is left."""


def _without_revision(argv: list[str]) -> list[str]:
    """``argv`` with every ``--expect-rev`` and its value taken out (``--expect-rev N``, ``--expect-rev=N``, the hint's
    own value): the value is the Lead's to supply."""
    out: list[str] = []
    at = 0
    while at < len(argv):
        word = argv[at]
        if word == EXPECT_REV:
            at += 1 if at + 1 == len(argv) or argv[at + 1].startswith("-") else 2
            continue
        if not word.startswith(f"{EXPECT_REV}="):
            out.append(word)
        at += 1
    return out


def fill_hint(text: str, subject: Any, revision: Any) -> list[str]:
    """The argv the Lead runs for a hint's command ``text`` (the words after ``aew``), or ``NotFollowable``. The subject
    goes after the command's words unless the hint already names what it acts on (``harness launch INV-0012``: a third
    word before the first option)."""
    values = {K.REVISION: revision, **dict.fromkeys(SUBJECTS, subject), **dict.fromkeys(REASONS, REASON)}
    for name, value in values.items():
        text = text.replace(name, shlex.quote(str(value)))
    left = ANGLE.findall(text)
    if left:
        raise NotFollowable(f"a placeholder the Lead holds no value for: {', '.join(left)}")
    try:
        argv = shlex.split(text)
    except ValueError as exc:
        raise NotFollowable(f"not one shell command line ({exc}): {text!r}") from None
    unfilled = [a for a in argv if a == ELIDED or NOT_FILLED & set(a)]
    if unfilled:
        raise NotFollowable(f"alternatives or a value the Lead cannot fill: {', '.join(unfilled)}")
    argv = _without_revision(argv)
    words = next((at for at, a in enumerate(argv) if a.startswith("-")), len(argv))
    if str(subject) not in argv and words <= 2:
        argv.insert(words, str(subject))
    return [*argv, EXPECT_REV, str(revision)]


def parse_failed(error: dict[str, Any]) -> bool:
    """Whether the command line did not parse: argparse's own message, with no AEW code. Its usage text lists options
    (`[--launch]`), so nothing in it is a refusal asking for one."""
    return not error.get("code") and PARSE_FAILED in str(error.get("message") or "")


def is_usage_error(error: dict[str, Any]) -> bool:
    """Whether a command's error is a usage error: argparse's, or AEW's own ``UsageError``."""
    return error.get("code") == USAGE_CODE or parse_failed(error)
