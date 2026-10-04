"""Probe 2 for the outbox ADR (T3): a crash between the control-file replace and the derived transition-log write
(fault points txn.after_replace, txn.after_apply) leaves control.yaml at N+1 with no log/N+1; the next recovery
(any read) must write it from last_transition, and the two must agree. Reuses the project probe 1 left behind."""
import json, os, subprocess, sys
from pathlib import Path
import yaml

REPO = Path(__file__).resolve().parent / "work" / "repo"
PY = sys.executable

def run(*args, fault=None):
    kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    env = {k: v for k, v in os.environ.items() if k not in ("AEW_LEAD_TOKEN", "AEW_FAULT")}
    if fault:
        env["AEW_FAULT"] = fault
    return subprocess.run([PY, "-m", "aew", "-C", str(REPO), *args], env=env, capture_output=True, text=True,
                          encoding="utf-8", stdin=subprocess.DEVNULL, **kw)

def control():
    text = (REPO / ".aew/state/control.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(text.rsplit("\n# aew-checksum", 1)[0])

def log_path(rev):
    return REPO / f".aew/state/log/{rev:06d}.yaml"

tok = (REPO.parent / "token.txt").read_text(encoding="utf-8").strip()  # the seat probe 1 left held

for point in ("txn.after_replace", "txn.after_apply"):
    before = control()["revision"]
    r = run("work", "create", "ticket", "--title", f"crash at {point}", "--class", "1", "--scope", "src/**",
            "--token", tok, "--expect-rev", str(before), fault=point)
    after = control()["revision"]
    print(f"\n[{point}] exit={r.returncode} revision {before} -> {after}; "
          f"log/{after:06d} exists before recovery: {log_path(after).exists()}; "
          f"txn record exists: {(REPO / f'.aew/state/txn/{after:06d}.yaml').exists()}")
    assert r.returncode != 0 and after == before + 1 and not log_path(after).exists()
    r2 = run("lead", "show")  # a read: lock, recovery, post-commit repair
    assert r2.returncode == 0, r2.stderr
    exists = log_path(after).exists()
    print(f"  after one read: log/{after:06d} exists: {exists}; "
          f"ticket file applied: {all((REPO / '.aew' / ref).exists() for ref in control()['last_transition']['refs'])}")
    assert exists
    logged = yaml.safe_load(log_path(after).read_text(encoding="utf-8"))
    last = control()["last_transition"]
    print(f"  log record == last_transition: {logged == last}")
    assert logged == last
    files = sorted((REPO / ".aew/state/log").glob("*.yaml"))
    print(f"  log files {len(files)} == revision+1 {after + 1}: {len(files) == after + 1}")
    assert len(files) == after + 1
print("\nOK: the derived transition log is complete after recovery at both fault points.")
