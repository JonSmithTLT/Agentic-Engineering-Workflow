**Placed Now (the operator, 2026-11-25).** In the operator's words: "my goal was expect rev goes away entirely. Aew
knows what revision is taking place and expect rev doesnt really save us from anything". This row is what removes it.

The chain before it is done: E326 closed earlier, and E327 (#464), E328 (#488) and E330 (#447), which had merged with
their rows still open, are closed in the same change. So this row waits on nothing. On the build board the chain is
SYS-53, partly built, which brings the limit's count from 10 to 11 of N = 12.

**`expect_rev` is removed outright (the operator, 2026-11-25).** Nothing has been released yet, so no release needs
the grace period. Asked whether to remove it outright, the operator answered: "Yup. ill have it removed outright". The
Work cell said "`expect_rev` is accepted and ignored for one release, then removed"; it now says the switch-on removes
it outright.
