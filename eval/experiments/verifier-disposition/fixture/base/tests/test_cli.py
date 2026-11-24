from pathlib import Path

from ledger.cli import main

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample.csv"


def test_summary_of_a_month(capsys):
    assert main(["summary", str(SAMPLE), "--month", "2026-02"]) == 0
    out = capsys.readouterr().out
    assert "Rent: $1,500.00" in out
    assert "Dining: $60.00" in out
