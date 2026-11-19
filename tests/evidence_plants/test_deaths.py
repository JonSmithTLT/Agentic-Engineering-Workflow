"""Blocking tests for the hosted lane proof. Evidence is written only by lane helpers."""

import os
import re
import threading

import pytest


def planted_block_deadline():
    threading.Event().wait(600)


def planted_block_hang():
    # Catastrophic backtracking holds the GIL. The wrapper must read this process from outside.
    re.fullmatch(r"(a+)+b", "a" * 40)


@pytest.mark.parametrize("kind", [os.environ.get("AEW_EVIDENCE_PLANT", "disabled")])
def test_death(kind):
    if kind == "normal":
        return
    if kind.startswith("hang"):
        planted_block_hang()
    else:
        planted_block_deadline()
