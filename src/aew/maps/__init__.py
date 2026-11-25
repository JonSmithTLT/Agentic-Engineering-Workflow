"""Project maps: derived project-navigation artifacts (design v0.5; register F22; ADR-0015).

A map is derived, non-authoritative state: it never grants workflow, policy, Knowledge-admission, integration or
publication authority (T5-INV-01), and it has its own revision domain (``map_revision``), never ``control_revision``.

* ``canonical``: names, canonical JSON and the artifact identity (pure);
* ``gitobjects``: ``TrackedTree``, the generator's only way to read a commit, with its input log;
* ``structural``: the structural generator, a pure function of a tracked tree and the ruleset (T5-A);
* ``store``: the closed writer of everything under ``.aew/local/maps/`` (artifacts, the registry and its log);
* ``freshness``: currentness of a record against a commit, computed on read and never written back;
* ``service``: what the ``aew map`` commands do.
"""

# The evidence class of every map V-01 serves (A-14 P01-37; register E293). It follows the path that produced and
# stored the map, never what the map says of itself: maps are written by agent-reachable code into agent-reachable
# ``.aew/local/maps/``, with no protected producer or ingress, so every map is this class, whatever its digest,
# generator name or freshness says. A reader adds it; the artifact never carries it (a self-label is a claim), and
# selecting a map never changes it (the Lead's selection is local, not a shared qualified one: P01-38).
EVIDENCE_CLASS = "AGENT_REACHABLE_DERIVED"
