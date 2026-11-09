**Built with steering PR 3.** `lead.push_wake` now defaults to on, and the flip is the migration: `aew init` never wrote the key, so an absent key is what existing projects hold. A typed `off` stays off and keeps the wait. No digest moves. The off switch is named in `docs/guides/opencode.md` and the status line. ADR-0009's amendment has the reasons.

**Closed from steering PR 2's list:** the Lead's text and next steps no longer say wait beside "end your turn"; a next step says when no broker is posting; a wake waits for this launch's first prompt; and a switch turned off mid-session stops the posts within a poll.

**Still open:** Windows stays a declared gap, closed by one real wake run there. An offer for a project with a typed `off` isn't built, since nothing wrote that value before this default moved.
