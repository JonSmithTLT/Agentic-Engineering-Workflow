**What the fix does not reach (review of #384, findings 4 and 5).** The server alone is pinned. The Lead's shell `aew`
is still the console script beside the interpreter, with no pinned import path, so with another tree's editable install
its commands run that tree while its typed tools run this one. An upgrade in place keeps the interpreter and the import
root, so a server started after it runs the new code beside the old broker. In the contained Lead, a copy of `aew` under
a directory the sandbox makes fresh (`/tmp`, `/run`) loses its import path. Each is stated in `projection.py`'s
docstrings. No row owes them: none has been asked for, and a new one needs a case that hits it.

**Still open from #384's review:** real OpenCode hasn't run on Windows, so a spaced `python.exe` path through OpenCode's
own spawn is proven on Linux only. The first real Windows `aew opencode` is that check.
