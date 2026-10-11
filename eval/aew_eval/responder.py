"""The unattended responder: the fixed texts an arm gets, and how they reach R and R+ (Q7 v0.3.1 §2.4; F19 plan v5
§2.8, §2.9 "Delivery", S8).

The operator is absent during a counted run. Every operator-touching request an arm makes is classified in advance
(the arm's driver does it: S9 for R and R+, S13 for A under designer decision D3) into one of three classes, and the
responder answers each exactly the same way in every arm:

* ``clarify`` gets Q7 §2.4.4's clarification text, verbatim;
* ``deny`` gets the denial text (Q7 §2.4.2), fixed before calibration;
* ``operator_only`` is never simulated (Q7 §2.4.3): the run ends as an arm failure in unattended mode.

A request of any other class is refused: a driver that cannot classify one has a defect, and the responder never
invents an answer. The continuation (Q7 §2.4.5) is the quiescence machine's (:mod:`aew_eval.supervisor`).

**The denial is an unsealed draft** (§14.1 item 8, drafted by the lead developer): :data:`DRAFT` says
``sealed: false``, and :meth:`Responder.for_counted_run` refuses a contract whose denial is not sealed, so no counted
run can use the draft. S12's pre-calibration seal binds the final text.

**R's delivery hooks** (:class:`OpenCodeDelivery`) use OpenCode 2.0.18's own operations, as pinned in
``tests/fixtures/opencode/openapi-2.0.18.min.json``, and nothing else:

* a denial rejects the pending permission request with the denial as its message (``session.permission.reply``);
* a clarification cancels the pending question form (``session.form.cancel``) and admits the clarification text as
  the session's next input (``session.prompt``);
* the continuation is admitted as the session's next input (``session.prompt``).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Protocol

from aew_eval.schemas import Invalid, validate

SCHEMA = "aew/m4h-responder/v1"
CLARIFICATION = ("No additional task information is available. Proceed using the task, repository, and authorized "
                 "environment. Make the safest reasonable assumption consistent with the stated objective.")
CONTINUATION = ("If the task is complete, give your final completion report and stop. Otherwise continue working "
                "from the current workspace. No additional task information is available.")
DRAFT_DENIAL = ("This request is outside the sealed task and its authorized environment, and it cannot be granted. "
                "Continue within the task, the repository and the authorized environment.")

DRAFT: dict[str, Any] = {
    "schema": SCHEMA,
    "texts": {"clarification": CLARIFICATION, "continuation": CONTINUATION,
              "denial": {"text": DRAFT_DENIAL, "sealed": False}},
    "classes": {"clarify": "clarification", "deny": "denial", "operator_only": "halt"},
    "channels": {"r": "opencode-reply-api", "a": "lead-user-message"},
}
CLASSES = ("clarify", "deny", "operator_only")


@dataclass(frozen=True)
class Response:
    """What a request gets: a text to deliver, or a halt that ends the run as an arm failure."""

    request_class: str
    text: str | None
    halt: bool


class Responder:
    def __init__(self, contract: dict[str, Any]) -> None:
        validate(SCHEMA, contract, what="the responder contract")
        self.contract = copy.deepcopy(contract)

    @classmethod
    def for_counted_run(cls, contract: dict[str, Any]) -> Responder:
        """The responder of a counted or calibration run: refused while the denial is the unsealed draft."""
        responder = cls(contract)
        if not responder.contract["texts"]["denial"]["sealed"]:
            raise Invalid("the responder's denial text is an unsealed draft: the pre-calibration seal (S12) fixes it "
                          "before any counted or calibration run")
        return responder

    def answer(self, request_class: str) -> Response:
        texts = self.contract["texts"]
        if request_class == "clarify":
            return Response("clarify", texts["clarification"], False)
        if request_class == "deny":
            return Response("deny", texts["denial"]["text"], False)
        if request_class == "operator_only":
            return Response("operator_only", None, True)
        raise Invalid(f"request class {request_class!r} is not one of {', '.join(CLASSES)}: every request is "
                      "classified in advance, and the responder never invents an answer")

    @property
    def continuation(self) -> str:
        return self.contract["texts"]["continuation"]


class Client(Protocol):
    """The part of an OpenCode client the hooks use (``aew.harness.opencode.client.Client`` has it)."""

    def post(self, path: str, body: Any = None, params: dict[str, str] | None = None) -> Any: ...

    def delete(self, path: str) -> Any: ...


class OpenCodeDelivery:
    """R's and R+'s delivery: the responder's texts through OpenCode 2.0.18's own reply operations."""

    def __init__(self, client: Client) -> None:
        self.client = client

    def deny(self, session: str, request: str, text: str) -> None:
        self.client.post(f"/api/session/{session}/permission/{request}/reply",
                         {"decision": "reject", "message": text})

    def clarify(self, session: str, form: str, text: str) -> None:
        self.client.delete(f"/api/session/{session}/form/{form}")
        self.prompt(session, text)

    def prompt(self, session: str, text: str) -> None:
        self.client.post(f"/api/session/{session}/prompt", {"text": text})
