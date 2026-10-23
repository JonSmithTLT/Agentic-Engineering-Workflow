"""Independent, read-only slice input checks; never executes the adopted oracle.

Run with Python containing jsonschema and PyYAML. Output is an intake result,
not website acceptance, source qualification, or backend interoperability.
"""

import argparse
import copy
import hashlib
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

PIN = "64e65578e9774fd9425c19ceaff30f1a0018ae819baa58d9469ed0c33e8f299f"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adopted", type=Path, required=True)
    parser.add_argument("--a23", type=Path, required=True)
    parser.add_argument("--zip", type=Path, required=True)
    args = parser.parse_args()
    root = args.adopted
    assert hashlib.sha256(args.zip.read_bytes()).hexdigest() == PIN
    files = 0
    for line in (root / "SHA256SUMS").read_text().splitlines():
        digest, relative = line.split(maxsplit=1)
        candidate = (root / relative).resolve()
        assert candidate.is_relative_to(root.resolve()), relative
        assert hashlib.sha256(candidate.read_bytes()).hexdigest() == digest, relative
        files += 1
    d01 = json.loads((root / "02-WIRE/aew-d01-read-v0.3.4-FULL.schema.json").read_text())
    o01 = yaml.safe_load((root / "02-WIRE/openapi-o01-extended-REVIEW-CANDIDATE.yaml").read_text())
    results = []

    def validate(name, body, definition, wire="d01", derived=False):
        if wire == "d01":
            schema = {"$defs": d01["$defs"], "$ref": "#/$defs/" + definition}
        else:
            schema = {"components": o01["components"], "$ref": "#/components/schemas/" + definition}
        errors = sorted(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(body),
            key=lambda e: str(e.json_path),
        )
        results.append(
            {
                "fixture": name,
                "schema": definition,
                "derived": derived,
                "valid": not errors,
                "errors": [{"path": e.json_path, "message": e.message} for e in errors],
            }
        )

    fixtures = root / "05-INTEGRATED-FIXTURES"
    for name in ["continuation-full-http-200.json", "continuation-http-200.json"]:
        validate(name, json.loads((fixtures / name).read_text())["body"], "ReadContinuationVector")
    for path in sorted(fixtures.glob("index-*-http-200.json")):
        validate(path.name, json.loads(path.read_text())["body"], "ReadOwnerOperations")
    for name, definition in [
        ("command-requests.json", "CommandSet"),
        ("command-receipts.json", "Receipt"),
        ("owner-operation-get.json", "OwnerOperationRead"),
    ]:
        for action, recording in json.loads((fixtures / name).read_text()).items():
            validate(
                name + ":" + action,
                recording if name == "command-requests.json" else recording["body"],
                definition,
                "o01",
            )
    inherited = [
        ("LEGACY/F01-waiting-positive.json", "ReadWaiting"),
        ("LEGACY/F32-empty-waiting-recipient-view-not-global-absence.json", "ReadWaiting"),
        ("NEW/F03-run-progress-limited.json", "ReadRuns"),
        ("NEW/F04-run-detail-limited.json", "ReadRunDetail"),
        ("NEW/F05-run-multiaxis-HEB-observed.json", "ReadRunDetail"),
        ("NEW/F13-run-no-outstanding-with-IF10-closure.json", "ReadRunDetail"),
    ]
    for name, definition in inherited:
        original = json.loads((args.a23 / "04-FIXTURES" / name).read_text())
        derived = copy.deepcopy(original)
        derived["wire_version"] = "0.3.4"
        validate("A23/" + name + " [version-only derivative]", derived, definition, derived=True)
    print(
        json.dumps(
            {
                "archive_sha256": PIN,
                "manifest_files_checked": files,
                "checks": results,
                "scope": "Structural/schema intake only; no owner qualification or UI acceptance.",
            },
            indent=2,
        )
    )
    return int(any(not r["valid"] for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
