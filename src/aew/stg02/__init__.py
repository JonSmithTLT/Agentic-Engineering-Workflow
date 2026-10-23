"""STG-02, the first vertical slice: a real HTTP producer for one operator journey on the adopted v0.5.4 wire.

The D-01 0.3.4 reads (waiting work, run detail, continuation state, owner operations) and the O-01 0.2 command route
with ``CONTINUE_ELIGIBLE_WORK``, as the architecture workspace's STG-02 handoff asks. Owner facts come from AEW's own
engine state where AEW has the owner record, and from a labelled fixture world where it does not. It is separate from
the dashboard and its provisional contract. The report and gap entries are in ``docs/stg02/``.
"""
