"""The `vertical` lane's scoreboard (register E115): whether anything moved, first, in a job that is red by design.

The job is red until every scenario passes, so a change in it cannot be seen from its colour: from #283 to #307 the
Linux lane measured nothing for about 40 hours and nobody noticed. This is a display. It moves no threshold and changes
no verdict, and the job stays red. Counter totals are deliberately not on it: V2-forced fell from 56 to 32 because it
stopped earlier, which is not progress.

**The series** is ``vertical-series.jsonl`` in the job's output directory, one line per ``main`` run: the artifact
carries the whole of it, and ``actions/cache`` carries it between runs (``vertical.yml``). Only ``main`` saves. A
dispatch on a branch reads ``main``'s series and shows its own values beside it, and writes nothing, so a branch can
never change ``main``'s line (``Run.saves``, and the save step's ``if``; test_ci_tools pins that one).

**Flat since** walks the runs that measured (``flat``), and compares only runs that measured the same thing. A run that
measured nothing is in the series, marked so, and neither resets nor extends it. So is a **partial** run, one that
measured fewer scenarios than the lane holds (``lane_sizes``), for the rows it changes (``WHOLE_LANE_ONLY``): scenarios
passing, driver owed and reached a result fall with what it reached, as V2-forced fell. It stays a data point for the
step rows, since a step's state is derived from the code when a scenario sets up. The scoreboard shows the last run
that measured the whole lane and says so, and the banner counts the stretch of runs that did not (``_blind``). A value
that falls on a whole run resets it and reads as fell.

**A restart** (no series restored, or one that cannot be read) is written on that run's line, since a first run and an
evicted entry look the same and the notice shows only once. A flat run that begins there says so for as long as it
holds, and nothing is compared across it. The nightly reads the entry so a quiet week does not evict it.

The limits: a lane that really shrinks reads partial for ``LANE_WINDOW`` runs, then its new size holds. A run cut short
right after a restart has no size to be held to. A restart back at a seed's value keeps the seed's date, as the lost
runs cannot say otherwise.

A step's state comes from the ledgers, never from a second derivation here. Two ledgers that disagree on a step show
as mixed, which counts as landed for neither side. A step on no ledger makes its row unknown, not a fall.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

from vertical import oracle
from vertical.ledger import ENFORCED_PLATFORMS, RESULT_REACHED

SERIES = "vertical-series.jsonl"
MAIN_REF = "refs/heads/main"
SHOWN_RUNS = 10  # the report's table; the whole series stays in the artifact
LANE_WINDOW = SHOWN_RUNS  # how far back a run is held to the lane's size: what the table shows, so a change heals there
THIS_RUN = "this run"  # a run's id outside a workflow

PASSING, V1_LANDED, OTHER_LANDED = "passing", "v1_landed", "other_landed"
DRIVER_OWED, REACHED = "driver_owed", "reached"
MEASURES = (PASSING, V1_LANDED, OTHER_LANDED, DRIVER_OWED, REACHED)
WHOLE_LANE_ONLY = (PASSING, DRIVER_OWED, REACHED)  # what a partial run changes: a data point only from the whole lane
PYTEST_FINISHED = "success"  # the pytest step's outcome (vertical.yml) when every scenario it collected ran and passed


class Seeded(NamedTuple):
    """Where a value's flat run began, before the series existed."""

    value: int
    date: str
    where: str


# The history the series starts from, read from the runs themselves on 2026-11-03. Linux only: Windows is outside the
# enforced gate and has its own series and no seed. "Reached a result" and the other rows have no history to seed.
# - passing: run 38188158379 (162adee0) is the lane's first on main, its job's log "17 failed", no scenario passing.
# - v1_landed: run 41120823321 (#306, efc98baa) is the first whose ledgers carry step states, `init` built and V1's
#   other seven not built. That run measured 4 of 17 on Linux (V3's four reached their verdict; the Lead did not start
#   on the rest), but a step's state is derived from the code when a scenario sets up, so it holds, as a partial run's
#   step states do; the states are unchanged at run 41393852877 (740a4fcf).
SEED: Mapping[str, Mapping[str, Seeded]] = {
    "linux": {PASSING: Seeded(0, "2026-10-12", "run 38188158379"),
              V1_LANDED: Seeded(1, "2026-10-30", "#306, run 41120823321")},
}


class Run(NamedTuple):
    """The workflow run this report belongs to (None outside a workflow: it shows its values and saves nothing)."""

    id: str
    sha: str
    date: str
    ref: str

    @property
    def saves(self) -> bool:
        return self.ref == MAIN_REF


def cell(text: str, limit: int = 160) -> str:
    """One table cell: whitespace collapsed and ``|`` escaped, then bounded."""
    return " ".join(text.split()).replace("|", "\\|")[:limit]


# ------------------------------------------------------------------------------------------------- the run's values


def step_states(ledgers: Iterable[Mapping[str, Any]]) -> dict[str, set[str]]:
    """Each step's states across the ledgers that carry it: more than one is a disagreement."""
    out: dict[str, set[str]] = {}
    for ledger in ledgers:
        for step in ledger.get("steps") or []:
            out.setdefault(str(step.get("key")), set()).add(str(step.get("state")))
    return out


def _landed(state: str) -> bool:
    return state in oracle.RANK and oracle.landed(state)


def _left_out(step: oracle.Step, states: Mapping[str, set[str]]) -> bool:
    """A step served outside AEW: its ledgers say so, or, on none, it has nothing but the harness's own act."""
    found = states.get(step.key)
    if found:
        return found == {oracle.OUTSIDE}
    return all(isinstance(i, oracle.Local) and i.outside for i in step.serves)


def _steps_row(steps: Sequence[oracle.Step], states: Mapping[str, set[str]]) -> dict[str, Any]:
    known = [s.key for s in steps if states.get(s.key)]
    mixed = {k: sorted(states[k]) for k in known if len(states[k]) > 1}
    landed = sum(1 for k in known if k not in mixed and _landed(next(iter(states[k]))))
    return {"landed": landed if len(known) == len(steps) else None, "of": len(steps), "mixed": mixed,
            "unseen": [s.key for s in steps if not states.get(s.key)]}


def driver_owed(ledgers: Iterable[Mapping[str, Any]]) -> list[str]:
    """The steps that have landed with no driver yet, by the oracle's step number (a step may be taken more than once,
    under more than one name). Its own row: such a step has landed and still fails the verdict."""
    owed = {o.get("oracle_step"): str(o.get("step")) for ledger in ledgers for o in ledger.get("observations") or []
            if o.get("kind") == "no_driver"}
    known = {s.n for s in oracle.STEPS}
    return [s.key for s in oracle.STEPS if s.n in owed] + sorted(v for n, v in owed.items() if n not in known)


def reached(ledgers: Iterable[Mapping[str, Any]]) -> dict[str, int | None]:
    """Whether a result reached the operator, over the measured ``ledgers`` whose verdict asks for one. A ledger with
    no such observation (an older one) is unknown, never no. None when no ledger recorded it."""
    yes = of = not_asked = unknown = 0
    for ledger in ledgers:
        seen = [o for o in ledger.get("observations") or [] if o.get("kind") == RESULT_REACHED]
        if not seen:
            unknown += 1
        elif not seen[-1].get("asked"):
            not_asked += 1
        else:
            of += 1
            yes += 1 if seen[-1].get("reached") else 0
    return {REACHED: yes if of else None, "reached_of": of, "reached_not_asked": not_asked, "reached_unknown": unknown}


def values(found: Sequence[Mapping[str, Any]], *, passing: int, measured: int) -> dict[str, Any]:
    """The scoreboard's values of a run that measured. ``found`` holds each scenario's ``ledger`` (None without one)."""
    ledgers = [r["ledger"] for r in found if r.get("ledger")]
    states = step_states(ledgers)
    first = oracle.path("V1")
    rest = [s for s in oracle.STEPS if s not in first]
    others = [s for s in rest if not _left_out(s, states)]
    v1, other = _steps_row(first, states), _steps_row(others, states)
    owed = driver_owed(ledgers)
    return {"total": len(found), "scenarios_measured": measured, PASSING: passing,
            V1_LANDED: v1["landed"], "v1_of": v1["of"], "v1_mixed": v1["mixed"], "v1_unseen": v1["unseen"],
            OTHER_LANDED: other["landed"], "other_of": other["of"], "other_mixed": other["mixed"],
            "other_unseen": other["unseen"], "left_out": [s.key for s in rest if s not in others],
            DRIVER_OWED: len(owed), "owed": owed,
            **reached([r["ledger"] for r in found if r.get("ledger") and r.get("counted")])}


# ------------------------------------------------------------------------------------------------------- the series


def _count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _names(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _checked(line: str) -> dict[str, Any]:
    """One line, with every field the display reads in the shape it reads: a report that fails would hide its run."""
    row = json.loads(line)
    if not isinstance(row, dict) or not isinstance(row.get("measured"), bool):
        raise ValueError("not a series line")
    if not all(isinstance(row.get(k), str) for k in ("run", "sha", "date")):
        raise ValueError("a series line without its run, sha or date")
    for measure in MEASURES:
        value = row.get(measure)
        if value is not None and not _count(value):
            raise ValueError(f"{measure} is not a count")
    if row["measured"] and not all(_count(row.get(k)) for k in (PASSING, "total", "scenarios_measured")):
        raise ValueError("a measured line without its counts")
    if not all(_names(row.get(k, [])) for k in ("owed", "left_out", "v1_unseen", "other_unseen")):
        raise ValueError("a series line whose names are not a list of names")
    for mixed in ("v1_mixed", "other_mixed"):
        found = row.get(mixed, {})
        if not isinstance(found, dict) or not all(_names(v) for v in found.values()):
            raise ValueError("a series line whose mixed steps are not their states")
    if "restarted" in row and not isinstance(row["restarted"], str):
        raise ValueError("a series line whose restart gives no reason")
    return row


def read_series(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    """The series, and why it restarted (None when it did not). One bad line makes the whole file unreadable, since a
    gap would read as flat. It never raises: a report that fails would hide the run it reports."""
    try:
        text = path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        return [], "no series was restored"
    except (OSError, ValueError) as exc:
        return [], f"the restored series is unreadable ({type(exc).__name__})"
    try:
        rows = [_checked(line) for line in text.splitlines() if line.strip()]
    except (ValueError, RecursionError) as exc:
        return [], f"the restored series is unreadable ({type(exc).__name__})"
    return (rows, None) if rows else ([], "the restored series is empty")


def save_series(path: Path, rows: Sequence[Mapping[str, Any]]) -> str | None:
    """Write the series whole, with LF endings on every platform; why it could not be written, else None."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows).encode("utf-8"))
    except OSError as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def joined(rows: Sequence[dict[str, Any]], row: dict[str, Any]) -> list[dict[str, Any]]:
    """The series with this run in it. A re-run of a ``main`` run restores the newest save, which may be a later run's,
    so it replaces its line where it stands rather than adding a data point (an attempt's run id is the run's). An
    attempt that measured less keeps the line it would replace, and a restart stays on its run's line."""
    if not any(r["run"] == row["run"] for r in rows):
        return [*rows, row]

    def settled(old: dict[str, Any]) -> dict[str, Any]:
        if old["run"] != row["run"]:
            return old
        kept = old if row.get("scenarios_measured", 0) < old.get("scenarios_measured", 0) else row
        return {**kept, "restarted": old["restarted"]} if old.get("restarted") else kept

    return [settled(r) for r in rows]


def lane_sizes(rows: Sequence[Mapping[str, Any]]) -> list[int | None]:
    """How many scenarios the lane held at each run (None: a run that measured nothing): its own total, or the largest
    of the last ``LANE_WINDOW`` runs before it. A JUnit report holds only the scenarios that ran (report.py), so a run
    cut short has a short total and only the runs around it show that."""
    out: list[int | None] = []
    for i, row in enumerate(rows):
        recent = [int(r.get("total") or 0) for r in rows[max(0, i - LANE_WINDOW):i] if r.get("measured")]
        out.append(max([int(row.get("total") or 0), *recent]) if row.get("measured") else None)
    return out


def partials(rows: Sequence[Mapping[str, Any]]) -> list[bool]:
    """Whether each run measured, but less than the lane held."""
    return [size is not None and int(row.get("scenarios_measured") or 0) < size
            for row, size in zip(rows, lane_sizes(rows), strict=True)]


class Flat(NamedTuple):
    value: int | None
    date: str = ""
    where: str = ""
    runs: int = 0  # measured runs in the series at this value, the newest included
    moved: str | None = None  # "fell" or "rose", while the value is the one it moved to
    before: int | None = None
    seeded: bool = False  # the flat run began before the series, whose earlier runs are not counted
    restart: str | None = None  # the run whose line says the series restarted, when the flat run begins there


def _named(run: str) -> str:
    return run if run == THIS_RUN else f"run {run}"


def flat(rows: Sequence[Mapping[str, Any]], measure: str, seed: Seeded | None) -> Flat:
    """How long ``measure`` has held. Only a run that measured what this measure needs is a data point (a falling value
    resets it; see the module's docstring). Nothing is compared across a restart: the runs it lost could have moved."""
    start = Flat(seed.value, seed.date, seed.where, seeded=True) if seed else Flat(None)
    now, restart = start, None
    for row, partial in zip(rows, partials(rows), strict=True):
        if row.get("restarted"):
            now, restart = start, str(row["run"])
        if not row.get("measured") or (partial and measure in WHOLE_LANE_ONLY):
            continue
        value = row.get(measure)
        if value is None:  # recorded nothing for this measure: neither a reset nor an extension
            continue
        where = _named(str(row["run"]))
        if now.value is None or (restart and now.seeded and not now.runs and value != now.value):
            now = Flat(value, row["date"], where, runs=1, restart=restart)
        elif value == now.value:
            now = now._replace(runs=now.runs + 1)
        else:
            now = Flat(value, row["date"], where, runs=1, moved="fell" if value < now.value else "rose",
                       before=now.value)
    return now


# ------------------------------------------------------------------------------------------------------ the display


def v01_line(platform: str, *, known: bool, passing: int, total: int, pytest: str | None = None) -> str:
    """The designer's rule: the V-01 line always leads, so alpha can't read as V-01. Derived from the counts, and it
    never reads as done before every scenario passes. ``total`` is what the JUnit report holds, which is only what ran,
    so "every" also needs ``pytest``, the pytest step's outcome: anything but finishing clean says what is known."""
    if known and total and passing == total:
        if pytest != PYTEST_FINISHED:
            how = f"pytest's step ended as {pytest}" if pytest else "nothing here says how pytest's step ended"
            return (f"**V-01 is not met:** {passing} of the {total} that ran pass, and the run may have ended early "
                    f"({how}); this job stays red until every scenario passes.")
        if platform in ENFORCED_PLATFORMS:
            return f"**Every scenario passes ({passing} of {total}).** Enforcing this job is the operator's decision."
        return (f"**Every scenario passes here ({passing} of {total}),** on a platform outside the enforced gate; "
                "enforcing this job is the operator's decision.")
    counted = f"{passing} of {total} scenarios pass" if known else "how many scenarios pass is unknown this run"
    return f"**V-01 is not met:** {counted}, and this job stays red until every scenario passes."


def _plural(n: int, what: str) -> str:
    return f"{n} {what}{'' if n == 1 else 's'}"


def _since(found: Flat) -> str:
    if found.value is None:
        return "no run has recorded it yet"
    runs = _plural(found.runs, "measured run")
    if found.moved:
        return f"{found.moved} from {found.before} by {found.date} ({found.where}); {runs} at this value"
    if found.restart:
        return f"since the series began or restarted at {_named(found.restart)}; any earlier runs lost; {runs}"
    if found.seeded:
        return f"{found.date} ({found.where}); {runs} in the series, earlier runs not counted"
    return f"{found.date} ({found.where}); {runs}"


def _detail(row: Mapping[str, Any], mixed: str, unseen: str) -> str:
    parts = [f"mixed: {k} ({', '.join(v)})" for k, v in (row.get(mixed) or {}).items()]
    if row.get(unseen):
        parts.append(f"on no ledger: {', '.join(row[unseen])}")
    return f"; {'; '.join(parts)}" if parts else ""


def _now(whole: Mapping[str, Any] | None, newest: Mapping[str, Any] | None,
         flats: Mapping[str, Flat]) -> dict[str, str]:
    """Each row's "now" cell: the rows a partial run changes from the last run that measured the whole lane (``whole``),
    the step rows from the last that measured at all (``newest``); without one, a seed's value, or unknown."""

    def counted(value: int | None, of: int) -> str:
        return f"{value} of {of}" if value is not None else f"unknown, of {of}"

    out = {m: f"{flats[m].value} (the seed's)" if flats[m].value is not None else "unknown" for m in MEASURES}
    if newest is not None:
        left_out = newest.get("left_out") or []
        out[V1_LANDED] = (counted(newest.get(V1_LANDED), newest.get("v1_of", 0))
                          + _detail(newest, "v1_mixed", "v1_unseen"))
        out[OTHER_LANDED] = (counted(newest.get(OTHER_LANDED), newest.get("other_of", 0))
                             + (f", leaving out {', '.join(left_out)} (outside AEW)" if left_out else "")
                             + _detail(newest, "other_mixed", "other_unseen"))
    if whole is not None:
        reach = "unknown"
        if whole.get(REACHED) is not None:
            reach = f"{whole[REACHED]} of the {whole.get('reached_of')} measured that ask for one"
        aside = [f"{whole[k]} {what}" for k, what in (("reached_not_asked", "not asked"),
                                                      ("reached_unknown", "unknown")) if whole.get(k)]
        owed = whole.get(DRIVER_OWED)
        out[PASSING] = (f"{whole[PASSING]} of {whole.get('scenarios_measured')} measured, "
                        f"{whole[PASSING]} of {whole.get('total')} total")
        out[DRIVER_OWED] = ("unknown" if owed is None
                            else f"{owed}" + (f": {', '.join(whole.get('owed') or [])}" if owed else ""))
        out[REACHED] = reach + (f" ({'; '.join(aside)})" if aside else "")
    return out


LABELS = {PASSING: "Scenarios passing",
          V1_LANDED: "V1's steps landed",
          OTHER_LANDED: "The other steps landed",
          DRIVER_OWED: "Landed, driver owed (these still fail the verdict)",
          REACHED: "Reached a result, passing or not (no history before the first run that records it)"}


def _blind(rows: Sequence[Mapping[str, Any]], whole: Mapping[str, Any] | None, newest: Mapping[str, Any] | None,
           *, seeded: bool, this_run: str) -> list[str]:
    """What a run that measured nothing or only part of the lane says, so a blind stretch cannot pass silently: the 40
    hours from #283 to #307 were runs that measured 4 of 17, so the banner counts them too."""
    cut = partials(rows)
    if not rows or (rows[-1].get("measured") and not cut[-1]):
        return []
    blind = 0
    for row, partial in zip(reversed(rows), reversed(cut), strict=True):
        if row.get("measured") and not partial:
            break
        blind += 1
    stretch = rows[-blind:]
    what = "measured nothing"
    if any(r.get("measured") for r in stretch):
        what = "measured nothing or only part of the lane"
    counted = f" {blind} runs in a row have {what}, since {stretch[0]['date']}." if blind > 1 else ""
    if whole is not None:
        shown = (f"The values below are from the last run that measured the whole lane: {_named(str(whole['run']))} "
                 f"(`{str(whole['sha'])[:8]}`, {whole['date']}).")
    elif newest is None:
        shown = ("No run in the series has measured, so the values below are the seed's." if seeded else
                 "No run in the series has measured, so the values below are unknown.")
    else:
        shown = "No run in the series has measured the whole lane, so the rows that need it are the seed's or unknown."
    if newest is not None and newest is not whole:
        shown += (f" The step rows are from {_named(str(newest['run']))}: a step's state is derived when a scenario "
                  "sets up, so part of the lane still shows it.")
    who = "This run" if rows[-1]["run"] == this_run else _named(str(rows[-1]["run"])).capitalize()
    if rows[-1].get("measured"):
        size, total = lane_sizes(rows)[-1], rows[-1].get("total")
        why = ("the others ended before their verdict" if total == size else
               f"its report holds only the {total} that ran; the others ended before their verdict or never ran")
        head = f"**{who} measured only {rows[-1].get('scenarios_measured')} of {size} scenarios** ({why})."
    else:
        head = f"**{who} measured nothing** ({cell(str(rows[-1].get('why') or ''), 200)})."
    return [f"{head} {shown}{counted}", ""]


def _series_cell(row: Mapping[str, Any], measure: str, of: str = "") -> str:
    value = row.get(measure)
    if value is None:
        return "-"
    return f"{value} of {row[of]}" if of and row.get(of) is not None else str(value)


def _measured_cell(row: Mapping[str, Any], size: int | None) -> str:
    if size is None:
        return f"no: {cell(str(row.get('why') or ''), 80)}"
    count = int(row.get("scenarios_measured") or 0)
    return f"{count} of {size}" + (", partial" if count < size else "")


def last_runs(rows: Sequence[Mapping[str, Any]], this_run: str, saved: bool) -> list[str]:
    """The last ``SHOWN_RUNS`` runs, newest last."""
    shown = min(len(rows), SHOWN_RUNS)
    whole = (f"the whole series is `{SERIES}` in this run's artifact" if saved else
             f"`main`'s series, when one was restored, is `{SERIES}` in this run's artifact, without this run")
    out = [f"**The last {'run' if shown == 1 else f'{shown} runs'}** ({whole}):",
           "", "| Run | Sha | Date | Measured | Passing | V1 landed | Other landed | Driver owed "
           "| Reached, of those that ask |",
           "|---|---|---|---|---|---|---|---|---|"]
    for row, size in list(zip(rows, lane_sizes(rows), strict=True))[-SHOWN_RUNS:]:
        run = cell(str(row["run"])) + (" (this run, not saved)" if not saved and row["run"] == this_run else "")
        measured = _measured_cell(row, size) + ("; the series began or restarted here" if row.get("restarted") else "")
        out.append(f"| {run} | `{cell(str(row['sha']))[:8]}` | {cell(str(row['date']))} | {measured} "
                   f"| {_series_cell(row, PASSING, 'total')} | {_series_cell(row, V1_LANDED, 'v1_of')} "
                   f"| {_series_cell(row, OTHER_LANDED, 'other_of')} | {_series_cell(row, DRIVER_OWED)} "
                   f"| {_series_cell(row, REACHED, 'reached_of')} |")
    return out


def render(platform: str, rows: Sequence[Mapping[str, Any]], *, this_run: str, saved: bool,
           restarted: str | None, save_problem: str | None = None) -> list[str]:
    """The scoreboard, then the last runs."""
    seed = SEED.get(platform, {})
    flats = {m: flat(rows, m, seed.get(m)) for m in MEASURES}
    newest = next((r for r in reversed(rows) if r.get("measured")), None)
    whole = next((r for r, partial in zip(reversed(rows), reversed(partials(rows)), strict=True)
                  if r.get("measured") and not partial), None)
    now = _now(whole, newest, flats)
    out = ["**Progress** (a display: no threshold moves and no verdict changes here):", "",
           *_blind(rows, whole, newest, seeded=bool(seed), this_run=this_run),
           "| Measure | Now | Flat since |", "|---|---|---|"]
    out += [f"| {LABELS[m]} | {cell(now[m], 240)} | {cell(_since(flats[m]), 240)} |" for m in MEASURES]
    out.append("")
    if restarted:
        kept = "from its seed" if seed else "with no seed, as this platform has none"
        out += [f"The series began or restarted {kept}: {restarted}. Any earlier lines are in the artifacts of the "
                "runs before this one.", ""]
    if not saved:
        out += ["This run is not `main`'s: its values are shown here and saved nowhere, so `main`'s series is "
                "unchanged.", ""]
    if save_problem:
        out += [f"The series could not be saved: {cell(save_problem, 200)}.", ""]
    return out + last_runs(rows, this_run, saved) + [""]
