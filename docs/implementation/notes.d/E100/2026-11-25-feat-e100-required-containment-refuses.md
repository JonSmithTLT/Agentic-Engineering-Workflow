**Built (ADR-0009, amendment 2026-11-25).** `containment.mode` no longer turns an explicit `required` into
`allow_weaker` on Windows: on every platform with no containment, Windows included, an explicit `required` refuses the
launch in `containment.establish` with `CONTAINMENT_UNAVAILABLE`, reason `unsupported_platform` and the `platform`,
naming what works instead (run on Linux, or `containment.mode: allow_weaker`). Worker runs, `aew check run`,
checks-mode validation and both Lead routes read the same mode; off Linux the Lead's refusal gives the same reason and no
longer points to `aew opencode`, which is not contained there either. An unset mode still runs weaker there, its
`weaker_because` naming the platform. The three tests are in `tests/unit/test_containment_required_everywhere.py`,
with the platform simulated so both sides run on every CI platform; the docstrings of `mode()` and of the containment
package say the same. No surface-map change. Nothing of the row's work is left: it closes once its pull request merges,
and SYS-02's E100 slice comes off `remaining` with it.
