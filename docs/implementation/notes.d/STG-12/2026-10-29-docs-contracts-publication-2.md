**D-A's second publication (2026-10-29, #295):** the set under [`docs/contracts/`](../../../contracts/README.md) is now
52 copies. A-44 (blocked-on-you, revision 2.1) and A-45 (the independent outage reader, O-02, revision 2.1) join, with
their `MANIFEST.json` entries and README rows as the generator writes them. The 50 copies of the first publication
(#288) are unchanged.

**#288's quick-check m1 is fixed in #295:** the `NOT_OURS` filter is one helper, `ours(label, refs)`, which
`reduced_readers`, the planted test `test_discoverys_conventions_are_not_ours_only_where_listed` and the hardened-docs
test call. The planted test now fails when the filter is widened to every file. Its limit, stated in its docstring
(review of #295, n1): it proves the helper; that the guard filters only through `ours()` is held by the module having
no second filter.
