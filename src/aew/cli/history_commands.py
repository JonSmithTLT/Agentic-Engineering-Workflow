"""`aew history`: the history surface and the integrity audit (ADR-0011; implementation plan §3)."""

from __future__ import annotations

import argparse

from aew.cli.commands import _add_json, _add_lead, _engine, _lead_token
from aew.errors import UsageError


def _audit(a: argparse.Namespace):
    """Advisory unless it is recorded: recording is a Lead mutation, so it names the revision it is based on."""
    if a.expect_rev is None:
        if a.token:
            raise UsageError("recording an audit is a Lead mutation: pass --expect-rev too (or drop --token for an "
                             "advisory audit)")
        return _engine(a).history_audit(full=a.full)
    return _engine(a).history_audit(full=a.full, token=_lead_token(a), expect_rev=a.expect_rev)


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("history", help="finished work: show, list, follow links, load as reference, audit")
    hsub = p.add_subparsers(dest="history_cmd", required=True)

    q = hsub.add_parser("show", help="an exact historical record by stable id, with its annotations and trust label")
    q.add_argument("record_id")
    _add_json(q)
    q.set_defaults(handler=lambda a: _engine(a).history_show(a.record_id))

    q = hsub.add_parser("list", help="historical records by kind and a bounded date range, newest first")
    q.add_argument("--kind", help="unit, annotation, audit or lead")
    q.add_argument("--since", metavar="UTC", help="from this time, e.g. 2026-10-01T00:00:00Z")
    q.add_argument("--until", metavar="UTC", help="up to this time")
    q.add_argument("--limit", type=int, default=50, help="at most this many (default 50, maximum 1000)")
    q.add_argument("--before", type=int, metavar="SEQ",
                   help="only entries numbered below this sequence number: the next page after a listing whose "
                        "oldest entry was SEQ")
    _add_json(q)
    q.set_defaults(handler=lambda a: _engine(a).history_list(kind=a.kind, since=a.since, until=a.until,
                                                            limit=a.limit, before=a.before))

    q = hsub.add_parser("log", help="committed transitions after a revision, with their typed events (the cursor is "
                                    "the revision; pass the returned `next` as the next --since)")
    q.add_argument("--since", type=int, required=True, metavar="REVISION",
                   help="return transitions after this revision (0 for all)")
    q.add_argument("--kind", action="append", metavar="KIND",
                   help="only transitions with an event of this kind, narrowed to them (repeatable), e.g. work.state")
    q.add_argument("--follow", action="store_true",
                   help="wait for a transition after --since when there is none yet (up to --timeout)")
    q.add_argument("--timeout", type=float, default=30.0, help="seconds --follow waits (default 30)")
    q.add_argument("--limit", type=int, default=500, help="at most this many revisions per call (default 500)")
    _add_json(q)
    q.set_defaults(handler=lambda a: _engine(a).history_log(since=a.since, kinds=a.kind, follow=a.follow,
                                                           timeout=a.timeout, limit=a.limit))

    q = hsub.add_parser("compact", help="seal transition-log revisions older than the 4,096-revision window into "
                                        "256-transition segments (maintenance; never discards a transition)")
    _add_json(q)
    q.set_defaults(handler=lambda a: _engine(a).history_compact())

    q = hsub.add_parser("links", help="follow the provenance and reference links recorded from and to a record")
    q.add_argument("record_id")
    q.add_argument("--depth", type=int, default=1, help="how many steps to follow (1-3)")
    _add_json(q)
    q.set_defaults(handler=lambda a: _engine(a).history_links(a.record_id, depth=a.depth))

    q = hsub.add_parser("load", help="attach a historical record to a unit as reference context, never as current "
                                     "evidence (Lead)")
    q.add_argument("record_id")
    q.add_argument("--into", required=True, metavar="WORK-ID", help="the hot unit whose later packs carry it")
    q.add_argument("--reason", required=True)
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).history_load(token=_lead_token(a), expect_rev=a.expect_rev,
                                                            record_id=a.record_id, into=a.into, reason=a.reason))

    q = hsub.add_parser("audit", help="verify the history incrementally (or --full); with --expect-rev the Lead "
                                      "records it and advances the verified root")
    q.add_argument("--full", action="store_true", help="verify everything, not only what is new since the last audit")
    q.add_argument("--token", help="Lead credential (or env AEW_LEAD_TOKEN), to record the audit")
    q.add_argument("--expect-rev", type=int, help="control revision: records the audit (a Lead mutation)")
    _add_json(q)
    q.set_defaults(handler=_audit)

    q = hsub.add_parser("reindex", help="rebuild the derived history index from the manifest")
    _add_json(q)
    q.set_defaults(handler=lambda a: _engine(a).history_reindex())
