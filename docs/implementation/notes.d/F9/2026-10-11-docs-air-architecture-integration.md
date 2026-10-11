**Architecture integration decisions (designer, 2026-10-11; [the architecture integration decision record](../../../design/decisions-2026-10-11-architecture-integration.md)).** Three changes for F9. (1) The typed worker
kinds `advice_request`/`advice`, `scope_request`/`scope_answer` and `confusion_report` are F9.1, preceded by the
kind-agnostic slice F9-X0 (a tolerant read of unknown kinds; a structured `data` object in the derived identity), with
an extensibility acceptance criterion: a new kind never needs broker, store, ordering or sealing changes (AIR-43 to
AIR-52). Worker-initiated messages remain F9-B's. (2) The Lead's wake for replies (MIC-09) is one decision-keyed
Lead-attention lane, the run-less form of `wait --any` that F43 S3 builds, not a separate F9 mechanism (AIR-19). (3)
Admitted Lead instructions reach reviewer and verifier packs through one canonical, bounded content record shared by
`harness send` and the F9 thread (F9.2, AIR-21 to AIR-23); advice exchanges show the question and the advice but not
the worker's proposed answer or uncertainty by default (AIR-53).
