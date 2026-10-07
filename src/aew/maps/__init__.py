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
