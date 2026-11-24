`aew lead mcp` bounds a line's JSON nesting itself (`MAX_DEPTH`, 128 levels), checked before the line is decoded: a
line nested deeper is one parse error on every interpreter, platform and Python version. It had relied on the decoder's
own recursion refusal, which comes at about 1,000 levels on Python 3.11 and about 10,000 on Linux 3.12 and later, so a
5,000-level line was a parse error on 3.11 and a nested batch on 3.13 (the nightly's reference lane, 2026-11-20 to 22).

**Follow-ons (PR #556 review, F2 and F3).** The Lead broker's `lead.tool` handler (`lead_broker._serve_tool`) decodes
a call's `arguments` with `json.loads` and catches only `ValueError`, so arguments from an ingress other than MCP that
nest past the decoder's limit, or past what the argument schema check can walk, reach the bridge's catch-all and are
answered as a defect rather than as `INVALID_ARGUMENTS`, depending on the Python version. The follow-on gives the
broker the same pre-decode bound, answered as `INVALID_ARGUMENTS`, with a test. The JSON nesting bound should then have
one owner, `util.JSON_MAX_DEPTH` with a `json_too_deep` check, which this server, the relay (#551 adds its own
`MAX_NESTING` of 128 with a chunked scan) and the broker derive from. One follow-on pull request does both, after #551
and #556 merge.
