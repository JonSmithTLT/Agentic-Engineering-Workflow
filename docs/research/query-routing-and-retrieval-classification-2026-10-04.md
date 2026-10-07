# S6 — Query routing: spending retrieval and reasoning in proportion to the information need

- **Status:** design note from the independent architecture review, 2026-10-04, on the designer's brief: a security-research platform (with SQL canonical records, vector retrieval, source/AST, call graphs, RE/Ghidra evidence, findings, LLM synthesis) found that "what does function X do?" and "how are packets handled through this program?" deserve radically different retrieval, and that rich questions got better once they could pull a connected neighbourhood rather than top-k chunks. The question is how a system classifies a query well enough to decide what path it deserves, and whether that gives AEW a reusable pattern for its substrates (source search, structural map, C/C++ semantic map, history/knowledge recall, raw evidence). Not governing; no coupling to that platform is proposed. It is used as the prior example; nothing in it was read beyond the brief.
- **Basis:** the recall/context-routing design v0.3 (§5 request modes, §9 exact resolution first, §10 similarity as candidates only, §16 L0–L3 disclosure, §19 context routing owns budget and omission reasons, §21 budgeting order, §24 "no useful result" is explicit, §27–§28 evaluation stages and metrics); the S1/S3 measurements (single-hop code questions answer in 55–450 tokens with evidence; radius-2 neighbourhoods 6–11k; the whole graph 33M); the T7 and T5 probes (exact structured lookups are the cheap, high-precision tier). **[probe]** marks a measured number; **[inf]** inference; **[rec]** recommendation; **[hyp]** open.
- **The pattern in one paragraph.** Route by **what the question binds to** and **what shape of answer it needs**, not by topic. Three cheap, deterministic signals decide the first path: whether the question names an anchor the system can resolve exactly (a symbol, an ID, a path, a failure signature), whether the asked relation is one the substrates store as a fact (defined-at, callers, includes, derived-from), and whether the answer is a *set of facts* or a *synthesis across facts*. A query with resolved anchors and a stored relation terminates on the exact path with no model call. Everything else escalates one stage at a time, each stage with a budget and a coverage check, and the thing that triggers escalation is a **measured gap** (unresolved anchor, empty or saturated result, low agreement between substrates), never a guess about the question's difficulty. Provenance is a property of the retrieved facts, so it survives every route; a classifier that could drop evidence or assert a fact is not allowed to exist, because the classifier only chooses *which deterministic query to run*.

## 1. A small taxonomy: six task classes, by binding and answer shape

Dozens of intents are brittle because they classify topics. Two dimensions classify needs, and they produce six classes that cover the designer's examples and AEW's.

| Class | Binding | Answer shape | Example (research platform / AEW) | Cheapest sufficient path |
|---|---|---|---|---|
| **A. Exact lookup** | one resolvable anchor | one record or locator | "where is X defined?" / `aew knowledge show K-0001` | exact resolution (§9 of the recall design); no model |
| **B. Relation fact** | one or more resolved anchors + a stored relation | a set of facts with evidence | "who calls X?", "which TUs include this header?", "what does K-0001 derive from?" | one typed query (`map.callers`, `history links`); no model |
| **C. Local explanation** | one resolved anchor | a short synthesis grounded in that anchor's own facts | "what does function X do?" | A + B at radius 1 (definition, callees, callers, its source range) → one bounded model call, or none if the record already carries a summary |
| **D. Neighbourhood trace** | several anchors, or one anchor plus a *path* relation | a connected subgraph with evidence per edge | "how does data get from X to Y?", "trace the ownership and lifetime of this object across the subsystem" | iterative expansion with a budget and a stop rule; model used to *choose* expansions and to synthesize, never to invent edges |
| **E. Discovery / unanchored** | no resolvable anchor (a concept, a behaviour, "packet handling") | candidates, then one of A–D | "how are packets handled through this program?" | lexical + semantic candidate generation (§10: candidates only) → anchor the top candidates → become D |
| **F. Judgement** | anchors optional | a decision or assessment, not a retrieval | "is this safe?", "should we reclassify?" | retrieval as needed (A–E) then the model; this class is the only one where reasoning, not retrieval, is the cost |

Two properties make this small set work:

- **Classes compose by escalation**: E becomes D once anchored; C is A+B plus a sentence; D is B repeated under a budget. There is one machinery with four dials (anchors, relations, radius, synthesis), not six engines.
- **The class is observable before any model call** (§3): "has an exact anchor" and "names a stored relation" are string and index checks; "needs synthesis" is decided by whether the asked shape is a set or a sentence, which the surface can expose as two different operations instead of inferring from prose.

## 2. The staged routing model

```text
Stage 0  Bind      parse anchors (IDs, symbols, paths, signatures) → try exact resolution for each
                   signal: anchors_total, anchors_resolved, relations_named, shape_requested
Stage 1  Exact     if anchors_resolved == anchors_total and the relation is stored:
                   run the typed query; return facts + evidence + boundary note.      STOP.   (classes A, B)
Stage 2  Local     if one anchor and shape == explanation:
                   gather radius-1 facts (definition, callees, callers, source range, prior knowledge about it)
                   within budget_small; if a summary record exists return it; else one model call grounded only in
                   those facts.                                                        STOP.   (class C)
Stage 3  Expand    if several anchors or a path relation: expand radius 1 from each anchor; check connectivity /
                   coverage; while gap and budget remain: pick the next expansion by a deterministic rule
                   (cheapest edge toward the other anchor; highest-fan-in unexplained node), re-check.
                   Synthesize over the collected subgraph with evidence per edge.        STOP.   (class D)
Stage 4  Discover  if anchors_resolved == 0: lexical + semantic candidates (bounded k); anchor the top ones
                   (resolve); re-enter at Stage 1–3 with them; report the candidate step as part of the answer.
                                                                                               (class E → A–D)
Stage 5  Judge     only when the shape requested is a decision: the model over whatever A–E produced.
                                                                                               (class F)
```

**Stopping conditions** (the designer's "no more context is needed" versus "retrieval failed"): each stage ends in exactly one of three states, and the state is part of the answer:

- `SATISFIED`: the requested relation returned facts, or the anchors are connected within radius, or the explanation's grounding set is non-empty and the model's answer cites only it.
- `EXHAUSTED_BUDGET`: facts exist but the expansion hit the budget; the answer says what was omitted and offers the next expansion (the recall design's "one useful next expansion", §16 L1).
- `NOT_FOUND`: an anchor did not resolve, or a stored relation returned nothing for a resolved anchor, or discovery produced no candidate above the floor. This is the recall design's "explicit no-hit state; do not fabricate" (§24), and it is distinguishable from `SATISFIED`-with-empty-set because the substrate's coverage says whether the question *could* have been answered: "no callers" with `calls` facts at `compiler_known` for that language is a fact; "no callers" for a language whose extension emits no `calls` is `NOT_SUPPORTED`, a fourth state.

**Escalation triggers are measured gaps, not difficulty estimates:** an unresolved anchor; a resolved anchor with an empty result for a relation the substrate does cover; two substrates disagreeing (the structural map says a directory is `tests`, the semantic map shows it defines public symbols); a radius-1 subgraph that does not connect the anchors; a discovery candidate set whose top scores are flat (no separation). Each is a boolean or a count the router can log.

## 3. Signals each decision can observe cheaply

Before any model call, in milliseconds, from the request binding (§5 of the recall design) and the substrates' indexes:

| Signal | How observed | Used by |
|---|---|---|
| `anchors_total`, `anchors_resolved` | regex for IDs (`K-0001`, `T-0001`, `INV-…`), paths, `symbol`-like tokens; exact lookup in the symbol table, the manifest, the knowledge index | Stage 0 → 1 / 4 |
| `relation_named` ∈ stored relations | a fixed vocabulary (`defined`, `callers`, `callees`, `includes`, `derived_from`, `supports`, `challenges`, `supersedes`, `history of`) matched lexically; or the operation the agent *called* (the surface makes the relation explicit) | Stage 1 |
| `shape_requested` ∈ {set, locator, explanation, trace, decision} | the operation called (`map.callers` is a set; a free-text question is explanation/trace by cue words "how", "trace", "why", "should") | Stage 2 / 3 / 5 |
| `substrate_coverage` for the anchor's language/kind | the capability matrix (S2 §1): which fact kinds exist at which tier | NOT_FOUND vs NOT_SUPPORTED |
| `result_size`, `fan_in`, `fan_out` of the anchor | counts from the index before fetching bodies | radius choice; the 6–11k-token cliff at radius 2 [probe] |
| `freshness` of the units/records touched | per-unit input-set staleness (S4); knowledge record freshness (KC §13) | qualification; whether to re-verify at L3 |
| `agreement` between substrates | structural role vs semantic facts; knowledge Case vs current source | escalation trigger |
| `candidate_separation` (Stage 4) | top-k lexical/semantic scores: gap between 1st and 5th | whether discovery produced an anchor or noise |
| `request_mode` | `EXPLICIT_LOOKUP` / `AUTOMATIC_DISCOVERY` / `CONTEXT_ROUTING` / `INVESTIGATION_HISTORY` (recall design §5) | which stages are allowed at all: context routing never runs Stage 5; investigation history may include held/challenged records |
| `budget_remaining` | tokens and calls from the request binding's `context_budget` | every stage's loop |

Not observable cheaply, and therefore not a routing input: "how hard is this question", "what the user really means", "whether the model will need more". The design refuses to estimate those; it measures gaps after cheap steps instead.

## 4. Should classification be deterministic, model-assisted or staged?

**Staged, with the model confined to three roles** [rec]:

1. **Never the first decision.** Stage 0/1 are deterministic; most research-platform-style simple queries and all of AEW's typed-surface calls end there. A model classifier in front of them would add latency and cost to the cheapest path and could misroute an exact lookup into a search.
2. **Choosing expansions in Stage 3 when the deterministic rule stalls** (two candidate edges toward the target with equal cost): the model picks, logs why, and the pick is itself recorded as a routing decision with evidence; it cannot add an edge.
3. **Synthesis** (Stages 2, 3, 5), grounded in retrieved facts only, with the citation check of the recall design's evaluation stages (§27).

**The failure the designer named: the classifier as a second semantic authority.** The safeguards are structural, not behavioural:

- The router selects **which deterministic queries run**; it never produces a fact. Facts come from substrates with provenance; the router's output is a plan plus a log.
- Candidate generation (Stage 4) is **candidates only** (recall design §10): a vector hit becomes an anchor only by exact resolution; nothing is asserted from similarity.
- Omission is **visible**: every answer lists what the router did not fetch and why (`EXHAUSTED_BUDGET`, `request_mode` exclusion, freshness), as §19 requires ("omission/truncation reasons").
- No answer loses provenance by route: the facts carry `unit:line`, record IDs, receipt and freshness regardless of whether they came through Stage 1 or Stage 4; the router adds its *own* provenance (stages run, signals observed, budget used) as a routing record, which is what makes it evaluable.
- The router cannot widen permissions or visibility (§19): `request_mode` and the visibility guard apply before Stage 0.

## 5. Failure and fallback

| Weakness | Behaviour |
|---|---|
| Anchor does not resolve (typo, renamed symbol, stale ID) | Stage 4 with the anchor text as the query, k small; return `NOT_FOUND` with the nearest candidates named as candidates, never substituted silently |
| Relation returns empty but the substrate covers it | `SATISFIED` with an empty set **and the coverage statement** ("no direct callers among 433 of 434 units; 1 unit failed to parse; address-taken in 3 tables") |
| Substrate does not cover the relation for this language | `NOT_SUPPORTED`, naming the extension and what it would take; no fallback to a model guess |
| Budget exhausted mid-trace | `EXHAUSTED_BUDGET` with the connected part so far, the frontier, and the one next expansion that would most reduce the gap |
| Substrates disagree | both facts returned with their tiers and freshness; the disagreement is the answer, and a candidate knowledge record (a challenge) if the request mode allows capture |
| Discovery yields flat scores | report "no anchor found above the floor"; offer the structural map's relevant directories as the deterministic fallback for orientation |
| Freshness is STALE on touched units | the answer is labelled; consequential claims point at L3 for re-verification, as KC §13 permits for navigation |
| Model synthesis cites a fact not in its grounding set | the citation check fails the answer (recall design §27 stage 3); return the facts without the synthesis |

## 6. Evaluation plan

Representative query set, built per substrate from questions whose ground truth is deterministic, so routing can be scored without a judge for most classes:

- **A/B (exact, relation)**: 200 questions generated from the artifacts themselves (definitions, callers, includes, derived-from) with known answers; metric: exact match, tokens and model calls (target: zero calls), latency.
- **C (local explanation)**: 50 functions with reference summaries written from their radius-1 facts; metrics: grounding (every claim cites a fact in the grounding set), tokens, one model call.
- **D (trace)**: 30 anchor pairs with a known connecting path in the semantic graph (curl's connection-filter chain is a good source); metrics: path found (recall), expansions used versus the shortest, tokens, `EXHAUSTED_BUDGET` rate, and whether the omission note names the right frontier.
- **E (discovery)**: 30 behaviour questions with a known anchor set (e.g. "packet handling" → the functions a human marked); metrics: anchor recall at k, candidate separation, and the cost of the wrong turn when the top candidate is a false anchor.
- **Negative controls**: questions about symbols that do not exist, relations the substrate does not cover, and stale units; metric: the router returns `NOT_FOUND` / `NOT_SUPPORTED` / labelled-stale rather than an answer. This is the hallucination test and it is the one that matters most.
- **Cost accounting**: for every query, tokens retrieved, tokens shown, model calls, substrates touched; a routing quality score is answer quality *minus* unnecessary spend, so that a router that always escalates to Stage 3 scores badly on the A/B set even though its answers are right. The recall design's §28 metrics (precision@k, qualification accuracy, counterevidence recall) apply to Stage 4 unchanged.
- **Ablations**: deterministic-only router; router with model-assisted expansion; always-RAG baseline (top-k chunks into one model call); always-agent baseline. The hypothesis to test is the designer's: proportionality beats either universal path on cost at equal or better quality.

Two evaluation arms belong to F19 and share its harness; the code-side questions are generated from the S1 extraction and need no human labels for A/B/D.

## 7. Implications for AEW's T5/S2–S3 design

1. **The typed surface is the router's Stage 1.** `map.symbol`, `map.callers`, `history links`, `knowledge show` are class A/B operations; making the relation explicit in the operation removes the only classification step that needs language understanding. An agent that calls `map.callers(X)` has classified its own question.
2. **Radius is the budget dial, and the cliff is measured.** Radius 1 answers are 80–450 tokens; radius 2 is 6–11k for connected functions [probe]. The surface should offer radius 1 freely and radius ≥ 2 only as a Stage 3 expansion under an explicit budget, which is the S2–S5 note's open question 4 answered.
3. **Coverage statements make empty answers meaningful.** `NOT_FOUND` versus `NOT_SUPPORTED` versus "none, and the substrate is complete here" is only possible because S2's capability matrix and per-unit quality exist; the routing design is a consumer of them, and they should be in the contract for that reason too.
4. **Discovery belongs to the structural map first.** For an unanchored question about a codebase, the cheapest deterministic orientation is the T5 structural map (directories, roles, entry points, a few KB), then lexical search over symbol names; vector search over code is optional and candidates-only, exactly as the recall design treats it for knowledge.
5. **The Lead's substrate choice is the same decision.** When a Lead asks "what do we know about X", the router binds X (a symbol → `map`; a Ticket → history; a failure signature → knowledge recall; a path → structural map plus source), and the request binding's mode decides whether held/challenged knowledge may appear. One router over all substrates, with the recall design's §5 binding as its input, rather than a per-substrate decision.
6. **Context routing for packs is Stage 1–2 only.** A pack preparer runs exact and local stages for the Ticket's declared subjects within the §21 budget order and never traces or judges; traces are what an investigator does on demand through the surface.

## 8. What is reusable, and what is not

Reusable as a pattern: the two-dimensional taxonomy (binding × shape), the staged model with measured-gap escalation, the three terminal states plus `NOT_SUPPORTED`, the "router selects queries, never produces facts" rule, and the cost-aware evaluation. These are substrate-agnostic.

Not transferable without re-measurement: the budgets and cliffs (AEW's radius-2 cliff is a property of C call graphs at curl's density; the research platform's RE evidence has its own), the anchor grammars, and the stored-relation vocabulary. Each system supplies its own, which is why the pattern is a contract for a router, not a router.

[hyp] Whether a learned classifier ever earns a place in front of Stage 1: only if the evaluation shows a class of questions where the deterministic signals misroute at a rate that costs more than the classifier's latency on every query. The data to decide that comes from the §6 evaluation, not from design.
