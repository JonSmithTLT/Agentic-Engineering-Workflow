**The test half is built, by #509 (`8f4aa3c6`, 2026-11-22), and the row stays open for the product half (the register
reconcile of 2026-11-26).** `test_the_clis_search_output_is_byte_identical_to_before_s2` exhausts the elapsed-time
budget once on each copy (`BUILD_BUDGET_S = 0`) and then lets document counts decide both copies' progress, so the
clock no longer decides the comparison; the flake register's `history-byte-identical` entry closed with #509. **What
remains** is the Work's second sentence: a walk that finished is still reported incomplete when the budget trips after
its last entry. Nothing merged addresses it.
