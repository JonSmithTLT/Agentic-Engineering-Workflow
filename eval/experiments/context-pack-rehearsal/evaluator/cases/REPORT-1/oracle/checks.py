"""REPORT-1 synthetic calibration. All observations go through the exporter's public CLI."""

import json
import sys


def export(run, format_name, rows):
    return run([sys.executable, "-I", "-B", "exporter.py", format_name], input=json.dumps(rows), timeout=10)


def json_output(run, rows):
    result = export(run, "json", rows)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except ValueError:
        return None


def row_has_status(output, row_id, status):
    if not isinstance(output, list):
        return False
    matching = [item.get("status") for item in output if isinstance(item, dict) and item.get("id") == row_id]
    return matching == [status]


def checks(tree, run):
    rows = [
        {"id": "r3", "title": "Review", "phase": "pending"},
        {"id": "r1", "title": 'Quoted, "café"\nline two'},
        {"id": "r2", "title": "Finish", "phase": "done"},
    ]
    batch = json_output(run, rows)
    preserves = isinstance(batch, list) and len(batch) == len(rows) and all(
        isinstance(item, dict) and item.get("id") == row["id"] and item.get("title") == row["title"]
        and isinstance(item.get("status"), str)
        for item, row in zip(batch, rows, strict=True)
    )
    yield "json-field", preserves and batch[2]["status"] == "done", "JSON fields, order and completed row"

    for criterion, row, status in (("current-spelling", rows[0], "queued"), ("legacy-default", rows[1], "unknown")):
        singleton = json_output(run, [row])
        single_ok = row_has_status(singleton, row["id"], status) and len(singleton) == 1
        batch_ok = row_has_status(batch, row["id"], status)
        yield criterion, single_ok and batch_ok, f"{row['id']} status {status!r}: single={single_ok}, batch={batch_ok}"

    populated = export(run, "csv", rows)
    empty = export(run, "csv", [])
    # score_child decodes bytes as UTF-8 without newline translation. Neither expected string contains U+FFFD,
    # so an invalid UTF-8 sequence (decoded with replacement) cannot compare equal either.
    expected = 'id,title\r\nr3,Review\r\nr1,"Quoted, ""café""\nline two"\r\nr2,Finish\r\n'
    exact = (populated.returncode == 0 and populated.stdout == expected
             and empty.returncode == 0 and empty.stdout == "id,title\r\n")
    yield "csv-exact", exact, "Exact CSV bytes for empty and populated exports"
