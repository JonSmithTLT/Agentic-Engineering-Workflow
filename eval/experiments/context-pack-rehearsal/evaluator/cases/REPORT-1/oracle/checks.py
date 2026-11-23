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


def checks(tree, run):
    rows = [
        {"id": "r3", "title": "Review", "phase": "pending"},
        {"id": "r1", "title": 'Quoted, "café"\nline two'},
        {"id": "r2", "title": "Finish", "phase": "done"},
    ]
    output = json_output(run, rows)
    preserves = isinstance(output, list) and len(output) == len(rows) and all(
        isinstance(item, dict) and item.get("id") == row["id"] and item.get("title") == row["title"]
        and isinstance(item.get("status"), str)
        for item, row in zip(output, rows, strict=True)
    )
    yield "json-field", preserves and output[2]["status"] == "done", "JSON fields, order and completed row"

    for criterion, row, status in (("current-spelling", rows[0], "queued"), ("legacy-default", rows[1], "unknown")):
        output = json_output(run, [row])
        ok = isinstance(output, list) and len(output) == 1 and isinstance(output[0], dict)
        yield criterion, ok and output[0].get("status") == status, f"{row['id']} JSON status equals {status!r}"

    populated = export(run, "csv", rows)
    empty = export(run, "csv", [])
    # score_child decodes bytes as UTF-8 without newline translation. Neither expected string contains U+FFFD,
    # so an invalid UTF-8 sequence (decoded with replacement) cannot compare equal either.
    expected = 'id,title\r\nr3,Review\r\nr1,"Quoted, ""café""\nline two"\r\nr2,Finish\r\n'
    exact = (populated.returncode == 0 and populated.stdout == expected
             and empty.returncode == 0 and empty.stdout == "id,title\r\n")
    yield "csv-exact", exact, "Exact CSV bytes for empty and populated exports"
