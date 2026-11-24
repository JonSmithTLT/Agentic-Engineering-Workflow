Two CI evidence defects on runs a newer push superseded (2026-11-24). Run 45339635974 (#536) reported `[cancel-reason]`
for two lane jobs that never started. GitHub created them after the newer push cancelled `tier`, whose outputs define
their matrix, so their names were left unrendered (`${{ matrix.lane }} ...`) and they had no runner, steps or annotation
of their own. Their siblings resolved to the superseding run 45340263626, but the in-run evidence check refused to
extend that to them because it required the run to have concluded `cancelled`, and assurance reads its own run while
that run is still in progress. The completed-run recorder, which sees the concluded run, already recorded it without a
gap. A run-wide origin now also covers its unannotated siblings while the run has not concluded; a run that completed
without concluding `cancelled` still covers none (`cancel_evidence.may_inherit_run_wide`). Run 45338188607 (#538)
reported `[live-stack]` for a Windows integration worker (`cancelled-7776.txt`) that was alive at the cancellation
collection with no interruption stack. Its bundle could not be read for this note, so the cause is not established: the
collection takes one nonblocking py-spy dump per worker, with none of the warning path's retries, discards a dump that
straddles a test boundary, and a worker in fixture setup or teardown has no test-function frame. The bundle (artifacts
14896480836 and 14896475843, retained 14 days) decides which.
