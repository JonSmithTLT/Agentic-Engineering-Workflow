"""The production OpenCode adapter with every Lead send posted as ``queue``.

No Lead path posts ``queue`` while coordination messaging is off (F9-A plan v4 amendment 2 §3.3, G1; register E55):
``harness send`` is ``next-step`` (``steer``) there, and ``turn-end`` goes only through the message store, from F9-A's
MS5b. The adapter's closing-window rule for a ``queue`` input (a turn is over only once none of AEW's prompts is still
queued) is kept covered at the adapter level instead: the supervisor's ``send`` reaches ``adapter.send(text, "queue")``.

Registered over the built-in ``opencode`` through ``AEW_HARNESS_ADAPTERS`` by the test that needs it.
"""

from __future__ import annotations

from aew.harness.opencode.adapter import OpenCodeAdapter


class QueueSendOpenCodeAdapter(OpenCodeAdapter):
    def send(self, text: str, delivery: str) -> None:
        super().send(text, "queue")
