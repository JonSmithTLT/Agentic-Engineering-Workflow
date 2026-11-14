E328 adds optional prior-value bindings to the eight class-B transaction entries. The engine compares under the control lock and reports CHANGED_SINCE_READ for changed subjects. Class-C mismatches share the error and continue to stop at the refusal boundary. The project revision check remains in force.

The prior-value diagnostic looks back at most 64 commits. Older queue events lack a work ID, so a retired entry from before this change may have no matching record. Class-C mismatches can include uncommitted file edits and may have no commit to name.

Before upgrading, finish open review and verification request stages. An intent whose stage contract or plan changed will fail its continuation recheck. Abandon that intent and read the current state before starting another stage. Intent migration belongs to E329.
