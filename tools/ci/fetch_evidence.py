"""Fetch the proof archive by upload ID and record its visibility wait.

download-artifact looks up even an ID through the run's eventually consistent
artifact listing. The archive endpoint takes the ID directly.
"""

import hashlib
import os
import subprocess
from pathlib import Path
from time import monotonic, sleep
from zipfile import ZipFile

# PR #483 missed the artifact about 150 ms after upload. Allow five seconds
# to start retries, with one-second spacing to avoid hammering the endpoint.
VISIBILITY_SECONDS = 5
PAUSE_SECONDS = 1
# Allow five seconds to connect and 30 seconds total per request. The latter
# allows the 64 MiB staging cap (stage_evidence.JOB_CAP) at roughly 2.2 MiB/s.
CONNECT_SECONDS = 5
TRANSFER_SECONDS = 30
DIAGNOSTIC_BYTES = 500


def fetch(artifact_id, name, digest, url, token, directory, summary):
    if not artifact_id.isascii() or not artifact_id.isdecimal() or not digest:
        raise SystemExit(f"Missing upload ID or digest for {name}")

    archive = directory / "evidence-proof.zip"
    started = monotonic()
    deadline = started + VISIBILITY_SECONDS
    outcome = "error"
    attempts = 0
    try:
        # The deadline stops new retries. An in-flight request has its own transfer limit.
        while monotonic() < deadline:
            attempts += 1
            response = subprocess.run(
                ["curl", "-q", "--silent", "--show-error", "--location",
                 "--connect-timeout", str(CONNECT_SECONDS), "--max-time", str(TRANSFER_SECONDS),
                 "--header", "@-", "--output", str(archive),
                 "--write-out", "%{http_code}", url],
                input=f"Authorization: Bearer {token}\n", capture_output=True, text=True,
            )
            if response.returncode:
                detail = response.stderr.strip().replace(token, "[redacted]")[:DIAGNOSTIC_BYTES]
                raise SystemExit(
                    f"Evidence download for {name} (ID {artifact_id}) failed: "
                    f"curl exit {response.returncode}: {detail!r}"
                )
            if response.stdout == "200":
                outcome = "visible"
                break
            if response.stdout != "404":
                with archive.open("rb") as body:
                    detail = body.read(DIAGNOSTIC_BYTES + len(token) + 1).decode("utf-8", "replace")
                detail = detail.replace(token, "[redacted]")[:DIAGNOSTIC_BYTES].strip()
                raise SystemExit(
                    f"Evidence download for {name} (ID {artifact_id}) returned HTTP {response.stdout}: {detail!r}"
                )
            remaining = deadline - monotonic()
            if remaining > 0:
                sleep(min(PAUSE_SECONDS, remaining))
        else:
            outcome = "timeout"
            raise SystemExit(f"Evidence {name} (ID {artifact_id}) was still unavailable after "
                             f"{attempts} attempts in {monotonic() - started:.2f}s")
    finally:
        evidence = (f"Evidence visibility for {name} (ID {artifact_id}): attempts={attempts}, "
                    f"elapsed={monotonic() - started:.2f}s, outcome={outcome}")
        print(evidence, flush=True)
        with summary.open("a", encoding="utf-8") as record:
            record.write(evidence + "\n")

    with archive.open("rb") as downloaded:
        if hashlib.file_digest(downloaded, "sha256").hexdigest() != digest:
            raise SystemExit(f"Evidence digest mismatch for {name} (ID {artifact_id})")
    with ZipFile(archive) as downloaded:
        downloaded.extractall(directory / "evidence-proof-download")


if __name__ == "__main__":
    artifact_id = os.environ["ARTIFACT_ID"]
    fetch(
        artifact_id, os.environ["ARTIFACT_NAME"], os.environ["ARTIFACT_DIGEST"],
        f"{os.environ['GITHUB_API_URL']}/repos/{os.environ['GITHUB_REPOSITORY']}/actions/artifacts/{artifact_id}/zip",
        os.environ["ARTIFACT_TOKEN"], Path(os.environ["RUNNER_TEMP"]), Path(os.environ["GITHUB_STEP_SUMMARY"]),
    )
