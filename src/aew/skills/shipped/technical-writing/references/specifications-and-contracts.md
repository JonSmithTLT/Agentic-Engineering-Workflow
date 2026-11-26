# Specifications and contracts

Read when drafting or reviewing normative requirements, domain contracts or interface specifications. These checks preserve an authorized obligation; they do not authorize inventing or adopting one.

Establish source status before wording. Foundational requirements define required outcomes and constraints; adopted contracts define required behavior. An architectural decision record documents a decision, rationale and consequences, with authority determined by its adoption and project rules. An implementation design selects an approach; code shows implemented behavior; conformance evidence shows what was checked under stated conditions. These are roles, not a universal precedence hierarchy. Verify actual adoption, scope and supersession rather than inferring them from a filename or confident language. Keep recommendations visibly proposed until the authorized owner adopts them.

For each consequential clause, check what applies:

- **Sufficiency:** Can an independent implementer identify the obligation from the clause and its available normative references? Do not require access to unstated design intent.
- **Observable behavior:** Identify relevant inputs, outputs, state effects, errors and failure conditions. Expose missing retry, refusal or partial-failure decisions where they affect the guarantee; do not fill them with a convenient default.
- **Applicability:** Name the obligated actor and triggering conditions. Trace the obligation to an adopted source or label it as proposed.
- **Implementation freedom:** State the observable guarantee independently of a preferred mechanism when allowed. Preserve explicitly mandated technology or algorithms. Flag an unsupported implementation restriction and propose a revision; never silently remove an adopted constraint.
- **Consistency and conformance:** Compare governing requirements and related clauses. Describe what observation could distinguish conforming behavior. A planned test is not evidence that the requirement is satisfied. Retain discrepancies between required and implemented behavior.

Use the project's declared normative vocabulary. Under BCP 14, MUST/SHALL express requirements, SHOULD expresses a recommendation with qualified exceptions, and MAY expresses an option; SHOULD and MAY are not merely explanatory prose. RFC 8174 clarifies uppercase keyword use. Requirements can also be expressed without those keywords. Do not impose BCP 14 on an unrelated document or change modality/capitalization for smoother style.

Keep rationale and examples separate from obligations where their status could be confused. Apply these checks proportionately; no verbose clause template is required. Missing decisions belong with the authorized decision owner, not hidden inside a polished contract.
