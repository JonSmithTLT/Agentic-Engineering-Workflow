"""The work-item fact issuer (WIS): a systemd service that reads one AEW store read-only and attests its state.

STG-04's WIS-A, built to the adopted WIS issuer contract (A-27 as A-36 amends it: revision 9, wire
``wis-issuer-0.5-candidate``). The issuer reads the store itself through a read-only view and nothing pushes to it
(WIS-01); each read runs WIS-02's checks in order (:mod:`aew_wis.issuer`); the facts come from one function, the WIS
fact rule (:mod:`aew_wis.facts`, WIS-03); attestations, renewal and the witness follow WIS-04 to WIS-06 and WIS-09
(:mod:`aew_wis.wire`, :mod:`aew_wis.keys`, :mod:`aew_wis.service`); the install manifest is WIS-12's
(:mod:`aew_wis.manifest`).

**This package imports nothing from** ``aew`` (a test enforces it, two ways), and lives apart from it: the issuer's
trusted code is kept apart from the engine whose store it reads (WIS-01). Root installs it to a root-owned path and
runs it from there, never from the operator's editable checkout (G3-14's install-path rule, which WIS-12 follows), so
the install manifest covers this package and nothing of AEW's: it changes when the issuer does, not on every AEW
release. The engine's own rules the issuer must apply exactly (the transition hash, the sealed segment check, the
YAML loader and the control file's checksum trailer) are vendored in :mod:`aew_wis.engine_rules`, and a test requires
every vendored definition to equal the engine's.
"""

from __future__ import annotations
