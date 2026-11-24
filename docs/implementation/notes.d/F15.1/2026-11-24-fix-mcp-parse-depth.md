`aew lead mcp` bounds a line's JSON nesting itself (`MAX_DEPTH`, 128 levels), checked before the line is decoded: a
line nested deeper is one parse error on every interpreter, platform and Python version. It had relied on the decoder's
own recursion refusal, which comes at about 1,000 levels on Python 3.11 and about 10,000 on Linux 3.12 and later, so a
5,000-level line was a parse error on 3.11 and a nested batch on 3.13 (the nightly's reference lane, 2026-11-20 to 22).
