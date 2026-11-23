"""Export report entries read as a JSON array on stdin."""
import csv
import io
import json
import sys


def export(rows, output_format):
    if output_format == "json":
        return json.dumps([{"id": row["id"], "title": row["title"]} for row in rows]).encode("utf-8")
    if output_format != "csv":
        raise ValueError("expected json or csv")
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["id", "title"])
    writer.writerows((row["id"], row["title"]) for row in rows)
    return stream.getvalue().encode("utf-8")


if __name__ == "__main__":
    sys.stdout.buffer.write(export(json.load(sys.stdin), sys.argv[1]))
