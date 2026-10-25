"""AEW's G3 service (STG-03): the trusted operator origin for a protected action, under A-37 (G3 revision 7.1).

It runs as its own systemd account (``DynamicUser=yes``), apart from the operator's editable ``aew`` install: root
installs this package under one root-owned path (G3-14), and the service reads its deployment values from that
path's ``etc/deployment.json``, never from anywhere a flag or the environment names. In the repository the same
layout holds: ``g3/aew_g3`` beside ``g3/etc/deployment.json``, the shipped defaults.
"""

from __future__ import annotations

from pathlib import Path

# G3-14: the install root is the directory this package is installed in (/opt/aew-g3 on a host).
ROOT = Path(__file__).resolve().parent.parent
DEPLOYMENT_FILE = ROOT / "etc" / "deployment.json"
