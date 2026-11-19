"""Blocking tests for the hosted lane proof. Evidence is written only by lane helpers."""

import os
import re
import threading
import time

import pytest


def planted_block_deadline():
    threading.Event().wait(600)


def planted_block_hang():
    # Catastrophic backtracking holds the GIL. The wrapper must read this process from outside.
    re.fullmatch(r"(a+)+b", "a" * 40)


@pytest.mark.parametrize("kind", [os.environ.get("AEW_EVIDENCE_PLANT", "disabled")])
def test_death(kind, request):
    if kind == "normal":
        return
    if kind.startswith("hang"):
        request.config.pluginmanager.get_plugin("capturemanager").suspend_global_capture(in_=False)
        ready = threading.Event()

        def heartbeat():
            count = 0
            while True:
                count += 1
                print(f"evidence-heartbeat {count} {time.time():.6f}", flush=True)
                if count >= 3:
                    ready.set()
                time.sleep(0.2)

        threading.Thread(target=heartbeat, daemon=True).start()
        assert ready.wait(5), "heartbeat did not start before GIL plant"
        print(f"evidence-gil-enter {time.time():.6f}", flush=True)
        planted_block_hang()
    else:
        planted_block_deadline()
