PR 2 implementation checkpoint: launch/relaunch records an enabled-only messaging snapshot from adopted bytes;
old/absent snapshots remain off. Worker reply/read/wait go only through that run's custody bridge, with no caller
invocation or credential selector. Wait has an 88 s maximum from the qualified Linux 2.2.6 timeout margin. Call/step
tracking invalidates waits on a bound call's completion, any step end/new step, execution end, stream loss or run end.
Windows runtime remains NOT RUN and production waits remain unsupported there. Deterministic fake-V2 tests exercise
the same lifetime machinery on either host through an explicitly registered test adapter, not a qualification claim.

The supervisor's one delivery lock covers wait selection, the final connection/lifetime check, successful send and
fact recording; the live transport must share it when built in PR 3. No wait fact is written before a successful
send. A shell-timeout orphan returns ended_early without a delivery fact. Fake V2 now emits tool completion and only
then step end; its fidelity test uses a real child. Worker thread reads consume nothing. Thread replies still grant
no authority and move no revision. The capability declaration remains GAP until the full PR 2 slice is completed.

This checkpoint is not a completed PR 2: Lead attention, stable-lock atomic told IDs, local told/posted integration,
switch-aware Lead guidance, the on golden and the carried independent guide/catalog oracle are still owed. No
real-binary run, live transport, turn-end support or default-on change is included.
