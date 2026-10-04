"""Per-header fan-out from `clang-scan-deps -format make` output (semantic-map thread S4: incremental freshness).

  clang-scan-deps -compilation-database cc.json -format make > deps.txt
  python header_fanout.py deps.txt PROJECT_SUBSTR

For each header: how many translation units read it (the TUs a change to it invalidates). Distribution, the headers
that reach (almost) every TU, and the long tail that reaches a handful.
"""

from __future__ import annotations

import collections
import statistics
import sys


def main() -> int:
    deps, proj_mark = sys.argv[1], sys.argv[2]
    tokens = open(deps, encoding="utf-8").read().replace("\\", " ").split()
    rules: list[set[str]] = []
    for tok in tokens:
        if tok.endswith(":"):
            continue
        if tok.endswith((".c", ".cc", ".cpp", ".cxx")):
            rules.append(set())
            continue
        if rules:
            rules[-1].add(tok)
    fan = collections.Counter(d for r in rules for d in r)
    tus = len(rules)
    proj = {d: n for d, n in fan.items() if proj_mark in d}
    gen = [d for d in proj if "/build/" in d]
    sysh = {d: n for d, n in fan.items() if d.startswith("/usr/")}
    vals = sorted(proj.values())
    print(f"TUs {tus}; distinct headers {len(fan)}: project {len(proj)} (generated {len(gen)}), system {len(sysh)}")
    print(f"project header fan-out (TUs a change invalidates): median {statistics.median(vals)}, "
          f"mean {statistics.mean(vals):.1f}, p75 {vals[int(len(vals) * 0.75)]}, p90 {vals[int(len(vals) * 0.9)]}, "
          f"max {max(vals)}")
    print("project headers reaching >=90% of TUs:",
          sorted(((n, d.rsplit("/", 1)[1]) for d, n in proj.items() if n >= 0.9 * tus), reverse=True))
    print(f"project headers reaching <=5 TUs: {sum(1 for n in vals if n <= 5)}; <=10% of TUs: "
          f"{sum(1 for n in vals if n <= 0.1 * tus)} of {len(vals)}")
    sv = sorted(sysh.values())
    print(f"system headers: median fan-out {statistics.median(sv)}; reaching all TUs: {sum(1 for n in sv if n == tus)} "
          f"of {len(sv)}")
    per_tu = sorted(len(r) for r in rules)
    print(f"headers per TU: median {statistics.median(per_tu)}, max {max(per_tu)}")
    hist = collections.Counter((n - 1) // 50 * 50 for n in vals)
    print("fan-out histogram (TU bucket -> project headers):", [(f"{b + 1}-{b + 50}", c) for b, c in sorted(hist.items())])
    return 0


if __name__ == "__main__":
    sys.exit(main())
