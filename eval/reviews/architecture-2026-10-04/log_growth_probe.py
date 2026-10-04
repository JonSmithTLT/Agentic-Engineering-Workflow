"""Probe for the outbox ADR (T3): does the per-revision transition log already record every commit, is it ever
pruned, and what does one record carry? Runs the frozen tree's CLI as the tests do (no console window)."""
import json, os, shutil, subprocess, sys, time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
WORK = HERE / "work"
REPO = WORK / "repo"
PY = sys.executable

def sh(*args, cwd=None, check=True):
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    env = {k: v for k, v in os.environ.items() if k not in ("AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN")}
    t0 = time.perf_counter()
    p = subprocess.run(list(args), cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
                       stdin=subprocess.DEVNULL, **kw)
    dt = time.perf_counter() - t0
    if check and p.returncode != 0:
        raise SystemExit(f"{' '.join(args)}\n{p.stdout}\n{p.stderr}")
    return p, dt

def aew(*args, **kw):
    p, dt = sh(PY, "-m", "aew", "-C", str(REPO), *args, **kw)
    out = json.loads(p.stdout) if p.stdout.strip().startswith("{") else p.stdout
    return out, dt

def git(*args):
    sh("git", *args, cwd=REPO)

def control():
    text = (REPO / ".aew/state/control.yaml").read_text(encoding="utf-8")
    body = text.rsplit("\n# aew-checksum", 1)[0]
    return yaml.safe_load(body)

def log_files():
    return sorted((REPO / ".aew/state/log").glob("*.yaml"))

def snapshot(label):
    st = control()
    files = log_files()
    print(f"{label:38s} rev={st['revision']:3d} log_files={len(files):3d} "
          f"txn_files={len(list((REPO / '.aew/state/txn').glob('*.yaml')))}")
    assert len(files) == st["revision"] + 1, "log file count != revision + 1"
    assert files[-1].stem == f"{st['revision']:06d}"

def _rw(func, path, exc):
    os.chmod(path, 0o700); func(path)
if WORK.exists():
    shutil.rmtree(WORK, onexc=_rw)
REPO.mkdir(parents=True)
git("init", "-q", "-b", "main")
git("config", "user.name", "probe"); git("config", "user.email", "probe@invalid")
(REPO / "README.md").write_text("# probe\n", encoding="utf-8")
(REPO / "src").mkdir(); (REPO / "src/a.py").write_text("x = 1\n", encoding="utf-8")
git("add", "-A"); git("commit", "-q", "-m", "initial")

aew("init")
snapshot("init (revision 0)")
res, dt = aew("lead", "acquire", "--expect-rev", "0", "--session-label", "probe")
tok = res["token"]
snapshot("lead.acquire (seat op, no finalizers)")

def rev():
    return control()["revision"]

timings = {}
for i in range(5):
    _, dt = aew("work", "create", "ticket", "--title", f"T{i}", "--class", "1", "--scope", "src/**",
                "--token", tok, "--expect-rev", str(rev()))
    timings.setdefault("work.create", []).append(dt)
snapshot("5x work.create (lead_txn)")
for i in range(3):
    _, dt = aew("checkpoint", "--next", f"step {i}", "--token", tok, "--expect-rev", str(rev()))
    timings.setdefault("checkpoint", []).append(dt)
snapshot("3x checkpoint (lead_txn)")
aew("lead", "handoff", "offer", "--token", tok, "--expect-rev", str(rev()))
snapshot("lead.handoff.offer (lead_txn)")
aew("lead", "handoff", "cancel", "--token", tok, "--expect-rev", str(rev()))
snapshot("lead.handoff.cancel (lead_txn)")
aew("lead", "release", "--token", tok, "--expect-rev", str(rev()))
snapshot("lead.release (lead_txn)")
res, _ = aew("lead", "acquire", "--expect-rev", str(rev()), "--session-label", "probe-2")
tok = res["token"]
snapshot("lead.acquire again (seat op)")
# a read-only pass and a doctor: must not change the log
aew("status"); aew("resume"); aew("doctor", check=False)
snapshot("after status/resume/doctor (reads)")

print("\n--- ops recorded, in revision order ---")
for f in log_files():
    d = yaml.safe_load(f.read_text(encoding="utf-8"))
    print(f"  {f.stem}  op={d['op']:22s} actor={json.dumps(d.get('actor'))[:60]} txn={'yes' if d.get('txn') else 'no'} "
          f"refs={len(d.get('refs') or [])} bytes={f.stat().st_size}")

print("\n--- one lead_txn record (work.create) ---")
print(log_files()[2].read_text(encoding="utf-8"))
print("--- one seat-op record (lead.acquire) ---")
print(log_files()[0].read_text(encoding="utf-8"))

print("--- what the hot state keeps about the last commit ---")
print(yaml.safe_dump(control()["last_transition"], sort_keys=False))

print("--- .aew layout ---")
for p in sorted((REPO / ".aew").rglob("*")):
    if p.is_file() and "log/" not in p.as_posix():
        print("  ", p.relative_to(REPO / ".aew").as_posix(), p.stat().st_size)
print("   state/log/: %d files, %d bytes total" % (len(log_files()), sum(f.stat().st_size for f in log_files())))

print("\n--- wall time per CLI commit (s), tiny project ---")
for k, v in timings.items():
    print(f"  {k:12s} n={len(v)} min={min(v):.2f} median={sorted(v)[len(v)//2]:.2f} max={max(v):.2f}")
(WORK / "token.txt").write_text(tok, encoding="utf-8")
_, dt = aew("lead", "show")
print(f"  lead show    (read) {dt:.2f}")
