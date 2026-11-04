**E112 built (2026-11-01).** Until this row is built, the live lane's Lead-session scenarios run the general Lead
command, which `required` refuses on Linux. So their labs set `containment.mode: allow_weaker`: the AT-14, AT-15 and
AT-17 scenarios have `lead_session=True` (`tests/helpers/harness_acceptance.py`), for those tests only, and each runs
labelled not contained and in the register of weaker contexts. A headless contained OpenCode Lead would let them run
contained.
