MS3's `message_send` is a MECHANICAL, non-progression STAGE with required `expect_rev`, no dispatch, no stage planner
and no intent journal. Its `message.send` primitive records coordination without a control commit, leaving the revision
valid for another send. The non-progression map names checkpoint, steering and message_send with their reasons; every
other STAGE or DECISION advances workflow. Its record-only result claims no delivery; turn-end is refused until MS5b.
