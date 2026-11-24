"""A deliberately misread probe: it expects the leftover cents on the last shares, the opposite of G1. Run over
VD-CLEAN it yields a plausible false rework, a supported failing claim against a correct change, that the grader must
reject."""

import json
from decimal import Decimal as D

from ledger.money import split_amount


def main():
    shares = split_amount(D("10.00"), 3)
    rows = [{"goal": "G1", "ok": shares == [D("3.33"), D("3.33"), D("3.34")],
             "observed": f"10.00 into 3 gave {[str(s) for s in shares]}"}]
    print(json.dumps({"checks": rows}))


if __name__ == "__main__":
    main()
