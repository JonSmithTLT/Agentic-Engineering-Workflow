"""Ablations of the run's one egress allowlist, self-test row 1's record of it, and the launch's relay-route report
(register E143): each one breaks one part in its source file, runs the tests that should catch it, and restores the
file byte for byte.

usage: python tools/ci/ablate_relay_label.py [NAME ...]   (run from the checkout; PYTHONPATH as for its tests)

Each selection of tests is first run unablated and must pass (pytest exit 0); then, ablated, CAUGHT means pytest
failed tests (exit 1) and MISSED means it passed. Any other outcome (a baseline that fails, no tests collected: exit 5,
a collection or usage error: 2, 3 or 4) is NOT A VERDICT. The runner exits 1 unless every ablation run reads CAUGHT
(#339 review m1). The label and acknowledgement ablations need the relay route (Linux with `bwrap` on PATH): elsewhere
they are skipped, since their tests cannot take that route there."""

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
                        "                **(net.get(\"egress_checked\") or {}),\n", "",
                        "tests/unit/test_containment_probe.py", "records_what_it_checked", False),
    # The launcher passes on any relay-route value the acknowledgement names.
    "launcher_open": (SRC / "engine" / "harness_ops.py",
                      'if ack.get("started") and isinstance(family, str) and family in RELAY_FAMILY_SHOWN:',
                      'if ack.get("started") and family:',
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


def pytest(tests: str, k: str) -> int:
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", tests, "-k", k],
                          cwd=ROOT, capture_output=True, text=True,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode


def main(names: list[str]) -> int:
    relay_route = sys.platform.startswith("linux") and shutil.which("bwrap") is not None
    baselines: dict[tuple[str, str], int] = {}
    failed = []
    for name in names or list(ABLATIONS):
        path, old, new, tests, k, needs_relay = ABLATIONS[name]
        if needs_relay and not relay_route:
            print(f"{name}: skipped (needs the relay route: Linux with bubblewrap)", flush=True)
            continue
        if (tests, k) not in baselines:
            baselines[(tests, k)] = pytest(tests, k)
        if baselines[(tests, k)] != 0:
            print(f"{name}: NOT A VERDICT (the unablated selection exits {baselines[(tests, k)]})", flush=True)
            failed.append(name)
            continue
        original = path.read_bytes()
        try:
            text = original.decode()
            assert text.count(old) == 1, (name, old)
            path.write_bytes(text.replace(old, new).encode())
            code = pytest(tests, k)
        finally:
            path.write_bytes(original)
        verdict = {1: "CAUGHT", 0: "MISSED"}.get(code, f"NOT A VERDICT (pytest exit {code})")
        print(f"{name}: exit {code} {verdict}", flush=True)
        if code != 1:
            failed.append(name)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
