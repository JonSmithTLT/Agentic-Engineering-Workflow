"""The capability register (STG-15; A-38, the capability register position revision 2.1, CAPR-01 to CAPR-13).

Roles ask for capabilities (``EXACT_CODE_SEARCH``), and the register resolves them to providers: AEW's shipped
records under the operator's (:mod:`.records`), each provider's pinned payload (:mod:`.payload`), and each
capability's status on this host in S-01's seven terms (:mod:`.status`), all held as host state outside every project
and sandbox (:mod:`.store`). :mod:`.ops` is what the commands, ``aew doctor`` and the operator endpoint call.

CAP-1 brings ripgrep. The register supports pinned fetch and offline import. Contained runs bind the available
payloads read-only and configure the harness's lookup (the designer's CAP-1 ruling 1).
"""
