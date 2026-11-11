"""Deterministic fake-V2 test adapter: exercise call binding on either host without qualifying Windows runtime.

Never registered by production. It changes only the qualification gate, not call tracking or delivery logic.
"""

from aew.harness.opencode.adapter import OpenCodeAdapter


class FakeWaitOpenCodeAdapter(OpenCodeAdapter):
    reports_steps = True


class UnsupportedWaitOpenCodeAdapter(OpenCodeAdapter):
    reports_steps = False
