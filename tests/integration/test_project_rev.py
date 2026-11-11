"""The test helper ``Project.rev`` reads the control revision in this process: it must be what `aew lead show` reads,
at every point, so every ``Project.lead`` call's `--expect-rev` is the committed revision, never a stale one."""

from __future__ import annotations

from aewflow import create_planned_ticket, sample_project


def test_the_revision_read_in_process_is_the_one_aew_lead_show_reads_after_every_commit(tmp_path):
    p = sample_project(tmp_path)
    seen = []
    for step in range(3):
        cli = p.ok("lead", "show")["revision"]
        assert p.rev() == cli, f"step {step}: in-process {p.rev()} against `aew lead show` {cli}"
        seen.append(cli)
        # Committed by another process (an `aew` subprocess): the next read must see it, never a cached revision
        create_planned_ticket(p, tmp_path, title=f"ticket {step}")
    assert p.rev() == p.ok("lead", "show")["revision"] > seen[-1]
    assert seen == sorted(set(seen))  # each step committed, and each read saw it
