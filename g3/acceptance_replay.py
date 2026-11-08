"""A host's acceptance of a replay (``g3/README.md``): no command makes one, so this does, at the operator's terminal.

It asks for an approval on a set that is not any project's, so it moves no mode. Approve it in the confirmer. It
consumes the approved member twice, and prints ``CONSUMED``, then ``CONSENT_ALREADY_USED``.
"""

from aew import g3client as C
from aew.harness import g3_adapter as G
from aew.stg02 import wire as W

bound = {"project": "replay-check", "mode": "walk", "previous": None, "mode_rev": 0, "generation": 1,
         "legality_digest": "0" * 64}
approved, _ = G.approve(G.raise_set(bound), lambda pending: print("approve", pending["approval_ref"]))
member = approved["intents"][0]
for op in ("first", "replay"):
    print(C.consume(consent_set_ref=approved["consent_set_ref"], set_digest=W.set_digest(approved),
                    recipient_ref=approved["recipient_ref"], installation_ref=approved["installation_ref"],
                    intent_ref=member["intent_ref"], origin_proof_ref=member["origin_proof_ref"], owner=G.OWNER,
                    operation_ref=f"aew:steering-raise:{op}").result)
