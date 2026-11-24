# ledger

Summaries of a personal-finance ledger kept as a CSV file with the columns `date` (YYYY-MM-DD), `amount`,
`category` and `memo`.

```
python -m ledger summary data/sample.csv                 # totals per category, all entries
python -m ledger summary data/sample.csv --month 2026-01 # one month
```

Amounts are exact (Decimal) and reported in dollars. Run the tests with `python -m pytest tests`.
