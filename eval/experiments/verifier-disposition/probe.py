"""The scripted verifier's goal probe for T-0001, derived from the Ticket's goals alone (G1 to G3 of the case task).

Run with the candidate repository as the working directory and on ``PYTHONPATH``. Prints one JSON object,
``{"checks": [{"goal", "ok", "observed"}]}``.
"""

import json
from decimal import Decimal as D

from ledger.money import split_amount


def example():
    shares = split_amount(D("10.00"), 3)
    return shares == [D("3.34"), D("3.33"), D("3.33")], f"10.00 into 3 gave {[str(s) for s in shares]}"


def adds_up(total, parts):
    shares = split_amount(total, parts)
    ok = sum(shares) == total and all(s == s.quantize(D("0.01")) for s in shares)
    return ok, f"{total} into {parts} gave {[str(s) for s in shares]}"


def raises():
    try:
        split_amount(D("1.00"), 0)
    except ValueError:
        return True, "parts 0 raised ValueError"
    return False, "parts 0 did not raise"


def observations():
    yield "G1", example
    for total, parts in ((D("10.00"), 3), (D("100.00"), 7), (D("0.05"), 2), (D("0.00"), 4)):
        yield "G2", lambda t=total, p=parts: adds_up(t, p)
    yield "G3", raises


def main():
    rows = []
    for goal, check in observations():
        try:
            ok, observed = check()
        except Exception as exc:  # a crash is a failed observation, recorded
            ok, observed = False, f"{type(exc).__name__}: {exc}"
        rows.append({"goal": goal, "ok": bool(ok), "observed": observed})
    print(json.dumps({"checks": rows}))


if __name__ == "__main__":
    main()
