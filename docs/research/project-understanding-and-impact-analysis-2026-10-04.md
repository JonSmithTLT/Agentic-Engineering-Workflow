# S8 — Project understanding, the Project Profile, and Requirement Impact Analysis: what should exist above the structural map

- **Status:** research note with one probe, independent architecture review, 2026-10-04/05 (the designer's third brief, Parts A–E). Not governing. **Designer decisions, 2026-10-05:** the five open questions in §10 are settled (answers recorded there), and §8 is corrected: the T5 structural record stays independent of semantic availability; the public-surface counts, the test→symbol index and the constraint locator index are sibling derived indexes composed when their inputs exist, not fields of the base artifact. Probe: `repro/ria/impact_probe.py` with `impact_probe.out.txt` and `case{1,2,3}.json`: a deterministic requirement→surface pass scored against three real changes in the live repository's history. Everything marked **[probe]** is read from it; **[doc]** from the contracts, designs and ADRs named; **[inf]** inference; **[rec]** recommendation; **[hyp]** open; **[reject]** a part of the brief's hypothesis this note argues against.
- **The verdict on the hypothesis in one paragraph.** The decomposition survives with two corrections. First, **"Project Profile" is not a new layer: it is KC §8's maps (overview, architecture, codebase, ownership) plus WC §16.15's machine-readable guardrails, given the storage, provenance and freshness rules ADR-0008 and ADR-0013 already define**; what is new is only the insistence that each claim carries its own evidence and freshness. Second, **"Requirement Impact Analysis" is not a new artifact either: it is the deterministic supplier of what the plan-assurance design (v0.4, adopted) already demands before planning**, namely the first-pass acceptance inputs (governing contracts, parent invariants, relevant current source), the load-bearing premises and their discriminating probes, and the dependency set that drives invalidation. Building a separate impact-analysis record beside those would create the parallel truth store the brief forbids. The useful new thing is a **deterministic impact surface** (where, with evidence) computed from the maps in seconds, which the probe shows catches 100% of a localized change's files at radius 1 and about half of a cross-cutting one's, with the rest being exactly the files a model has to reason about. Accuracy over speed: the surface is labelled by how it was found, and what it cannot find is named.

## 0. The probe, because the rest leans on it [probe]

Three real requirements, each a commit or commit set on a live branch, scored at the commit's base from Git objects (no checkout): seed terms from the requirement → Python symbols, files, transition ops; one hop of callers/callees by name; tests that name the symbols; constraints surfaced (oracle rules in `tests/helpers/invariants.py`, schema keys, ADR mentions, error codes). Files the change *created* are reported separately: no location-based method can name a file that does not exist yet.

| Case | Requirement (from the commit) | Truth (existing files) | Seeds only | Seeds + radius 1 | Tests by named symbol | Created files |
|---|---|---|---|---|---|---|
| 1 Integration recovery (`9102b9b`) | "a later operator commit never strands a publish; failures named rightly" | 4 src | recall 0.75, precision 0.19 (16 predicted) | **recall 1.00**, precision 0.09 (44) | 0 of 0 | 1 (the new regression test) |
| 2 M4-C concurrency (`e91ab4f`+2) | "mutating concurrency above 1; both caps are admission rules checked by the walks" | 3 src + 4 tests | **recall 1.00**, precision 0.20 (15) | 1.00, 0.08 (37) | 0.75 (missed `invariants.py`, which the constraint pass surfaced as the rule "serial cap exceeded") | 0 |
| 3 M4-A dispatch predicate (`a149563`+1) | "one dispatch predicate on every dispatch route; Class 0 eligibility at dispatch" | 24 src + 5 tests | recall 0.29, precision 0.88 (8) | **recall 0.54**, precision 0.59 (22) | 0.60 | 10 (`dispatch.py`, `assurance.py`, `reasons.py`, …) |

Constraints surfaced without a model: case 1 brought up the six integration oracle rules (frontier coverage, candidate binding, gated fingerprint) and ADR-0004 (31 mentions); case 2 the serial-cap rule and the non-mutating cap rule, plus five schema files; case 3 ADR-0008/0006/0003 and the dispatch dependency rules. Each list is what a reviewer would want on the table before planning; none of it required judgement to find, and all of it is a locator into authority, not a restatement of it.

What the numbers mean, honestly [inf]: a seed-and-one-hop surface is **complete for localized requirements and about half-complete for cross-cutting ones**, at a precision of 10–20% (five to ten candidates per real file). The misses in case 3 are not noise: `gates.py`, `guide.py`, `lock.py`, `store.py`, `bridge.py` changed because "every dispatch route" and "Class 0 eligibility" are semantic couplings (same concept, no call edge), and ten files were created. That is the boundary between the deterministic part (where the requirement's nouns live and what touches them) and the model's part (which concepts the requirement reaches that share no symbol). The deterministic part costs about two seconds per requirement on AEW (185 files, 2,637 symbols) and names its evidence for every entry.

## 1. Recommended architecture (deliverable 1, question 15)

The brief's chain, corrected:

```text
AUTHORITATIVE PROJECT SOURCES           source, build config, schemas, contracts, ADRs, tests, requirements ledger
        ↓ (deterministic, revision-bound)
T5 STRUCTURAL MAP                       where the code is, shape, build/test artefacts, roles        [F22, exists as design]
        ↓ (deterministic, per-unit, labelled by tier)
SEMANTIC EXTENSIONS                     symbols, definitions, references, includes, configurations    [S2 contract]
        ↓
PROJECT PROFILE = KC §8 maps + §16.15 guardrails, as evidence-bound records with per-claim freshness
   ├─ deterministic records (overview facts, stack, build/test, boundaries)           ← generated
   └─ synthesized records (architecture, ownership, flows), each claim ← evidence     ← investigator discovery records
        ↓ at Story (or Epic) creation, and on demand
DETERMINISTIC IMPACT SURFACE            seeds → symbols/files/units → radius-1 → tests, rules, schemas, ADRs; labelled by how found
        ↓ feeds, does not replace
PLAN ASSURANCE FIRST PASS (v0.4 §7–§8)  acceptance inputs, preservation obligations, load-bearing premises, discriminating probes
        ↓
investigator (when a load-bearing premise has no current evidence) → planning → Tickets (inherit the Story's surface)
```

Three structural rules, all from existing authority [doc]:

1. **Nothing above the first line is authority** (KC §7.4 derived knowledge; the review response G3: "derived project knowledge with freshness/provenance, may contain K0 references"). Profile records and impact surfaces are locators and labelled summaries; the thing they point at is the evidence.
2. **One record family, one freshness mechanism.** Profile claims and discovery records are ADR-0008 source-bound records (`facts[{statement, evidence[]}]`, `observed_paths`, CURRENT/STALE/UNKNOWN by `engine/freshness.py`); the deterministic maps are ADR-0013 `reference` records with the S4 per-unit freshness. The impact surface is a **projection computed on demand** from those, recorded only when the Lead binds it to a Story (then it is a decision input with evidence refs, as plan proposals already are).
3. **Impact analysis has no record kind of its own beyond what plan assurance already specifies.** Its deterministic output lands in the first-pass artefact's slots ("relevant current source/runtime evidence", "known compatibility/security/persistence obligations", "relevant parent Story/Epic invariants", "what appears to be the intended subject of change"); its judgement output is the premise list of v0.4 §8 (`claim, status, evidence, alternatives, falsifier, probe, impact_if_wrong`). This is deliverable 9's main contradiction and it is argued in §9.

## 2. Part A — what an agent needs, and from which layer (questions 6, 13)

The brief's capability list, assigned [inf, with the S1/S3/T5 measurements]:

| Capability | Layer | Stored or on demand | Confidence |
|---|---|---|---|
| structural repository map | universal structural fact (T5) | stored, a few KB, in packs | deterministic |
| build targets, test/build commands, generated-code boundaries | structural (T5 `build_system`, `test_locations`, `generated_and_vendor`) plus the build's own compile database for C/C++ | stored | deterministic; "proposal for `checks.yaml`, never written into it" stands |
| translation units, configuration/compilation context | semantic extension (S2 units, configurations) | stored per unit; queried | compiler-known |
| symbol lookup, definition/reference lookup | semantic extension | **on demand** (`map.symbol`, 75–100 tokens [S3]) | compiler-known for C/C++; imports-only for Python until a type checker is an extension |
| call relationships | semantic extension | on demand (`map.callers/callees`, 55–345 tokens) | direct edges compiler-known; indirect labelled; `holds_pointer_to` separate |
| dependency/include relationships | semantic extension | on demand (`map.includers`) | compiler-known |
| subsystem/component membership | **Profile**, derived: directory role (structural) + public surface per directory (semantic) + a synthesized component record with evidence | stored as records; queried | deterministic for the directory→symbols part; synthesized for the component names |
| important data/control flows | Profile, synthesized (investigator) from `map.*` queries, each flow bound to the edges it rests on | stored as a discovery record | model synthesis over compiler-known edges; labelled |
| relevant contracts and architectural boundaries | Profile: the requirements ledger, ADR index and T7's amendment index are already the deterministic part; "boundary" statements are synthesized with evidence | stored; queried by subject | deterministic locators; synthesized prose |
| "what owns this state?" | Profile ownership record (KC §8.4: "prefer references to existing project authority"): deterministic candidates = the symbols that write the state (the probe's seed→writers pass), synthesized assignment | on demand with candidates | partial; must say so |
| which build configuration includes this code | semantic (`map.configuration`) | on demand | compiler-known |

**Not attempted** [rec]: whole-repository summaries written by a model and stored as fact (the brief's "large Markdown summary and hope"); inferred ownership without a cited authority or writer set; call graphs for languages without a compiler-grade extractor (Python calls by name are the probe's 10–20% precision tool, fine for an impact *candidate* list, not for a stored graph); "importance" scores for flows without a stated metric.

**The query surface is the S3 surface plus two operations the brief adds**, both deterministic over the Profile's records: `profile.component(path|symbol)` (which component record claims it, with the record's evidence and freshness) and `profile.owner(state_key|symbol)` (the writer set, deterministic, plus the ownership record if one exists, labelled). "What evidence supports this relationship?" is `map.evidence` for code edges and the record's `evidence[]` for profile claims.

## 3. Part B — the Project Profile (questions 1–5; deliverable 2)

### What it is [rec]

A **small set of structured records**, not documents: KC §8.1–§8.5 realized as records with the ADR-0008 shape, stored as ADR-0013 `reference` knowledge records (immutable versions, manifest-pinned, FTS-searchable, with dispositions when a claim is challenged or superseded). Humans get a projection (the dashboard renders the records; `aew profile show` renders text). The GSD-style `ARCHITECTURE.md`/`STACK.md`/`CONCERNS.md` set is **[reject]**ed as the *representation*: prose files have one freshness for the whole file, no per-claim evidence, invite editing as if authoritative, and duplicate KC §8 under new names. They are fine as a *rendering*.

### Fields that earn their place, with their source class

| Record | Content | Source class | Freshness scope |
|---|---|---|---|
| `profile.overview` (KC §8.1) | what the project is, problem, environment assumed, **which documents are authoritative** (pointers to spec-pin, ADR index, requirements ledger), high-level constraints as pointers | deterministic for the pointers; one synthesized paragraph for "what it is", bound to README/docs evidence | the pointed-at files |
| `profile.stack` | languages, toolchains, versions, package managers, runtimes | deterministic (T5 `languages`, `build_system`, lockfiles, CI config) | the files read |
| `profile.build_test` | build systems, test runners, check commands **as observed**, CI lanes, coverage baseline location | deterministic (T5 + CI files + `checks.yaml` + `pyproject`); the proposal/actual distinction kept | the files read |
| `profile.boundaries` | generated vs source, vendor, protected paths, schema and contract locations, public vs private surfaces (external-linkage definitions per directory for C; `__all__`/underscore for Python) | deterministic (T5 + semantic) | listing + the units' facts |
| `profile.components[]` (KC §8.2 "major components") | name, directories, public surface, depends-on (edge counts between directories), evidence | **hybrid**: directories, surfaces and edge counts deterministic; the component *names and boundaries* synthesized by an investigator from those, each with evidence | per component: its directories' units |
| `profile.flows[]` (KC §8.2 "important cross-component flows") | name, the edge path, entry and exit symbols, evidence per edge | synthesized over `map.*` answers; each edge is a compiler-known fact or labelled | the units on the path |
| `profile.ownership[]` (KC §8.4) | state or behaviour → owning component, **writer set** (deterministic), authority reference if any | hybrid; "prefer references to existing project authority" | writers' units |
| `profile.contracts` | the authoritative documents and their amendment status (T7's index), the invariant index, the requirements ledger: **pointers only** | deterministic | those files |
| `profile.guardrails` (WC §16.15) | machine-readable: ownership/directory boundaries, dependency directions, layering, generated-file policy, review triggers | **declared by the project** (policy), not derived; the Profile only points at and checks them | the policy file |
| `profile.navigation` | "start here for X": entry points, the test for a subsystem, the ADR for a decision | deterministic candidates (entry points, test locations, ADR index) + a few synthesized hints with evidence | mixed |

### Rejected fields, and why [rec]

- **"Stable project constraints" as prose.** Constraints are either in authority (WC/KC, ADRs, the invariant index, `checks.yaml`, guardrails), where the Profile points, or they are requirement-relative (Part C). A constraint written only in the Profile is a second specification; **[reject]**.
- **A global "concerns" record.** Agreed with the brief: a fact becomes a concern relative to a goal. The deterministic facts that *tend* to become concerns (several writers of one state, a hot header, a dispatch-table interface) are Profile facts with their writer sets and fan-outs; the concern is computed in Part C. **[reject]** as a stored section.
- **Roadmap / current state / handoff (KC §8.6–§8.8).** They are control state and decisions, already durable elsewhere; the Profile would copy them. Out.
- **Glossary (KC §8.5).** Useful, but it is model-authored prose with no evidence binding beyond "the term appears here"; keep it as a discovery record if an investigator writes one, not as a Profile field with freshness semantics it cannot honour. [hyp] revisit after the K-arm evaluation.
- **"Importance" rankings of flows or components** without a stated metric. Edge counts and fan-out are metrics; "important" is not.
- **Anything a model wrote about code it did not cite.**

### Representation (question 4) [rec]

One `aew/profile/v1` record *per section* (so sections version and age independently), each a knowledge `reference` record: `{schema, id, version, section, source_revision, extractor|author, claims[{statement, evidence[{kind: file|symbol|edge|record|contract, locator, sha256?}], source_class, observed_paths}], freshness}`. The deterministic sections are regenerated by `aew map generate`-style jobs (T5's command family grows `profile`); the synthesized sections are investigator discovery records accepted by the Lead and *pointed at* by the Profile (exactly T5 §6's architecture-map mechanism). One human projection renders them all. This is the brief's "one structured profile with human projections", with the hybrid that the synthesized parts are already a record kind AEW has.

### Provenance and freshness at claim level (question 5) [rec]

- **Per claim, not per section, not per profile.** Each claim carries `observed_paths` (and, for semantic facts, the unit ids); `record_freshness` already computes CURRENT/STALE from `git diff --name-only observed authoritative -- paths`. A section is CURRENT when all its claims are; the Profile reports counts, never one flag (S4's rule for the semantic map, for the same reason: at any real scale something is always stale).
- **Source class per claim**, reusing the knowledge drafts' vocabulary: `ENGINE_OBSERVED` for deterministic claims (the generator ran against the tree), `ROLE_ATTESTED` for an investigator's synthesis (bound to evidence but authored by a model), `EXTERNAL_UNTRUSTED` for anything imported (a README's self-description). Packs render the class, as T4's prototype renders the entry trust label.
- **Invalidation is per claim and cheap**: a commit stales the claims whose paths it touched; the deterministic sections regenerate in a second (T5: 0.1 s structural; S4 per-unit for semantic); synthesized claims stay STALE until an investigator re-verifies them or the Lead accepts them as still valid with a disposition (ADR-0013 `reassessed`). A STALE architecture claim is navigation (KC §13), and is shown as such.
- **No silent widening**: a claim's evidence list is fixed at authoring; "still true" is a new version or a disposition, never an edit.

## 4. Part C — Requirement Impact Analysis (questions 7–12; deliverable 3)

### The contract [rec]

Not a new record kind. Two outputs, both into existing slots:

**(a) The deterministic impact surface**, computed at Story creation (and on demand, `aew impact <work-id>`), from the requirement text, the Story's declared subject refs, and the maps:

```text
impact_surface (projection, recorded as a decision input when the Lead binds it):
  requirement_ref            the Story's accepted intent (its revision)
  seeds[]                    terms and exact refs resolved: symbols, files, ops, schema keys, ids   [how found: exact|lexical]
  affected_units[]           seed units + radius-1 (callers/callees/includers), each with {reason, evidence, tier}
  tests[]                    tests naming the symbols; the check lanes that run them
  constraints[]              oracle rules, invariant-index entries, schema fields, guardrails, ADR sections, contract
                             citations (T7 index) that mention the seeds: locators into authority, never restated
  configurations[]           build configurations / units the surface spans (C: cfg ids; Python: n/a)
  ownership_candidates[]     writer sets of the state the seeds touch (deterministic), plus Profile ownership records
  coverage                   how it was computed: index revision, map freshness counts, languages without call facts,
                             radius, generic names excluded, "created files cannot be predicted"
  not_found[]                seeds that resolved to nothing (a `NOT_FOUND` the Lead must look at, per S6)
```

**(b) The judgement part, written into plan assurance's first-pass artefact and premise list** (v0.4 §7–§8), by the Lead or an investigator, each item citing surface entries:

```text
intended subject of change        ← the surface's affected units, trimmed by judgement, each kept or dropped with a reason
preservation obligations          ← constraints[] the change must keep (rules, invariants, contracts)
known externally visible constraints  ← guardrails, public surfaces among affected units
requirement-relative risks        ← "N writers of state S + requirement R" style statements, each citing the writer set
assumptions / load-bearing premises   ← v0.4 §8 records: claim, evidence, alternatives, falsifier, probe, impact_if_wrong
known unknowns                    ← not_found[], STALE claims the surface touched, languages without facts
investigation needs               ← the premises with no current evidence and a cheap discriminating probe
likely tests/gates affected       ← tests[] plus the gates the constraints imply
```

Every line in (b) cites (a); (a) cites the maps; the maps cite the source. That is the evidence path the brief requires, and it is why (b) is not a new authority: it is a plan-assurance artefact that happens to be better grounded.

### Epic versus Story (question 1) [rec]

- **Epic**: the surface is computed at **component granularity** (Profile `components[]`, directory roles, configurations), with seeds from the Epic's intent; its judgement output is the list of Stories' likely subjects and the cross-component constraints (contracts touched by more than one component). No file-level surface: it would be wrong by the time Stories exist, and the probe shows cross-cutting requirements are where file-level prediction is weakest (0.54).
- **Story**: file/symbol/unit granularity, as above; this is where the probe's 1.00 recall for localized requirements applies, and where the premise list is written.
- The two differ in granularity and in what they feed (Stories' creation versus a Story's plan), not in mechanism.

### Tickets (question 2) [rec]

Tickets **inherit** the Story's surface and premises; a Ticket's own pass is a *narrowing* (its declared scope ∩ the Story surface) plus a staleness check, computed, not re-analysed. A Ticket runs a fresh analysis only when its scope leaves the Story surface (which is itself a finding: `SCOPE_OUTSIDE_STORY_SURFACE`, a plan-lint item) or when the Story's surface is STALE beyond a threshold.

### Deterministic versus judgement (questions 3, 4, 9) [probe-grounded]

Deterministic: seeds, affected units at radius 1, tests, constraints as locators, configurations, writer sets, coverage, not-found. Judgement: trimming the surface (precision is 10–20%), the semantic couplings with no edge (the case-3 misses), the risk statements, which premises are load-bearing, what the probe should be, what will be created (new files are a design output). The line is exactly where the probe's recall stopped.

### When an investigator is launched before planning (questions 5, 10) [rec]

Deterministically triggered, in the plan-assurance spirit ("which uncertain premise, if false, would change the work?"):

- a load-bearing premise whose evidence is **absent** (the Lead wrote it; the surface has nothing for it) or **STALE** (its paths changed since the Profile claim or discovery record it rests on);
- a seed that resolved to **nothing** (`NOT_FOUND`) while the requirement clearly names a thing;
- a surface spanning a language or component **without call facts** ("no `calls` facts for Python": the dispatch routes question of case 3 is exactly this);
- an **ownership question** with more than one writer and no authority reference;
- the Epic→Story split touching **more than one component's contract**.

Otherwise the Lead plans. The investigator's discovery record then becomes evidence for the premise and, if general, a Profile claim (question 9 below).

### Staleness and amendment (questions 7, 8, 12) [rec]

- The surface is stale when any of its `observed_paths` changed (the same mechanism), when the requirement revision changed (Ticket revisions, F4), or when the maps it was computed from were regenerated with a different extractor identity. Recompute is seconds; the *judgement* lines are re-read against the new surface, and the Lead re-affirms or revises them: an explicit, recorded step (the hierarchy design §12 checklist applies: plan, packs, evidence, dependencies, descendants).
- When implementation discovers something unexpected (a writer the surface missed; a constraint not surfaced), the implementer's report (WC §10 "unexpected findings, deviations") is the trigger; the Lead records a **premise outcome** (`EXECUTION_PREMISE_CONTRADICTION` exists in v0.4's registry) and either amends the Story's premises or revises the Ticket. The surface itself is recomputed; what changed between versions is the "impact delta" the Lead reads.

### Promotion to the Profile (question 9) [rec]

A local finding becomes a Profile claim only through the existing path: an investigator's discovery record (or the implementer's attested finding, as a K1 Case via ADR-0013's capture) → Lead acceptance → a `reference` record version with the finding's evidence. "Repeated" is detectable (the knowledge index's `about()` over the same subject) but repetition is not the criterion; **generality with evidence** is. A finding that is only true for the Story stays with the Story.

### Challenging the brief's equation [inf]

"Profile = stable reusable understanding; impact analysis = requirement × current understanding" is right as a slogan and wrong as an architecture in one way: the *current understanding* a requirement is multiplied by is mostly **not the Profile**, it is the maps (symbols, edges, tests, constraints as locators), because the Profile's synthesized claims are the least precise inputs available. The Profile contributes component membership, ownership records and guardrails to the surface; the heavy lifting is maps × requirement. So: impact analysis = requirement × maps, qualified by the Profile.

## 5. Part D — context delivery (question 13; deliverable 6)

Per consumer, what arrives automatically versus by deferred tool, following the recall design's budgeting order (§21) and S6's staging (packs run Stage 1–2 only):

| Consumer | Automatically in the pack | Through deferred typed tools | Never |
|---|---|---|---|
| **Lead planning a cross-cutting Story** | the Story's deterministic impact surface summary (counts, top units by reason, constraints as locators, not-found list), Profile `components` touched with freshness counts, the premise template | `map.*`, `profile.component/owner`, `history`, `knowledge.search`, `aew impact --radius 2` under budget | the graph; synthesized architecture prose beyond the touched components |
| **Investigator establishing unknown architecture** | the structural map; Profile L0 (which records exist, their freshness); the premise it is to discriminate; the launch contract's query list | everything in `map.*` and `profile.*`; source read; checks in its observation workspace | the Lead's preferred answer (plan assurance's anti-anchoring rule) |
| **Implementer changing one subsystem** | its Ticket's narrowed surface: the units in scope with their constraints (rules, guardrails, public surfaces) and the tests that name them; the Profile boundary record for its directories | `map.symbol/callers/callees/evidence` for the symbols it touches; `profile.owner` | Epic-level material; other components' flows |
| **Reviewer examining a diff** | the diff's units mapped onto the Ticket's surface: in-scope / **outside the surface** (the finding), the constraints those units carry, the tests that should have run | `map.callers` of changed symbols (who else is affected), `map.evidence` | the implementer's rationale beyond the report |
| **Verifier checking requirement satisfaction** | the Story's intended observable change and preservation obligations (first-pass artefact), the tests[] and gates the surface named, coverage of the surface by executed tests (S1's coverage overlay) | `map.*` for the symbols in the acceptance checks | the plan |

Two rules from the measurements: a pack section built from the surface is a few hundred tokens per subject symbol (S3) and should stay there; anything with "all" in it (all callers across the repo, radius 2) is a tool call with a budget. And S6's router is the same decision engine here: "where is X" from the pack's locators, "trace" through tools.

## 6. Part E — evaluation (question 14; deliverable 7)

Codebase understanding (most of it already measured, and the measurements are the baseline):

- symbol/definition accuracy, call-edge precision/coverage, build-context accuracy: S1's oracle (100% / 99.4–99.5% / compiler-known) per extractor identity, rerun on every toolchain or extractor change; a C++ and a Python-with-type-checker extension each get the same oracle;
- generated/source and subsystem-location classification: T5's role table versus a hand-labelled directory set per repository (the probe showed 2 of 7 and 8 of 13 `unknown`; the metric is `unknown` rate and mislabel rate);
- architectural claim support: for each Profile synthesized claim, does every statement cite evidence that exists and is CURRENT, and does a fresh investigator reading only the evidence reach the same claim (inter-rater agreement on a sample);
- context retrieval usefulness: the K-arm comparison (F19) of a role with the pack-plus-tools design against grep-only, on tokens, time and task success;
- refresh cost: wall time per commit for the deterministic sections, per unit for semantic (S4), per claim for synthesized (count of STALE claims per week).

Impact analysis, with the probe as the method and more cases as the corpus:

- **affected-area recall** and **false-positive expansion** at seeds-only, radius 1, radius 2, against real changes' existing files (the probe's three cases; target 20–30 from the live history, each with its commit message as the requirement); report **created files** separately as the ceiling on any location-based method;
- **missed constraints**: for each case, the rules/ADRs/guardrails the change touched (its diff hits them) versus those the surface listed;
- **useful risks / hallucinated risks**: for the judgement lines, a reviewer labels each risk statement as supported-by-cited-surface / unsupported; the hallucination rate is the number that cite nothing or cite a surface entry that does not say what the risk claims;
- **investigations correctly requested**: did the deterministic triggers (§4) fire for the cases where the real change needed reconnaissance (M4-A's "every route" is one), and did they stay quiet for localized ones (cases 1–2);
- **planning quality and rework**: the two-arm dogfood (plan assurance's own evaluation program): Leads with the surface versus without, scored on plan scope validity (v0.4 §challenge "is the mutable scope broader than evidence justifies / is required scope missing") and on Ticket revisions caused by surprises;
- **token cost** of the surface in packs versus the baseline pack.

The primary metric, as the brief says: the rate at which a Lead or implementer **confidently pursued an incomplete or incorrect surface** with the analysis present versus absent, measured by scope-validity challenges raised and by implementer "unexpected findings" that were in the surface's not-found or STALE lists (the analysis knew it did not know) versus ones that were not (it missed).

## 7. Tool and data surface for the impact analyser (question 8; deliverable 4)

Inputs: the requirement text and its exact refs; the Story's parent obligations; the structural map; the semantic artefacts (symbol table, edges, units, configurations, fan-out); the test index (test → symbols named; lanes); the constraint locators (oracle rules, invariant index, schema keys, guardrails, ADR index, T7 amendment index, requirements ledger); the Profile records with freshness; the history index (prior Cases about the same subjects, through `knowledge.search` by subject). Tools: the S3 `map.*` set, `profile.*`, `history links/show`, `knowledge.search`, and `aew impact` itself with `--radius`, `--configuration`, `--explain <entry>` (why an entry is in the surface, which is the evidence line).

## 8. Implications for T5 v0.4 (deliverable 8)

**Changes that belong in T5 v0.4 (structural), as corrected by the designer:**

1. The structural generator reads the commit's tree (`ls-tree`), not the index, and freshness is listing-plus-config scoped (T5 probe corrections). This is the only change to the base structural artifact; it must stay generatable from Git objects alone, with no dependency on semantic data.
2. The semantic-extension contract carries S2's fact tiers, unit identity and per-unit freshness, the `holds_pointer_to` edge kind, and S1b's additions (`instances[]`, `dependent | virtual | overrides`, mandatory toolchain identity, `source: codegen`); the query surface is S3's plus `map.configuration` and `map.evidence`.

**Sibling project-understanding indexes (derived, composed, each with its own freshness; not part of the structural record):**

3. **Test index**: test file → directories it exercises (structural, from paths) and, when a semantic extension exists, → symbols it names. Degrades to the structural half without semantic data and says so.
4. **Public-surface counts per directory**: external-linkage definitions per directory, available only when a semantic extension covers the language; absent otherwise, never a required structural field.
5. **Constraint locator index**: oracle rules, invariant-index ids, schema keys, guardrail entries, ADR sections, requirements-ledger ids, each with the terms they mention. Deterministic text indexing over authority; a project-understanding index beside the maps, because contract and ADR text is not repository structure.

The impact surface (§4) composes 1–5 and declares which of them were available (its `coverage`), which is what lets an Epic-level pass run on directory roles alone before any `components[]` record exists.

**Features that belong in a later Profile/Impact design, not in T5:** the Profile record family and its generators; `aew impact`; the plan-assurance slot filling; investigator triggers; the Ticket narrowing rule; the evaluation corpus of real changes. T5 v0.4 states that it is the substrate for them and names items 1–2 as its own and 3–5 as the sibling indexes it enables.

## 9. Contradictions with the hypothesis (deliverable 9)

1. **[reject] A Project Profile layer distinct from KC §8 and WC §16.15.** The content the brief lists is KC §8.1–§8.5 plus §16.15 guardrails. Introducing a new name invites a new document set and a second specification. Keep the KC names; add the record representation and per-claim freshness.
2. **[reject] Impact analysis as its own artefact.** Plan assurance v0.4 already defines the first-pass inputs, premise records, probes and dependency-sensitive invalidation that the brief's candidate output lists. The deterministic surface is new and valuable; the judgement output must be those artefacts, or AEW has two premise lists.
3. **[reject] "Profile = understanding; impact = requirement × Profile."** Measured: the surface comes from maps, tests and constraint locators; the Profile qualifies it (components, ownership, guardrails). Design the surface against the maps first.
4. **[reject] Full-profile invalidation.** Per-claim freshness exists in `engine/freshness.py` and ADR-0008; use it.
5. **[reject] Separate generated documents as representation.** Records per section, projections for humans.
6. **Partly reject "stable project constraints" and "concerns" as Profile sections.** Constraints live in authority and are pointed at; concerns are requirement-relative and computed.
7. **Confirm** the three-layer base (sources → structural → semantic) and the flow into investigation/planning, the preference for on-demand queries over graph dumps (S3's sizes), the rule that partial beats convincing, and the primary evaluation metric.

## 10. Designer decisions (2026-10-05), closing the questions this note left open

1. **`aew impact` is one deterministic operation with two consumers**: an inspectable Lead command, and Plan Assurance calling it automatically at Story creation. One implementation, no divergence.
2. **Radius 1 by default; radius 2 only when explicitly requested and budgeted.**
3. **Epics do not wait for synthesized `components[]`.** Before those records exist, the Epic-level surface runs on structural directory roles and declares the reduced coverage.
4. **Impact-derived investigator triggers are advisory during the evaluation phase.** Plan Assurance's existing hard evidence and protected-condition requirements remain hard independently of this.
5. **A 20–30 case stratified real-change corpus** is enough for the first promotion decision, provided it includes localized and genuinely cross-cutting work, not thirty easy examples.

And the program state the designer set: D9 → architecture proven → approve and amend ADRs → capture-service implementation later. T5 structural probe + S1–S7 + S1b → research capped → consolidate T5 v0.4 and the semantic-extension contract. S8 → stable project understanding uses existing KC machinery; a new deterministic impact surface feeds existing Plan Assurance; evaluate before making it mandatory.
