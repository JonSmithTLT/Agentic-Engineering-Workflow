"""E231's typed-versus-shell measurement runs end to end on its fixture project (``tools/perf/lead_typed_vs_shell.py``).

The tool is run by hand; this proves it still runs against the current CLI and typed surface."""

from __future__ import annotations

from tools.perf import lead_typed_vs_shell as E


def test_the_typed_versus_shell_measurement_reads_every_route_on_a_fresh_project():
    result = E.measure((34,))
    reads = {read["read"]: read for read in result["reads"]}
    assert set(reads) == {name for name, *_ in E.READS}
    for name, tool, _arguments, _command in E.READS:
        read = reads[name]
        assert read["shell_stdout_bytes"] > 0 and read["shell_result_bytes"] > read["shell_stdout_bytes"]
        if tool is not None:
            assert read["typed_text_bytes"] > 0 and read["typed_result_bytes"] > read["typed_text_bytes"]
    # status is named throughout the guide; the map reads are not, so the shell route needs a line for each.
    assert reads["status"]["shell_guide_line_bytes"] == 0
    assert reads["map show"]["shell_guide_line_bytes"] > 0 and reads["map search"]["shell_guide_line_bytes"] > 0
    assert {row["read"] for row in result["break_even"]} == set(reads)
    assert all(len(row["break_even_uses"]) == len(E.EXTRA_ROUND_TRIPS) * len(E.ROUND_TRIP_POOLS)
               for row in result["break_even"])
