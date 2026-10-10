"""Coordination messages: first-class Lead-worker messaging (register F9, F9-A; ADR-0017).

A coordination message moves knowledge, never project state: recording one commits nothing, moves no revision and is
read by no gate, transition or dispatch (F9 invariant 1). Messaging is off unless the operator adopts
``coordination.messaging: enabled`` in the execution policy, and off means absent: nothing is written, advertised or
changed.

* ``layout``: paths, ids, bounds and vocabularies, a leaf module that imports nothing from ``aew.engine``, so the
  store can learn a thread's path from it without depending on the engine.

The engine side (recording, identity, idempotency, refs, the switch) is ``aew.engine.coordination_ops``.
"""
