"""Blocking tests selected by explicit path in the hosted lane proof."""

import ctypes
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

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


KIND = os.environ.get("AEW_EVIDENCE_PLANT", "disabled")
CHAIN = {"worker-kill", "oom", "time-limit-github", "cancel"}


def oom_group() -> Path:
    """Only the dedicated synthetic worker may consume memory in the capped, swap-free proof leaf."""
    pid = os.getpid()
    path = Path(os.environ["AEW_PROOF_OOM_GROUP"])
    assert path.parent == Path("/sys/fs/cgroup") and path.name.startswith("aew-evidence-oom-")
    cap = int((path / "memory.max").read_text())
    assert 0 < cap <= 192 * 1024 * 1024 and (path / "memory.swap.max").read_text().strip() == "0"
    subprocess.run(["sudo", "-n", "tee", str(path / "cgroup.procs")], input=str(pid), text=True,
                   stdout=subprocess.DEVNULL, check=True, timeout=5)
    assert (path / "cgroup.procs").read_text().split() == [str(pid)]
    assert Path("/proc/self/cgroup").read_text().strip() == "0::/" + path.name
    return path


def reach_memory_limit() -> None:
    group = oom_group()
    cap = int((group / "memory.max").read_text())
    held = []
    size = 1024 * 1024
    for _ in range(cap // size):
        held.append(bytearray(size))
        if int((group / "memory.current").read_text()) >= .86 * cap:
            # Allow the real monitor one bounded chance to capture the high-water state before the kernel acts.
            time.sleep(5)
            break
    for _ in range((cap - len(held) * size) // size):
        held.append(bytearray(size))
    raise AssertionError("plant misfired: capped worker survived its bounded allocation")


def end_this_worker() -> None:
    # An external child can signal only its own still-identical parent. It accepts no target from the lane's files.
    import proctree

    pid, birth = proctree.identity(os.getpid())
    code = ("import os,sys; sys.path.insert(0,sys.argv[1]); import proctree; "
            "identity=(int(sys.argv[2]),int(sys.argv[3])); "
            "sys.exit(0 if os.getppid()==identity[0] and proctree.end(identity) else 1)")
    subprocess.run([sys._base_executable, "-B", "-c", code, str(Path(proctree.__file__).parent), str(pid), str(birth)],
                   check=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    raise AssertionError("plant misfired: signalled worker continued")


# Keep the cancellation workload live for the full six-minute plant deadline on either runner.
CANCEL_CASES = 720 if sys.platform == "linux" else 180


@pytest.mark.parametrize("step", range(CANCEL_CASES if KIND == "cancel" else 90) if KIND in CHAIN else [0])
@pytest.mark.parametrize("kind", [KIND])
def test_death(kind, step, request):
    if kind in CHAIN:
        selected = 2 + int(os.environ.get("GITHUB_RUN_ID", "0")) % 3
        if kind == "oom" and step == 0:
            oom_group()
        if step == selected and kind in {"oom", "worker-kill"}:
            time.sleep(0.5 + int(os.environ.get("GITHUB_RUN_ATTEMPT", "1")) % 3)
            if kind == "oom":
                reach_memory_limit()
            else:
                end_this_worker()
        time.sleep(2 + step % 4)
        return
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
