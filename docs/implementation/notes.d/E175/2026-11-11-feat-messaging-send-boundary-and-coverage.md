PR 2 send-boundary correction: real bridge sender plants reproduced durable shown and local told receipts being
recorded before a result write failed, for live and sealed replies. Typed and relayed bridge handlers now use the
existing ResultDelivery send-success callback. Relayed wait sequence/end marks are deferred with message receipts;
the direct run_read helper retains its inline compatibility behavior. No serialization/control lock spans result
transmission. Current authority and verified body identity are checked for post-send message writes. Own-shell typed
receipts are a trusted parsed-argument callback invoked only after successful emit and stdout flush, not from the
runner before output. A crash after successful output but before receipt may re-list; this is not a read/understood
acknowledgment. Tests wait on existing bridge drain when inspecting post-send writes, without a protocol handshake.

Added six-condition delivery-record oracle: real broker/run positives, payload/identity/generation/actor/path plants,
and hard local-only checks for each record member even under a widened declaration. A real wrong-path writer plant
shows the oracle rejecting the actual write; a separate real non-writer child is refused before creating directories.
The oracle observes .aew paths and bytes, not arbitrary host I/O, model understanding or every concurrency schedule.
Real CLI/bridge tests cover EOF, server close, parallel call end, grace-arriving call and outside-step refusal with
actual engine selection counters. Wait/wake handler ablations fail the exact missing-delivery assertions, then pass
after restoration. Real worker final reply then submit then Lead ingestion/seal preserves durable unseen despite
a local receipt, and resume still carries the pinned settled body.

These additions are deterministic fake/process coverage, not Windows or provider/runtime qualification. Windows
runtime remains NOT RUN/GAP; existing Linux qualification records/pins are unchanged. No live transport, timing
expansion, default-on, push or PR opening is included. Final requirements/documentation audit and independent
product review remain necessary before PR 2 hand-back.
