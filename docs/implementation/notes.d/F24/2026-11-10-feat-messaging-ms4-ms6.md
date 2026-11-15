The messaging worker-wait capability is report_step_and_shell_calls: open foreground shell call and step identities,
their completion/failure, execution end and reconnect invalidation. Codex has no adapter integrating those lifetimes
or message waits, so its declaration is a gap owned here. API steer support alone does not establish an integrated
messaging binding or queue. Unsupported adapters must not enable worker waits from an API enum or another platform's
qualification record.
