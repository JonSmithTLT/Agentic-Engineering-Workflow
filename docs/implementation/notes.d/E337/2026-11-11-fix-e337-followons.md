The live lane now refuses a catalog entry with unusable input or output rates for any provider. A
finite non-negative Python integer counts as a rate without conversion to a float. This preserves
the paid-model classification for large exact integers because this guard only distinguishes zero
from positive prices. The quickstart makes key export conditional and points to the shell forms above.

Ablations: restoring the old pricing check fails all seven unusable-price cases. Passing a large
integer through the float finiteness check fails with overflow. Restoring the old quickstart
wording fails the guide test.
