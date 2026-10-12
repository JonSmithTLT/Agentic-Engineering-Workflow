# Dashboard configuration read: the contract 0.1.4 change note (v0.1)

- **Status:** **Proposed** (slice F1b of register F46.1); Appendix A is not adopted yet. The web developer applies it
  in W2; F1c then serves the two routes and writes the adopted line here. Ledger prefix DCR.
- **Owns:** the main line's proposal for contract 0.1.4: two routes, `/configuration` and `/configuration/execution`
  (pending until F1c serves them), the `configuration` capability key, and the response shapes the configuration read
  projection (`aew.engine.configuration`, slice F1a) already emits.
- **Does not own:** the contract file and everything under `web/` (the web developer applies Appendix A, §3.1); the
  projection itself (F1a, `aew settings show`); serving the routes, their ETag and the read-session check (F1c); Save
  (F46.2) and the model catalog (F46.3).
- **Reads:** the F46.1 proposal (v10, reviewed CLEAR; designer- and operator-approved; not in this repository), its
  §3, §6, §7, §8 and Appendix A; the designer's ruling on it (its Decision Record D3 and D4 are quoted below); the
  web developer's opinion on its v5; contract 0.1.3 (`docs/design/dashboard-api-v1-provisional.yaml`, SHA-256
  `417fa777…87fb`, vendored as `tests/fixtures/dashboard/contract-0.1.3.yaml`); the
  [0.1.3 change note](dashboard-maps-and-history-search-v0.1.md), whose compatibility rule and readiness this note
  reuses; `src/aew/engine/configuration.py` and `src/aew/policy/config_paths.py` as merged (PR #220).

## 1. Authority

The operator approved the F46 work breakdown on 2026-10-11 and signed off the F46.1 proposal's slices on 2026-10-12.
The proposal's §8 names this slice: "The change note for contract 0.1.4: Appendix A, which the web developer applies.
The main line edits nothing in `web/`". It depends on "F1a's shapes; this proposal's review and the operator's
approval", all of which hold: F1a merged as PR #220.

The designer's ruling on the proposal, in its Decision Record, constrains two of the shapes here:

> "D3 — REQUIRED CLARIFICATIONS: Make FieldValue's value-presence comment consistent with the NULL state, and
> describe @i locators as display-only masked extensions to RFC 6901, not ordinary persistent JSON Pointer
> identities."

> "D4 — REQUIRED IN F1c: Verify that the existing F20.3 read-session boundary applies to both configuration HTTP
> routes. No new authentication subsystem is authorized."

D3 is carried by §5.1 and §5.2; D4 is F1c's (§8).

## 2. What changes, and what does not

| # | Decision |
|---|---|
| D1 | **0.1.4, additive.** Every 0.1.3 path, parameter and response schema keeps its wire shape and its envelope's `schema_version`; the two new responses carry `0.1.4`. The one changed body is `/capabilities`, which gains the `configuration` key through the `Capabilities` exception of the compatibility check (a key that is exactly `$ref: Capability`), the precedent of 0.1.3's `maps` |
| D2 | **Contract first, through this note.** The web developer applies Appendix A to the contract file in W2; the main line edits nothing in `web/`. Appendix A's shapes are the projection's real output, checked against it by test (§6) |
| D3 | **Two routes,** `/configuration` (the inventory) and `/configuration/execution` (the execution policy field by field), GET and HEAD. They are in the contract from W2 and pending until F1c serves them |
| D4 | **The real output is the owner.** Where the proposal's Appendix A and what the projection emits differ, this note follows the projection and lists each difference (§7) |
| D5 | **Nothing served changes in F1b.** The server answers every 0.1.3 route byte for byte; the routes, the ETag over observations and capability states, and the read-session check are F1c's |

## 3. Versioning: 0.1.4 is additive

The 0.1.3 change note's compatibility rule holds unchanged: a minor version adds new paths and never changes what an
existing path returns, and an envelope's `schema_version` is the contract version that defined that response's
schema. So the 0.1.2 routes keep emitting `0.1.2`, the 0.1.3 routes `0.1.3`, and the configuration routes `0.1.4`.
The rule is already in the contract's `info.description`; Appendix A changes only `info.version`.

### 3.1 Who edits what

1. **F1b (main line):** this note, with Appendix A (the exact OpenAPI additions as fenced YAML), the vendored 0.1.3
   reference and the tests of §3.2 and §6. The contract file is not touched.
2. **W2 (web developer):** applies Appendix A to `docs/design/dashboard-api-v1-provisional.yaml`, amending the
   additions if the UI needs it, and bumps `info.version` to 0.1.4. In `web/`: `c0-approval.json` (0.1.4 accepted, and
   0.1.3 moved into `previous_reviews` with `"disposition": "ACCEPT"`), the parsers, the capability name and the
   fixtures.
3. **C0 renewal:** a fresh-context main-line reviewer checks W2's contract diff against the compatibility rule and this
   note. F1c records any W2 amendment here and writes the adopted line.

### 3.2 Readiness on the main line

The 0.1.3 note's readiness is a set of rules, not lists, so W2 needs no main-line edit first:

- **Versions:** the accepted contract may be any `0.1.x` at or above `0.1.2` (`contract.CONTRACT_SERIES`); a 0.1.4 needs
  no `contract.py` change.
- **Pending routes are derived** (`server.pending_routes`: contract paths minus served minus conditional), so
  `/configuration` and `/configuration/execution` are pending from W2 until F1c serves them, and answer as this server
  answers without them. The dashboard's integration tests take this note's proposed routes into the pending set from
  the note itself (never a list), so they are tested as pending before W2 and after, and leave the set once F1c serves
  them.
- **This note is a code input** (`tools/ci/tier.py`'s `SHARED`), as the 0.1.3 note is: the tests read its appendix
  and its status line, so a change to it runs the full gate.
- **The 0.1.3 note** checks a later minor version against its adopted shapes over the routes served at adoption; W2's
  0.1.4 passes it without a note edit.
- **This note against the contract** (`tests/unit/test_dashboard_config_note.py`): Appendix A compiles as JSON Schema
  2020-12 and, merged into the vendored 0.1.3, passes the compatibility check with every 0.1.3 path covered. Against the
  accepted contract the mode follows this note's status line, as for 0.1.3: one-way before adoption (any W2 amendment
  of the additions passes), strict at the adopted version, the compatibility check for a later one.
- **The 0.1.3 reference is vendored,** never read from git history: `tests/fixtures/dashboard/contract-0.1.3.yaml`,
  whose SHA-256 must be the approval record's accepted 0.1.3 review (current now, a previous review after W2).
- **Done when:** a local dry run of W2 passes the main-line contract, dashboard and configuration suites twice, once
  with Appendix A as written and once amended (a renamed property, an added field and a renamed path), on a scratch
  copy of the contract and of the approval record; F1b's pull request records the results.

## 4. The two routes

Both are `GET` and `HEAD` under `/api/v1`, behind the dashboard's existing read session (F20.3), with envelope
`schema_version: 0.1.4`, the projection's own data as `data`, and no query parameters:

- **`/configuration`:** the manifest's state, the four activities and every logical document with its state, digest
  and write capability (`ConfigurationIndex`). The same data as `aew settings show --json`.
- **`/configuration/execution`:** the execution policy field by field (`ExecutionConfiguration`). The same data as
  `aew settings show execution --json`, except `observed`, which reports the environment of the process that renders it
  (`checked_in: dashboard_server_environment` on HTTP).

The `configuration` capability is AVAILABLE on every project. Write capability is `UNSUPPORTED` with
`AWAITS_F46_2` on every document until F46.2.

## 5. The shapes

### 5.1 FieldValue: one withheld representation

A FieldValue is `{path, state, value?, withheld?, effective?, effective_source?, class, allowed?, description?, edit,
editable}`. `state` is a closed enum, and the schema enforces the four cases with `if`/`then`:

| Case | `state` | `value` | `withheld` |
|---|---|---|---|
| SET, shown | `SET` | required, never `null` | forbidden |
| SET, withheld | `SET` | forbidden | the reason |
| NULL (configured null) | `NULL` | required, `null` | forbidden |
| ABSENT | `ABSENT` | forbidden | forbidden |

So a withheld SET can never read as a configured null. `effective` (with `effective_source`) is the supplied effective
value: for example the steering envelope's defaults while the envelope is ABSENT. `description` is the field's own
schema description, or absent: it is never an enclosing object's (§7). `provider_env.state.value` is the number of
entries (the names are in `provider_env.entries`). `editable` is false everywhere until F46.2.

### 5.2 Paths and `@i`

Every `path`, `Violation.path`, `identity_error.field_path`, switch `path` and `routed_by` entry is built by one
encoder (`aew.policy.config_paths`): an RFC 6901 JSON Pointer over the policy document. A key that may not be shown
(it fails the shown-key shape or holds a credential shape), and every non-string key, is the segment `@i`: its index
in that mapping, in document order. An `@i` segment is a display-only, masked extension to RFC 6901: a path containing
one is not a persistent identity, is valid only under the digest it was rendered with, and is never an edit target.

### 5.3 Every list: complete or flagged

Each list either has a boolean truncation flag beside it (`*_truncated`, or `truncated` in a route table) or is
complete by an invariant: `activities` (the four activities), `allowed` (a schema enum of at most 16 values),
`resolution_order` (four), `switches` (one per string switch) and `Capability.reasons` (bounded by the registered
reason codes). A truncated connection list never makes a profile look disconnected: every profile keeps its
`connection_id`.

### 5.4 Withheld values and bounds

A string the projection would show is withheld when it fails its shape rule or holds a credential shape
(`credential_shaped`), and when it is over Appendix A's bound of 512 bytes (`too_long`, an open `withheld` code; F1a
review). A value is never clipped: a clipped value would show content that is not the file's. A name over its bound is
`null`. The schemas state the bounds as `maxLength` in characters, which every value within its byte bound satisfies.

Most bounds are the engine's own caps, each compared to its owner constant. Six are contract-only bounds, which the
engine does not enforce: `ConfigurationPath` (256), the `routed_by` entries (256), and `hint`, `caption`, `pins_note`
and `Violation.expected` (512). The engine writes values that fit them, and the tests show that (the longest value the
engine can write is checked against each); they are not caps the engine would hold if its values grew.

### 5.5 Structured errors

A document's problems are structure, never a validator's message: `violations[]` of `{path, code, expected,
extra_key}`, with `code` the schema keyword or `NO_SUCH_PROFILE` / `NO_DEFAULT_ROUTE`, and `UNPROCESSABLE` (one
violation at the root) for a document the walk cannot process; a YAML error is `{code: YAML_SYNTAX, line, column}`,
one-based, both `null` without a parser mark.

## 6. Derived, not restated

There is no engine-side JSON Schema for the projection, so Appendix A is written here and pinned by tests so that it
cannot drift from the code:

- **The shapes against the real output** (`tests/integration/test_dashboard_config_note_shapes.py`): the projection's
  index and execution output over a corpus validate against Appendix A merged into 0.1.3, every object closed. The
  corpus is F1a's own: every row of the proposal's §4.2 state table, the hostile documents, the bounded and the
  oversized policies, and withheld `@i` keys. Every property Appendix A defines is emitted somewhere in the corpus.
- **Every open enum and every bound against its owner** (`tests/unit/test_dashboard_config_note.py`): each
  `x-known-values` list equals the engine constant that owns it (`configuration.STATES`, `WITHHELD_REASONS`,
  `EFFECTIVE_SOURCES`, `EDIT_SCOPES`, `IDENTITY_RULES`, `DATA_CODES`, `RESOLUTION_ORDER`, `OBSERVED_CAPTIONS`,
  `ACTIVITIES`; `harness.models.REFUSAL_REASONS`; `harness.agentenv.PROVIDER_ENV_PROBLEMS`;
  `engine.steering.EFFECTIVE_SOURCES`; the execution schema's `x-aew-class` values), and each list's `maxItems` and
  each string's `maxLength` equals the engine's cap.
- **The four cases and the lists** are checked against Appendix A itself: a SET-withheld FieldValue with `value: null`
  fails it, a YAML error without a mark is valid, and every array has a flag or is in §5.3's complete set.

## 7. Differences from the proposal's Appendix A

The proposal's Appendix A is a shorthand, not OpenAPI, so it cannot be validated against directly. These differences
come from comparing it field by field with the merged projection (#220); this note's Appendix A is then validated
against the projection's real output (§6). In each case the projection is the owner and Appendix A here follows it:

| # | The proposal's Appendix A | The projection, and this note |
|---|---|---|
| 1 | `withheld`: `not_a_model_id`, `not_a_name`, `not_a_harness_name`, `credential_shaped` | adds `too_long`: a string over 512 bytes is withheld, never clipped (F1a review, the operator's decision); so `identity_error.withheld_reason` also gains `too_long` |
| 2 | `Violation.code`: a schema keyword, `NO_SUCH_PROFILE` or `NO_DEFAULT_ROUTE` | adds `UNPROCESSABLE`: one violation at the root for a document the walk cannot process (F1a review) |
| 3 | §3.5's complete lists: activities, allowed, resolution_order, switches | adds `Capability.reasons`, bounded by the registered reason codes |
| 4 | `FieldValue.description`: "the schema's description of the field" | the field's own description or absent, never an enclosing object's (F1a review); today no projected field has one of its own, so the page shows none until the schema gains them (a register note on F46) |
| 5 | `provider_env.state: FieldValue` over a list | its `value` is the entry count |
| 6 | `FieldValue.path` and the other locators: an RFC 6901 pointer | the same, and an index is accepted only as `0` or `[1-9][0-9]*` in ASCII, after `@` too (F1a review). This rule is descriptive: it is F1a's parser behaviour, and the `ConfigurationPath` pattern does not express it, so `/profiles/01` validates against the schema |
| 7 | Strings at most 512 bytes "unless stated" | stated per field: shown names and keys 128 bytes, harness names 64, model ids 128, paths 256, everything else 512; `ModelIdentity.harness_ref` (`<provider><separator><model>`) is 257 |
| 8 | The document state, the digest, a path and a connection id written inline at each use | named once as `ConfigurationDocumentState`, `ConfigurationDigest`, `ConfigurationPath` and `ConnectionId`, with the same shapes, so each bound and pattern has one definition |

## 8. What stays out until F1c

- Serving the routes, their entries in `RESPONSE_SCHEMAS` and `ENVELOPE_VERSION`, and the `configuration` key in
  `/capabilities`.
- The ETag over the control revision, the configuration digests, the runtime observation and the capability states,
  so a `304` is never served across a change in any of them.
- The read-session check on both routes (the designer's D4), with no new authentication subsystem.
- The tests that need served responses: the HTTP bodies against the adopted 0.1.4, `/configuration` and
  `aew settings show --json` equal, conditional requests, and the read-session refusal.

## 9. What is the web developer's

**What they receive:** this note and Appendix A; `aew settings show [execution] --json` on any project for live
shapes; the shape corpus of §6 as synthetic fixtures.

**What they build:** W2 (the contract, the approval record with 0.1.3 kept as an accepted predecessor, the parsers,
the capability name, the fixtures) and the read-only configuration pages: the header with each document's state,
`in_force` and Read-only reason; Profiles, Routing, Controls and Providers from `ExecutionConfiguration`; withheld
values shown as withheld with their reason, never as a configured null; an `@i` path shown as its display form, never
offered as an edit target; an unknown enum value shown with a warning.

**What they decide:** any shape amendments in W2; how withheld values and `@i` locators read on the page.

## 10. Slices

```text
F1a (merged, #220) ──► F1b (this note) ──► W2 (web) ──► F1c (routes, ETag, read session)
```

F1c records W2's amendments and writes the adopted line here. F1b, W2 and F1c are one pull request each, never
stacked, each with an independent review to CLEAR.

## Appendix A. The OpenAPI additions

The blocks below are merged, in order, into contract 0.1.3: a mapping merges key by key, anything else replaces.
`tests/unit/test_dashboard_config_note.py` checks that the result compiles and passes the compatibility check against
0.1.3; `tests/integration/test_dashboard_config_note_shapes.py` checks that the projection's real output validates.
Every open enum is a string with `x-known-values`: an unknown value is shown with a warning.

The version:

```yaml
info:
  version: 0.1.4
```

The capability key:

```yaml
components:
  schemas:
    Capabilities:
      properties:
        configuration:
          $ref: '#/components/schemas/Capability'
          description: The configuration pages (from 0.1.4). AVAILABLE on every project.
```

The two routes:

```yaml
paths:
  /configuration:
    get:
      operationId: configurationIndexResponse
      description: The manifest's state, the four activities and every logical document with its state, digest
        and write capability. Lock-free and read-only.
      parameters:
      - name: If-None-Match
        in: header
        schema:
          type: string
      responses:
        '200':
          description: Validated read-only projection.
          headers:
            ETag:
              schema:
                type: string
              description: Validator over the full representation, the configuration digests and the capability
                states; every control commit changes it.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ConfigurationIndexResponse'
        '304':
          description: Representation unchanged. No payload.
        '401':
          description: Session required.
        '403':
          description: Capability unavailable.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '500':
          description: Projection refresh failed. Keep last-known-good content visibly stale.
    head:
      operationId: headConfigurationIndexResponse
      parameters:
      - name: If-None-Match
        in: header
        schema:
          type: string
      responses:
        '200':
          description: Validated read-only projection.
          headers:
            ETag:
              schema:
                type: string
              description: Validator over the full representation, the configuration digests and the capability
                states; every control commit changes it.
        '304':
          description: Representation unchanged. No payload.
        '401':
          description: Session required.
        '403':
          description: Capability unavailable.
        '500':
          description: Projection refresh failed. Keep last-known-good content visibly stale.
  /configuration/execution:
    get:
      operationId: configurationExecutionResponse
      description: The execution policy field by field, with its document's state, violations, profiles, routing,
        provider connections, the server's observation of the provider variables, and controls. Lock-free and
        read-only; secrets withheld by structure.
      parameters:
      - name: If-None-Match
        in: header
        schema:
          type: string
      responses:
        '200':
          description: Validated read-only projection.
          headers:
            ETag:
              schema:
                type: string
              description: Validator over the full representation, the configuration digest, the runtime observation
                and the capability states; a change in any of them changes it.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ConfigurationExecutionResponse'
        '304':
          description: Representation unchanged. No payload.
        '401':
          description: Session required.
        '403':
          description: Capability unavailable.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '500':
          description: Projection refresh failed. Keep last-known-good content visibly stale.
    head:
      operationId: headConfigurationExecutionResponse
      parameters:
      - name: If-None-Match
        in: header
        schema:
          type: string
      responses:
        '200':
          description: Validated read-only projection.
          headers:
            ETag:
              schema:
                type: string
              description: Validator over the full representation, the configuration digest, the runtime observation
                and the capability states; a change in any of them changes it.
        '304':
          description: Representation unchanged. No payload.
        '401':
          description: Session required.
        '403':
          description: Capability unavailable.
        '500':
          description: Projection refresh failed. Keep last-known-good content visibly stale.
```

The envelopes and the index:

```yaml
components:
  schemas:
    ConfigurationIndexResponse:
      type: object
      properties:
        schema_version:
          type: string
          const: 0.1.4
        project_id:
          $ref: '#/components/schemas/OpaqueId'
        control_revision:
          $ref: '#/components/schemas/ControlRevision'
        generated_at:
          $ref: '#/components/schemas/Timestamp'
        data:
          $ref: '#/components/schemas/ConfigurationIndex'
      required: [schema_version, project_id, control_revision, generated_at, data]
      additionalProperties: false
    ConfigurationExecutionResponse:
      type: object
      properties:
        schema_version:
          type: string
          const: 0.1.4
        project_id:
          $ref: '#/components/schemas/OpaqueId'
        control_revision:
          $ref: '#/components/schemas/ControlRevision'
        generated_at:
          $ref: '#/components/schemas/Timestamp'
        data:
          $ref: '#/components/schemas/ExecutionConfiguration'
      required: [schema_version, project_id, control_revision, generated_at, data]
      additionalProperties: false
    ConfigurationIndex:
      type: object
      properties:
        manifest:
          type: object
          properties:
            state:
              type: string
              x-known-values: [ADOPTED, DRIFTED]
              description: Open semantic value. Whether project.yaml matches its pin.
          required: [state]
          additionalProperties: false
        activities:
          type: array
          maxItems: 8
          items:
            type: object
            properties:
              activity:
                type: string
                x-known-values: [execution, providers, workflow, project]
                description: Open semantic value.
              capability:
                $ref: '#/components/schemas/Capability'
            required: [activity, capability]
            additionalProperties: false
        documents:
          type: array
          maxItems: 16
          items:
            $ref: '#/components/schemas/ConfigurationDocument'
        documents_truncated:
          type: boolean
      required: [manifest, activities, documents, documents_truncated]
      additionalProperties: false
    ConfigurationDocument:
      type: object
      description: One logical document - project, each key of the manifest's policy object in its order, then
        execution at its conventional path when the manifest names none. No path is ever projected.
      properties:
        document:
          anyOf:
          - type: string
            maxLength: 128
          - type: 'null'
          description: The logical name; null when it fails the shown-key shape or holds a credential shape.
        index:
          $ref: '#/components/schemas/BoundedCount'
        same_file_as:
          anyOf:
          - $ref: '#/components/schemas/BoundedCount'
          - type: 'null'
          description: The index of the first entry naming the same file; always null while the manifest is drifted.
        supported:
          $ref: '#/components/schemas/Capability'
        state:
          $ref: '#/components/schemas/ConfigurationDocumentState'
        in_force:
          type: boolean
        digest:
          $ref: '#/components/schemas/ConfigurationDigest'
        write:
          $ref: '#/components/schemas/Capability'
      required: [document, index, same_file_as, supported, state, in_force, digest, write]
      additionalProperties: false
    ConfigurationDocumentState:
      type: string
      x-known-values: [MANIFEST_DRIFTED, DRIFTED, INVALID, ADOPTED, UNPINNED, ABSENT]
      description: Open semantic value, in precedence order. A function of the manifest pin, the pins map, the
        document's pin, the bytes on disk and their validity; independent of in_force.
    ConfigurationDigest:
      type: string
      pattern: ^sha256:[0-9a-f]{64}$
      description: The configuration digest (aew/config-digest/v2) a later Save binds to. Not the control revision.
    ConfigurationPath:
      type: string
      maxLength: 256
      pattern: ^(/[^/]*)*$
      description: An RFC 6901 JSON Pointer over the policy document. A segment @i is a withheld key - a
        display-only, masked extension to RFC 6901, valid only under the digest it was rendered with, never stored
        and never an edit target.
```

The FieldValue, the violations and the YAML error:

```yaml
components:
  schemas:
    FieldValue:
      type: object
      properties:
        path:
          $ref: '#/components/schemas/ConfigurationPath'
        state:
          type: string
          enum: [SET, 'NULL', ABSENT]
        value:
          type: [string, number, integer, boolean, 'null']
          maxLength: 512
        withheld:
          type: string
          x-known-values: [not_a_model_id, not_a_name, not_a_harness_name, credential_shaped, too_long]
          description: Open semantic value. Why a SET value is not shown; present only then.
        effective:
          type: [string, number, integer, boolean, 'null']
          maxLength: 512
        effective_source:
          type: string
          x-known-values: [profile, policy, default]
          description: Open semantic value.
        class:
          type: string
          x-known-values: [legality_affecting, operational]
          description: Open semantic value. The schema's x-aew-class.
        allowed:
          type: array
          maxItems: 16
          items:
            type: string
            maxLength: 512
        description:
          type: string
          maxLength: 512
          description: The field's own schema description; absent when the schema gives it none.
        edit:
          type: string
          x-known-values: [F46.2, later, never]
          description: Open semantic value.
        editable:
          type: boolean
      required: [path, state, class, edit, editable]
      additionalProperties: false
      allOf:
      - if:
          properties:
            state:
              const: SET
          required: [withheld]
        then:
          not:
            required: [value]
      - if:
          properties:
            state:
              const: SET
          not:
            required: [withheld]
        then:
          required: [value]
          properties:
            value:
              not:
                type: 'null'
      - if:
          properties:
            state:
              const: 'NULL'
        then:
          required: [value]
          properties:
            value:
              type: 'null'
          not:
            required: [withheld]
      - if:
          properties:
            state:
              const: ABSENT
        then:
          not:
            anyOf:
            - required: [value]
            - required: [withheld]
    Violation:
      type: object
      properties:
        path:
          $ref: '#/components/schemas/ConfigurationPath'
        code:
          type: string
          x-known-values: [$ref, additionalProperties, const, enum, exclusiveMinimum, items, maximum, minItems,
            minLength, minimum, oneOf, pattern, properties, propertyNames, required, type, uniqueItems,
            NO_SUCH_PROFILE, NO_DEFAULT_ROUTE, UNPROCESSABLE]
          description: Open semantic value. The schema keyword that failed, or a semantic code.
        expected:
          anyOf:
          - type: string
            maxLength: 512
          - type: 'null'
          description: The schema's side only (a pattern, a type, an enum, a bound), never the instance.
        extra_key:
          anyOf:
          - type: string
            maxLength: 128
          - type: 'null'
          description: An additionalProperties violation's key when it may be shown, else @i.
      required: [path, code, expected, extra_key]
      additionalProperties: false
    YamlError:
      type: object
      properties:
        code:
          type: string
          const: YAML_SYNTAX
        line:
          anyOf:
          - type: integer
            minimum: 1
          - type: 'null'
        column:
          anyOf:
          - type: integer
            minimum: 1
          - type: 'null'
      required: [code, line, column]
      additionalProperties: false
      description: A YAML syntax error located by the parser's mark only, one-based; both null without a mark.
```

The execution configuration:

```yaml
components:
  schemas:
    ExecutionConfiguration:
      type: object
      properties:
        document:
          type: object
          properties:
            state:
              $ref: '#/components/schemas/ConfigurationDocumentState'
            in_force:
              type: boolean
            digest:
              $ref: '#/components/schemas/ConfigurationDigest'
            on_disk_matches_adopted:
              type: boolean
            write:
              $ref: '#/components/schemas/Capability'
            violations:
              type: array
              maxItems: 50
              items:
                $ref: '#/components/schemas/Violation'
            violations_truncated:
              type: boolean
            yaml_error:
              anyOf:
              - $ref: '#/components/schemas/YamlError'
              - type: 'null'
          required: [state, in_force, digest, on_disk_matches_adopted, write, violations, violations_truncated,
            yaml_error]
          additionalProperties: false
        configured:
          $ref: '#/components/schemas/FieldValue'
        harness:
          $ref: '#/components/schemas/FieldValue'
        description:
          $ref: '#/components/schemas/FieldValue'
        profiles:
          type: array
          maxItems: 64
          items:
            $ref: '#/components/schemas/ExecutionProfile'
        profiles_truncated:
          type: boolean
        routing:
          type: object
          properties:
            default:
              $ref: '#/components/schemas/FieldValue'
            archetypes:
              $ref: '#/components/schemas/RouteTable'
            classes:
              $ref: '#/components/schemas/RouteTable'
            cards:
              $ref: '#/components/schemas/RouteTable'
            resolution_order:
              type: array
              maxItems: 4
              items:
                type: string
                x-known-values: [card, class, archetype, default]
          required: [default, archetypes, classes, cards, resolution_order]
          additionalProperties: false
        connections:
          type: array
          maxItems: 32
          items:
            $ref: '#/components/schemas/Connection'
        connections_truncated:
          type: boolean
        provider_env:
          type: object
          properties:
            state:
              $ref: '#/components/schemas/FieldValue'
            entries:
              type: array
              maxItems: 64
              items:
                type: object
                properties:
                  index:
                    $ref: '#/components/schemas/BoundedCount'
                  name:
                    anyOf:
                    - type: string
                      maxLength: 512
                    - type: 'null'
                  valid_name:
                    type: boolean
                required: [index, name, valid_name]
                additionalProperties: false
            entries_truncated:
              type: boolean
          required: [state, entries, entries_truncated]
          additionalProperties: false
        observed:
          type: object
          properties:
            checked_in:
              type: string
              x-known-values: [cli_environment, dashboard_server_environment]
              description: Open semantic value. Whose environment this is.
            caption:
              type: string
              maxLength: 512
            provider_env:
              type: array
              maxItems: 64
              items:
                type: object
                properties:
                  index:
                    $ref: '#/components/schemas/BoundedCount'
                  name:
                    anyOf:
                    - type: string
                      maxLength: 512
                    - type: 'null'
                  present:
                    type: boolean
                  problem:
                    anyOf:
                    - type: string
                      x-known-values: [unset, aew_variable, holds_aew_credential]
                    - type: 'null'
                    description: Open semantic value; never a value.
                required: [index, name, present, problem]
                additionalProperties: false
            provider_env_truncated:
              type: boolean
          required: [checked_in, caption, provider_env, provider_env_truncated]
          additionalProperties: false
        controls:
          type: object
          properties:
            steering:
              type: object
              properties:
                mode:
                  $ref: '#/components/schemas/FieldValue'
                envelope:
                  type: object
                  properties:
                    loop_deadline_s:
                      $ref: '#/components/schemas/FieldValue'
                    max_auto_actions:
                      $ref: '#/components/schemas/FieldValue'
                    repetition_n:
                      $ref: '#/components/schemas/FieldValue'
                  required: [loop_deadline_s, max_auto_actions, repetition_n]
                  additionalProperties: false
                effective:
                  type: object
                  properties:
                    mode:
                      anyOf:
                      - type: string
                        maxLength: 64
                      - type: 'null'
                    source:
                      type: string
                      x-known-values: [raise, lower, default, none]
                      description: Open semantic value.
                  required: [mode, source]
                  additionalProperties: false
              required: [mode, envelope, effective]
              additionalProperties: false
            containment:
              type: object
              properties:
                mode:
                  $ref: '#/components/schemas/FieldValue'
                writable_count:
                  $ref: '#/components/schemas/BoundedCount'
                hide_count:
                  $ref: '#/components/schemas/BoundedCount'
                trusted_git_drivers_count:
                  $ref: '#/components/schemas/BoundedCount'
                effective:
                  type: string
                  const: NOT_SUPPLIED
              required: [mode, writable_count, hide_count, trusted_git_drivers_count, effective]
              additionalProperties: false
            switches:
              type: array
              maxItems: 16
              items:
                type: object
                properties:
                  path:
                    $ref: '#/components/schemas/ConfigurationPath'
                  value:
                    $ref: '#/components/schemas/FieldValue'
                  default:
                    type: string
                    maxLength: 64
                required: [path, value, default]
                additionalProperties: false
            notify:
              type: object
              properties:
                configured:
                  type: boolean
                timeout_s:
                  $ref: '#/components/schemas/FieldValue'
                max_output_bytes:
                  $ref: '#/components/schemas/FieldValue'
              required: [configured, timeout_s, max_output_bytes]
              additionalProperties: false
          required: [steering, containment, switches, notify]
          additionalProperties: false
        pins_note:
          type: string
          maxLength: 512
      required: [document, configured, harness, description, profiles, profiles_truncated, routing, connections,
        connections_truncated, provider_env, observed, controls, pins_note]
      additionalProperties: false
    RouteTable:
      type: object
      properties:
        entries:
          type: array
          maxItems: 256
          items:
            type: object
            properties:
              key:
                anyOf:
                - type: string
                  maxLength: 128
                - type: 'null'
                description: The route key; null when withheld, and the entry's paths then use @i.
              index:
                $ref: '#/components/schemas/BoundedCount'
              profile:
                $ref: '#/components/schemas/FieldValue'
            required: [key, index, profile]
            additionalProperties: false
        truncated:
          type: boolean
      required: [entries, truncated]
      additionalProperties: false
```

The profiles and the connections:

```yaml
components:
  schemas:
    ExecutionProfile:
      type: object
      properties:
        name:
          anyOf:
          - type: string
            maxLength: 128
          - type: 'null'
          description: Null when withheld; the profile's paths then use @<index>.
        index:
          $ref: '#/components/schemas/BoundedCount'
        fields:
          type: object
          properties:
            harness:
              $ref: '#/components/schemas/FieldValue'
            provider:
              $ref: '#/components/schemas/FieldValue'
            model:
              $ref: '#/components/schemas/FieldValue'
            effort:
              $ref: '#/components/schemas/FieldValue'
            max_steps:
              $ref: '#/components/schemas/FieldValue'
            deadline_s:
              $ref: '#/components/schemas/FieldValue'
            description:
              $ref: '#/components/schemas/FieldValue'
          required: [harness, provider, model, effort, max_steps, deadline_s, description]
          additionalProperties: false
        identity:
          anyOf:
          - $ref: '#/components/schemas/ModelIdentity'
          - type: 'null'
        identity_rule:
          type: string
          x-known-values: [adapter, inherited]
          description: Open semantic value.
        identity_error:
          anyOf:
          - type: object
            properties:
              code:
                type: string
                x-known-values: [model_id_malformed, model_id_no_provider, model_id_provider_conflict, field_withheld]
                description: Open semantic value.
              withheld_reason:
                anyOf:
                - type: string
                  x-known-values: [not_a_model_id, not_a_name, not_a_harness_name, credential_shaped, too_long]
                - type: 'null'
                description: Set exactly when code is field_withheld, and then the field's own withheld code.
              field_path:
                $ref: '#/components/schemas/ConfigurationPath'
              suggestion:
                anyOf:
                - type: string
                  maxLength: 128
                - type: 'null'
              hint:
                type: string
                maxLength: 512
            required: [code, withheld_reason, field_path, suggestion, hint]
            additionalProperties: false
          - type: 'null'
        connection_id:
          anyOf:
          - $ref: '#/components/schemas/ConnectionId'
          - type: 'null'
          description: Present whenever the profile has a connection, even when connections is truncated.
        routed_by:
          type: array
          maxItems: 64
          items:
            type: string
            maxLength: 256
          description: card:<id>, card:@i when withheld, class:<n>, archetype:<name>, default.
        routed_by_truncated:
          type: boolean
      required: [name, index, fields, identity, identity_rule, identity_error, connection_id, routed_by,
        routed_by_truncated]
      additionalProperties: false
    ModelIdentity:
      type: object
      properties:
        catalog_id:
          type: string
          maxLength: 128
        provider:
          type: string
          maxLength: 128
        model:
          type: string
          maxLength: 128
        harness_ref:
          type: string
          maxLength: 257
      required: [catalog_id, provider, model, harness_ref]
      additionalProperties: false
    ConnectionId:
      type: string
      pattern: ^conn-[0-9a-f]{16}$
      description: Opaque and stable while the project, harness and provider are unchanged; sent back as is.
    Connection:
      type: object
      properties:
        connection_id:
          $ref: '#/components/schemas/ConnectionId'
        harness:
          type: string
          maxLength: 64
        provider:
          type: string
          maxLength: 128
        profiles:
          type: array
          maxItems: 64
          items:
            $ref: '#/components/schemas/BoundedCount'
          description: The profiles' index values (document order).
        profiles_truncated:
          type: boolean
        credential_sources:
          type: object
          properties:
            provider_env:
              type: object
              properties:
                scope:
                  type: string
                  const: policy_wide
                ref:
                  type: string
                  const: /provider_env
              required: [scope, ref]
              additionalProperties: false
            saved_login:
              type: string
              const: NOT_SUPPLIED
          required: [provider_env, saved_login]
          additionalProperties: false
        endpoint:
          type: string
          const: NOT_SUPPLIED
        catalog:
          $ref: '#/components/schemas/Capability'
      required: [connection_id, harness, provider, profiles, profiles_truncated, credential_sources, endpoint, catalog]
      additionalProperties: false
```
