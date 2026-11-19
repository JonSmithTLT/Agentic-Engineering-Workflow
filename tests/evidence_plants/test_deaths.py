"""Blocking tests for the hosted lane proof. Evidence is written only by lane helpers."""

import ctypes
import os
import re
import signal
import sys
import threading
import time

import pytest


def planted_block_deadline():
    threading.Event().wait(600)


def planted_block_hang():
    if os.name == "nt":
        re.fullmatch(r"(a+)+b", "a" * 40)
        return
    # The regex engine checks POSIX signals. A native read with restart enabled stays in C with the GIL held.
    read_fd, write_fd = os.pipe()
    try:
        signal.siginterrupt(signal.SIGALRM, False)
        read = ctypes.PyDLL(None).read
        read.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t]
        read.restype = ctypes.c_ssize_t
        read(read_fd, ctypes.create_string_buffer(1), 1)
        raise RuntimeError("the planted native read returned before an external kill")
    finally:
        os.close(read_fd)
        os.close(write_fd)


@pytest.mark.parametrize("kind", [os.environ.get("AEW_EVIDENCE_PLANT", "disabled")])
def test_death(kind, request):
    if kind == "normal":
        return
    if kind.startswith("hang"):
        # execnet routes a worker's stdout to devnull. Its stderr reaches the lane log.
        request.config.pluginmanager.get_plugin("capturemanager").suspend_global_capture(in_=False)
        ready = threading.Event()

        def heartbeat():
            count = 0
            while True:
                count += 1
                print(f"evidence-heartbeat {count} {time.time():.6f}", file=sys.stderr, flush=True)
                if count >= 3:
                    ready.set()
                time.sleep(0.2)

        threading.Thread(target=heartbeat, daemon=True).start()
        assert ready.wait(5), "heartbeat did not start before GIL plant"
        print(f"evidence-gil-enter {time.time():.6f}", file=sys.stderr, flush=True)
        planted_block_hang()
    else:
        planted_block_deadline()
