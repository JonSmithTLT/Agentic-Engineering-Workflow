"""Deterministic fake-V2 test adapter: exercise call binding on either host without qualifying Windows runtime.

Never registered by production. It changes only the qualification gate, not call tracking or delivery logic.
"""

from aew.harness.opencode.adapter import OpenCodeAdapter


class FakeWaitOpenCodeAdapter(OpenCodeAdapter):
    reports_steps = True


class BoundWaitOpenCodeAdapter(FakeWaitOpenCodeAdapter):
    """Only the orphan scenario needs a file barrier after a real adapter start and captured call."""

    def wait_binding(self):
        binding = super().wait_binding()
        if binding is not None:
            (self.state_dir / "wait-bound").touch()  # test barrier: the actual wait captured its call, not just a PID
        return binding


class UnsupportedWaitOpenCodeAdapter(OpenCodeAdapter):
    reports_steps = False
