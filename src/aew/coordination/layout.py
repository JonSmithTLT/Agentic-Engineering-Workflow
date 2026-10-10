"""Where coordination lives, how its ids look, and its bounds (F9-A plan v4 D-2, D-3, D-6, D-7, D-11, D-12, D-31).

A leaf module: paths and constants only. It imports nothing from ``aew.engine``, so any module (the store, from MS2)
can find a thread without depending on the engine (D-16).
"""

from __future__ import annotations

import re

MESSAGE_SCHEMA = "aew/coordination-message/v1"
MARKER_SCHEMA = "aew/coordination-marker/v1"
THREAD_GENESIS = "aew/coordination-thread/v1"  # the chain's genesis is the sha256 of this, a colon, and the thread id

# The project-scoped marker (D-31): written once, before the project's first thread, and never removed. Reads ask
# "does any thread exist" with one stat of it. Under `.aew/coordination/`, never under a run directory.
COORDINATION_DIR = "coordination"
MARKER_REL = f"{COORDINATION_DIR}/marker.yaml"

INVOCATION_RE = re.compile(r"^INV-[0-9]+$")  # a role invocation: the only kind that has a thread
# Any invocation id control state holds: a role invocation, or an engine custodian (`IA-n`, M4-D), which is refused
# as a recipient by what it is (NOT_A_WORKER), not by the shape of its name.
ANY_INVOCATION_RE = re.compile(r"^[A-Z]+-[0-9]+$")
MESSAGE_ID_RE = re.compile(r"^MSG-(INV-[0-9]+)-([1-9][0-9]*)$")
IDEMPOTENCY_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")  # an explicit id; a derived one is `sha256:<hex>` (D-8)
DERIVED_ID_PREFIX = "sha256:"


def thread_rel(work_id: str, invocation: str) -> str:
    """One append-only thread per invocation, under its unit (D-1, D-3): outside control state and every run
    directory, so a contained worker cannot write it."""
    return f"work/{work_id}/{COORDINATION_DIR}/{invocation}.jsonl"


def message_id(invocation: str, seq: int) -> str:
    """``MSG-<INV>-<n>``, the thread's own sequence (D-2): no global counter, so recording commits nothing."""
    return f"MSG-{invocation}-{seq}"


def lead_party(generation: int) -> str:
    return f"lead:{generation}"


def invocation_party(invocation: str) -> str:
    return f"invocation:{invocation}"


# Bounds (D-7), code constants. Each refusal names its bound.
MAX_BODY_CHARS = 4000
MAX_REFS = 8
MAX_REF_CHARS = 200
MAX_THREAD_MESSAGES = 200
MAX_UNDELIVERED_LEAD = 16  # Lead messages on one thread not yet delivered
MAX_UNSEEN_WORKER = 20  # worker messages on one thread not yet shown to the Lead (LEAD_INBOX_FULL)

# The eight kinds of F9-A1 §9 (D-11): presentation only; no engine module branches on a kind.
KINDS = ("instruction", "question", "clarification", "finding", "blocker", "status", "acknowledgement", "correction")
LEAD_DEFAULT_KIND = "instruction"
WORKER_DEFAULT_KIND = "status"
ACKNOWLEDGEMENT = "acknowledgement"

# Where a message entered (D-6).
CHANNELS = ("lead_mcp", "lead_broker", "cli", "run_bridge")

# Refs are `kind:value` strings (D-12). They grant no access and are never resolved for the recipient.
REF_KINDS = ("evidence", "ticket", "finding", "message", "run", "decision", "source")

# Line types of a thread (D-3). MS1 writes messages only; facts (POSTED, DELIVERED, UNDELIVERABLE) arrive with the
# slices that observe them, and readers already chain-verify and count them.
MESSAGE_LINE, FACT_LINE = "message", "fact"
DELIVERED = "DELIVERED"
