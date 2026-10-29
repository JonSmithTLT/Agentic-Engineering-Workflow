**Its decisions-due item is filed (2026-10-28).** The item the Notes cell says "waits until `test_register` admits a new
item" is now in `docs/implementation/decisions-due.yaml`, and `python tools/register.py show E99` prints it beside this
note. `test_register` now pins the live decisions-due list only on the rows the rebaseline gave a fate, so an item on a
later row such as this one is admitted (#285's review, m5).
