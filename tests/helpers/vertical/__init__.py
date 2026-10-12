"""The vertical UAT's actors and its burden ledger (docs/implementation/vertical-uat.md).

``ledger`` holds the counters, the pinned thresholds and the one-screen summary; ``scripted_operator`` is the
operator (only what a human types at a fresh terminal); ``lead`` is the scripted Lead that runs inside the fake
OpenCode TUI; ``chat`` is the chat between them; ``workers`` routes the fake harness's worker runs to their role's
script.
"""
