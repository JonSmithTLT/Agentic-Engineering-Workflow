"""Wait for a hosted cancellation target before queuing its concurrency replacement."""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flake_register import _pages  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests/helpers"))
from session_deadline import SENTINEL_READY_S  # noqa: E402


def ready_job(target, jobs, delay):
    job = next((job for job in jobs if job["name"] == target), None)
    if job:
        if job.get("conclusion"):
            raise RuntimeError("cancellation target finished before its replacement queued")
        step = next((step for step in job.get("steps", []) if step["name"] == "Real planted lane"), None)
        if step and step.get("started_at"):
            started = datetime.fromisoformat(step["started_at"].replace("Z", "+00:00")).timestamp()
            if time.time() - started >= delay:
                return job
    return None


def main(runner: str) -> None:
    target = f"plant ({runner}, cancel, none)"
    endpoint = (f"actions/runs/{os.environ['GITHUB_RUN_ID']}/attempts/"
                f"{os.environ['GITHUB_RUN_ATTEMPT']}/jobs?per_page=100")
    until = time.monotonic() + 600  # inside this polling job's 12-minute bound, including setup and one API timeout
    while time.monotonic() < until:
        jobs = list(_pages(os.environ["GITHUB_REPOSITORY"], endpoint, "jobs"))
        if ready_job(target, jobs, SENTINEL_READY_S):
            print("The cancellation target entered its lane; queue its concurrency replacement.")
            return
        time.sleep(2)
    raise SystemExit("plant did not start before the cancellation poll expired")


if __name__ == "__main__":
    main(sys.argv[1])
