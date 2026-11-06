"""Ablations of the relay-route model-address check (register E143): each one breaks one part of the check in
``src/aew/harness/opencode/adapter.py``, runs the tests that should catch it, and restores the file byte for byte.

usage: python tools/ci/ablate_relay_address.py [NAME ...]   (run from the checkout; PYTHONPATH as for its tests)
Prints one line per ablation: its name, the tests' exit code, and CAUGHT when they failed. The refusal ablation
needs Linux with bubblewrap (the relay route); elsewhere its test passes either way and it reads MISSED."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "src" / "aew" / "harness" / "opencode" / "adapter.py"
TESTS = "tests/integration/test_opencode_adapter.py"

ABLATIONS = {
    # The refusal never raised: a mismatch launches.
    "no_refusal": ('        if found["check"] == RELAY_ADDRESS_MISMATCH:\n',
                   '        if False:\n',
                   "a_model_served_elsewhere_than_the_relays_upstream_is_refused"),
    # Neighbours of any package stand in for the pinned model.
    "any_package": ("                  and m.get(\"package\") == package and not declared_only(m)]",
                    "                  and not declared_only(m)]",
                    "infers_the_pinned_models_address"),
    # The projection's provider-level address (the relay's) counted as a catalog address.
    "relay_counted": ("        if where is not None and where != relay:",
                      "        if where is not None:",
                      "infers_the_pinned_models_address"),
    # Models of another provider stand in for it.
    "any_provider": ("                  if package and m.get(\"providerID\") == provider and",
                     "                  if package and",
                     "infers_the_pinned_models_address"),
}


def main(names: list[str]) -> int:
    original = ADAPTER.read_bytes()
    try:
        for name in names or list(ABLATIONS):
            old, new, tests = ABLATIONS[name]
            text = original.decode()
            assert text.count(old) == 1, (name, old)
            ADAPTER.write_bytes(text.replace(old, new).encode())
            code = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", TESTS, "-k", tests],
                                  cwd=ROOT, capture_output=True, text=True).returncode
            print(f"{name}: exit {code} {'CAUGHT' if code != 0 else 'MISSED'}", flush=True)
    finally:
        ADAPTER.write_bytes(original)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
