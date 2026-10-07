"""The structural map's rule table (``rules.yaml``, package data) and its identity, ``ruleset_sha256``."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any

import yaml

from aew.maps.canonical import sha256

RULES_SCHEMA = "aew/structural-map-rules/v1"
KEYS = ("languages", "language_files", "directory_labels", "build_descriptors", "build_descriptor_globs",
        "entry_point_conventions", "test_directories", "test_file_patterns", "test_runner_configs",
        "vendor_directories", "generated_directories", "vendor_globs", "generated_globs", "semantic_prerequisites")


@dataclass(frozen=True)
class Rules:
    data: dict[str, Any]
    sha256: str


def parse(raw: bytes) -> Rules:
    data = yaml.safe_load(raw.decode("utf-8"))
    if not isinstance(data, dict) or data.get("schema") != RULES_SCHEMA or any(k not in data for k in KEYS):
        raise ValueError(f"the structural rule table is not {RULES_SCHEMA} with {', '.join(KEYS)}")
    return Rules(data=data, sha256=sha256(raw))


@cache
def load() -> Rules:
    """The installed rule table: its bytes are the identity, so any edit is a new ruleset."""
    return parse(resources.files("aew.maps").joinpath("rules.yaml").read_bytes())
