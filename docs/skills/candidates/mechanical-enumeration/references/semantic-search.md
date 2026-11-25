# Semantic search and stable identity

Use for code-structure classes, aliases/constants, graph closure or multiple parses.

**Bindings before spellings.** Resolve a read through its lexical binding and reaching definitions. In straight-line local code, the last assignment before the read replaces earlier values. Across branches, loops, exceptions, closures or calls that mutate state, there may be several reaching values or an unknown. Do not take the last textual assignment in the function as proof it always executes. Respect shadowing, global/nonlocal rules and imported aliases; resolve calls through imports/bindings, not every attribute with the same name.

**Cover the forms the class permits.** Inspect positional and keyword arguments, dict keys/values, annotated assignments, class/attribute writes, unpacking and imported constants as applicable. Decode literal values rather than trusting comments or source spellings. In Python, Assign and AnnAssign differ; C macros and build flags require their own preprocessing/configuration account. A parser accepting a file does not prove a matcher covers its constructs.

**Stable sites.** Never join separate parses by object id(), or retain freed-object IDs as identities. Use pinned file identity plus source span, node kind, enclosing scope and a deterministic structural path where spans collide. Line/column alone can be insufficient, notably for older Python f-string positions. Verify parser behavior on the supported minimum runtime. Across revisions, use explicit matching rather than assuming unchanged line numbers.

**Closure with limits.** Follow supported calls to a fixed point with visited identities. If bounded, report the bound, frontier and unresolved edges. Dynamic dispatch or unmodelled imports remain unknown; an over-approximate graph is a candidate set. Inspect/classify its members rather than treating reachability guesses as violations.

**Independent checks.** Compare distinct methods at common site identity, not just counts or function names. Shared parsing/binding logic is a shared blind spot. Document each detector's limits plus combined unknowns; agreement does not erase either. Plant controls for known unsupported forms. If the consumer renders or concatenates strings, examine the final representation too: source-level boundaries can change after interpolation or separators are added.
