"""A deliberately incomplete probe: it checks only that shares add up in whole cents and that parts < 1 raises, and
never the leftover order G1 states. Run over VD-3 it yields a plausible false accept the grader must reject."""

import json
from decimal import Decimal as D

from ledger.money import split_amount


def main():
    rows = []
    for total, parts in ((D("10.00"), 3), (D("100.00"), 7), (D("0.05"), 2)):
        shares = split_amount(total, parts)
        rows.append({"goal": "G2", "ok": sum(shares) == total and all(s == s.quantize(D("0.01")) for s in shares),
                     "observed": f"{total} into {parts} gave {[str(s) for s in shares]}"})
    try:
        split_amount(D("1.00"), 0)
        rows.append({"goal": "G3", "ok": False, "observed": "parts 0 did not raise"})
    except ValueError:
        rows.append({"goal": "G3", "ok": True, "observed": "parts 0 raised ValueError"})
    print(json.dumps({"checks": rows}))


if __name__ == "__main__":
    main()
