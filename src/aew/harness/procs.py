"""Process-tree ownership for harness runs (ADR-0009), independent of any harness-specific lease.

The run supervisor starts every harness process through a :class:`ProcessTree`:

* **Windows:** the processes are created suspended, assigned to a job object with
  ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` and then resumed, so no descendant can start outside the job.
  ``kill()`` terminates the job; if the supervisor dies, the OS closes its only job handle and kills
  every process in the job. The job does not allow breakaway.
* **POSIX:** the processes share one new process group, and a small *sentinel* outside the group kills
  the whole group when the supervisor's pipe to it closes, including when the supervisor is killed. (No
  ``preexec_fn``: the supervisor is multi-threaded.) A descendant that calls ``setsid`` escapes the group
  (documented residual; authority is unaffected, because authority lives in the credential).
* **Linux, contained (M4-B):** a tree built with a :class:`~aew.harness.containment.Layout` starts every process
  inside that bubblewrap sandbox, in its own PID namespace. The recorded pid is bubblewrap's host pid, which leads
  the process group; killing it ends the namespace, including a descendant that called ``setsid``. A tree that
  requires a layout and has none refuses to spawn: there is no per-call way to start an uncontained process.

Also: detached spawning of the supervisor itself, liveness by pid, and process suspension (tests).
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

IS_WINDOWS = sys.platform == "win32"
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_SUSPENDED = 0x00000004
CREATE_BREAKAWAY_FROM_JOB = 0x01000000

if sys.platform == "win32":  # pragma: windows-only
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _ntdll = ctypes.WinDLL("ntdll")
    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    _k32.SetInformationJobObject.restype = wintypes.BOOL
    _k32.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                               ctypes.c_void_p]
    _k32.QueryInformationJobObject.restype = wintypes.BOOL
    _k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _k32.AssignProcessToJobObject.restype = wintypes.BOOL
    _k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _k32.TerminateJobObject.restype = wintypes.BOOL
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _k32.GetExitCodeProcess.restype = wintypes.BOOL
    _k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _k32.TerminateProcess.restype = wintypes.BOOL
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.CloseHandle.restype = wintypes.BOOL
    _k32.GetProcessTimes.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
                                     ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
                                     ctypes.POINTER(wintypes.FILETIME)]
    _k32.GetProcessTimes.restype = wintypes.BOOL
    _k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _k32.WaitForSingleObject.restype = wintypes.DWORD
    _ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    _ntdll.NtSuspendProcess.argtypes = [wintypes.HANDLE]

    _KILL_ON_JOB_CLOSE = 0x2000
    _EXTENDED_LIMIT_INFORMATION = 9
    _BASIC_ACCOUNTING_INFORMATION = 1
    _PROCESS_TERMINATE = 0x0001
    _PROCESS_SUSPEND_RESUME = 0x0800
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _SYNCHRONIZE = 0x00100000
    _WAIT_TIMEOUT = 0x102
    _STILL_ACTIVE = 259

    class _IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ("r", "w", "o", "rb", "wb", "ob")]

    class _BasicLimit(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _ExtendedLimit(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _BasicLimit), ("IoInfo", _IoCounters),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    class _BasicAccounting(ctypes.Structure):
        _fields_ = [("TotalUserTime", ctypes.c_longlong), ("TotalKernelTime", ctypes.c_longlong),
                    ("ThisPeriodTotalUserTime", ctypes.c_longlong), ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
                    ("TotalPageFaultCount", wintypes.DWORD), ("TotalProcesses", wintypes.DWORD),
                    ("ActiveProcesses", wintypes.DWORD), ("TotalTerminatedProcesses", wintypes.DWORD)]

    def _winerr(what: str) -> OSError:
        code = ctypes.get_last_error()
        return OSError(code, f"{what} failed (winerror {code})")


_SENTINEL = (
    "import os, signal, sys\n"
    "pgid = int(sys.argv[1])\n"
    "sys.stdin.buffer.read()\n"           # returns at EOF: the supervisor exited or was killed
    "try:\n    os.killpg(pgid, signal.SIGKILL)\nexcept OSError:\n    pass\n"
)


class ProcessTree:
    """Every harness process of one run. ``kill()`` ends all of them; so does the supervisor's death.

    ``layout`` contains every process the tree starts (Linux). ``require_layout`` makes a tree without one refuse
    to start anything (fail closed until the run's containment is decided)."""

    def __init__(self, layout: Any = None, *, require_layout: bool = False) -> None:
        if layout is not None and sys.platform == "win32":  # pragma: windows-only
            raise ValueError("filesystem containment layouts are Linux-only")
        self.layout = layout
        self.require_layout = require_layout
        self.pids: list[int] = []
        self._job: Any = None
        self._pgid: int | None = None
        self._sentinel: subprocess.Popen[bytes] | None = None
        if sys.platform == "win32":  # pragma: windows-only
            job = _k32.CreateJobObjectW(None, None)
            if not job:
                raise _winerr("CreateJobObject")
            info = _ExtendedLimit()
            info.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE
            if not _k32.SetInformationJobObject(job, _EXTENDED_LIMIT_INFORMATION, ctypes.byref(info),
                                                ctypes.sizeof(info)):
                raise _winerr("SetInformationJobObject")
            self._job = job

    def spawn(self, argv: list[str], **kwargs: Any) -> subprocess.Popen[Any]:
        if self.layout is not None:  # pragma: posix-only
            from aew.harness.containment import bwrap_argv

            argv = bwrap_argv(self.layout, list(argv), cwd=kwargs.get("cwd"))
        elif self.require_layout:
            from aew.errors import ContainmentUnavailable

            raise ContainmentUnavailable("this process tree requires filesystem containment and has no layout")
        if sys.platform == "win32":  # pragma: windows-only
            flags = kwargs.pop("creationflags", 0) | CREATE_SUSPENDED | CREATE_NO_WINDOW
            proc = subprocess.Popen(argv, creationflags=flags, **kwargs)
            handle = int(proc._handle)  # type: ignore[attr-defined]
            if not _k32.AssignProcessToJobObject(self._job, handle):
                err = _winerr("AssignProcessToJobObject")
                _k32.TerminateProcess(handle, 1)
                raise err
            _ntdll.NtResumeProcess(handle)
        else:  # pragma: posix-only
            if self._pgid is None:
                proc = subprocess.Popen(argv, start_new_session=True, **kwargs)
                self._pgid = proc.pid
                self._sentinel = subprocess.Popen([sys.executable, "-c", _SENTINEL, str(self._pgid)],
                                                  stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                                  stderr=subprocess.DEVNULL, start_new_session=True)
            else:
                proc = subprocess.Popen(argv, process_group=self._pgid, **kwargs)
        self.pids.append(proc.pid)
        return proc

    def active(self) -> int:
        """Processes still running in the tree (Windows: the job's count; POSIX: 1 if the group exists)."""
        if sys.platform == "win32":  # pragma: windows-only
            info = _BasicAccounting()
            if not _k32.QueryInformationJobObject(self._job, _BASIC_ACCOUNTING_INFORMATION, ctypes.byref(info),
                                                  ctypes.sizeof(info), None):
                return 0
            return int(info.ActiveProcesses)
        if self._pgid is None:
            return 0
        try:
            os.killpg(self._pgid, 0)
            return 1
        except OSError:
            return 0

    def kill(self) -> None:
        if sys.platform == "win32":  # pragma: windows-only
            if self._job:
                _k32.TerminateJobObject(self._job, 1)
            return
        if self._pgid is not None:
            try:
                os.killpg(self._pgid, signal.SIGKILL)
            except OSError:
                pass
        if self._sentinel is not None and self._sentinel.stdin:
            self._sentinel.stdin.close()  # the sentinel exits (its kill is now a no-op)

    def close(self, timeout_s: float = 10.0) -> int:
        """End every process still in the tree and wait until none runs. Returns how many were still running.

        For a tree whose owner is done with it (a check that returned): nothing it started may outlive it."""
        import time

        left = self.active()
        if left:
            self.kill()
        deadline = time.monotonic() + timeout_s
        while self.active() and time.monotonic() < deadline:
            time.sleep(0.02)
        if sys.platform == "win32" and self._job:  # pragma: windows-only
            _k32.CloseHandle(self._job)  # KILL_ON_JOB_CLOSE: anything still there ends with the handle
            self._job = None
        elif self._sentinel is not None:
            if self._sentinel.stdin and not self._sentinel.stdin.closed:
                self._sentinel.stdin.close()
            self._sentinel.wait(timeout_s)
        return left


def harden_current_process() -> None:
    """Make the credential-holding supervisor harder to inspect from same-user processes.

    Linux: non-dumpable, so /proc/<pid>/mem and /proc/<pid>/environ are not readable by other processes
    of the same user without CAP_SYS_PTRACE. Windows offers no equivalent within one user and integrity
    level (documented residual, ADR-0009).
    """
    if sys.platform.startswith("linux"):  # pragma: posix-only
        try:
            import ctypes as c
            c.CDLL(None, use_errno=True).prctl(4, 0)  # PR_SET_DUMPABLE = 0
        except Exception:  # noqa: S110 (hardening is best effort; ADR-0009 documents the residual)
            pass


def spawn_detached(argv: list[str], *, env: dict[str, str], cwd: str | Path | None = None,
                   stdin: Any = None, stdout: Any = None, stderr: Any = None) -> subprocess.Popen[Any]:
    """Start the run supervisor so that it outlives the launching CLI, without any visible console."""
    kwargs: dict[str, Any] = {"env": env, "cwd": cwd, "stdin": stdin, "stdout": stdout, "stderr": stderr}
    if sys.platform == "win32":  # pragma: windows-only
        base = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        try:  # leave any job the launching terminal runs in, where the job allows it
            return subprocess.Popen(argv, creationflags=base | CREATE_BREAKAWAY_FROM_JOB, **kwargs)
        except OSError:
            return subprocess.Popen(argv, creationflags=base, **kwargs)
    return subprocess.Popen(argv, start_new_session=True, **kwargs)


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if sys.platform == "win32":  # pragma: windows-only
        h = _k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        try:
            code = wintypes.DWORD()
            return bool(_k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == _STILL_ACTIVE
        finally:
            _k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:  # a zombie child of ours is not alive
        done, _ = os.waitpid(pid, os.WNOHANG)
        return done == 0
    except ChildProcessError:
        return True


def started_at(pid: int | None) -> float | None:
    """When the process with this pid started (epoch seconds), or None if unknown. A pid is only a process's
    identity together with its start time: pids are reused."""
    if not pid:
        return None
    if sys.platform == "win32":  # pragma: windows-only
        h = _k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return None
        try:
            created = wintypes.FILETIME()
            others = [wintypes.FILETIME() for _ in range(3)]
            if not _k32.GetProcessTimes(h, ctypes.byref(created), *(ctypes.byref(o) for o in others)):
                return None
            ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime  # 100 ns since 1601-01-01
            return ticks / 1e7 - 11644473600.0
        finally:
            _k32.CloseHandle(h)
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        boot = next(float(line.split()[1]) for line in Path("/proc/stat").read_text().splitlines()
                    if line.startswith("btime "))
        return boot + int(fields[19]) / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError, StopIteration):
        return None


def host_pid(ns_pid: int, *, under: int | None = None) -> int:
    """The host pid of a process that knows itself as ``ns_pid`` inside a PID namespace (Linux, ``NSpid`` in
    ``/proc/<pid>/status``: the host pid first, the innermost last). With ``under``, only descendants of that
    host process count. A process in no nested namespace is its own host pid. Raises ``LookupError`` when more
    than one process matches: watching the wrong one would prove nothing."""
    if not sys.platform.startswith("linux"):
        return ns_pid
    matches = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            status = Path("/proc", entry, "status").read_text()
        except OSError:
            continue
        fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
        ids = [int(x) for x in fields.get("NSpid", "").split()]
        if len(ids) >= 2 and ids[-1] == ns_pid and (under is None or _descends(int(entry), under)):
            matches.append(ids[0])
    if len(matches) > 1:
        raise LookupError(f"namespace pid {ns_pid} matches host pids {sorted(matches)}")
    return matches[0] if matches else ns_pid


def _descends(pid: int, ancestor: int) -> bool:
    seen = 0
    while pid > 1 and seen < 4096:
        if pid == ancestor:
            return True
        try:
            status = Path("/proc", str(pid), "status").read_text()
        except OSError:
            return False
        pid = next((int(line.split()[1]) for line in status.splitlines() if line.startswith("PPid:")), 0)
        seen += 1
    return pid == ancestor


def same_process(pid: int | None, started_by: float) -> bool:
    """The live process ``pid`` is the one that existed at ``started_by`` (not a later one reusing the pid)."""
    start = started_at(pid)
    return start is not None and start <= started_by + 2.0 and pid_alive(pid)


class Watch:
    """Observe one process by a handle opened while it was known to exist, immune to pid reuse (tests)."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self._handle: Any = None
        self._fd: int | None = None
        if sys.platform == "win32":  # pragma: windows-only
            self._handle = _k32.OpenProcess(_SYNCHRONIZE | _PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        elif hasattr(os, "pidfd_open"):
            try:
                self._fd = os.pidfd_open(pid)
            except OSError:
                self._fd = None

    def alive(self) -> bool:
        if sys.platform == "win32":  # pragma: windows-only
            return bool(self._handle) and _k32.WaitForSingleObject(self._handle, 0) == _WAIT_TIMEOUT
        if self._fd is not None:
            import select
            return not select.select([self._fd], [], [], 0)[0]
        return pid_alive(self.pid)

    def close(self) -> None:
        if sys.platform == "win32" and self._handle:  # pragma: windows-only
            _k32.CloseHandle(self._handle)
            self._handle = None
        elif self._fd is not None:
            os.close(self._fd)
            self._fd = None


def kill_pid(pid: int | None) -> None:
    if not pid:
        return
    if sys.platform == "win32":  # pragma: windows-only
        h = _k32.OpenProcess(_PROCESS_TERMINATE, False, pid)
        if h:
            _k32.TerminateProcess(h, 1)
            _k32.CloseHandle(h)
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def suspend(pid: int) -> None:
    """Freeze a process (tests: an 'old run wakes up later')."""
    if sys.platform == "win32":  # pragma: windows-only
        h = _k32.OpenProcess(_PROCESS_SUSPEND_RESUME, False, pid)
        if not h:
            raise _winerr("OpenProcess")
        _ntdll.NtSuspendProcess(h)
        _k32.CloseHandle(h)
    else:  # pragma: posix-only
        os.kill(pid, signal.SIGSTOP)


def resume(pid: int) -> None:
    if sys.platform == "win32":  # pragma: windows-only
        h = _k32.OpenProcess(_PROCESS_SUSPEND_RESUME, False, pid)
        if not h:
            raise _winerr("OpenProcess")
        _ntdll.NtResumeProcess(h)
        _k32.CloseHandle(h)
    else:  # pragma: posix-only
        os.kill(pid, signal.SIGCONT)
