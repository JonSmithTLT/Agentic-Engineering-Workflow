"""Processes and file holders for the hang autopsy and the session deadline (the hang-and-flake diagnosis plan, G3 H1
and H3), with no new dependency (no psutil), no admin rights, no WMI and no window.

- **The process table:** Linux reads ``/proc/<pid>/stat`` (parent pid, start time) and ``/proc/<pid>/cmdline``;
  Windows walks a ``CreateToolhelp32Snapshot`` (pid, parent pid, executable) and reads each process's creation time
  (``GetProcessTimes``) and, where the process can be opened, its command line (``NtQueryInformationProcess``,
  ``ProcessCommandLineInformation``). A process that cannot be opened is listed with its executable only.
- **Identity is (pid, start time), never a pid alone:** Windows reuses pids and Toolhelp keeps reporting a dead
  parent's pid; Linux reuses pids too. :func:`descendants` accepts a child only if it started no earlier than its
  parent, so a reused pid never brings in an unrelated process.
- **Who holds a file:** Windows asks the Restart Manager (``RmStartSession``, ``RmRegisterResources``, ``RmGetList``);
  Linux scans ``/proc/*/fd``.
- **The session's own process set** (Windows): a job object (:class:`Job`) without breakaway. Its member list is exact
  (``JobObjectBasicProcessIdList``), and the sentinel ends it with ``TerminateJobObject``.

This module imports nothing from AEW: the session sentinel loads it before anything else.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"


@dataclass(frozen=True)
class Proc:
    pid: int
    ppid: int
    start: int  # Windows: creation FILETIME (100 ns since 1601); Linux: start time in clock ticks since boot; 0 unknown
    exe: str = ""
    cmdline: str = ""

    @property
    def identity(self) -> tuple[int, int]:
        return (self.pid, self.start)


def descendants(root: tuple[int, int], table: Iterable[Proc], *,
                exclude: Iterable[tuple[int, int]] = ()) -> list[Proc]:
    """Every process descending from ``root`` (pid, start time) in ``table``, parents before children. A child is
    accepted only if its start time is no earlier than its parent's: a pid the parent's pid was reused for, or a
    process whose recorded parent pid is stale, is never taken in. ``exclude`` (identities) and their descendants are
    left out (the sentinel)."""
    kids: dict[int, list[Proc]] = {}
    for p in table:
        kids.setdefault(p.ppid, []).append(p)
    skip = set(exclude)
    out: list[Proc] = []
    todo = [root]
    seen = {root}
    while todo:
        pid, start = todo.pop(0)
        for child in sorted(kids.get(pid, []), key=lambda p: p.pid):
            if child.pid == pid or child.identity in seen or child.identity in skip:
                continue
            if start and child.start and child.start < start:
                continue  # it started before its "parent": the parent pid is stale or reused
            seen.add(child.identity)
            out.append(child)
            todo.append(child.identity)
    return out


def children_first(procs: list[Proc]) -> list[Proc]:
    """The order to end a set in: the latest started first, so a parent never respawns a child already ended."""
    return sorted(procs, key=lambda p: (-p.start, -p.pid))


def describe(procs: Iterable[Proc], *, title: str = "") -> str:
    lines = [title] if title else []
    lines.append(f"{'pid':>7} {'ppid':>7} {'start':>20}  exe / command line")
    for p in procs:
        lines.append(f"{p.pid:>7} {p.ppid:>7} {p.start:>20}  {p.cmdline or p.exe or '?'}")
    if IS_WINDOWS:
        lines.append("(Windows: a command line is shown where the process could be opened, else its executable)")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------------------------- Linux

def _stat(pid: int, *, living: bool = False) -> tuple[int, int] | None:
    """(parent pid, start time) from ``/proc/<pid>/stat``: fields 4 and 22, counted after the command's ``)``. With
    ``living``, a zombie (state ``Z``, or ``X``) counts as gone: it has ended and only waits for its parent to reap it
    (a controller killed from outside stays one until its launcher waits)."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            rest = f.read().decode("latin-1").rsplit(")", 1)[1].split()
        if living and rest[0] in ("Z", "X"):
            return None
        return int(rest[1]), int(rest[19])
    except (OSError, ValueError, IndexError):
        return None


def _linux_table() -> list[Proc]:
    out = []
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        pid = int(d)
        st = _stat(pid)
        if st is None:
            continue
        try:
            raw = Path(f"/proc/{pid}/cmdline").read_bytes()
            cmd = " ".join(a.decode("utf-8", "replace") for a in raw.split(b"\0") if a)
        except OSError:
            cmd = ""
        try:
            exe = os.readlink(f"/proc/{pid}/exe")
        except OSError:
            try:
                exe = Path(f"/proc/{pid}/comm").read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                exe = ""
        out.append(Proc(pid, st[0], st[1], exe, cmd))
    return out


def set_child_subreaper() -> bool:
    """Linux: make this process a child subreaper (``PR_SET_CHILD_SUBREAPER``), as ``procs.py`` does for interactive
    sessions, so a descendant that detaches is re-parented to it instead of to init."""
    if not sys.platform.startswith("linux"):
        return False
    import ctypes

    return ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0


def _linux_holders(paths: list[str]) -> dict[str, list[Proc]]:
    wanted = {os.path.realpath(p): p for p in paths}
    found: dict[str, list[Proc]] = {p: [] for p in paths}
    table = {p.pid: p for p in _linux_table()}
    for pid, proc in table.items():
        try:
            fds = os.listdir(f"/proc/{pid}/fd")
        except OSError:  # another user's process, or gone
            continue
        for fd in fds:
            try:
                target = os.readlink(f"/proc/{pid}/fd/{fd}")
            except OSError:
                continue
            target = target.removesuffix(" (deleted)")
            if target in wanted and proc not in found[wanted[target]]:
                found[wanted[target]].append(proc)
    return found


# ---------------------------------------------------------------------------------------------- Windows

if IS_WINDOWS:  # pragma: windows-only
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _ntdll = ctypes.WinDLL("ntdll")
    TH32CS_SNAPPROCESS = 0x2
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    PROCESS_TERMINATE = 0x0001
    SYNCHRONIZE = 0x00100000
    STILL_ACTIVE = 259
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260)]

    class UNICODE_STRING(ctypes.Structure):
        _fields_ = [("Length", wintypes.USHORT), ("MaximumLength", wintypes.USHORT), ("Buffer", ctypes.c_void_p)]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class RM_UNIQUE_PROCESS(ctypes.Structure):
        _fields_ = [("dwProcessId", wintypes.DWORD), ("ProcessStartTime", wintypes.FILETIME)]

    class RM_PROCESS_INFO(ctypes.Structure):
        _fields_ = [("Process", RM_UNIQUE_PROCESS), ("strAppName", wintypes.WCHAR * 256),
                    ("strServiceShortName", wintypes.WCHAR * 64), ("ApplicationType", ctypes.c_int),
                    ("AppStatus", wintypes.ULONG), ("TSSessionId", wintypes.DWORD), ("bRestartable", wintypes.BOOL)]

    _k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    _k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    _k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _k32.OpenJobObjectW.restype = wintypes.HANDLE
    _k32.OpenJobObjectW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    _k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _k32.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                               ctypes.POINTER(wintypes.DWORD)]
    _k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _k32.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
    _k32.GetCurrentProcess.restype = wintypes.HANDLE
    _ntdll.NtQueryInformationProcess.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.ULONG,
                                                 ctypes.POINTER(wintypes.ULONG)]
    _ntdll.NtQueryInformationProcess.restype = ctypes.c_long

    def _open(pid: int, access: int = PROCESS_QUERY_LIMITED_INFORMATION) -> int | None:
        h = _k32.OpenProcess(access, False, pid)
        return h or None

    def _creation(h: int) -> int:
        times = [wintypes.FILETIME() for _ in range(4)]
        if not _k32.GetProcessTimes(h, *[ctypes.byref(t) for t in times]):
            return 0
        return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime

    def _alive_handle(h: int) -> bool:
        code = wintypes.DWORD()
        return bool(_k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == STILL_ACTIVE

    def _cmdline(h: int) -> str:
        size = wintypes.ULONG(0)
        _ntdll.NtQueryInformationProcess(h, 60, None, 0, ctypes.byref(size))  # ProcessCommandLineInformation
        if not size.value or size.value > 1 << 20:
            return ""
        buf = ctypes.create_string_buffer(size.value)
        if _ntdll.NtQueryInformationProcess(h, 60, buf, size.value, ctypes.byref(size)) != 0:
            return ""
        us = UNICODE_STRING.from_buffer(buf)
        if not us.Buffer or not us.Length:
            return ""
        return ctypes.wstring_at(us.Buffer, us.Length // 2)

    def _image(h: int) -> str:
        n = wintypes.DWORD(1024)
        out = ctypes.create_unicode_buffer(n.value)
        return out.value if _k32.QueryFullProcessImageNameW(h, 0, out, ctypes.byref(n)) else ""

    def _windows_table(*, details: bool = True) -> list[Proc]:
        snap = _k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if not snap or snap == INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        rows: list[tuple[int, int, str]] = []
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            ok = _k32.Process32FirstW(snap, ctypes.byref(entry))
            while ok:
                rows.append((entry.th32ProcessID, entry.th32ParentProcessID, entry.szExeFile))
                ok = _k32.Process32NextW(snap, ctypes.byref(entry))
        finally:
            _k32.CloseHandle(snap)
        out = []
        for pid, ppid, exe in rows:
            start, cmd = 0, ""
            h = _open(pid) if pid else None
            if h:
                try:
                    start = _creation(h)
                    if details:
                        cmd = _cmdline(h)
                        exe = _image(h) or exe
                finally:
                    _k32.CloseHandle(h)
            out.append(Proc(pid, ppid, start, exe, cmd))
        return out

    def _windows_holders(paths: list[str]) -> dict[str, list[Proc]]:
        rm = ctypes.WinDLL("rstrtmgr")
        found: dict[str, list[Proc]] = {}
        for path in paths:
            found[path] = []
            session = wintypes.DWORD()
            key = ctypes.create_unicode_buffer(33)  # CCH_RM_SESSION_KEY + 1, zeroed
            if rm.RmStartSession(ctypes.byref(session), 0, key) != 0:
                continue
            try:
                files = (wintypes.LPCWSTR * 1)(path)
                if rm.RmRegisterResources(session, 1, files, 0, None, 0, None) != 0:
                    continue
                needed, count, reasons = wintypes.UINT(0), wintypes.UINT(0), wintypes.DWORD(0)
                rc = rm.RmGetList(session, ctypes.byref(needed), ctypes.byref(count), None, ctypes.byref(reasons))
                if rc not in (0, 234) or not needed.value:  # 234 ERROR_MORE_DATA: the sizing call's expected answer
                    continue
                infos = (RM_PROCESS_INFO * needed.value)()
                count = wintypes.UINT(needed.value)
                if rm.RmGetList(session, ctypes.byref(needed), ctypes.byref(count), infos, ctypes.byref(reasons)):
                    continue
                for info in infos[:count.value]:
                    ft = info.Process.ProcessStartTime
                    found[path].append(Proc(info.Process.dwProcessId, 0,
                                            (ft.dwHighDateTime << 32) | ft.dwLowDateTime, info.strAppName))
            finally:
                rm.RmEndSession(session)
        return found

    class Job:
        """A job object for the session's process set, created without ``JOB_OBJECT_LIMIT_BREAKAWAY_OK``: every
        process created after the controller joins it is a member, and ``spawn_detached``'s breakaway attempt fails
        into its fallback, inside the job. The handle is inheritable only so it can be handed to the sentinel."""

        def __init__(self, name: str | None = None) -> None:
            self.handle = _k32.CreateJobObjectW(None, name)
            if not self.handle:
                raise ctypes.WinError(ctypes.get_last_error())

        @classmethod
        def open(cls, name: str) -> Job:
            """The sentinel's own handle on the session job, by its name: it can end the job after the controller
            is gone (a job lives while a handle or a member does)."""
            job = cls.__new__(cls)
            job.handle = _k32.OpenJobObjectW(0x1F001F, False, name)  # JOB_OBJECT_ALL_ACCESS
            if not job.handle:
                raise ctypes.WinError(ctypes.get_last_error())
            return job

        def assign_self(self) -> None:
            if not _k32.AssignProcessToJobObject(self.handle, _k32.GetCurrentProcess()):
                raise ctypes.WinError(ctypes.get_last_error())

        def pids(self) -> list[int]:
            n = 4096
            while True:
                size = 8 + n * ctypes.sizeof(ctypes.c_size_t)
                buf = ctypes.create_string_buffer(size)
                if _k32.QueryInformationJobObject(self.handle, 3, buf, size, None):  # JobObjectBasicProcessIdList
                    listed = ctypes.c_uint32.from_buffer(buf, 4).value
                    ids = (ctypes.c_size_t * listed).from_buffer(buf, 8)
                    return [int(i) for i in ids]
                if ctypes.get_last_error() != 234 or n > 1 << 16:
                    raise ctypes.WinError(ctypes.get_last_error())
                n *= 4

        def members(self) -> list[Proc]:
            listed = set(self.pids())
            return [p for p in _windows_table() if p.pid in listed]

        def terminate(self, code: int) -> bool:
            return bool(_k32.TerminateJobObject(self.handle, code))

    def outer_job() -> str:
        """Whether this process is already in a job (a terminal's, a CI runner's) and, if so, that job's limit flags:
        the session job nests under it (Windows 8 and later). Recorded so a CI run shows how the nesting went."""
        inside = wintypes.BOOL()
        if not _k32.IsProcessInJob(_k32.GetCurrentProcess(), None, ctypes.byref(inside)):
            return f"IsProcessInJob failed (winerror {ctypes.get_last_error()})"
        if not inside.value:
            return "not in any job before the session job"
        info = JOBOBJECT_BASIC_LIMIT_INFORMATION()
        if not _k32.QueryInformationJobObject(None, 2, ctypes.byref(info), ctypes.sizeof(info), None):
            return f"in an outer job whose limits cannot be read (winerror {ctypes.get_last_error()})"
        flags = info.LimitFlags
        named = [n for bit, n in ((0x800, "BREAKAWAY_OK"), (0x1000, "SILENT_BREAKAWAY_OK"),
                                  (0x2000, "KILL_ON_JOB_CLOSE")) if flags & bit]
        return f"in an outer job, limit flags {flags:#x} ({', '.join(named) or 'none of breakaway or kill-on-close'})"


# ---------------------------------------------------------------------------------------------- portable

def table() -> list[Proc]:
    """Every process this user can see, with what can be read of each."""
    if IS_WINDOWS:  # pragma: windows-only
        return _windows_table()
    return _linux_table()


def start_time(pid: int) -> int | None:
    """A process's start time, or None when it is gone (or cannot be opened)."""
    if IS_WINDOWS:  # pragma: windows-only
        h = _open(pid)
        if not h:
            return None
        try:
            return _creation(h) if _alive_handle(h) else None
        finally:
            _k32.CloseHandle(h)
    st = _stat(pid, living=True)
    return st[1] if st else None


def identity(pid: int) -> tuple[int, int] | None:
    start = start_time(pid)
    return None if start is None else (pid, start)


def same(ident: tuple[int, int]) -> bool:
    """The process with this (pid, start time) is still alive: a reused pid is not."""
    return start_time(ident[0]) == ident[1]


def end(ident: tuple[int, int]) -> bool:
    """End the process with this identity, re-checking its start time first; a reused pid is left alone."""
    pid, start = ident
    if IS_WINDOWS:  # pragma: windows-only
        h = _open(pid, PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_TERMINATE)
        if not h:
            return False
        try:
            return _creation(h) == start and _alive_handle(h) and bool(_k32.TerminateProcess(h, 1))
        finally:
            _k32.CloseHandle(h)
    import signal

    if start_time(pid) != start:
        return False
    try:
        os.kill(pid, signal.SIGKILL)
        return True
    except OSError:
        return False


def holders(paths: list[str]) -> dict[str, list[Proc]]:
    """For each path, the processes holding it open (Restart Manager on Windows, ``/proc/*/fd`` on Linux)."""
    paths = [str(p) for p in paths]
    if not paths:
        return {}
    if IS_WINDOWS:  # pragma: windows-only
        return _windows_holders(paths)
    if sys.platform.startswith("linux"):
        return _linux_holders(paths)
    return {p: [] for p in paths}


def describe_holders(found: dict[str, list[Proc]]) -> str:
    if not found:
        return "no failed I/O recorded: no file to look up\n"
    lines = []
    for path, procs in found.items():
        lines.append(f"{path}:")
        lines.extend(f"  held by pid {p.pid} (started {p.start}) {p.exe}" for p in procs)
        if not procs:
            lines.append("  no holder found")
    return "\n".join(lines) + "\n"
