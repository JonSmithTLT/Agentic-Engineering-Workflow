"""Ablations of the run's one egress allowlist, self-test row 1's record of it, and the launch's relay-route report
(register E143): each one breaks one part in its source file, runs the tests that should catch it, and restores the
file byte for byte.

usage: python tools/ci/ablate_relay_label.py [NAME ...]   (run from the checkout; PYTHONPATH as for its tests)
Prints one line per ablation: its name, the tests' exit code, and CAUGHT when they failed; exits 1 when any reads
MISSED. The label and acknowledgement ablations need the relay route (Linux with `bwrap` on PATH): elsewhere they are
skipped, never MISSED, since their tests cannot take that route there."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "aew"
ADAPTER_TESTS = "tests/integration/test_opencode_adapter.py"
RECORDED = "the_family_check_is_recorded"
REFUSED = "a_model_of_a_family_the_upstream_does_not_serve_is_refused"

# name: (file, old, new, test file, -k, needs the relay route)
ABLATIONS: dict[str, tuple[Path, str, str, str, str, bool]] = {
    # The run's network builds its own allowlist from the policy again, beside the one it is given.
    "network_rebuilds": (SRC / "harness" / "containment" / "netns.py", "            if allow is not None:\n",
                         "            allow = egress_policy(policy, ()) or allow\n            if allow is not None:\n",
                         "tests/unit/test_containment_netns.py", "allowlist_its_caller_built", False),
    # Row 1 does not record the allowlist it checked.
    "row1_unrecorded": (SRC / "harness" / "containment" / "probe.py",
                        "                egress_allow=net.get(\"egress_allow\"),\n", "",
                        "tests/unit/test_containment_probe.py", "records_what_it_checked", False),
    # The launcher passes on any relay-route value the acknowledgement names.
    "launcher_open": (SRC / "engine" / "harness_ops.py",
                      'if ack.get("started") and ack.get("relay_family") in RELAY_FAMILY_SHOWN:',
                      'if ack.get("started") and ack.get("relay_family"):',
                      "tests/unit/test_launch_failure_vocabulary.py", "closed_report", False),
    # The label does not show the check.
    "label_unset": (SRC / "harness" / "supervisor.py",
                    '                self.record["containment"]["network"]["relay_family"] = relay_family\n',
                    "                pass\n", ADAPTER_TESTS, RECORDED, True),
    # The started acknowledgement does not carry the check.
    "ack_no_family": (SRC / "harness" / "supervisor.py",
                      '**({"relay_family": relay_family} if relay_family else {})})',
                      "})", ADAPTER_TESTS, RECORDED, True),
    # The failure acknowledgement does not carry the adapter's refusal reason.
    "ack_no_refusal": (SRC / "harness" / "supervisor.py",
                       '                        **({"refusal": refusal} if refusal is not None else {})})',
                       "                        })", ADAPTER_TESTS, REFUSED, True),
}


def main(names: list[str]) -> int:
    relay_route = sys.platform.startswith("linux") and shutil.which("bwrap") is not None
    missed = []
    for name in names or list(ABLATIONS):
        path, old, new, tests, k, needs_relay = ABLATIONS[name]
        if needs_relay and not relay_route:
            print(f"{name}: skipped (needs the relay route: Linux with bubblewrap)", flush=True)
            continue
        original = path.read_bytes()
        try:
            text = original.decode()
            assert text.count(old) == 1, (name, old)
            path.write_bytes(text.replace(old, new).encode())
            code = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", tests, "-k", k],
                                  cwd=ROOT, capture_output=True, text=True,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode
        finally:
            path.write_bytes(original)
        print(f"{name}: exit {code} {'CAUGHT' if code != 0 else 'MISSED'}", flush=True)
        if code == 0:
            missed.append(name)
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
