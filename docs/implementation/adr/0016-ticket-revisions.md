# ADR-0016 — Ticket revisions

- **Status:** **Accepted** (lead developer, 2026-10-09), with the [F4 plan v8](../f4-ticket-revisions-plan.md) that it records, after eight independent plan reviews (v8 CLEAR). The ADR is written section by section, each with the slice that builds it (plan decision 42): §1 lands with slice S1. Later slices add their sections (enablement and the format raise, the hierarchy rules, records, admissibility, the lifecycle, confirmation, holds, replacement) and the readings RD1 to RD4 of the plan's §4.2, and ADR-0003, ADR-0004, ADR-0006, ADR-0007, ADR-0009 and ADR-0011 get dated amendments as those slices change them.
- **Resolves:** how the engine meets the Ticket-revision amendment (E19-B v0.4): which inputs a revision governs and how their change is computed (§1), and, in later sections, how revisions are recorded, bound, confirmed and committed.
- **Basis:** [E19-B v0.4](../../design/workflow-contract-amendment-ticket-revisions-2026-10-06.md) §2.3 and §2.4 (ledger TRA-04, TRA-05) for §1; the designer's decisions D1 to D7 of 2026-09-30; the [F4 plan v8](../f4-ticket-revisions-plan.md) §3.3, §3.4 and decisions 1 to 6; register F4.
- **Nature:** §1 adds a pure module, a packaged registry and its schema. It changes no engine behaviour, writes no state, and nothing calls it until S2a records live digests at enablement. F4 stays dormant on every project that has not been explicitly enabled (plan §3.2).

## Context

A Ticket's inputs live in two stores: its record (`work/<T>/ticket.md`: title, body, scope, acceptance, Class 0 assertions, external references, parent, kind) and control state (current class, own dependency edges, role plan). Further obligations come from its ancestors: the class floor, inherited mandatory gates and inherited dependency edges. E19-B §2.3 requires every revision-governed input, whichever store holds it, to belong to exactly one field group of an AEW-owned registry with a stable identity, with an unassigned input failing closed into the broadest acceptance-bearing group; §2.4 fixes the v1 canonicalization. Evidence (S3), plans (S4a) and revisions bind these digests, so they must be defined once, before any of those slices.

## 1. The field-group registry, canonicalization and digests (S1)

### 1.1 The registry and its identity

The registry is a package JSON document, `src/aew/schemas/ticket-field-registry.v1.json`, validated by `ticket-field-registry.schema.json` and by the loader's own rules (each field in exactly one primary group per store; every group declared; the `unassigned` group declared and material; every derived value the engine computes classified; a field hashed only through derived values in exactly those values' groups, so a change to what it feeds is a change to its groups; no key both an input and bookkeeping; version 1 with no predecessor and no moves; a later version's move names a group that version hashes the field in). It lists:

- the groups, each with its materiality: `acceptance`, `check_definition`, `scope`, `gate_set`, `dependencies` and `kind` are material (E19-B §4.3's list); `parent`, `card` and `staffing` are not;
- the record fields, the control-state keys and the derived values in each group, each with its canonicalization rule (§1.2);
- the record's provenance fields (`schema`, `id`, `created_at`, `created_by`), which are not inputs, and every control-state key that is engine bookkeeping, changed only by its own governed path;
- `moves`, empty in version 1 (§1.4).

The classification is the plan's §3.3 table. Two keys it does not name are classified here: a unit's `policy` (record and control) is in `gate_set`, because it holds the obligations a Story or Epic imposes on its descendants (a Ticket's is always absent or null), and `integration_frontier` is bookkeeping. F4's own later keys (`hierarchy_baseline`, `recorded_digests`, `revision_events` and the rest of the table's F4 row) are listed as bookkeeping now, and `carried_obligations` (written from S2b.2) is classified as an input hashed only through the derived values it feeds (V5). E6b's `authorization_envelope` stamp is not listed: the slice that adds it classifies it in `gate_set` (plan §9.2, §1.5).

Its identity is `aew/ticket-field-registry/v<version>@<sha256>`, the SHA-256 of the document's canonical JSON (§1.2), not of the file's bytes, so a checkout's line endings or formatting never change it. Every binding cites the identity.

### 1.2 Canonicalization

`aew.engine.ticket_fields.canonical(value, rule)` applies one rule per field:

- `text` and `text_list`: exactly E19-B §2.4's v1 set on prose (the title, the body, goal-backwards and contract statements, external references): CR and CRLF to LF, Unicode NFC, trailing spaces and tabs removed at each line's end. Nothing else is folded: case, punctuation, blank lines, interior and leading whitespace, a final newline, a no-break space and compatibility forms (NFKC) all change the digest. List order is kept.
- `exact`: the stored value, for identifiers, paths and globs (`scope.paths`, `acceptance.checks`, `acceptance.inputs`), classes, kind, parent and the role plan. The plan's §3.4 applies the text set to "text values"; this reads it as prose, because folding a trailing space in a glob or a check id could make two different scopes collide, and an exact value never collides more.
- Two declared set rules, each able to make two authored values hash the same, each with a collision conformance test (m7): `sorted_set` for `class0_assertions` (and the derived inherited gate names), deduplicated and sorted; `edge_set` for the effective dependency edges, `{id, kind}` per edge, deduplicated, sorted by id.

A group's payload maps `<store>:<field>` (`record:acceptance.checks`, `control:risk_class`, `derived:effective_edges`) to the canonical value; a classified field that is absent is `null`, so an absent field and an empty list differ. The digest is SHA-256 over `aew/tfg/v1:<group>\n` followed by the payload's canonical JSON: sorted keys, no whitespace, ASCII only. The mapping to JSON is one to one, so it adds no collision of its own: a YAML date or timestamp in an unclassified field is hashed as a tagged value, `{"$date": "<ISO>"}` or `{"$datetime": "<ISO>"}`, never as the same text, and an authored mapping key that starts with `$` is escaped with one more `$` (`$date` becomes `$$date`), so no authored value can spell a tag (`test_a_yaml_date_never_hashes_like_its_text`); a value JSON cannot hold exactly (NaN, a non-text key) is refused, never coerced. The authored bytes stay in the record (and, from S2c, in each revision record); canonical values are only hashed.

### 1.3 Live digests

`live_digests(state, work_id, record_text)` computes every group's digest now, from the Ticket's current record, its control state and what it inherits (M10). It is pure, so the caller passes the record's text, read from the record the unit names; the function refuses text that does not hash to the unit's `record_sha256` (`INTEGRITY_ERROR`, reason `RECORD_MISMATCH`), so a digest is never computed over another record. It refuses a Story or Epic: the groups are a Ticket's.

- **`gate_set`** holds the record's `class0_assertions` and `initial_risk_class`, the control `risk_class`, and the derived effective class, class floor and inherited mandatory gates, taken from `gates.effective_obligations`, the function gate evaluation uses. The class path's own gates are policy, bound by the legality digest of the [Policy Binding and Digest Amendment](../../design/policy-binding-digest-amendment-v0.1.md) (that amendment's A3, ledger PBD; not the F4 plan's §3.1 A3, the workspace carry-forward), and are not hashed.
- **`dependencies`** is the effective edge set from `hierarchy.effective_edges`: own and inherited edges are one group (m4), so an ancestor's `work depend` changes every descendant's digest (N6), and the same edge declared on the Ticket or inherited from its Story hashes the same.
- **Fail closed:** a record field, or a control-state key, that the registry does not classify is hashed into `acceptance` (`record:?<path>`, `control:?<key>`, where `<path>` is the JSON list of the path's keys, `record:?["acceptance","edge_cases"]`, so two paths never share an entry). A frontmatter key named `body` is such a field; the registry's `body` is the Markdown body. Record paths are matched key by key, never as joined text: a key that contains `.` (a literal `"scope.paths"` beside or instead of `scope: {paths: ...}`) is never a field, wherever it appears, so it is hashed here and reported unclassified (`["scope.paths"]`) by invariant 50. Unclassified control keys are refused by the meta-test (§1.5) as well, and a stray one at run time is still bound, conservatively.

From S2b.1 both derived functions read through the inherited-obligations accessor (plan §3.12a), so carried obligations reach these digests from S2b.2 without a change to this module.

### 1.4 Comparing: changed groups, registry moves, materiality

`changed_groups(before, after)` returns the groups whose digests differ. When the two were computed under different registry versions, the groups each version step between them affects count as changed whatever the digests say (E19-B §2.3). They are read from the two registries themselves, not only from the moves a version declares:

- every field added, removed, regrouped (primary or `also` groups), given another rule or hashed through other derived values counts in both its old and its new groups, including the fields hashed only through derived values (`depends_on`, `carried_obligations`), which have no payload entry of their own;
- every group added, removed or whose materiality changed;
- the old and new `unassigned` groups when the unassigned group, the provenance or the bookkeeping list changed, since those decide which keys fall into it;
- the step's declared moves.

A later version names its `predecessor` and lists `moves: [{field, from, to}]` (the loader refuses a move to a group the version does not hash the field in, so a declared move is always visible in the comparison), and every step between the two versions is compared. When neither registry descends from the other among the packaged versions, every group counts as changed. S3 adds the other half: a moved group stays changed until its evidence is regenerated or the engine records a mechanical revalidation.

`material(groups)` returns the material ones (E19-B §4.3). A group the registry does not declare counts as material. `card` counts as material while the Ticket's `card_acceptance_bearing` override is set (plan §3.3, the title; the override itself is S7's).

### 1.5 Classifying a new unit key (M4-E and later slices)

A slice that adds a work-unit key, or a field to the Ticket record, adds one line to the registry in its own pull request: an input in its group (with a rule), or a name under `bookkeeping` (control) or `provenance` (record). A key that can influence publication, gates, scope, acceptance or dependencies is an input, and its pull request says so for the reviewer (E6b's `authorization_envelope` is in `gate_set`). Two checks refuse an unclassified key:

- `tests/unit/test_ticket_field_registry.py::test_every_ticket_field_is_classified` walks the record schema and the control state's unit definition;
- invariant 50 (`tests/helpers/invariants.py`, `ticket_field_violations`) checks every hot and archived unit's keys and every hot unit's record fields after every step of every walk and every test that checks the invariants, so a key the schemas do not declare is caught too.

Once S3 binds evidence to a registry identity, changing version 1 in place would orphan those bindings: a classification change then needs version 2, with its predecessor and moves.

## Consequences and limits

- No behaviour changes: nothing calls the module before S2a, and F4 stays dormant on every project that has not been explicitly enabled.
- The digests are platform independent by construction (canonical JSON, NFC, LF), pinned by fixed vectors (`test_digests_are_platform_independent`), including a record stored with CRLF line endings.
- The engine cannot tell mechanically whether free text carries acceptance meaning, so the body and external references are in `acceptance`, and the title's misuse is found by review or confirmation (register F4's build note; S7's override).
- A group's digest changes when a field is added to it, even an absent one (it joins the payload as `null`). That is why the registry is versioned once bindings exist.
