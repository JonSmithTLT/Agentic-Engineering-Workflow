"""Spike probe 3 (Windows): process-tree ownership without relying on the --stdio lease.

A. A supervisor-like parent puts itself in a KILL_ON_JOB_CLOSE job, starts a private server, and has the
   server's shell start a *detached* grandchild. Killing the parent must take the server and the grandchild.
B. A child started from a session shell command (no AEW job around the server) survives the command's normal
   exit and the server's exit - the property `aew harness launch` needs when a Lead runs it from OpenCode.
C. Inside the job, a shell command trying CREATE_BREAKAWAY_FROM_JOB is refused (the job does not allow it).
"""

from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from v2lib import isolated_env, new_id, start_server

PY = sys.executable
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.CreateJobObjectW.restype = wintypes.HANDLE
k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
k32.GetCurrentProcess.restype = wintypes.HANDLE
k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
k32.CloseHandle.argtypes = [wintypes.HANDLE]
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JobObjectExtendedLimitInformation = 9


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in ("r", "w", "o", "rb", "wb", "ob")]


class BASIC(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]


class EXTENDED(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO_COUNTERS), ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


def job_self() -> int:
    job = k32.CreateJobObjectW(None, None)
    info = EXTENDED()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k32.SetInformationJobObject(job, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)):
        raise OSError(ctypes.get_last_error())
    if not k32.AssignProcessToJobObject(job, k32.GetCurrentProcess()):
        raise OSError(ctypes.get_last_error())
    return job


def alive(pid: int) -> bool:
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = wintypes.DWORD()
    k32.GetExitCodeProcess(h, ctypes.byref(code))
    k32.CloseHandle(h)
    return code.value == 259  # STILL_ACTIVE


GRANDCHILD = ("import subprocess,sys;p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)'],"
              "creationflags=0x08000000|0x00000200{extra});open(r'{pidfile}','w').write(str(p.pid))")


def shell_spawn(srv, sid: str, pidfile: Path, extra: str = "") -> tuple[int, str]:
    code = GRANDCHILD.format(pidfile=str(pidfile), extra=extra)
    cmd = f'"{PY}" -c "{code}"'
    st, r = srv.post(f"/api/session/{sid}/shell", {"id": new_id("msg"), "command": cmd}, timeout=60)
    time.sleep(1.5)
    return st, str(r)[:300]


def role_a(root: Path, report: Path) -> None:
    """Runs as the child 'supervisor': jobs itself, starts a server, spawns a detached grandchild, then waits."""
    job_self()
    ws = root / "ws-a"
    ws.mkdir(parents=True, exist_ok=True)
    srv = start_server(isolated_env(root / "state-a", config={"snapshots": False}), ws)
    st, sess = srv.post("/api/session", {"location": {"directory": str(ws)}})
    sid = sess["data"]["id"]
    pidfile = root / "grandchild-a.pid"
    shell_spawn(srv, sid, pidfile)
    # C: breakaway attempt from inside the job (CREATE_BREAKAWAY_FROM_JOB = 0x01000000)
    pidfile_c = root / "grandchild-c.pid"
    stc, rc = shell_spawn(srv, sid, pidfile_c, extra="|0x01000000")
    report.write_text(json.dumps({"server_pid": srv.proc.pid, "grandchild_pid": int(pidfile.read_text())
                                  if pidfile.exists() else None, "breakaway_pid_file": pidfile_c.exists(),
                                  "breakaway_shell": rc}))
    time.sleep(600)  # killed by the parent


def main(root: Path, out: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    res: dict = {}
    # ---------------- A + C
    report = root / "a-report.json"
    sup = subprocess.Popen([PY, __file__, "--role-a", str(root), str(report)], creationflags=subprocess.CREATE_NO_WINDOW)
    deadline = time.time() + 120
    while time.time() < deadline and not report.exists():
        time.sleep(0.5)
    a = json.loads(report.read_text()) if report.exists() else {}
    a["server_alive_before"] = alive(a["server_pid"]) if a.get("server_pid") else None
    a["grandchild_alive_before"] = alive(a["grandchild_pid"]) if a.get("grandchild_pid") else None
    sup.kill()  # TerminateProcess: no finalizers, no stdin-close courtesy beyond the OS
    sup.wait()
    time.sleep(3)
    a["server_alive_after_supervisor_killed"] = alive(a["server_pid"]) if a.get("server_pid") else None
    a["grandchild_alive_after_supervisor_killed"] = alive(a["grandchild_pid"]) if a.get("grandchild_pid") else None
    res["A_job_kill_on_close"] = a
    # ---------------- B: no job; child of a shell command must survive command exit and server exit
    ws = root / "ws-b"
    ws.mkdir(parents=True, exist_ok=True)
    srv = start_server(isolated_env(root / "state-b", config={"snapshots": False}), ws)
    st, sess = srv.post("/api/session", {"location": {"directory": str(ws)}})
    sid = sess["data"]["id"]
    pidfile = root / "grandchild-b.pid"
    shell_spawn(srv, sid, pidfile)
    gpid = int(pidfile.read_text()) if pidfile.exists() else None
    b = {"grandchild_pid": gpid, "alive_after_command_exit": alive(gpid) if gpid else None}
    b["lease_exit_s"] = srv.close_lease()
    time.sleep(2)
    b["alive_after_server_exit"] = alive(gpid) if gpid else None
    if gpid and b["alive_after_server_exit"]:
        subprocess.run(["taskkill", "/PID", str(gpid), "/F"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    res["B_detached_from_shell_tool"] = b
    (out / "probe_process.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "--role-a":
        role_a(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        main(Path(sys.argv[1]), Path(sys.argv[2]))
