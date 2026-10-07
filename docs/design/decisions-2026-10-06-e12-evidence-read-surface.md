# Designer decision of 2026-10-06: the Evidence read surface (E12)

**Status:** Decision record, governing. **Adopted** by the designer on 2026-10-06; it answers register E12 (the form
of the evidence view) and needs no further design document. §1 is the decision recorded as given; §2 says where it is
filed.

## 1. The decision, recorded as given

> # E12 — Evidence Read Surface
>
> **Status:** ADOPTED
> **Date:** 2026-10-06
> **Decision type:** Bounded product/contract decision; no separate design phase required
>
> ## Decision
>
> AEW will provide:
>
> ```
> aew evidence show <id>
> ```
>
> as the canonical detailed read surface for an Evidence record.
>
> Normal workflow surfaces such as stage results, `harness wait`, status/next-action output, and typed Lead responses should continue to carry the evidence record's top-level conclusion and Evidence ID.
>
> `aew evidence show <id>` is the Lead/operator drill-down path when deeper inspection is required.
>
> ## Rationale
>
> M3 dogfood showed that Leads needed to inspect individual Evidence records in more detail and, lacking an Evidence read command, opened backing files directly.
>
> The intended interaction is now clear:
>
> ```
> workflow result
>     ↓
> concise evidence conclusion + evidence id
>     ↓
> Lead needs more detail
>     ↓
> aew evidence show <id>
>     ↓
> bounded detailed Evidence projection
> ```
>
> There is no longer a meaningful choice between "show the Evidence record" and "put its conclusion in next actions."
>
> AEW needs both:
>
> * concise evidence conclusions in normal workflow output; and
> * an explicit detailed read command for deeper inspection.
>
> ## Required behavior
>
> `aew evidence show <id>` must:
>
> * read through the existing AEW query/projection layer rather than directly reading `.aew` backing files;
> * expose backend-owned Evidence semantics rather than deriving them in CLI/UI code;
> * use the same semantic Evidence projection consumed by other typed/read-only surfaces where practical;
> * provide structured output (`--json` or the established equivalent) so the typed Lead surface and other adapters can consume the same representation;
> * bound large bodies/artifacts rather than unconditionally dumping arbitrary raw output into Lead context;
> * preserve Evidence identity, provenance, bindings and currentness information supplied by the authoritative backend.
>
> The detailed projection should expose the available form of:
>
> * Evidence ID and kind;
> * result;
> * currentness;
> * claim/conclusion;
> * findings and/or deviations;
> * `requires_disposition`;
> * evaluated candidate/snapshot and relevant bindings;
> * evaluator/environment metadata;
> * bounded body/detail;
> * provenance;
> * related artifact/reference identifiers.
>
> Exact field naming should follow the existing Evidence/query contracts rather than creating an E12-specific parallel schema.
>
> ## Non-goals
>
> E12 does not:
>
> * create a new Evidence authority or storage model;
> * make the CLI parse raw Evidence files;
> * require every Evidence body to be injected into every workflow result;
> * turn backing-artifact browsing into part of the Evidence command;
> * change Evidence acceptance, currentness, gate or disposition semantics.
>
> ## Implementation disposition
>
> No further E12 architecture/design document is required.
>
> Implementation should add the bounded Evidence read projection/command using existing plumbing, plus the structured form required by the typed Lead surface.
>
> E12 is closed as ADOPTED.

## 2. Filing (lead developer)

Register E12 becomes build work: `aew evidence show <id>` through the existing projection layer, with its structured
form for the typed Lead surface, in M4-G (the decision was due there). Today `aew evidence` has only `ingest`. E12's
decisions-due item is removed. Ledger prefix EVR.
