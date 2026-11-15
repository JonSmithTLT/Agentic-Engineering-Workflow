"""Prepare the personal alpha's seeded project with models named by the operator."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from importlib.resources import files
from pathlib import Path
from typing import Any

from aew.engine import first_configuration
from aew.engine.api import Engine
from aew.errors import UsageError
from aew.harness import models
from aew.harness.opencode.projection import LEAD_DENIED_PROVIDERS
from aew.maps.service import first_map
from aew.policy import execution
from aew.policy.checks import PYTEST_CACHES
from aew.util import dump_yaml, load_yaml, utc_now

CHECK_COMMAND = "{python} -m pytest -q tests/unit"
KIT_RECORD = "kit.json"
MONEY_SCOPE = ("ledger/money.py", "tests/unit/test_money.py")
DATES_SCOPE = ("ledger/dates.py", "tests/unit/test_dates.py")
OPENING_REQUEST = (
    "Please draft two independent Tickets, one per fix, and run both mutating workers together. "
    f"Fix A uses {MONEY_SCOPE[0]} and {MONEY_SCOPE[1]}: preserve the negative sign on refunds. "
    f"Fix B uses {DATES_SCOPE[0]} and {DATES_SCOPE[1]}: put the month before the day and remove the lint marker. "
    "Add a regression test for each fix. If validation reveals an affected file outside its Ticket's scope, "
    "tell me what needs to change and why."
)
RECEIPT_READER = (
    "Copy alpha-receipt.json into a directory. From an AEW source checkout with tests/helpers on PYTHONPATH, "
    "run python -m vertical.report <directory>."
)


class KitConfiguration(first_configuration.FirstConfiguration):
    """Pin structural pack slices in the same initialization as the model and check."""

    def files(self) -> dict[str, str]:
        configured = super().files()
        policy = load_yaml(configured[execution.REL_PATH])
        policy["maps"] = {"pack_slices": "structural"}
        configured[execution.REL_PATH] = dump_yaml(policy)
        return configured


def _model(ref: str | None, flag: str, *, provider: str | None = None) -> str:
    if not ref or not ref.strip():
        raise UsageError(f"{flag} is required for each kit run")
    identity = models.from_profile(provider, ref, field=flag)
    if reason := models.free_model_id(identity.harness_ref):
        raise UsageError(f"{flag}: {reason}")
    if flag == "--lead-model" and identity.provider in LEAD_DENIED_PROVIDERS:
        raise UsageError(f"{flag}: the Lead denies provider {identity.provider}. Choose another provider.")
    return identity.harness_ref


def git(repo: Path, *args: str) -> str:
    """Keep the invoking process's Git environment out of the kit repository."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    result = subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True,
                            timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return result.stdout.strip()


def prepare(dest: Path, model: str | None, lead_model: str | None, provider: str | None = None,
            lead_provider_env: tuple[str, ...] = ()) -> Engine:
    worker_ref = _model(model, "--model", provider=provider)
    lead_ref = _model(lead_model, "--lead-model")
    given = first_configuration.from_flags(check_command=CHECK_COMMAND, check_timeout=None, model=model,
                                           provider=provider)
    assert given is not None
    configuration = KitConfiguration(given.argv, given.timeout_s, given.identity, given.provider, given.model,
                                     given.provider_env, check_caches=PYTEST_CACHES)
    dest = dest.resolve()
    repo = dest / "repo"
    if repo.exists() or (dest / KIT_RECORD).exists():
        raise UsageError("the kit destination already contains a repository or kit record. Choose a new destination, "
                         "or move the existing kit aside before retrying. If setup finished, use the existing repo "
                         "or write its receipt with python -m aew.kit receipt <dest>.")
    repo.mkdir(parents=True)
    seed = files("aew.kit").joinpath("seed.json").read_bytes()
    for name, content in json.loads(seed).items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    git(repo, "init", "--initial-branch=main")
    git(repo, "config", "--local", "user.name", "AEW Kit")
    git(repo, "config", "--local", "user.email", "kit@example.invalid")
    git(repo, "add", "--all")
    git(repo, "-c", "core.hooksPath=.git/no-hooks", "-c", "commit.gpgSign=false", "commit", "-m", "Seed the ledger kit")

    engine = Engine.initialize(repo, project_id="ledger", first_configuration=configuration)
    mapped = first_map(engine)
    if mapped.get("selected") is not True:
        raise UsageError(f"the kit's first map was not selected: {mapped.get('reason', 'reason not recorded')}. "
                         "Move this incomplete kit aside or choose a new destination before retrying.")
    record: dict[str, Any] = {
        "prepared_at": utc_now(),
        "seed_digest": hashlib.sha256(seed).hexdigest(),
        "seed_commit": git(repo, "rev-parse", "HEAD"),
        "workers_model": worker_ref,
        "lead_model": lead_ref,
        "lead_provider_env": list(lead_provider_env),
    }
    (dest / KIT_RECORD).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return engine


def launch_argv(dest: Path, provider_env: tuple[str, ...], lead_model: str) -> list[str]:
    model = _model(lead_model, "--lead-model")
    provider_args = [arg for name in provider_env for arg in ("--provider-env", name)]
    return [sys.executable, "-m", "aew", "-C", str(dest.resolve() / "repo"), "opencode", "--acquire",
            *provider_args, "--", "--model", model]
