**For F1b's contract change note (0.1.4), from slice F1a's review.** The projection's shapes gained three things
Appendix A of the F46.1 proposal does not list yet; F1b's change note should carry them:

- **`withheld: too_long`**, a new open `withheld` code. A FieldValue string over Appendix A's bound ("strings are at
  most 512 bytes unless stated") has no `value` and `withheld: too_long`, and no `effective` either; a `provider_env`
  name over the bound is `name: null`. A value is never clipped, since a clipped value would show content that is not
  the file's (the operator's decision, 2026-10-12). Schema descriptions stay clipped to 512 bytes.
- **`code: UNPROCESSABLE`**, a violation code: a document the structured walk cannot process (a nesting deep enough
  to exhaust the recursion limit) is one violation at the root (`path: ""`) with this code and no message.
- **`Capability.reasons`** belongs in §3.5's table of complete lists: it is bounded by the registered reason codes.

`FieldValue.description` is the field's own schema description or absent (never an enclosing block's); see the note on
F46 about the schema's missing per-field descriptions.

**For F1c (the HTTP routes): what an absent file costs on Windows.** The projection reads each file lock-free through
`aew.engine.store.read_lock_free`. On Windows an open in the middle of a writer's replace can report a present file
missing, so a missing file counts as absent only after the read retries. That costs about 0.29 s per absent file per
read (measured: `configuration()` takes about 0.003 s with the execution policy present, and about 0.285 s when it is
ABSENT). On POSIX, `rename` is atomic, so an absent file is reported absent at once. ABSENT is rare on Windows,
because `aew init` writes a default execution policy. Still, a dashboard polling a Windows project whose policy file
is absent pays this on every request, and F1c's ETag and caching design should take it into account.
