"""Trusted synthetic reference for REPORT-1."""

import csv
import io
import json
import sys


def export(rows, output_format):
    if output_format == "json":
        output = []
        for row in rows:
            item = {"id": row["id"], "title": row["title"]}
            status = {"done": "done", "pending": "queued"}.get(row.get("phase"), "unknown")
            item["status"] = status
            output.append(item)
        return json.dumps(output).encode("utf-8")
    if output_format != "csv":
        raise ValueError("expected json or csv")
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["id", "title"])
    writer.writerows((row["id"], row["title"]) for row in rows)
    return stream.getvalue().encode("utf-8")


if __name__ == "__main__":
    sys.stdout.buffer.write(export(json.load(sys.stdin), sys.argv[1]))
