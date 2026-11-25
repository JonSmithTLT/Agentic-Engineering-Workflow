# Asynchronous lifecycle checks

Read when cancellation, source replacement or scope retirement affects reads or results. Derive the permitted behavior from the host's lifecycle/API/cache owner; do not invent a universal caching policy.

Use controllable promises, events or barriers to establish the sequence. Include a noncooperative fake source that continues to resolve or reject after cancellation. A fake that always obeys abort cannot establish protection against late results. Keep real orchestration and state-publication logic under test.

1. Start source A and pause its result. Replace A with B. At the first observable state under B, assert that A's prior displayed result is excluded, before flushing later effects or resolving B. Checking only the eventual screen misses transient misattribution.
2. Resolve B, then resolve or reject A. Assert B's identity/result remains authoritative and A cannot overwrite state, raise a current-source error or cause an unhandled rejection. Also test A finishing before B where relevant.
3. Pause the first read, retire its scope, then release it. Assert no next read/subscription begins and no retired result is published. This catches checks performed only before an await. Record read effects as well as the final display.
4. Keep an active-scope control that completes the legitimate sequence. Preserve permitted same-source refresh behavior; the fix must not suppress all reads or discard valid data indiscriminately.

For a repair, demonstrate failure before and success after for each independent mechanism, or retain an explicit verification gap. An isolated ablation can demonstrate a test's sensitivity but is not historical reproduction. Use timeouts to bound hangs, not sleeps to establish order. Clean up pending work and rejected promises.

Validate fixture identity relationships and bounds before using a fixture as valid input. A long-name case must update its dependent locators; use an explicit over-limit case separately. Prefer contract-supported boundary values to arbitrary giant strings. Do not turn a convenient fixture validator into a stricter product acceptance rule.
