"""Deterministic fake-V2 test adapter: exercise call binding on either host without qualifying Windows runtime.

Never registered by production. Wait-specific tests select the continuation-only transport so they can
stage a message before releasing a worker into its wait.
"""

from aew.harness.opencode.adapter import OpenCodeAdapter


class FakeWaitOpenCodeAdapter(OpenCodeAdapter):
    reports_steps = True
    coordination_live = False


class BoundWaitOpenCodeAdapter(FakeWaitOpenCodeAdapter):
    """Only the orphan scenario needs a file barrier after a real adapter start and captured call."""

    def wait_binding(self):
        binding = super().wait_binding()
        if binding is not None:
            (self.state_dir / "wait-bound").touch()  # test barrier: the actual wait captured its call, not just a PID
        return binding


class UnsupportedWaitOpenCodeAdapter(OpenCodeAdapter):
    reports_steps = False
    coordination_live = False
