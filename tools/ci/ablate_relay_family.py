"""Ablations of the relay-route model-family check (register E143): each one breaks one part of the check in
``src/aew/harness/opencode/adapter.py``, runs the tests that should catch it, and restores the file byte for byte.

usage: python tools/ci/ablate_relay_family.py [NAME ...]   (run from the checkout; PYTHONPATH as for its tests)
Prints one line per ablation: its name, the tests' exit code, and CAUGHT when they failed; exits 1 when any reads
MISSED. The refusal ablation needs Linux with bubblewrap (the relay route): elsewhere, or without `bwrap` on PATH,
it is skipped, never MISSED, since its test cannot take the relay route there."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "src" / "aew" / "harness" / "opencode" / "adapter.py"
TESTS = "tests/integration/test_opencode_adapter.py"
UNIT = "compares_the_pinned_models_package"

ABLATIONS = {
    # The refusal never raised: a mismatch launches.
    "no_refusal": ('        if found["check"] == RELAY_FAMILY_MISMATCH:\n', '        if False:\n',
                   "a_model_of_a_family_the_upstream_does_not_serve_is_refused"),
    # What the upstream serves read from every model of the provider, wherever it is served.
    "any_address": (" and _served_at((m.get(\"settings\") or {}).get(\"baseURL\")) == want})", "})", UNIT),
    # Other providers' models count for this provider's upstream.
    "any_provider": ("if m.get(\"providerID\") == provider and m.get(\"id\") != pin", "if m.get(\"id\") != pin", UNIT),
    # Nothing served from the upstream read as a mismatch (a refusal on the snapshot's spelling).
    "unverified_refused": ("    if not package or not served:\n", "    if not package:\n", UNIT),
    # A package no other model carries refused (#338 review, F1: the lone mistral model at the upstream).
    "lone_refused": ("RELAY_FAMILY_MISMATCH if carried else RELAY_FAMILY_UNVERIFIED",
                     "RELAY_FAMILY_MISMATCH", UNIT),
    # A carrier with no readable address of its own counted as served elsewhere (#338 quick check, m2).
    "unaddressed_carrier": ("for m in addressed)", "for m in others)", UNIT),
}
RELAY_ONLY = {"no_refusal"}  # its test takes the relay route's branch on Linux only


def main(names: list[str]) -> int:
    original = ADAPTER.read_bytes()
    missed = []
    try:
        for name in names or list(ABLATIONS):
            if name in RELAY_ONLY and not (sys.platform.startswith("linux") and shutil.which("bwrap")):
                print(f"{name}: skipped (needs the relay route: Linux with bubblewrap)", flush=True)
                continue
            old, new, tests = ABLATIONS[name]
            text = original.decode()
            assert text.count(old) == 1, (name, old)
            ADAPTER.write_bytes(text.replace(old, new).encode())
            code = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", TESTS, "-k", tests],
                                  cwd=ROOT, capture_output=True, text=True,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode
            print(f"{name}: exit {code} {'CAUGHT' if code != 0 else 'MISSED'}", flush=True)
            if code == 0:
                missed.append(name)
    finally:
        ADAPTER.write_bytes(original)
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
