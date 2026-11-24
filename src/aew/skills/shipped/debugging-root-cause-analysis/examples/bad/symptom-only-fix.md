# Bad: change behavior until the example passes

Given the cache example, a worker declares the translation table broken, changes the English label to `Livre`, and reports that the French request now passes.

The changed table makes the symptom disappear for one order by corrupting the English behavior. It does not test the competing cache hypothesis, does not preserve expected behavior, and is an unauthorized repair if the assignment was diagnosis only.

A subtler failure is “clear the whole cache before every call; root cause fixed.” That may hide the trigger but does not establish why identity was wrong or whether cache removal is an acceptable repair. Diagnose the omitted language dimension with mixed-state and fresh-state observations; leave repair tradeoffs and authorization to the assignment.
